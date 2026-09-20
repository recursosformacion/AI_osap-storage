"""Materialización reversible `works_person_import` → `works_person_roles` (2.540 propuestas).

Valida contra la BBDD antes de aplicar (aborta si el CSV quedó obsoleto), audita con
`operation='assign'` en `works_person_roles_history` y permite revert exacto.

    .venv\\Scripts\\python.exe scripts/execute_wpi_materialization.py            # dry-run
    .venv\\Scripts\\python.exe scripts/execute_wpi_materialization.py --apply
    .venv\\Scripts\\python.exe scripts/execute_wpi_materialization.py --revert
"""

from __future__ import annotations

import argparse
import contextlib
import csv
import sys
import uuid
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

import pymysql  # noqa: E402
import yaml  # noqa: E402

DDL = """
CREATE TABLE IF NOT EXISTS `works_person_roles_history` (
  `id` bigint(20) unsigned NOT NULL AUTO_INCREMENT,
  `works_person_roles_id` bigint(20) unsigned NOT NULL,
  `work_id` bigint(20) unsigned NOT NULL,
  `person_id` char(36) NOT NULL,
  `role_id` int(11) NOT NULL,
  `works_person_roles_order` int(11) NOT NULL DEFAULT 0,
  `operation` varchar(16) NOT NULL,
  `batch_id` char(36) DEFAULT NULL,
  `created_at` datetime(6) NOT NULL DEFAULT current_timestamp(6),
  PRIMARY KEY (`id`),
  KEY `idx_wprh_batch` (`batch_id`),
  KEY `idx_wprh_work` (`work_id`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci
"""


def _load(csv_path: Path) -> list[tuple[int, str, int, int, str]]:
    out = []
    with open(csv_path, encoding="utf-8") as fh:
        for r in csv.DictReader(fh):
            out.append((int(r["work_id"]), r["import_name"], int(r["target_role"]),
                        int(r["target_role"]), r["person_id"]))
    return out


def run(csv_path: Path, apply: bool, revert: bool) -> None:
    with open(ROOT / "config.yaml", encoding="utf-8") as fh:
        cfg = yaml.safe_load(fh)["db"]
    conn = pymysql.connect(host=cfg["host"], port=cfg["port"], user=cfg["user"],
                           password=cfg["password"], database=cfg["name"], charset="utf8mb4",
                           autocommit=False, cursorclass=pymysql.cursors.DictCursor)
    cur = conn.cursor()
    cur.execute(DDL)
    conn.commit()

    if revert:
        cur.execute("SELECT batch_id FROM works_person_roles_history WHERE operation='assign' "
                    "ORDER BY id DESC LIMIT 1")
        row = cur.fetchone()
        if not row:
            print("nada que revertir")
            conn.close()
            return
        batch = row["batch_id"]
        cur.execute("SELECT works_person_roles_id FROM works_person_roles_history "
                    "WHERE batch_id=%s", (batch,))
        ids = [r["works_person_roles_id"] for r in cur.fetchall()]
        for i in range(0, len(ids), 2000):
            part = ids[i:i + 2000]
            ph = ",".join(["%s"] * len(part))
            cur.execute(f"DELETE FROM works_person_roles WHERE works_person_roles_id IN ({ph})", part)
        cur.execute("DELETE FROM works_person_roles_history WHERE batch_id=%s", (batch,))
        conn.commit()
        print(f"REVERTIDO batch {batch}: {len(ids)} filas")
        conn.close()
        return

    proposals = _load(csv_path)
    mismatches = 0
    for work_id, _name, role, _t, person_id in proposals:
        cur.execute("SELECT 1 FROM persons WHERE persons_id=%s", (person_id,))
        if not cur.fetchone():
            mismatches += 1
            continue
        cur.execute("SELECT 1 FROM works WHERE id=%s", (work_id,))
        if not cur.fetchone():
            mismatches += 1
            continue
        cur.execute("SELECT 1 FROM works_person_roles WHERE works_person_roles_work_id=%s "
                    "AND works_person_roles_role_id=%s", (work_id, role))
        if cur.fetchone():
            mismatches += 1
    print(f"propuestas={len(proposals)} mismatches_con_BBDD={mismatches}")
    if mismatches:
        print("ABORTADO: el CSV no coincide con el estado actual; regenera el dry-run.")
        conn.close()
        return

    if not apply:
        conn.close()
        print("DRY-RUN (sin escribir)")
        return

    batch = str(uuid.uuid4())
    inserted = 0
    for work_id, _name, role, _t, person_id in proposals:
        cur.execute("INSERT IGNORE INTO works_person_roles (works_person_roles_work_id, "
                    "works_person_roles_person_id, works_person_roles_role_id, "
                    "works_person_roles_order) VALUES (%s,%s,%s,0)", (work_id, person_id, role))
        if cur.rowcount == 0:
            continue
        rid = cur.lastrowid
        cur.execute("INSERT INTO works_person_roles_history (works_person_roles_id, work_id, "
                    "person_id, role_id, works_person_roles_order, operation, batch_id) "
                    "VALUES (%s,%s,%s,%s,0,'assign',%s)", (rid, work_id, person_id, role, batch))
        inserted += 1
    conn.commit()
    print(f"APLICADO batch {batch}: {inserted} materializaciones")
    conn.close()


def main() -> None:
    with contextlib.suppress(AttributeError, ValueError):
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--csv", type=Path, default=Path(r"G:\rism\wpi_materializacion.csv"))
    ap.add_argument("--apply", action="store_true")
    ap.add_argument("--revert", action="store_true")
    args = ap.parse_args()
    run(args.csv, args.apply, args.revert)


if __name__ == "__main__":
    main()
