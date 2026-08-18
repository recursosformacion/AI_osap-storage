"""Backfill de metadatos de obras desde PDMX (pdmx_index.db).

Puebla `works.title/composer/artist/genre/license/subtitle` a partir del índice
PDMX local, uniendo por `work_key` (CID IPFS = basename de la ruta `mxl` de
PDMX). Idempotente (siempre sobrescribe desde PDMX). La BD de obras objetivo es
la réplica local (osap-storage); NO toca producción.

Uso:
    python scripts/backfill_works_pdmx.py --db osap-storage \
        --pdmx D:/Proyectos/AI_OSAP/pdmx_index.db [--dry-run] [--limit N]
"""

from __future__ import annotations

import argparse
import sqlite3
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from infrastructure.config import Settings  # noqa: E402


def main() -> int:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")  # type: ignore[union-attr]
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--db", default=None)
    parser.add_argument("--pdmx", default=r"D:\Proyectos\AI_OSAP\pdmx_index.db")
    parser.add_argument("--limit", type=int, default=0, help="0 = todas")
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()

    import pymysql

    base = Settings()  # type: ignore[call-arg]
    db_name = args.db or base.db_name
    conn = pymysql.connect(host="127.0.0.1", port=3306, user="osap2027",
                           password="2027osapdb", database=db_name, charset="utf8mb4")

    p = sqlite3.connect(args.pdmx)
    cur = p.cursor()
    cur.execute("SELECT mxl, title, subtitle, composer_name, artist_name, genres, license "
                "FROM works")
    rows = [(r[0], r[1], r[2], r[3], r[4], r[5], r[6]) for r in cur.fetchall()]
    p.close()

    meta = {}
    for mxl, title, subtitle, composer, artist, genres, license in rows:
        key = (mxl or "").rsplit("/", 1)[-1]
        if key.endswith(".mxl"):
            key = key[:-4]
        if key:
            meta[key] = (title, subtitle, composer, artist, genres, license)
    print("pdmx work_keys:", len(meta))

    c = conn.cursor()
    c.execute("SELECT work_key FROM works")
    keys = [r[0] for r in c.fetchall()]
    matched = [k for k in keys if k in meta]
    print(f"works={len(keys)} | con match pdmx={len(matched)}")

    target = matched[: args.limit] if args.limit else matched
    updated = 0
    batch = []
    for k in target:
        batch.append((*meta[k], k))
        if len(batch) >= 1000:
            if not args.dry_run:
                c.executemany(
                    "UPDATE works SET title=%s, subtitle=%s, composer=%s, artist=%s, genre=%s, "
                    "license=%s, updated_at=NOW(6) WHERE work_key=%s", batch)
                updated += c.rowcount
            else:
                updated += len(batch)
            batch = []
    if batch:
        if not args.dry_run:
            c.executemany(
                "UPDATE works SET title=%s, subtitle=%s, composer=%s, artist=%s, genre=%s, "
                "license=%s, updated_at=NOW(6) WHERE work_key=%s", batch)
            updated += c.rowcount
        else:
            updated += len(batch)
    conn.commit()
    print(f"actualizadas (dry_run={args.dry_run}): {updated}")
    print("ejemplo:", meta[target[0]] if target else None)
    conn.close()
    return 0


if __name__ == "__main__":
    sys.exit(main())
