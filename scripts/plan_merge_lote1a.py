"""Dry-run del Lote 1A de merges (read-only): identidad semántica segura.

Un candidato entra en 1A solo si cumple TODO:
 1. tipo_destino = duplicado_seguro.
 2. destino rol1>0 o evidencia fuerte (alias/identificador).
 3. destino con identidad nominal completa (no solo iniciales; no nickname/un token).
 4. origen y destino = misma persona (compatibilidad de tokens + sin nombres de pila en conflicto).
 5. origen no es obra/fuente/colección/metadata.
 6. sin conflictos de identidad/alias/identificadores.

No escribe nada.

    .venv\\Scripts\\python.exe scripts/plan_merge_lote1a.py
"""

from __future__ import annotations

import argparse
import contextlib
import csv
import json
import sys
from collections import defaultdict
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

import pymysql  # noqa: E402
import yaml  # noqa: E402
from domain.services.composer_names import normalize_composer_name as norm  # noqa: E402

REF_TABLES = (
    ("works_person_roles", "works_person_roles_person_id"),
    ("persons_aliases", "person_id"),
    ("persons_identity", "persons_id"),
    ("persons_evidence", "persons_id"),
    ("representation_persons", "representation_persons_person_id"),
    ("cpdl_edition_persons", "persons_id"),
)


def _tokens(name: str | None) -> list[str]:
    return norm(name).split()


def _initials_only(tokens: list[str]) -> bool:
    return len(tokens) >= 2 and all(len(t) == 1 for t in tokens[:-1])


def _fuzzy_eq(a: str, b: str) -> bool:
    if a == b or a.startswith(b) or b.startswith(a):
        return True
    if abs(len(a) - len(b)) > 2:
        return False
    prev = list(range(len(b) + 1))
    for i, ca in enumerate(a, 1):
        cur = [i]
        for j, cb in enumerate(b, 1):
            cur.append(min(prev[j] + 1, cur[j - 1] + 1, prev[j - 1] + (ca != cb)))
        prev = cur
    return prev[-1] <= 2


def run(map_csv: Path, out_csv: Path, out_md: Path) -> None:
    with open(map_csv, encoding="utf-8") as fh:
        candidates = [r for r in csv.DictReader(fh) if r["tipo_destino"] == "duplicado_seguro"]
    with open(ROOT / "config.yaml", encoding="utf-8") as fh:
        cfg = yaml.safe_load(fh)["db"]
    conn = pymysql.connect(host=cfg["host"], port=cfg["port"], user=cfg["user"],
                           password=cfg["password"], database=cfg["name"], charset="utf8mb4",
                           cursorclass=pymysql.cursors.DictCursor)

    def person(pid: str) -> dict:
        with conn.cursor() as cur:
            cur.execute("SELECT persons_name, persons_birth_year, persons_death_year, "
                        "persons_source_system FROM persons WHERE persons_id=%s", (pid,))
            data = cur.fetchone() or {}
            cur.execute("SELECT person_aliases_normalized_alias a FROM persons_aliases WHERE person_id=%s", (pid,))
            aliases = {r["a"] for r in cur.fetchall() if r["a"]}
            cur.execute("SELECT identity_type, identity_value FROM persons_identity WHERE persons_id=%s", (pid,))
            ids: dict[str, set[str]] = defaultdict(set)
            for r in cur.fetchall():
                if r["identity_type"]:
                    ids[r["identity_type"]].add(str(r["identity_value"]))
            cur.execute("SELECT works_person_roles_role_id role, "
                        "COUNT(DISTINCT works_person_roles_work_id) n FROM works_person_roles "
                        "WHERE works_person_roles_person_id=%s GROUP BY 1", (pid,))
            roles = {r["role"]: r["n"] for r in cur.fetchall()}
            refs = {}
            for table, column in REF_TABLES:
                cur.execute(f"SELECT COUNT(*) n FROM {table} WHERE {column}=%s", (pid,))
                refs[table] = cur.fetchone()["n"]
            cur.execute("SELECT w.id, w.works_title FROM works w JOIN works_person_roles r "
                        "ON r.works_person_roles_work_id=w.id "
                        "WHERE r.works_person_roles_person_id=%s AND r.works_person_roles_role_id=1 "
                        "LIMIT 5", (pid,))
            works = cur.fetchall()
        return {"data": data, "aliases": aliases, "ids": ids, "roles": roles,
                "refs": refs, "works": works}

    plan, excluded = [], []
    for r in candidates:
        origin_id, target_id = r["person_id"], r["destino"]
        if not target_id:
            continue
        o, t = person(origin_id), person(target_id)
        evidence = r["metodo"] or "nombre exacto"
        target_rol1 = t["roles"].get(1, 0)
        strong = evidence in ("alias", "identificador")
        o_tokens, t_tokens = _tokens(r["nombre_limpio"]), _tokens(t["data"].get("persons_name"))

        categoria = None
        if r["subtipo"]:
            categoria = "no_persona"
        elif len(t_tokens) < 2 or _initials_only(t_tokens):
            categoria = "destino_inadecuado"
        elif not (target_rol1 > 0 or strong):
            categoria = "sin_evidencia"
        else:
            origin_set, target_set = set(o_tokens), set(t_tokens)
            compatible = origin_set <= target_set or target_set <= origin_set
            if not compatible:
                categoria = "identidad_dudosa"
            elif len(o_tokens) >= 2 and len(t_tokens) >= 2:
                o_given, t_given = o_tokens[0], t_tokens[0]
                if not _fuzzy_eq(o_given, t_given):
                    categoria = "identidad_dudosa"
            if categoria is None:
                o_id = dict(o["ids"])
                t_id = dict(t["ids"])
                id_conf = {k: (sorted(o_id[k]), sorted(t_id[k])) for k in set(o_id) & set(t_id)
                           if o_id[k] != t_id[k]}
                personal = [f"{f}: {o['data'].get(f)} vs {t['data'].get(f)}"
                            for f in ("persons_birth_year", "persons_death_year")
                            if o["data"].get(f) and t["data"].get(f)
                            and o["data"].get(f) != t["data"].get(f)]
                if id_conf or personal:
                    categoria = "conflicto"

        if categoria:
            excluded.append({
                "origin_id": origin_id, "origin_name": o["data"].get("persons_name"),
                "candidato_destino": t["data"].get("persons_name"),
                "categoria": categoria, "evidencia": evidence,
                "motivo": f"{categoria}: {evidence}",
            })
            continue

        plan.append({
            "origin_id": origin_id, "origin_name": o["data"].get("persons_name"),
            "target_id": target_id, "target_name": t["data"].get("persons_name"),
            "evidencia": evidence, "origin_rol1": o["roles"].get(1, 0), "target_rol1": target_rol1,
            "alias_a_mover": sorted(o["aliases"] - t["aliases"]),
            "alias_coincidentes": sorted(o["aliases"] & t["aliases"]),
            "identificadores_origen": json.dumps({k: sorted(v) for k, v in o["ids"].items()}, ensure_ascii=False),
            "identificadores_destino": json.dumps({k: sorted(v) for k, v in t["ids"].items()}, ensure_ascii=False),
            "roles_afectados": json.dumps({str(k): v for k, v in o["roles"].items()}),
            "refs_afectadas": json.dumps({k: v for k, v in o["refs"].items() if v}, ensure_ascii=False),
            "obras_muestra": "; ".join(f"{w['id']}:{w['works_title']}" for w in o["works"]),
            "merge_history": json.dumps({"source_person_id": origin_id, "target_person_id": target_id,
                                         "merged_by": "rism-lote1a", "revertible": True}, ensure_ascii=False),
        })

    with open(out_csv, "w", newline="", encoding="utf-8") as fh:
        writer = csv.DictWriter(fh, fieldnames=list(plan[0].keys()) if plan else ["origin_id"])
        writer.writeheader()
        writer.writerows(plan)
    conn.close()

    from collections import Counter
    cats = Counter(e["categoria"] for e in excluded)
    lines = ["# Lote 1A definitivo (read-only)\n",
             f"- Candidatos `duplicado_seguro`: {len(candidates)}",
             f"- **1A (listos para merge)**: **{len(plan)}**",
             f"- Fuera de 1A: {len(excluded)}\n",
             "## 1A — merges propuestos\n",
             "| origen | destino | evidencia | rol1 orig→dest | alias a mover | refs |",
             "|---|---|---|---|---|---|"]
    for m in sorted(plan, key=lambda x: -x["origin_rol1"]):
        lines.append(f"| {m['origin_name']} | {m['target_name']} | {m['evidencia']} | "
                     f"{m['origin_rol1']}→{m['target_rol1']} | {len(m['alias_a_mover'])} | {m['refs_afectadas']} |")
    lines += ["\n## Fuera de 1A\n", "| origen | candidato destino | categoría | evidencia |",
              "|---|---|---|---|"]
    for e in excluded:
        lines.append(f"| {e['origin_name']} | {e['candidato_destino'] or '—'} | {e['categoria']} | {e['evidencia']} |")
    lines += ["\n## Categorías de exclusión\n", "| categoría | casos |", "|---|---|"]
    for k, v in cats.most_common():
        lines.append(f"| {k} | {v} |")
    out_md.write_text("\n".join(lines) + "\n", encoding="utf-8")
    print(f"candidatos={len(candidates)} 1A={len(plan)} fuera={len(excluded)} cats={dict(cats)}")
    print("csv:", out_csv, "| informe:", out_md)


def main() -> None:
    with contextlib.suppress(AttributeError, ValueError):
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--map", type=Path, default=Path(r"G:\rism\identity_map_v2.csv"))
    ap.add_argument("--csv", type=Path, default=Path(r"G:\rism\merge_lote1a.csv"))
    ap.add_argument("--md", type=Path, default=ROOT / "docsNew" / "lote1a-merge.md")
    args = ap.parse_args()
    run(args.map, args.csv, args.md)


if __name__ == "__main__":
    main()
