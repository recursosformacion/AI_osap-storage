#!/usr/bin/env python
"""Canonicaliza `ensembles.ensembles_code` y fusiona duplicados por separador.

Regla (estrecha, para no destrozar descriptivos): un separador (`-`, `/`, `.`, espacio)
se unifica a `.` **solo si todas las partes son bloques de voces** (S/A/T/B/MZ/BAR/TR...).
Así `SATB-SATB` == `SATB.SATB` y `SA / TB` == `SA.TB`, pero `SOLO SOPRANO`,
`EQUAL VOICES` o `A_CAPP` se dejan intactos.

Al fusionar, las obras y las voces del ensemble redundante pasan al canónico y el
redundante se elimina. Idempotente. Después hay que re-ejecutar
`populate_ensemble_voices.py` y reindexar CPDL.

Uso (en osap-storage, con su venv):
    .venv\\Scripts\\python.exe scripts/normalize_ensembles.py --dry-run
    .venv\\Scripts\\python.exe scripts/normalize_ensembles.py
"""

from __future__ import annotations

import argparse
import asyncio
import re
import sys
from collections import defaultdict

from infrastructure.config import Settings
from infrastructure.db.connection import Database

_TOKENS = ["BAR", "MZ", "TR", "CT", "S", "A", "T", "B", "C", "V"]
_SEP = re.compile(r"[\s/_.\-]+")
# Vacío, con plantilla o con dígitos -> no es un conjunto de voces.
_NOISE = re.compile(r"(\{\{|\}\}|=|\d)")


def is_voice_block(text: str) -> bool:
    """True si el texto se compone íntegramente de símbolos de voz (BAR, S, A...)."""
    if not text or _NOISE.search(text):
        return False
    i = 0
    while i < len(text):
        for token in _TOKENS:
            if text.startswith(token, i):
                i += len(token)
                break
        else:
            return False
    return True


def canonical_code(code: str) -> str:
    upper = str(code or "").strip().upper()
    parts = [p for p in _SEP.split(upper) if p]
    if len(parts) > 1 and all(is_voice_block(p) for p in parts):
        # Multi-coro: separador canónico '.' (SATB-SATB == SATB.SATB).
        return ".".join(parts)
    # Descriptivos: se unifican guiones/puntos/espacios a un solo espacio
    # (SOLO MEZZO-SOPRANO == SOLO MEZZO SOPRANO).
    return " ".join(parts)


async def run(dry_run: bool) -> None:
    db = Database(Settings())  # type: ignore[call-arg]
    async with db.connection() as conn, conn.cursor() as cur:
        await cur.execute(
            "SELECT e.id, e.ensembles_code AS code, "
            "(SELECT COUNT(*) FROM work_ensembles we WHERE we.ensembles_id = e.id) AS n "
            "FROM ensembles e"
        )
        rows = await cur.fetchall()

    groups: dict[str, list[tuple[int, str, int]]] = defaultdict(list)
    for r in rows:
        groups[canonical_code(r["code"])].append((int(r["id"]), str(r["code"]), int(r["n"])))

    renames = merges = moved = 0
    for canonical, variants in groups.items():
        # Solo se actúa si hay duplicados reales (varias formas del mismo conjunto).
        # Los códigos únicos no se tocan (evita churn cosmético de separadores).
        if len(variants) < 2:
            continue
        # Objetivo: el que ya se llama canónico; si no, el de más obras.
        target = next((v for v in variants if v[1] == canonical), None)
        if target is None:
            target = max(variants, key=lambda v: v[2])
        t_id, t_code, _ = target
        others = [v for v in variants if v[0] != t_id]
        if not dry_run:
            async with db.transaction() as conn, conn.cursor() as cur:
                if t_code != canonical:
                    await cur.execute(
                        "UPDATE ensembles SET ensembles_code = %s WHERE id = %s",
                        (canonical, t_id),
                    )
                for o_id, _o_code, o_n in others:
                    await cur.execute(
                        "INSERT IGNORE INTO work_ensembles "
                        "(works_id, ensembles_id, work_ensembles_quantity) "
                        "SELECT works_id, %s, work_ensembles_quantity FROM work_ensembles "
                        "WHERE ensembles_id = %s",
                        (t_id, o_id),
                    )
                    moved += o_n
                    await cur.execute("DELETE FROM work_ensembles WHERE ensembles_id = %s", (o_id,))
                    await cur.execute("DELETE FROM ensembles WHERE id = %s", (o_id,))
                    merges += 1
        else:
            moved += sum(v[2] for v in others)
            merges += len(others)
        if t_code != canonical:
            renames += 1
        print(
            f"  {canonical}: objetivo id={t_id} ({t_code!r})"
            + (f" + fusiona {[v[1] for v in others]}" if others else "")
        )

    print(f"renombrados: {renames} | fusiones: {merges} | enlaces movidos: {moved}")
    await db.close()


def main() -> int:
    if sys.stdout and hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()
    asyncio.run(run(args.dry_run))
    return 0


if __name__ == "__main__":
    sys.exit(main())
