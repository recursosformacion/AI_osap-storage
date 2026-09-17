"""Unifica la normalización de `persons_authority_name` y elimina filas redundantes.

El catálogo de autoridad se normalizó con `composer_key` (iniciales + apellido: `r wagner`),
pero la incorporación de CPDL usó `normalize_composer_name` (`richard wagner`). Al convivir
las dos convenciones, aparecen filas del mismo nombre que no aportan nada.

Este script:
  1. Recalcula `persons_authority_name_normalized_name` para **todas** las filas con
     `composer_key` (la convención del catálogo).
  2. Elimina las filas redundantes: misma (authority_id, nombre, normalizado), conservando
     la de menor `id`.

Uso:
    .venv\\Scripts\\python.exe scripts/normalize_authority_names.py --dry-run
    .venv\\Scripts\\python.exe scripts/normalize_authority_names.py
"""

from __future__ import annotations

import argparse
import asyncio
import contextlib
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "scripts"))

from infrastructure.config import Settings  # noqa: E402
from infrastructure.db.connection import Database  # noqa: E402
from load_composer_authority import composer_key  # noqa: E402


async def run(db_name: str, dry_run: bool) -> None:
    base = Settings()  # type: ignore[call-arg]
    db = Database(base.model_copy(update={"db_name": db_name}))
    await db.connect()

    async with db.connection() as conn, conn.cursor() as cur:
        await cur.execute(
            "SELECT id, authority_id, persons_authority_name_name AS name, "
            "persons_authority_name_normalized_name AS norm FROM persons_authority_name"
        )
        rows = await cur.fetchall()

    changes = 0
    seen: set[tuple[int, str, str]] = set()
    dup_ids: list[int] = []
    for r in rows:
        key = (composer_key(str(r["name"])) or str(r["norm"]))[:128]
        if key != str(r["norm"]):
            changes += 1
        tri = (int(r["authority_id"]), str(r["name"]), key)
        if tri in seen:
            dup_ids.append(int(r["id"]))
        else:
            seen.add(tri)
    print({"filas": len(rows), "normalizado cambia": changes, "filas redundantes": len(dup_ids)})

    if dry_run:
        await db.close()
        return

    async with db.transaction() as conn, conn.cursor() as cur:
        for r in rows:
            key = (composer_key(str(r["name"])) or str(r["norm"]))[:128]
            if key != str(r["norm"]):
                await cur.execute(
                    "UPDATE persons_authority_name SET persons_authority_name_normalized_name=%s "
                    "WHERE id=%s",
                    (key, r["id"]),
                )
        for i in range(0, len(dup_ids), 1000):
            chunk = dup_ids[i : i + 1000]
            ph = ", ".join(["%s"] * len(chunk))
            await cur.execute(f"DELETE FROM persons_authority_name WHERE id IN ({ph})", chunk)
    await db.close()
    print(f"actualizadas: {changes} | borradas: {len(dup_ids)}")


def main() -> None:
    with contextlib.suppress(AttributeError, ValueError):
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--db", default="osap-storage")
    ap.add_argument("--dry-run", action="store_true")
    args = ap.parse_args()
    asyncio.run(run(args.db, args.dry_run))


if __name__ == "__main__":
    main()
