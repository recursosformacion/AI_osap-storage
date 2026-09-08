#!/usr/bin/env python
"""Backfill de términos de voicing CPDL (`cpdl_voicings`) desde `cpdl_pages.voicing`.

Para registros CPDL ya importados sin la tabla derivada (migración 036 posterior):
reescribe los términos de voicing de cada página a partir de su `voicing` actual.
No crea obras ni toca `works`: solo rellena la estructura de búsqueda auxiliar
(una fila por término, misma página CPDL). Idempotente y reanudable.

Uso (en osap-storage, con su venv):
    .venv\\Scripts\\python.exe scripts/backfill_cpdl_voicings.py
    .venv\\Scripts\\python.exe scripts/backfill_cpdl_voicings.py --limit 2000   # prueba
"""

from __future__ import annotations

import argparse
import asyncio
import sys

from application.services.cpdl_voicing import voicing_terms
from infrastructure.config import Settings
from infrastructure.db.connection import Database


async def run(from_id: int, limit: int, batch: int = 1000) -> int:
    db = Database(Settings())
    total = 0
    last_id = from_id
    done = False
    while not done:
        async with db.connection() as conn, conn.cursor() as cur:
            await cur.execute(
                "SELECT id, voicing FROM cpdl_pages WHERE id > %s ORDER BY id LIMIT %s",
                (last_id, batch),
            )
            rows = await cur.fetchall()
        if not rows:
            break
        async with db.connection() as conn, conn.cursor() as cur:
            for row in rows:
                page_id = int(row["id"])
                await cur.execute("DELETE FROM cpdl_voicings WHERE cpdl_page_id = %s", (page_id,))
                for term in voicing_terms(row["voicing"]):
                    await cur.execute(
                        "INSERT INTO cpdl_voicings (cpdl_page_id, term) VALUES (%s, %s)",
                        (page_id, term),
                    )
                total += 1
                last_id = page_id
            await conn.commit()
        print(f"  ... {total} páginas (última id {last_id})", flush=True)
        if limit > 0 and total >= limit:
            break
        if len(rows) < batch:
            done = True
    return total


def main() -> int:
    if sys.stdout and hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--from-id", type=int, default=0)
    parser.add_argument("--limit", type=int, default=0)
    args = parser.parse_args()
    return asyncio.run(run(args.from_id, args.limit))


if __name__ == "__main__":
    sys.exit(main())
