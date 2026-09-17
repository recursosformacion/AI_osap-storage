"""Unifica `persons_identity.identity_name_norm` a la clave **sin acentos**.

La clave usada en identidad venía de `composer_key` (conservaba diacríticos: `g f händel`),
mientras que el resto del sistema normaliza sin acentos (`g f handel`). Este script recalcula
el normalizado de **todas** las filas de `persons_identity` con la clave sin acentos
(iniciales + apellido), que es la que usan los enlazadores.

Uso:
    .venv\\Scripts\\python.exe scripts/normalize_identity_names.py --dry-run
    .venv\\Scripts\\python.exe scripts/normalize_identity_names.py
"""

from __future__ import annotations

import argparse
import asyncio
import contextlib
import re
import sys  # noqa: F401
import unicodedata
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from infrastructure.config import Settings  # noqa: E402
from infrastructure.db.connection import Database  # noqa: E402

_ANON = {
    "anon", "anonymous", "trad", "traditional", "unknown", "desconocido", "various",
    "attrib", "attributed", "urheber unbekannt",
}


def key(name: str) -> str:
    """Clave canónica sin acentos: iniciales + apellido (la misma que usan los enlazadores)."""
    text = unicodedata.normalize("NFKD", name or "").encode("ascii", "ignore").decode("ascii")
    low = text.lower().replace("'", "").replace("_", " ")
    if low.strip() in _ANON or low.strip().startswith("urheber unbekannt"):
        return "anonymous"
    clean = re.sub(r"\([^)]*\)", "", low)
    tokens = re.findall(r"[a-z]+", clean)
    if not tokens:
        return ""
    if len(tokens) > 1 and tokens[-2] == "o":
        return f"o{tokens[-1]} {''.join(t[0] for t in tokens[:-2])}".strip()
    return f"{''.join(t[0] for t in tokens[:-1])} {tokens[-1]}".strip()


async def run(db_name: str, dry_run: bool) -> None:
    base = Settings()  # type: ignore[call-arg]
    db = Database(base.model_copy(update={"db_name": db_name}))
    await db.connect()

    async with db.connection() as conn, conn.cursor() as cur:
        await cur.execute(
            "SELECT id, identity_name, identity_name_norm FROM persons_identity"
        )
        rows = await cur.fetchall()

    updates = [(key(str(r["identity_name"]))[:128], int(r["id"]))
               for r in rows if key(str(r["identity_name"]))[:128] != str(r["identity_name_norm"])]
    print({"filas": len(rows), "cambian": len(updates)})

    if dry_run:
        for new, rid in updates[:10]:
            print(f"   id={rid} -> [{new}]")
        await db.close()
        return

    async with db.transaction() as conn, conn.cursor() as cur:
        for i in range(0, len(updates), 1000):
            chunk = updates[i : i + 1000]
            await cur.executemany(
                "UPDATE persons_identity SET identity_name_norm = %s WHERE id = %s", chunk
            )
    await db.close()
    print(f"actualizadas: {len(updates)}")


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
