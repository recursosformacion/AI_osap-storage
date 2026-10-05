#!/usr/bin/env python
"""Rellena `representations_ensemble_code` / `voice_signature` (Bloque 3, best-effort).

Fuente disponible hoy: la formación de la **obra** (`work_ensembles` → `ensembles`, ya
canónico). Solo se rellena cuando la obra tiene **una única** formación distinta; si tiene
varias (lo habitual en CPDL: una por edición) queda `NULL`, porque la representación no
guarda su voicing por-edición. La población correcta por-edición se hará en la importación
(aplicando `canonical_ensemble` al voicing del proveedor).

`voice_signature` se deriva del id canónico (fuente de verdad: ensembles → ensemble_voices).

Uso (osap-storage, venv, `PYTHONPATH=.`):
    python scripts/backfill_representation_ensembles.py --dry-run
    python scripts/backfill_representation_ensembles.py --apply
"""

from __future__ import annotations

import argparse
import asyncio
import sys

from application.services.representation_ensembles import voice_signature
from infrastructure.config import Settings
from infrastructure.db.connection import Database

_DERIVABLE = """
SELECT r.id AS rep_id, t.code
FROM representations r
JOIN (
  SELECT we.works_id, COUNT(DISTINCT e.ensembles_code) AS n, MIN(e.ensembles_code) AS code
  FROM work_ensembles we JOIN ensembles e ON e.id = we.ensembles_id
  GROUP BY we.works_id
) t ON t.works_id = r.representations_works_id
WHERE t.n = 1
"""


async def run(apply: bool) -> None:
    db = Database(Settings())  # type: ignore[call-arg]
    async with db.connection() as conn, conn.cursor() as cur:
        await cur.execute("SELECT COUNT(*) n FROM representations")
        total = int((await cur.fetchone())["n"])
        await cur.execute(_DERIVABLE)
        rows = [(int(r["rep_id"]), str(r["code"])) for r in await cur.fetchall()]

    print(f"representations: {total} | derivables (obra con 1 formación): {len(rows)}")
    by_code: dict[str, int] = {}
    for _, code in rows:
        by_code[code] = by_code.get(code, 0) + 1
    print(f"ids canonicos distintos: {len(by_code)} | resto quedara NULL: {total - len(rows)}")

    if not apply:
        await db.close()
        return

    sig_cache = {code: voice_signature(code) for code in by_code}
    async with db.transaction() as conn, conn.cursor() as cur:
        await cur.execute(
            "UPDATE representations SET representations_ensemble_code=NULL, "
            "representations_voice_signature=NULL"
        )
        for rep_id, code in rows:
            await cur.execute(
                "UPDATE representations SET representations_ensemble_code=%s, "
                "representations_voice_signature=%s WHERE id=%s",
                (code, sig_cache[code], rep_id),
            )
    await db.close()
    print(f"APLICADO -> {len(rows)} representaciones con formación")


def main() -> int:
    if sys.stdout and hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--apply", action="store_true", help="ejecuta (por defecto dry-run)")
    args = parser.parse_args()
    asyncio.run(run(args.apply))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
