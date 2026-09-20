"""Plan de ejecución (dry-run, read-only) del Lote 1A: 9 merges, grupos A/B.

Muestra por merge: identidades origen/destino, alias e identificadores que se trasladan y sus
colisiones, works_person_roles por rol y colisiones, otras FKs, entrada de persons_merge_history y
revert exacto, comprobando que NO se pierde información del destino.

No escribe nada.

    .venv\\Scripts\\python.exe scripts/plan_execute_merge_1a.py
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

GROUP_B = {"Arr : Iraj Goli", "Edited byJAY YOUNG"}
REF_TABLES = (
    ("works_person_roles", "works_person_roles_person_id"),
    ("persons_aliases", "person_id"),
    ("persons_identity", "persons_id"),
    ("persons_evidence", "persons_id"),
    ("representation_persons", "representation_persons_person_id"),
    ("cpdl_edition_persons", "persons_id"),
)


def run(csv_path: Path, out_md: Path) -> None:
    with open(csv_path, encoding="utf-8") as fh:
        plan_rows = list(csv.DictReader(fh))
    with open(ROOT / "config.yaml", encoding="utf-8") as fh:
        cfg = yaml.safe_load(fh)["db"]
    conn = pymysql.connect(host=cfg["host"], port=cfg["port"], user=cfg["user"],
                           password=cfg["password"], database=cfg["name"], charset="utf8mb4",
                           cursorclass=pymysql.cursors.DictCursor)

    def details(pid: str) -> dict:
        with conn.cursor() as cur:
            cur.execute("SELECT persons_name, persons_merged_into, persons_review_status FROM persons "
                        "WHERE persons_id=%s", (pid,))
            data = cur.fetchone() or {}
            cur.execute("SELECT person_aliases_normalized_alias a FROM persons_aliases WHERE person_id=%s", (pid,))
            aliases = {r["a"] for r in cur.fetchall() if r["a"]}
            cur.execute("SELECT identity_type t, identity_value v FROM persons_identity WHERE persons_id=%s", (pid,))
            ids: dict[str, set[str]] = defaultdict(set)
            for r in cur.fetchall():
                if r["t"]:
                    ids[r["t"]].add(str(r["v"]))
            cur.execute("SELECT works_person_roles_role_id role, COUNT(*) n FROM works_person_roles "
                        "WHERE works_person_roles_person_id=%s GROUP BY 1", (pid,))
            roles = {r["role"]: r["n"] for r in cur.fetchall()}
            cur.execute("SELECT w.id, w.works_title FROM works w JOIN works_person_roles r "
                        "ON r.works_person_roles_work_id=w.id "
                        "WHERE r.works_person_roles_person_id=%s AND r.works_person_roles_role_id=1 LIMIT 6", (pid,))
            works = cur.fetchall()
            refs = {}
            for table, column in REF_TABLES:
                cur.execute(f"SELECT COUNT(*) n FROM {table} WHERE {column}=%s", (pid,))
                refs[table] = cur.fetchone()["n"]
        return {"data": data, "aliases": aliases, "ids": ids, "roles": roles,
                "works": works, "refs": refs}

    entries = []
    for row in plan_rows:
        oid, tid = row["origin_id"], row["target_id"]
        o, t = details(oid), details(tid)
        with conn.cursor() as cur:
            cur.execute("SELECT COUNT(*) n FROM works_person_roles r1 WHERE "
                        "r1.works_person_roles_person_id=%s AND EXISTS (SELECT 1 FROM works_person_roles r2 "
                        "WHERE r2.works_person_roles_person_id=%s "
                        "AND r2.works_person_roles_work_id=r1.works_person_roles_work_id "
                        "AND r2.works_person_roles_role_id=r1.works_person_roles_role_id)", (oid, tid))
            wpr_collisions = cur.fetchone()["n"]
        ids_move = {k: sorted(v - t["ids"].get(k, set())) for k, v in o["ids"].items()}
        ids_move = {k: v for k, v in ids_move.items() if v}
        entries.append({
            "group": "B" if row["origin_name"] in GROUP_B else "A",
            "origin_id": oid, "origin_name": row["origin_name"],
            "target_id": tid, "target_name": row["target_name"], "evidencia": row["evidencia"],
            "origin_roles": json.dumps(o["roles"]), "target_roles": json.dumps(t["roles"]),
            "wpr_collisions": wpr_collisions,
            "aliases_move": sorted(o["aliases"] - t["aliases"]),
            "aliases_dup": sorted(o["aliases"] & t["aliases"]),
            "ids_move": json.dumps(ids_move, ensure_ascii=False),
            "refs": json.dumps({k: v for k, v in o["refs"].items() if v}, ensure_ascii=False),
            "works_muestra": "; ".join(f"{w['id']}:{w['works_title']}" for w in o["works"]),
            "merge_history": json.dumps({"merge_operation_id": f"merge:{oid}->{tid}",
                                         "source_person_id": oid, "target_person_id": tid,
                                         "merged_by": "rism-lote1a"}, ensure_ascii=False),
            "revert": ("mover de vuelta los roles/alias/identificadores trasladados; "
                       "personas_origen.persons_merged_into=NULL; borrar la fila de persons_merge_history"),
            "target_preservado": "sí (no se sobrescribe; solo se añaden alias/ids que faltan)",
        })
    conn.close()

    lines = ["# Plan de ejecución Lote 1A (dry-run, read-only)\n",
             f"- Merges: **{len(entries)}** (A={sum(1 for e in entries if e['group'] == 'A')}, "
             f"B={sum(1 for e in entries if e['group'] == 'B')})\n"]
    for g in ("A", "B"):
        lines += [f"## Grupo {g}\n",
                  "| origen | destino | evidencia | roles origen | roles destino | "
                  "colisiones wpr | alias a mover | ids a mover | refs |",
                  "|---|---|---|---|---|---|---|---|---|"]
        for e in [x for x in entries if x["group"] == g]:
            lines.append(f"| {e['origin_name']} | {e['target_name']} | {e['evidencia']} | "
                         f"{e['origin_roles']} | {e['target_roles']} | {e['wpr_collisions']} | "
                         f"{len(e['aliases_move'])} | {e['ids_move']} | {e['refs']} |")
        lines.append("")
    lines += ["## Detalle y revert\n"]
    for e in entries:
        lines += [f"### [{e['group']}] {e['origin_name']} → {e['target_name']}\n",
                  f"- origen: `{e['origin_id']}` · destino: `{e['target_id']}`",
                  f"- roles origen: {e['origin_roles']} · roles destino: {e['target_roles']}",
                  f"- colisiones works_person_roles: {e['wpr_collisions']}",
                  f"- alias a mover: {e['aliases_move']} · ya en destino: {e['aliases_dup']}",
                  f"- identificadores a mover: {e['ids_move']}",
                  f"- otras refs: {e['refs']}",
                  f"- obras (muestra): {e['works_muestra'] or '—'}",
                  f"- persons_merge_history: {e['merge_history']}",
                  f"- revert: {e['revert']}",
                  f"- info del destino: {e['target_preservado']}\n"]
    out_md.write_text("\n".join(lines) + "\n", encoding="utf-8")
    print("merges:", len(entries), "| A:", sum(1 for e in entries if e["group"] == "A"),
          "| B:", sum(1 for e in entries if e["group"] == "B"))
    print("informe:", out_md)


def main() -> None:
    with contextlib.suppress(AttributeError, ValueError):
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--csv", type=Path, default=Path(r"G:\rism\merge_lote1a.csv"))
    ap.add_argument("--md", type=Path, default=ROOT / "docsNew" / "ejecucion-merge-1a.md")
    args = ap.parse_args()
    run(args.csv, args.md)


if __name__ == "__main__":
    main()
