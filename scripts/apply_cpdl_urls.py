"""Activa la derivación de URLs CPDL en `works_resources.url` (reversible).

Solo modifica `works_resources_url` para los recursos CPDL con nombre. Guarda historial en
`works_resources_field_history`. No toca `file_id` ni descarga nada.

    .venv\\Scripts\\python.exe scripts/apply_cpdl_urls.py            # dry-run
    .venv\\Scripts\\python.exe scripts/apply_cpdl_urls.py --apply
    .venv\\Scripts\\python.exe scripts/apply_cpdl_urls.py --revert
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

FIELD = "works_resources_url"
DDL = """
CREATE TABLE IF NOT EXISTS `works_resources_field_history` (
  `id` bigint(20) unsigned NOT NULL AUTO_INCREMENT,
  `resource_id` bigint(20) unsigned NOT NULL,
  `field` varchar(64) NOT NULL,
  `old_value` varchar(1024) DEFAULT NULL,
  `new_value` varchar(1024) DEFAULT NULL,
  `operation` varchar(32) NOT NULL,
  `batch_id` char(36) DEFAULT NULL,
  `created_at` datetime(6) NOT NULL DEFAULT current_timestamp(6),
  PRIMARY KEY (`id`),
  KEY `idx_wrfh_batch` (`batch_id`),
  KEY `idx_wrfh_resource` (`resource_id`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci
"""


def _load(csv_path: Path) -> list[tuple[int, str, str]]:
    out = []
    with open(csv_path, encoding="utf-8") as fh:
        for r in csv.DictReader(fh):
            if r["name"] and r["url"]:
                out.append((int(r["resource_id"]), r["name"], r["url"]))
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
        cur.execute("SELECT batch_id FROM works_resources_field_history WHERE field=%s "
                    "AND operation='derive_url' ORDER BY id DESC LIMIT 1", (FIELD,))
        row = cur.fetchone()
        if not row:
            print("nada que revertir")
            conn.close()
            return
        batch = row["batch_id"]
        cur.execute("SELECT resource_id, old_value FROM works_resources_field_history "
                    "WHERE batch_id=%s", (batch,))
        entries = cur.fetchall()
        for i in range(0, len(entries), 2000):
            part = entries[i:i + 2000]
            cur.executemany("UPDATE works_resources SET works_resources_url=%s WHERE id=%s",
                            [(e["old_value"], e["resource_id"]) for e in part])
        cur.execute("DELETE FROM works_resources_field_history WHERE batch_id=%s", (batch,))
        conn.commit()
        print(f"REVERTIDO batch {batch}: {len(entries)} filas")
        conn.close()
        return

    rows = _load(csv_path)
    mismatches = 0
    for rid, name, _url in rows:
        cur.execute("SELECT works_resources_name n, works_resources_url u FROM works_resources WHERE id=%s", (rid,))
        r = cur.fetchone()
        if not r or (r["n"] or "") != name or r["u"] is not None:
            mismatches += 1
    print(f"propuestas={len(rows)} mismatches={mismatches}")
    if mismatches:
        print("ABORTADO: el CSV no coincide con el estado actual.")
        conn.close()
        return
    if not apply:
        conn.close()
        print("DRY-RUN (sin escribir)")
        return

    batch = str(uuid.uuid4())
    for i in range(0, len(rows), 2000):
        part = rows[i:i + 2000]
        cur.executemany("INSERT INTO works_resources_field_history (resource_id, field, old_value, "
                        "new_value, operation, batch_id) VALUES (%s,%s,NULL,%s,'derive_url',%s)",
                        [(rid, FIELD, url, batch) for rid, _name, url in part])
        cur.executemany("UPDATE works_resources SET works_resources_url=%s WHERE id=%s",
                        [(url, rid) for rid, _name, url in part])
    conn.commit()
    cur.execute("SELECT COUNT(*) n FROM works_resources_field_history WHERE batch_id=%s", (batch,))
    print(f"APLICADO batch {batch}: {cur.fetchone()['n']} URLs")
    conn.close()


def main() -> None:
    with contextlib.suppress(AttributeError, ValueError):
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--csv", type=Path, default=Path(r"G:\rism\cpdl_url_derivation.csv"))
    ap.add_argument("--apply", action="store_true")
    ap.add_argument("--revert", action="store_true")
    args = ap.parse_args()
    run(args.csv, args.apply, args.revert)


if __name__ == "__main__":
    main()
