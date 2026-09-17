"""Crea los **alias** de persona a partir de las variantes vistas en `works_person_import`.

Para cada fila del import se calcula su clave canónica (iniciales + apellido, **sin
acentos**) y se busca la persona en `persons_identity`. Si coincide, se guarda **el nombre
tal cual aparece en el import** como alias de esa persona.

Reglas:
  - **Nunca** se toman alias de `persons_identity` (allí el mismo nombre se repite muchas
    veces y generaría alias duplicados/basura).
  - Se deduplica por `(persona, alias_normalizado)`; el normalizado es **sin acentos**
    (`normalize_composer_name`).
  - Se omite el alias si coincide con el nombre canónico de la persona.

Uso:
    .venv\\Scripts\\python.exe scripts/create_aliases_from_import.py --dry-run
    .venv\\Scripts\\python.exe scripts/create_aliases_from_import.py
"""

from __future__ import annotations

import argparse
import asyncio
import contextlib
import re
import sys
import unicodedata
from collections import Counter
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from domain.services.composer_names import normalize_composer_name  # noqa: E402
from infrastructure.config import Settings  # noqa: E402
from infrastructure.db.connection import Database  # noqa: E402
from populate_persons_from_import import is_personlike  # noqa: E402

_ARR = re.compile(r"\s*[,;]?\s*(?:arr\.?|arranged|arrangement)\s*(?:by)?\s*[:.]?\s*", re.I)


def key(name: str) -> str:
    """Clave canónica sin acentos: iniciales + apellido."""
    t = unicodedata.normalize("NFKD", name or "").encode("ascii", "ignore").decode("ascii")
    t = t.lower().replace("'", "").replace("_", " ")
    toks = re.findall(r"[a-z]+", t)
    if not toks:
        return ""
    if len(toks) > 1 and toks[-2] == "o":
        return f"o{toks[-1]} {''.join(x[0] for x in toks[:-2])}".strip()
    return f"{''.join(x[0] for x in toks[:-1])} {toks[-1]}".strip()


async def run(db_name: str, dry_run: bool) -> None:
    base = Settings()  # type: ignore[call-arg]
    db = Database(base.model_copy(update={"db_name": db_name}))
    await db.connect()

    async with db.connection() as conn, conn.cursor() as cur:
        await cur.execute(
            "SELECT identity_name, persons_id FROM persons_identity WHERE persons_id IS NOT NULL"
        )
        votes: dict[str, Counter] = {}
        for r in await cur.fetchall():
            k = key(str(r["identity_name"]))
            if k:
                votes.setdefault(k, Counter())[str(r["persons_id"])] += 1
        by_key = {k: sorted(c.items(), key=lambda kv: (-kv[1], kv[0]))[0][0] for k, c in votes.items()}
        await cur.execute("SELECT persons_id, persons_name FROM persons")
        canonical = {str(r["persons_id"]): str(r["persons_name"]) for r in await cur.fetchall()}
        await cur.execute(
            "SELECT works_person_import_name AS name FROM works_person_import "
            "WHERE works_person_import_role IN ('composer','artist')"
        )
        rows = await cur.fetchall()

    candidates: set[tuple[str, str, str]] = set()  # (persona, alias, normalizado)
    stats = {"filas": len(rows), "sin_match": 0, "alias": 0, "canonico": 0}
    for r in rows:
        raw = str(r["name"]).strip()
        name = _ARR.split(raw, maxsplit=1)[0].strip()
        name = re.sub(r"^(?:by|from|after)\s+", "", name, flags=re.I).strip()
        pid = by_key.get(key(name))
        if not pid:
            stats["sin_match"] += 1
            continue
        if not is_personlike(name):
            stats['sin_match'] += 1
            continue
        norm = normalize_composer_name(name)
        if not norm:
            continue
        if normalize_composer_name(canonical.get(pid, "")) == norm:
            stats["canonico"] += 1
            continue
        candidates.add((pid, name[:255], norm[:255]))
    stats["alias"] = len(candidates)
    print(stats)

    if dry_run:
        sample = list(candidates)[:10]
        for pid, alias, norm in sample:
            print(f"   {alias}  ->  {canonical.get(pid)}  [{norm}]")
        await db.close()
        return

    async with db.transaction() as conn, conn.cursor() as cur:
        for pid, alias, norm in candidates:
            await cur.execute(
                "INSERT IGNORE INTO persons_aliases (person_id, person_aliases_alias, "
                "person_aliases_normalized_alias, person_aliases_name_type, "
                "person_aliases_source) VALUES (%s, %s, %s, 'import', 'works_person_import')",
                (pid, alias, norm),
            )
    await db.close()
    print(f"alias creados: {len(candidates)}")


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
