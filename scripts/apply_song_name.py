"""Ejecución reversible: rellenar `works_song_name` (subconjunto A seguro).

A = propuesta == works_title (sin separador ' - ' o sufijo no-persona). B (con stripping) queda fuera.

    .venv\\Scripts\\python.exe scripts/apply_song_name.py            # dry-run
    .venv\\Scripts\\python.exe scripts/apply_song_name.py --apply
    .venv\\Scripts\\python.exe scripts/apply_song_name.py --revert
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
CREATE TABLE IF NOT EXISTS `works_field_history` (
  `id` bigint(20) unsigned NOT NULL AUTO_INCREMENT,
  `work_id` bigint(20) unsigned NOT NULL,
  `field` varchar(64) NOT NULL,
  `old_value` varchar(1024) DEFAULT NULL,
  `new_value` varchar(1024) DEFAULT NULL,
  `operation` varchar(32) NOT NULL,
  `batch_id` char(36) DEFAULT NULL,
  `created_at` datetime(6) NOT NULL DEFAULT current_timestamp(6),
  PRIMARY KEY (`id`),
  KEY `idx_wfh_work` (`work_id`),
  KEY `idx_wfh_batch` (`batch_id`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci
"""


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
        cur.execute("SELECT batch_id FROM works_field_history WHERE field='works_song_name' "
                    "AND operation='fill' ORDER BY id DESC LIMIT 1")
        row = cur.fetchone()
        if not row:
            print("nada que revertir")
            conn.close()
            return
        batch = row["batch_id"]
        cur.execute("SELECT work_id FROM works_field_history WHERE field='works_song_name' "
                    "AND operation='fill' AND batch_id=%s", (batch,))
        ids = [r["work_id"] for r in cur.fetchall()]
        for i in range(0, len(ids), 2000):
            part = ids[i:i + 2000]
            ph = ",".join(["%s"] * len(part))
            cur.execute(f"UPDATE works SET works_song_name=NULL WHERE id IN ({ph})", part)
        cur.execute("DELETE FROM works_field_history WHERE batch_id=%s", (batch,))
        conn.commit()
        print(f"REVERTIDO batch {batch}: {len(ids)} obras")
        conn.close()
        return

    safe = []
    with open(csv_path, encoding="utf-8") as fh:
        for r in csv.DictReader(fh):
            if r["song_name_propuesto"].strip() == r["works_title"].strip():
                safe.append((int(r["work_id"]), r["song_name_propuesto"]))
    print("subconjunto A (seguro):", len(safe))

    if not apply:
        conn.close()
        print("DRY-RUN (sin escribir)")
        return

    batch = str(uuid.uuid4())
    for i in range(0, len(safe), 2000):
        part = safe[i:i + 2000]
        cur.executemany(
            "INSERT INTO works_field_history (work_id, field, old_value, new_value, operation, batch_id) "
            "VALUES (%s,'works_song_name',NULL,%s,'fill',%s)",
            [(wid, song, batch) for wid, song in part])
        cur.executemany("UPDATE works SET works_song_name=%s WHERE id=%s",
                        [(song, wid) for wid, song in part])
    conn.commit()
    cur.execute("SELECT COUNT(*) n FROM works_field_history WHERE batch_id=%s", (batch,))
    print(f"APLICADO batch {batch}: {cur.fetchone()['n']} filas de historial")
    conn.close()


def main() -> None:
    with contextlib.suppress(AttributeError, ValueError):
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--csv", type=Path, default=Path(r"G:\rism\song_name_proposals.csv"))
    ap.add_argument("--apply", action="store_true")
    ap.add_argument("--revert", action="store_true")
    args = ap.parse_args()
    run(args.csv, args.apply, args.revert)


if __name__ == "__main__":
    main()
