#!/usr/bin/env python
"""Puebla `ensemble_voices` descomponiendo `ensembles.ensembles_code` en voces.

Cada ensemble (p. ej. `SSATTB`, `SATB.SATB`) se descompone en sus voces con cantidad
(S×2, A×1, T×2, B×1). Solo se procesan códigos formados íntegramente por símbolos de voz
conocidos; el resto (descriptivos, ruido) se deja sin filas. Idempotente: reemplaza las
filas del ensemble antes de insertar. Requiere que `ensembles_code` esté normalizado en
mayúsculas (migración 008).

Uso (en osap-storage, con su venv):
    .venv\\Scripts\\python.exe scripts/populate_ensemble_voices.py --dry-run
    .venv\\Scripts\\python.exe scripts/populate_ensemble_voices.py
"""

from __future__ import annotations

import argparse
import asyncio
import sys
from collections import Counter

from infrastructure.config import Settings
from infrastructure.db.connection import Database

# Símbolo -> nombre canónico en `voices`. `A` = Alto, que el catálogo llama Contralto.
_SYMBOL_VOICE = {
    "BAR": "Baritone",
    "MZ": "Mezzo-soprano",
    "TR": "Treble",
    "CT": "Countertenor",
    "S": "Soprano",
    "A": "Contralto",
    "T": "Tenor",
    "B": "Bass",
    "C": "Countertenor",
    "V": "Voice",
}
_TOKENS = sorted(_SYMBOL_VOICE, key=len, reverse=True)
_DROP = str.maketrans("", "", ".-/, _")


def parse_code(code: str) -> list[tuple[str, int]]:
    """Descompone un código en (nombre_voz, cantidad), en orden de aparición.

    Devuelve [] si el código contiene algo que no es un símbolo de voz conocido.
    """
    text = str(code or "").strip().upper().translate(_DROP)
    if not text:
        return []
    counts: Counter[str] = Counter()
    order: list[str] = []
    i = 0
    while i < len(text):
        for token in _TOKENS:
            if text.startswith(token, i):
                name = _SYMBOL_VOICE[token]
                if name not in counts:
                    order.append(name)
                counts[name] += 1
                i += len(token)
                break
        else:
            return []  # símbolo desconocido: no arriesgamos una composición falsa
    return [(name, counts[name]) for name in order]


async def run(dry_run: bool) -> int:
    db = Database(Settings())  # type: ignore[call-arg]
    async with db.connection() as conn, conn.cursor() as cur:
        await cur.execute("SELECT id, voices_name FROM voices")
        voice_ids = {str(r["voices_name"]): int(r["id"]) for r in await cur.fetchall()}
        await cur.execute("SELECT id, ensembles_code FROM ensembles ORDER BY id")
        ensembles = [(int(r["id"]), str(r["ensembles_code"] or "")) for r in await cur.fetchall()]

    parsed = skipped = rows = 0
    for ens_id, code in ensembles:
        voices = parse_code(code)
        if not voices:
            skipped += 1
            continue
        pairs = [(voice_ids[name], qty) for name, qty in voices if name in voice_ids]
        if not pairs:
            skipped += 1
            continue
        parsed += 1
        if dry_run:
            rows += len(pairs)
            continue
        async with db.transaction() as conn, conn.cursor() as cur:
            await cur.execute("DELETE FROM ensemble_voices WHERE ensembles_id = %s", (ens_id,))
            for order, (vid, qty) in enumerate(pairs):
                await cur.execute(
                    "INSERT INTO ensemble_voices "
                    "(ensembles_id, voices_id, ensemble_voices_quantity, ensemble_voices_order) "
                    "VALUES (%s, %s, %s, %s)",
                    (ens_id, vid, qty, order),
                )
                rows += 1
    print(
        f"ensembles: {len(ensembles)} | parseados: {parsed} | sin voces: {skipped} "
        f"| filas ensemble_voices: {rows}"
    )
    await db.close()
    return parsed


def main() -> int:
    if sys.stdout and hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()
    return asyncio.run(run(args.dry_run))


if __name__ == "__main__":
    sys.exit(main())
