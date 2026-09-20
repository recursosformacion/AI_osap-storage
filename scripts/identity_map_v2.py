"""Mapa de identidad v2 (read-only) de las 404 personas prefijadas del import.

Correcciones: (1) filtro `no_persona` global con subtipos (metadata/obra/fuente/otro);
(2) fuzzy conservador: genera candidatos, nunca decide; prioriza identidad > alias > nombre
exacto > variante > iniciales; conserva todos los candidatos y la evidencia.

No escribe nada.

    .venv\\Scripts\\python.exe scripts/identity_map_v2.py
"""

from __future__ import annotations

import argparse
import contextlib
import csv
import json
import re
import sys
from collections import Counter, defaultdict
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

import pymysql  # noqa: E402
import yaml  # noqa: E402
from domain.services.composer_names import normalize_composer_name as norm  # noqa: E402

PREFIX = re.compile(
    r"^\s*(arranged\s+from|arranged\s+by|arr\s+from|arr\.?\s+|attr\.?\s+|attributed\s+to|"
    r"from|edited\s+by|transcribed\s+by|transcr\.?\s+)\s*:?\s*",
    re.I,
)
TRAILING = re.compile(r"\s*(\((?:[^()]*\d{4}[^()]*)\)|\bop\.?\s*\d+.*|\bopus\s+\d+.*)\s*$", re.I)
METADATA = re.compile(r"^(arranged|transcribed|composed|edited|adapted|lyrics|words)\s+by\b", re.I)
FUENTE = re.compile(
    r"psalter|orchesographie|orchésographie|collection|sett of tunes|carmina|hymnal|chorale|"
    r"songbook|song book|book|school|series|musical|anthology|album|repertory", re.I)
OBRA = re.compile(
    r"symphony|sinfonia|sonata|suite|prelude|waltz|polka|march|opera|mass\b|motet|carol|hymn|"
    r"tune\b|melody|score|parts?\b|concerto|quartet|quintet|etude|étude|variations|overture", re.I)
ID_TYPES = ("viaf", "wikidata_qid", "mbid", "isni", "gnd")


def _mk(value: str | None) -> str:
    return " ".join(sorted(norm(value).split()))


def _tokens(value: str | None) -> list[str]:
    return norm(value).split()


def _clean(name: str) -> str:
    return TRAILING.sub("", PREFIX.sub("", name or "")).strip(" .,-:")


def _edit_leq(a: str, b: str, limit: int = 2) -> bool:
    if a == b or a.startswith(b) or b.startswith(a):
        return True
    if abs(len(a) - len(b)) > limit:
        return False
    prev = list(range(len(b) + 1))
    for i, ca in enumerate(a, 1):
        cur = [i]
        for j, cb in enumerate(b, 1):
            cur.append(min(prev[j] + 1, cur[j - 1] + 1, prev[j - 1] + (ca != cb)))
        prev = cur
    return prev[-1] <= limit


def _fuzzy_pair(clean: list[str], ptokens: list[str]) -> bool:
    left = clean[:-1] or clean
    right = ptokens[:-1] or ptokens
    return any(_edit_leq(a, b) for a in left for b in right)


def _ranked(cands: set[str], role1: dict[str, int]) -> list[str]:
    return sorted(cands, key=lambda cid: (-role1.get(cid, 0), cid))


def run(out_csv: Path, out_md: Path) -> None:
    with open(ROOT / "config.yaml", encoding="utf-8") as fh:
        cfg = yaml.safe_load(fh)["db"]
    conn = pymysql.connect(host=cfg["host"], port=cfg["port"], user=cfg["user"],
                           password=cfg["password"], database=cfg["name"], charset="utf8mb4",
                           cursorclass=pymysql.cursors.DictCursor)
    with conn.cursor() as cur:
        cur.execute("SELECT persons_id, persons_name, persons_source_system FROM persons "
                    "WHERE persons_name REGEXP '^(Arranged from|Arranged by|Arr from|Arr |Attr|"
                    "Attributed to|from |From |Edited by|Transcribed by|Transcr)'")
        prefixed = cur.fetchall()
        prefixed_ids = {r["persons_id"] for r in prefixed}
        cur.execute("SELECT persons_id, persons_name FROM persons")
        clean = [r for r in cur.fetchall() if r["persons_id"] not in prefixed_ids]

        name_index: dict[str, set[str]] = defaultdict(set)
        alias_index: dict[str, set[str]] = defaultdict(set)
        surname_index: dict[str, list[tuple[str, list[str]]]] = defaultdict(list)
        for p in clean:
            name_index[_mk(p["persons_name"])].add(p["persons_id"])
            tokens = _tokens(p["persons_name"])
            if tokens:
                surname_index[tokens[-1]].append((p["persons_id"], tokens))
        cur.execute("SELECT person_id, person_aliases_normalized_alias a FROM persons_aliases")
        for r in cur.fetchall():
            if r["a"] and r["person_id"] not in prefixed_ids:
                alias_index[_mk(r["a"])].add(r["person_id"])
        id_index: dict[tuple[str, str], set[str]] = defaultdict(set)
        cur.execute("SELECT persons_id, identity_type, identity_value FROM persons_identity "
                    "WHERE persons_id IS NOT NULL")
        for r in cur.fetchall():
            type_ = (r["identity_type"] or "").lower()
            if type_ in ID_TYPES and r["identity_value"] and r["persons_id"] not in prefixed_ids:
                id_index[(type_, str(r["identity_value"]).strip())].add(r["persons_id"])
        cur.execute("SELECT works_person_roles_person_id pid, COUNT(DISTINCT works_person_roles_work_id) n "
                    "FROM works_person_roles WHERE works_person_roles_role_id=1 GROUP BY 1")
        role1 = {r["pid"]: r["n"] for r in cur.fetchall()}
        own_ids: dict[str, dict[str, set[str]]] = defaultdict(lambda: defaultdict(set))
        cur.execute("SELECT persons_id, identity_type, identity_value FROM persons_identity "
                    "WHERE persons_id IS NOT NULL")
        for r in cur.fetchall():
            type_ = (r["identity_type"] or "").lower()
            if type_ in ID_TYPES and r["identity_value"]:
                own_ids[r["persons_id"]][type_].add(str(r["identity_value"]).strip())
    conn.close()

    rows, counts = [], Counter()
    for p in prefixed:
        pid, name = p["persons_id"], p["persons_name"]
        clean_name = _clean(name)
        tokens = _tokens(clean_name)

        subtype = ""
        if METADATA.match(name) or re.search(
                r"\b(arranged|transcribed|composed|edited|adapted|combined|lyrics|words)\s+by\s*:",
                name, re.I):
            subtype = "metadata"
        elif FUENTE.search(clean_name):
            subtype = "fuente_coleccion"
        elif OBRA.search(clean_name):
            subtype = "obra"
        elif ":" in clean_name:
            subtype = "metadata"

        id_candidates: set[str] = set()
        for type_, values in own_ids.get(pid, {}).items():
            for value in values:
                id_candidates |= id_index.get((type_, value), set())
        alias_candidates = alias_index.get(_mk(clean_name), set())
        exact_candidates = name_index.get(_mk(clean_name), set())
        variant_candidates: set[str] = set()
        initials_candidates: set[str] = set()
        if tokens:
            surname = tokens[-1]
            for cid, ptokens in surname_index.get(surname, []):
                if set(tokens) <= set(ptokens) or set(tokens) & set(ptokens) and _fuzzy_pair(tokens, ptokens):
                    variant_candidates.add(cid)

        def ranked(cands: set[str]) -> list[str]:
            return _ranked(cands, role1)

        for_merge = ranked(id_candidates or alias_candidates or exact_candidates)
        fuzzy_all = ranked((variant_candidates | initials_candidates) - set(for_merge))

        if subtype:
            kind, method, confidence = "no_persona", subtype, ""
        elif for_merge:
            if len(for_merge) == 1:
                kind = "duplicado_seguro"
                method = ("identificador" if id_candidates else
                          "alias" if alias_candidates else "nombre exacto")
                confidence = "alta" if id_candidates else "media"
            else:
                kind, method, confidence = "ambigua", "varios", ""
        elif fuzzy_all:
            kind = "duplicado_variante"
            method = "variante" if variant_candidates else "iniciales"
            confidence = "baja"
        elif len(tokens) >= 2:
            kind, method, confidence = "sin_destino", "rename", ""
        else:
            kind, method, confidence = "descartado_no_resoluble", "", ""

        all_cands = for_merge + fuzzy_all
        rows.append({
            "person_id": pid, "nombre_actual": name, "nombre_limpio": clean_name,
            "rol1": role1.get(pid, 0), "source_system": p["persons_source_system"],
            "tipo_destino": kind, "subtipo": subtype, "metodo": method, "confianza": confidence,
            "destino": for_merge[0] if (kind == "duplicado_seguro" and for_merge) else "",
            "n_candidatos": len(all_cands),
            "candidatos": ";".join(all_cands[:6]),
            "evidencia": json.dumps({c: role1.get(c, 0) for c in all_cands[:6]}, ensure_ascii=False),
        })
        counts[kind] += 1
        if subtype:
            counts[f"no_persona:{subtype}"] += 1

    with open(out_csv, "w", newline="", encoding="utf-8") as fh:
        writer = csv.DictWriter(fh, fieldnames=list(rows[0].keys()))
        writer.writeheader()
        writer.writerows(rows)

    spotlight = ("franz josef haydn", "john french", "nathan s", "arbeau", "genevan psalter")
    lines = ["# Mapa de identidad v2 (404 prefijadas, read-only)\n",
             f"- Personas: **{len(rows)}**\n", "| tipo_destino | Personas |", "|---|---|"]
    for k, v in counts.most_common():
        if not k.startswith("no_persona:"):
            lines.append(f"| {k} | {v} |")
    lines += ["\nSubtipos `no_persona`:\n"]
    for k, v in counts.most_common():
        if k.startswith("no_persona:"):
            lines.append(f"- {k.split(':')[1]}: {v}")
    lines += [
        "\n## Casos destacados\n",
        "| nombre actual | limpio | tipo | subtipo | destino | candidatos | evidencia |",
        "|---|---|---|---|---|---|---|",
    ]
    for s in spotlight:
        for r in rows:
            if s in (r["nombre_actual"] or "").lower() or s in (r["nombre_limpio"] or "").lower():
                lines.append(
                    f"| {r['nombre_actual']} | {r['nombre_limpio']} | {r['tipo_destino']} | "
                    f"{r['subtipo']} | {r['destino'] or '—'} | {r['candidatos'] or '—'} | "
                    f"{r['evidencia']} |"
                )
    lines += ["\n## Duplicados seguros (muestra)\n",
              "| nombre limpio | rol1 | método | destino | rol1 destino |", "|---|---|---|---|---|"]
    for r in [x for x in rows if x["tipo_destino"] == "duplicado_seguro"][:30]:
        lines.append(f"| {r['nombre_limpio']} | {r['rol1']} | {r['metodo']} | {r['destino']} | "
                     f"{json.loads(r['evidencia']).get(r['destino'], 0)} |")
    out_md.write_text("\n".join(lines) + "\n", encoding="utf-8")
    print("personas:", len(rows), "| tipos:", {k: v for k, v in counts.items() if not k.startswith("no_persona:")})
    print("no_persona:", {k: v for k, v in counts.items() if k.startswith("no_persona:")})
    print("csv:", out_csv, "| informe:", out_md)


def main() -> None:
    with contextlib.suppress(AttributeError, ValueError):
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--csv", type=Path, default=Path(r"G:\rism\identity_map_v2.csv"))
    ap.add_argument("--md", type=Path, default=ROOT / "docsNew" / "mapa-identidad-v2.md")
    args = ap.parse_args()
    run(args.csv, args.md)


if __name__ == "__main__":
    main()
