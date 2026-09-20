"""Ejecución reversible del Lote 1A (7 merges) con snapshots y comprobaciones/abortos.

Modos: --dry-run (por defecto), --apply, --revert.
No elimina información del destino: solo mueve/deduplica filas del origen con snapshot.

    .venv\\Scripts\\python.exe scripts/execute_merge_1a.py            # dry-run
    .venv\\Scripts\\python.exe scripts/execute_merge_1a.py --apply
    .venv\\Scripts\\python.exe scripts/execute_merge_1a.py --revert
"""

from __future__ import annotations

import argparse
import contextlib
import csv
import json
import sys
import uuid
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

import pymysql  # noqa: E402
import yaml  # noqa: E402

GROUP_B = {"Arr : Iraj Goli", "Edited byJAY YOUNG"}
MERGED_BY = "rism-lote1a"
DDL = """
CREATE TABLE IF NOT EXISTS `persons_merge_snapshot` (
  `id` bigint(20) unsigned NOT NULL AUTO_INCREMENT,
  `merge_operation_id` varchar(80) NOT NULL,
  `source_person_id` char(36) NOT NULL,
  `target_person_id` char(36) NOT NULL,
  `payload_json` longtext NOT NULL,
  `created_at` datetime(6) NOT NULL DEFAULT current_timestamp(6),
  PRIMARY KEY (`id`),
  KEY `idx_pms_op` (`merge_operation_id`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci
"""


def _conn():
    with open(ROOT / "config.yaml", encoding="utf-8") as fh:
        cfg = yaml.safe_load(fh)["db"]
    return pymysql.connect(host=cfg["host"], port=cfg["port"], user=cfg["user"],
                           password=cfg["password"], database=cfg["name"], charset="utf8mb4",
                           autocommit=False, cursorclass=pymysql.cursors.DictCursor)


def _pairs(csv_path: Path) -> list[tuple[str, str, str]]:
    with open(csv_path, encoding="utf-8") as fh:
        return [(r["origin_id"], r["target_id"], r["origin_name"])
                for r in csv.DictReader(fh) if r["origin_name"] not in GROUP_B]


def _snapshot(cur, oid: str, tid: str, op: str) -> dict:
    def rows(table: str, column: str) -> list[dict]:
        cur.execute(f"SELECT * FROM {table} WHERE {column}=%s", (oid,))
        return cur.fetchall()

    wpr = rows("works_person_roles", "works_person_roles_person_id")
    aliases = rows("persons_aliases", "person_id")
    identity = rows("persons_identity", "persons_id")
    evidence = rows("persons_evidence", "persons_id")
    rep_persons = rows("representation_persons", "representation_persons_person_id")
    cpdl_persons = rows("cpdl_edition_persons", "persons_id")

    cur.execute("SELECT works_person_roles_work_id w, works_person_roles_role_id r FROM "
                "works_person_roles WHERE works_person_roles_person_id=%s", (tid,))
    target_keys = {(x["w"], x["r"]) for x in cur.fetchall()}
    collisions = [x for x in wpr
                  if (x["works_person_roles_work_id"], x["works_person_roles_role_id"]) in target_keys]

    cur.execute("SELECT person_aliases_normalized_alias a FROM persons_aliases WHERE person_id=%s", (tid,))
    target_aliases = {x["a"] for x in cur.fetchall()}
    alias_dups = [x for x in aliases if x["person_aliases_normalized_alias"] in target_aliases]

    cur.execute("SELECT identity_type t, identity_value v FROM persons_identity WHERE persons_id=%s", (tid,))
    target_ids = {(x["t"], x["v"]) for x in cur.fetchall()}
    id_dups = [x for x in identity if (x["identity_type"], x["identity_value"]) in target_ids]

    return {
        "operation": op, "source": oid, "target": tid,
        "moved": {
            "works_person_roles": [x["works_person_roles_id"] for x in wpr if x not in collisions],
            "persons_aliases": [x["id"] for x in aliases if x not in alias_dups],
            "persons_identity": [x["id"] for x in identity if x not in id_dups],
            "persons_evidence": [x["id"] for x in evidence],
            "representation_persons": [x["id"] for x in rep_persons],
            "cpdl_edition_persons": [x["id"] for x in cpdl_persons],
        },
        "deleted": {
            "works_person_roles": collisions,
            "persons_aliases": alias_dups,
            "persons_identity": id_dups,
        },
    }


def _restore(cur, snap: dict) -> None:
    moved, deleted = snap["moved"], snap["deleted"]
    for row in deleted["works_person_roles"]:
        cur.execute(
            "INSERT IGNORE INTO works_person_roles (works_person_roles_id, "
            "works_person_roles_work_id, works_person_roles_person_id, "
            "works_person_roles_role_id, works_person_roles_order) VALUES (%s,%s,%s,%s,%s)",
            (row["works_person_roles_id"], row["works_person_roles_work_id"],
             snap["source"], row["works_person_roles_role_id"], row["works_person_roles_order"]))
    for row in deleted["persons_aliases"]:
        cur.execute("INSERT IGNORE INTO persons_aliases (id, person_id, person_aliases_alias, "
                    "person_aliases_normalized_alias, person_aliases_source) VALUES (%s,%s,%s,%s,%s)",
                    (row["id"], snap["source"], row["person_aliases_alias"],
                     row["person_aliases_normalized_alias"], row.get("person_aliases_source")))
    for row in deleted["persons_identity"]:
        cur.execute("INSERT IGNORE INTO persons_identity (id, persons_id, identity_type, "
                    "identity_value) VALUES (%s,%s,%s,%s)",
                    (row["id"], snap["source"], row["identity_type"], row["identity_value"]))
    if moved["works_person_roles"]:
        ph = ",".join(["%s"] * len(moved["works_person_roles"]))
        cur.execute(f"UPDATE works_person_roles SET works_person_roles_person_id=%s "
                    f"WHERE works_person_roles_id IN ({ph})", [snap["source"], *moved["works_person_roles"]])
    for table, col, key in (("persons_aliases", "person_id", "id"),
                            ("persons_identity", "persons_id", "id"),
                            ("persons_evidence", "persons_id", "id"),
                            ("representation_persons", "representation_persons_person_id", "id"),
                            ("cpdl_edition_persons", "persons_id", "id")):
        ids = moved.get(table) or []
        if ids:
            ph = ",".join(["%s"] * len(ids))
            cur.execute(f"UPDATE {table} SET {col}=%s WHERE {key} IN ({ph})", [snap["source"], *ids])
    cur.execute("UPDATE persons SET persons_merged_into=NULL, persons_merged_at=NULL "
                "WHERE persons_id=%s", (snap["source"],))


def run(csv_path: Path, apply: bool, revert: bool) -> None:
    conn = _conn()
    cur = conn.cursor()
    cur.execute(DDL)
    conn.commit()

    if revert:
        cur.execute("SELECT merge_operation_id, payload_json FROM persons_merge_snapshot")
        snaps = cur.fetchall()
        for s in snaps:
            snap = json.loads(s["payload_json"])
            _restore(cur, snap)
            cur.execute("DELETE FROM persons_merge_history WHERE merge_operation_id=%s",
                        (s["merge_operation_id"],))
            cur.execute("DELETE FROM persons_merge_snapshot WHERE merge_operation_id=%s",
                        (s["merge_operation_id"],))
        conn.commit()
        print(f"REVERTIDOS {len(snaps)} merges")
        conn.close()
        return

    plans = []
    for oid, tid, oname in _pairs(csv_path):
        cur.execute("SELECT persons_name, persons_merged_into FROM persons WHERE persons_id=%s", (oid,))
        origin = cur.fetchone()
        cur.execute("SELECT persons_name, persons_merged_into FROM persons WHERE persons_id=%s", (tid,))
        target = cur.fetchone()
        if not origin or not target:
            plans.append({"op": f"merge:{oid}->{tid}", "abort": "origen/destino inexistente"})
            continue
        if origin["persons_merged_into"] or target["persons_merged_into"]:
            plans.append({"op": f"merge:{oid}->{tid}", "abort": "ya fusionado"})
            continue
        snap = _snapshot(cur, oid, tid, str(uuid.uuid4()))
        n_del = {k: len(v) for k, v in snap["deleted"].items()}
        n_mov = {k: len(v) for k, v in snap["moved"].items()}
        plans.append({"op": snap["operation"], "origin": oname, "target": target["persons_name"],
                      "moved": n_mov, "deleted": n_del, "snap": snap})
        if not apply:
            continue
        # aplicar el merge
        moved, deleted = snap["moved"], snap["deleted"]
        if moved["works_person_roles"]:
            ph = ",".join(["%s"] * len(moved["works_person_roles"]))
            cur.execute(f"UPDATE works_person_roles SET works_person_roles_person_id=%s "
                        f"WHERE works_person_roles_id IN ({ph})", [tid, *moved["works_person_roles"]])
        for row in deleted["works_person_roles"]:
            cur.execute("DELETE FROM works_person_roles WHERE works_person_roles_id=%s",
                        (row["works_person_roles_id"],))
        for table, col, key in (("persons_aliases", "person_id", "id"),
                                ("persons_identity", "persons_id", "id"),
                                ("persons_evidence", "persons_id", "id"),
                                ("representation_persons", "representation_persons_person_id", "id"),
                                ("cpdl_edition_persons", "persons_id", "id")):
            ids = moved.get(table) or []
            if ids:
                ph = ",".join(["%s"] * len(ids))
                cur.execute(f"UPDATE {table} SET {col}=%s WHERE {key} IN ({ph})", [tid, *ids])
        for row in deleted["persons_aliases"]:
            cur.execute("DELETE FROM persons_aliases WHERE id=%s", (row["id"],))
        for row in deleted["persons_identity"]:
            cur.execute("DELETE FROM persons_identity WHERE id=%s", (row["id"],))
        cur.execute("UPDATE persons SET persons_merged_into=%s, persons_merged_at=now() "
                    "WHERE persons_id=%s", (tid, oid))
        cur.execute("INSERT INTO persons_merge_history (merge_operation_id, source_person_id, "
                    "target_person_id, merged_by) VALUES (%s,%s,%s,%s)",
                    (snap["operation"], oid, tid, MERGED_BY))
        cur.execute("INSERT INTO persons_merge_snapshot (merge_operation_id, source_person_id, "
                    "target_person_id, payload_json) VALUES (%s,%s,%s,%s)",
                    (snap["operation"], oid, tid, json.dumps(snap, default=str, ensure_ascii=False)))
    if apply:
        conn.commit()
    conn.close()
    for p in plans:
        print(p.get("abort") and f"ABORT {p['op']}: {p['abort']}" or
              f"{p['op']}: movidos={p['moved']} borrados={p['deleted']}")
    print("APLICADO" if apply else "DRY-RUN (sin escribir)")


def main() -> None:
    with contextlib.suppress(AttributeError, ValueError):
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--csv", type=Path, default=Path(r"G:\rism\merge_lote1a.csv"))
    ap.add_argument("--apply", action="store_true")
    ap.add_argument("--revert", action="store_true")
    args = ap.parse_args()
    run(args.csv, args.apply, args.revert)


if __name__ == "__main__":
    main()
