#!/usr/bin/env python
"""Probar cobertura de la autoridad local (composer_authority) sobre las 100 primeras obras.

Solo LECTURA (no crea Composer ni asocia): mide cuánto resuelve la autoridad local sin
depender de Wikidata en vivo, para comparar con la pasada anterior.

Clasificación por obra (authority-only):
  * resolved  -> al menos un candidato con viaf_id (identidad fuerte)
  * ambiguous -> varios candidatos con identidades distintas / sin clara
  * not_found -> la autoridad no tiene el nombre

Además reporta: matched (ya en Maestro), nuevos detectados, ausentes, identificadores.

Uso:
    python scripts/test_authority_coverage.py --db osap-storage --limit 100
"""

from __future__ import annotations

import argparse
import re
import sys
import time
from collections import Counter, defaultdict
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from infrastructure.config import Settings  # noqa: E402
from infrastructure.db.connection import Database  # noqa: E402

_ANON = {
    "anon", "anon.", "anonymous", "trad", "trad.", "traditional", "attrib.", "attributed",
    "attrib", "unknown", "author unknown", "urheber unbekannt", "urheber unbek.",
}


def composer_key(raw: str) -> str:
    text = (raw or "").strip()
    if not text:
        return ""
    low = text.lower()
    if low in _ANON or low.startswith("urheber unbekannt"):
        return "anonymous"
    text = re.sub(r"\s+\d{3,4}\s*$", "", text)
    text = re.sub(r"\([^)]*\)", "", text)
    tokens = [t for t in text.split() if t]
    if not tokens:
        return ""
    last = tokens[-1].lower()
    firsts = "".join(t[0].lower() for t in tokens[:-1] if t[0].isalnum())
    return f"{firsts} {last}".strip()


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--db", default=None)
    parser.add_argument("--limit", type=int, default=100)
    parser.add_argument("--from-id", type=int, default=0)
    args = parser.parse_args()

    base = Settings()  # type: ignore[call-arg]
    settings = base.model_copy(update={"db_name": args.db or base.db_name})
    db = Database(settings)

    import asyncio

    async def run():
        t0 = time.time()
        async with db.connection() as conn, conn.cursor() as cur:
            # Autoridad: nombre normalizado -> [candidatos]
            await cur.execute(
                "SELECT n.normalized_name, ca.wikidata_id, ca.viaf_id, ca.canonical_name "
                "FROM composer_authority ca JOIN composer_authority_names n ON n.authority_id=ca.authority_id"
            )
            authority: dict[str, list[dict]] = defaultdict(list)
            for row in await cur.fetchall():
                authority[row["normalized_name"]].append(
                    {"wikidata_id": row["wikidata_id"], "viaf_id": row["viaf_id"], "name": row["canonical_name"]}
                )
            # Maestro: identificadores ya presentes (viaf/wikidata) en composer_identifiers
            await cur.execute(
                "SELECT id_type, id_value FROM composer_identifiers WHERE id_type IN ('viaf','wikidata')"
            )
            maestro_ids = set()
            for row in await cur.fetchall():
                if row.get("id_type") and row.get("id_value"):
                    maestro_ids.add(f"{row['id_type']}:{row['id_value']}")
            # Obras (solo lectura)
            await cur.execute(
                "SELECT id, title, composer FROM works WHERE id > %s ORDER BY id LIMIT %s",
                (args.from_id, args.limit),
            )
            works = await cur.fetchall()
        elapsed = time.time() - t0

        stats: Counter = Counter()
        matched = 0
        new_detected: list[str] = []
        absent: list[str] = []
        identifiers = 0
        works_per_composer: Counter = Counter()
        detail: list[str] = []
        for w in works:
            wid = int(w["id"])
            name = (w.get("composer") or "").strip()
            if not name or composer_key(name) == "anonymous":
                stats["not_applicable"] += 1
                detail.append(f"[{wid}] {name or '-':20} -> anon/unknown")
                continue
            key = composer_key(name)
            cands = authority.get(key, [])
            strong = [c for c in cands if c["viaf_id"]]
            if not cands:
                stats["not_found"] += 1
                absent.append(name)
                detail.append(f"[{wid}] {name:20} -> NOT_FOUND (no en autoridad)")
                continue
            if len(strong) == 1 or (strong and len({c["viaf_id"] for c in strong}) == 1):
                best = strong[0] if strong else cands[0]
                stats["resolved"] += 1
                identifiers += 1 if best["viaf_id"] else 0
                identity = f"viaf:{best['viaf_id']}" if best["viaf_id"] else f"wikidata:{best['wikidata_id']}"
                if identity in maestro_ids:
                    matched += 1
                else:
                    new_detected.append(best["name"])
                works_per_composer[best["name"]] += 1
                detail.append(
                    f"[{wid}] {name:20} -> RESOLVED {best['name']} {best['wikidata_id']} viaf={best['viaf_id']}"
                )
            else:
                stats["ambiguous"] += 1
                detail.append(f"[{wid}] {name:20} -> AMBIGUOUS ({len(cands)} cand)")

        print(f"=== COBERTURA AUTORIDAD LOCAL ({len(works)} obras, solo lectura) ===")
        print(f"tiempo: {elapsed:.1f}s | {elapsed/max(len(works),1)*1000:.0f} ms/obra")
        print(f"resolved   : {stats['resolved']}")
        print(f"ambiguous  : {stats['ambiguous']}")
        print(f"not_found  : {stats['not_found']}")
        print(f"not_applicable: {stats['not_applicable']}")
        print(f"matched (ya en Maestro): {matched}")
        print(f"nuevos detectados: {len(new_detected)}")
        print(f"ausentes (no en autoridad): {len(absent)}")
        print(f"identificadores encontrados (viaf): {identifiers}")
        print("obras por compositor candidato (top):")
        for n_, c_ in works_per_composer.most_common(8):
            print(f"   {n_}: {c_}")
        print("\nDETALLE:")
        for d in detail:
            print("  " + d)

    asyncio.run(run())
    return 0


if __name__ == "__main__":
    sys.exit(main())
