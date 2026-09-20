"""Mapa de identidad (read-only) de las personas con prefijo del import.

Para cada persona prefijada: nombre limpio propuesto, atribuciones por rol, source, identificadores,
alias, destino candidato y método (identificador/alias/nombre exacto/normalizado/variante), con
detección de colisiones (varios candidatos o identificadores contradictorios ⇒ ambigua).

NO escribe nada.

    .venv\\Scripts\\python.exe scripts/identity_map_prefixed.py
"""

from __future__ import annotations

import argparse
import contextlib
import csv
import json
import re
import sys
from collections import defaultdict
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

import pymysql  # noqa: E402
import yaml  # noqa: E402
from domain.services.composer_names import normalize_composer_name as norm  # noqa: E402

PREFIX = re.compile(
    r"^\s*(arranged\s+from|arranged\s+by|arr\s+from|arr\.?\s+|attr\.?\s+|attributed\s+to|"
    r"from|edited\s+by|transcribed\s+by|transcr\.?\s+)\s*",
    re.I,
)
TRAILING = re.compile(r"\s*(\((?:[^()]*\d{4}[^()]*)\)|\bop\.?\s*\d+.*|\bopus\s+\d+.*)\s*$", re.I)
ID_TYPES = ("viaf", "wikidata_qid", "mbid", "isni", "gnd")


def _mk(value: str | None) -> str:
    return " ".join(sorted(norm(value).split()))


def _tokens(value: str | None) -> set[str]:
    return set(norm(value).split())


def _clean(name: str) -> str:
    return TRAILING.sub("", PREFIX.sub("", name or "")).strip(" .,-")


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
        clean_persons = [r for r in cur.fetchall() if r["persons_id"] not in prefixed_ids]
        name_index: dict[str, set[str]] = defaultdict(set)
        token_index: dict[str, set[str]] = defaultdict(set)
        for r in clean_persons:
            name_index[_mk(r["persons_name"])].add(r["persons_id"])
            for token in _tokens(r["persons_name"]):
                token_index[token].add(r["persons_id"])

        cur.execute("SELECT person_id, person_aliases_normalized_alias a FROM persons_aliases")
        alias_index: dict[str, set[str]] = defaultdict(set)
        for r in cur.fetchall():
            if r["a"] and r["person_id"] not in prefixed_ids:
                alias_index[_mk(r["a"])].add(r["person_id"])

        cur.execute("SELECT persons_id, identity_type, identity_value FROM persons_identity "
                    "WHERE persons_id IS NOT NULL")
        id_index: dict[tuple[str, str], set[str]] = defaultdict(set)
        identities: dict[str, dict[str, set[str]]] = defaultdict(lambda: defaultdict(set))
        for r in cur.fetchall():
            type_ = (r["identity_type"] or "").lower()
            if type_ not in ID_TYPES or not r["identity_value"]:
                continue
            identities[r["persons_id"]][type_].add(str(r["identity_value"]).strip())
            if r["persons_id"] not in prefixed_ids:
                id_index[(type_, str(r["identity_value"]).strip())].add(r["persons_id"])

        cur.execute("SELECT person_id, COUNT(*) n FROM persons_aliases GROUP BY 1")
        alias_count = {r["person_id"]: r["n"] for r in cur.fetchall()}
        cur.execute("SELECT works_person_roles_person_id pid, works_person_roles_role_id role, "
                    "COUNT(DISTINCT works_person_roles_work_id) n FROM works_person_roles GROUP BY 1,2")
        roles: dict[str, dict[int, int]] = defaultdict(dict)
        for r in cur.fetchall():
            roles[r["pid"]][r["role"]] = r["n"]

    rows = []
    for p in prefixed:
        pid, name = p["persons_id"], p["persons_name"]
        clean = _clean(name)
        own_ids = identities.get(pid, {})

        id_matches: dict[str, set[str]] = defaultdict(set)
        for type_, values in own_ids.items():
            for value in values:
                id_matches[type_] |= id_index.get((type_, value), set())
        id_candidates = {c for v in id_matches.values() for c in v}

        key = _mk(clean)
        alias_candidates = alias_index.get(key, set())
        exact_candidates = name_index.get(key, set())
        tokens = _tokens(clean)
        variant_candidates = (
            set.intersection(*(token_index.get(t, set()) for t in tokens)) if tokens else set()
        )

        if id_candidates:
            candidates, method = id_candidates, "identificador externo"
        elif alias_candidates:
            candidates, method = alias_candidates, "alias"
        elif exact_candidates:
            candidates, method = exact_candidates, "nombre exacto/normalizado"
        elif variant_candidates:
            candidates, method = variant_candidates, "variante abreviada"
        else:
            candidates, method = set(), ""

        if not candidates:
            target, kind, confidence = None, "sin_destino", ""
        elif len(candidates) == 1:
            target = next(iter(candidates))
            kind = "duplicado_de"
            confidence = {"identificador externo": "alta", "alias": "media",
                          "nombre exacto/normalizado": "media",
                          "variante abreviada": "baja"}.get(method, "baja")
        else:
            target, kind, confidence = None, "ambigua", ""

        rows.append({
            "person_id": pid, "nombre_actual": name, "nombre_limpio": clean,
            "rol1": roles.get(pid, {}).get(1, 0), "rol3": roles.get(pid, {}).get(3, 0),
            "rol10": roles.get(pid, {}).get(10, 0), "source_system": p["persons_source_system"],
            "identificadores": json.dumps({k: sorted(v) for k, v in own_ids.items()}, ensure_ascii=False),
            "n_alias": alias_count.get(pid, 0), "destino": target or "",
            "tipo_destino": kind, "metodo": method, "confianza": confidence,
            "n_candidatos": len(candidates),
            "candidatos": ";".join(sorted(candidates)[:5]),
        })
    conn.close()

    with open(out_csv, "w", newline="", encoding="utf-8") as fh:
        writer = csv.DictWriter(fh, fieldnames=list(rows[0].keys()) if rows else ["person_id"])
        writer.writeheader()
        writer.writerows(rows)

    from collections import Counter
    kinds = Counter(r["tipo_destino"] for r in rows)
    methods = Counter(r["metodo"] for r in rows if r["metodo"])
    lines = [
        "# Mapa de identidad de personas con prefijo del import (read-only)\n",
        f"- Personas: **{len(rows)}**",
        f"- Con atribuciones rol 1: **{sum(1 for r in rows if r['rol1'])}**\n",
        "## Resultado\n", "| tipo_destino | Personas |", "|---|---|",
    ]
    for k, v in kinds.most_common():
        lines.append(f"| {k} | {v} |")
    lines += ["\n## Método de coincidencia\n", "| método | Personas |", "|---|---|"]
    for k, v in methods.most_common():
        lines.append(f"| {k} | {v} |")
    lines += ["\n## Casos de mayor volumen\n",
              "| person_id | nombre | limpio | rol1 | tipo | método | confianza | destino |",
              "|---|---|---|---|---|---|---|---|"]
    for r in sorted(rows, key=lambda x: -x["rol1"])[:25]:
        lines.append(f"| {r['person_id']} | {r['nombre_actual']} | {r['nombre_limpio']} | {r['rol1']} | "
                     f"{r['tipo_destino']} | {r['metodo']} | {r['confianza']} | {r['destino'] or '—'} |")
    out_md.write_text("\n".join(lines) + "\n", encoding="utf-8")
    print("personas:", len(rows), "| tipos:", dict(kinds))
    print("métodos:", dict(methods))
    print("csv:", out_csv, "| informe:", out_md)


def main() -> None:
    with contextlib.suppress(AttributeError, ValueError):
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--csv", type=Path, default=Path(r"G:\rism\identity_map_prefixed.csv"))
    ap.add_argument("--md", type=Path, default=ROOT / "docsNew" / "mapa-identidad-prefijos.md")
    args = ap.parse_args()
    run(args.csv, args.md)


if __name__ == "__main__":
    main()
