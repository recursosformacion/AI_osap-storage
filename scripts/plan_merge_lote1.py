"""Dry-run del lote 1 de merges (read-only): `duplicado_seguro` con filtro de calidad.

Criterio: tipo_destino='duplicado_seguro' Y (destino rol1>0 O método alias/identificador).
No escribe nada. Detecta conflictos (identificadores/personales) y los saca del lote.

    .venv\\Scripts\\python.exe scripts/plan_merge_lote1.py
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


def run(map_csv: Path, out_csv: Path, out_md: Path) -> None:
    with open(map_csv, encoding="utf-8") as fh:
        rows = [r for r in csv.DictReader(fh) if r["tipo_destino"] == "duplicado_seguro"]
    with open(ROOT / "config.yaml", encoding="utf-8") as fh:
        cfg = yaml.safe_load(fh)["db"]
    conn = pymysql.connect(host=cfg["host"], port=cfg["port"], user=cfg["user"],
                           password=cfg["password"], database=cfg["name"], charset="utf8mb4",
                           cursorclass=pymysql.cursors.DictCursor)

    def person(pid: str) -> dict:
        with conn.cursor() as cur:
            cur.execute("SELECT persons_name, persons_givenname, persons_familyname, persons_sortname, "
                        "persons_birth_year, persons_death_year, persons_review_status, "
                        "persons_source_system FROM persons WHERE persons_id=%s", (pid,))
            data = cur.fetchone() or {}
            cur.execute("SELECT id, person_aliases_alias, person_aliases_normalized_alias "
                        "FROM persons_aliases WHERE person_id=%s", (pid,))
            aliases = cur.fetchall()
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
    for r in rows:
        origin_id, target_id = r["person_id"], r["destino"]
        if not target_id:
            continue
        o, t = person(origin_id), person(target_id)
        evidence = r["metodo"] or "nombre exacto"
        target_rol1 = t["roles"].get(1, 0)
        strong = evidence in ("alias", "identificador")
        single_token = len(norm(r["nombre_limpio"]).split()) < 2
        if not (target_rol1 > 0 or strong):
            excluded.append({"origin": origin_id, "target": target_id,
                             "motivo": "destino rol1=0 sin alias/identificador"})
            continue
        if single_token and target_rol1 == 0 and not strong:
            excluded.append({"origin": origin_id, "target": target_id, "motivo": "un solo token y destino rol1=0"})
            continue

        o_alias = {a["person_aliases_normalized_alias"] for a in o["aliases"] if a["person_aliases_normalized_alias"]}
        t_alias = {a["person_aliases_normalized_alias"] for a in t["aliases"] if a["person_aliases_normalized_alias"]}
        o_id = {k: v for k, v in o["ids"].items()}
        t_id = {k: v for k, v in t["ids"].items()}
        id_conflicts = {k: {"origen": sorted(o_id[k]), "destino": sorted(t_id[k])}
                        for k in set(o_id) & set(t_id) if o_id[k] != t_id[k]}
        personal_conflicts = []
        for field in ("persons_birth_year", "persons_death_year"):
            a, b = o["data"].get(field), t["data"].get(field)
            if a and b and a != b:
                personal_conflicts.append(f"{field}: {a} vs {b}")

        estado = "fuera" if (id_conflicts or personal_conflicts) else "propuesto"
        record = {
            "origin_id": origin_id, "origin_name": o["data"].get("persons_name"),
            "target_id": target_id, "target_name": t["data"].get("persons_name"),
            "evidence": evidence, "origin_rol1": o["roles"].get(1, 0), "target_rol1": target_rol1,
            "aliases_to_move": sorted(o_alias - t_alias), "alias_coincidentes": sorted(o_alias & t_alias),
            "origin_identifiers": json.dumps({k: sorted(v) for k, v in o_id.items()}, ensure_ascii=False),
            "target_identifiers": json.dumps({k: sorted(v) for k, v in t_id.items()}, ensure_ascii=False),
            "identifier_conflicts": json.dumps(id_conflicts, ensure_ascii=False),
            "personal_conflicts": "; ".join(personal_conflicts),
            "roles_affected": json.dumps({str(k): v for k, v in o["roles"].items()}),
            "refs_affected": json.dumps({k: v for k, v in o["refs"].items() if v}, ensure_ascii=False),
            "works_sample": "; ".join(f"{w['id']}:{w['works_title']}" for w in o["works"]),
            "merge_history_plan": json.dumps({"source_person_id": origin_id,
                                              "target_person_id": target_id,
                                              "merged_by": "rism-lote1"}, ensure_ascii=False),
            "estado": estado,
        }
        (plan if estado == "propuesto" else excluded).append(record)

    with open(out_csv, "w", newline="", encoding="utf-8") as fh:
        writer = csv.DictWriter(fh, fieldnames=list(plan[0].keys()) if plan else ["origin_id"])
        writer.writeheader()
        writer.writerows(plan)

    lines = ["# Dry-run lote 1 de merges (read-only)\n",
             f"- Candidatos `duplicado_seguro`: {len(rows)}",
             f"- **Propuestos (calidad OK)**: {len(plan)}",
             f"- **Fuera por conflicto/filtro**: {len(excluded)}\n",
             "## Propuestos\n",
             "| origen | destino | evidencia | rol1 orig→dest | alias a mover | refs | conflictos |",
             "|---|---|---|---|---|---|---|"]
    for m in sorted(plan, key=lambda x: -x["origin_rol1"]):
        lines.append(f"| {m['origin_name']} | {m['target_name']} | {m['evidence']} | "
                     f"{m['origin_rol1']}→{m['target_rol1']} | {len(m['aliases_to_move'])} | "
                     f"{m['refs_affected']} | {m['identifier_conflicts'] or '—'} |")
    lines += ["\n## Fuera del lote\n", "| origen | destino | motivo |", "|---|---|---|"]
    for m in excluded:
        motivo = m.get("motivo") or (m["identifier_conflicts"] or m["personal_conflicts"]
                                     or "conflicto")
        origin = m.get("origin_name", m.get("origin"))
        target = m.get("target_name", m.get("target"))
        lines.append(f"| {origin} | {target} | {motivo} |")
    out_md.write_text("\n".join(lines) + "\n", encoding="utf-8")
    conn.close()
    print(f"candidatos={len(rows)} propuestos={len(plan)} fuera={len(excluded)}")
    print("csv:", out_csv, "| informe:", out_md)


def main() -> None:
    with contextlib.suppress(AttributeError, ValueError):
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--map", type=Path, default=Path(r"G:\rism\identity_map_v2.csv"))
    ap.add_argument("--csv", type=Path, default=Path(r"G:\rism\merge_lote1_plan.csv"))
    ap.add_argument("--md", type=Path, default=ROOT / "docsNew" / "dry-run-merge-lote1.md")
    args = ap.parse_args()
    run(args.map, args.csv, args.md)


if __name__ == "__main__":
    main()
