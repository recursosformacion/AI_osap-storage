"""Enlaza `works_person_import` con personas existentes (SIN crear ninguna).

Lee los nombres pendientes de `works_person_import`, los **normaliza** (minúsculas,
sin acentos ni puntuación) y los **compacta** (sin espacios), y busca en:
  1. `persons.persons_name`
  2. `persons_aliases.person_aliases_normalized_alias`

Solo se enlaza cuando la búsqueda por nombre normalizado (o compacto) da **una única**
persona; si hay ambigüedad o no hay coincidencia, la fila queda pendiente.
Nunca se crean personas: el alta de compositores queda bajo estudio (fichero aparte).

Escribe:
  - `works_person_roles` (rol 1 = Composer para `composer`, 10 = Intérprete para `artist`)
  - `works_person_import.works_person_import_resolved = 1` en las filas casadas

Uso:
    .venv\\Scripts\\python.exe scripts/link_works_person_import.py --dry-run
    .venv\\Scripts\\python.exe scripts/link_works_person_import.py --roles composer
"""

from __future__ import annotations

import argparse
import asyncio
import contextlib
import re
import sys
import unicodedata
from collections import defaultdict
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from domain.services.composer_names import normalize_composer_name  # noqa: E402
from infrastructure.config import Settings  # noqa: E402
from infrastructure.db.connection import Database  # noqa: E402

ROLE_IDS = {"composer": 1, "artist": 10}

# Nombres que no identifican a una persona.
_NOISE = {
    "", "na", "n a", "nan", "null", "none", "unknown", "desconocido", "anon",
    "anonimo", "anonymous", "trad", "tradicional", "traditional", "various",
    "attrib", "attributed", "sg", "s d", "o", "-", "?",
}
_QTY = re.compile(r"\s*\(\s*\d+\s*\)\s*$")


def compact(name: str) -> str:
    """Nombre normalizado sin espacios ('w a mozart' -> 'wamozart')."""
    return normalize_composer_name(name).replace(" ", "")


def clean_raw(raw: str) -> str:
    text = unicodedata.normalize("NFKC", raw or "").strip()
    text = _QTY.sub("", text)
    return re.sub(r"\s+", " ", text).strip()


async def run(db_name: str, roles: list[str], dry_run: bool) -> None:
    base = Settings()  # type: ignore[call-arg]
    db = Database(base.model_copy(update={"db_name": db_name}))
    await db.connect()

    by_norm: dict[str, set[str]] = defaultdict(set)
    by_compact: dict[str, set[str]] = defaultdict(set)
    work_count: dict[str, int] = {}

    async with db.connection() as conn, conn.cursor() as cur:
        await cur.execute("SELECT persons_id, persons_name FROM persons")
        for r in await cur.fetchall():
            by_norm[normalize_composer_name(r["persons_name"])].add(r["persons_id"])
            by_compact[compact(r["persons_name"])].add(r["persons_id"])
        await cur.execute(
            "SELECT person_id, person_aliases_normalized_alias, person_aliases_alias "
            "FROM persons_aliases"
        )
        for r in await cur.fetchall():
            by_norm[str(r["person_aliases_normalized_alias"])].add(r["person_id"])
            by_compact[compact(r["person_aliases_alias"])].add(r["person_id"])
        await cur.execute(
            "SELECT works_person_roles_person_id AS pid, COUNT(*) AS n "
            "FROM works_person_roles WHERE works_person_roles_role_id = 1 "
            "GROUP BY works_person_roles_person_id"
        )
        work_count = {str(r["pid"]): int(r["n"]) for r in await cur.fetchall()}

        roles_ph = ", ".join(["%s"] * len(roles))
        await cur.execute(
            f"SELECT id, works_id, works_person_import_name AS name, "
            f"works_person_import_role AS role FROM works_person_import "
            f"WHERE works_person_import_resolved = 0 "
            f"AND works_person_import_role IN ({roles_ph})",
            roles,
        )
        rows = await cur.fetchall()

    matches: list[tuple[int, str, int]] = []  # (works_id, person_id, role_id)
    resolved_ids: list[int] = []
    unmatched: dict[str, int] = {}
    ambiguous: dict[str, int] = {}
    stats = {"rows": len(rows), "casadas": 0, "ambiguas": 0, "sin_match": 0, "ruido": 0}
    cache: dict[str, str | None] = {}

    for r in rows:
        raw = clean_raw(str(r["name"]))
        role = str(r["role"])
        role_id = ROLE_IDS.get(role)
        if role_id is None:
            continue
        key = normalize_composer_name(raw)
        if key in _NOISE or not key:
            stats["ruido"] += 1
            continue
        if key not in cache:
            candidates = by_norm.get(key) or by_compact.get(compact(raw)) or set()
            if len(candidates) == 1:
                cache[key] = next(iter(candidates))
            elif not candidates:
                cache[key] = None
            else:
                # Desempate: la persona con más obras atribuidas (rol compositor).
                ranked = sorted(candidates, key=lambda p: (-work_count.get(p, 0), p))
                if work_count.get(ranked[0], 0) > work_count.get(ranked[1], 0):
                    cache[key] = ranked[0]
                else:
                    cache[key] = "__ambiguous__"
        pid = cache[key]
        if pid == "__ambiguous__":
            ambiguous[raw] = ambiguous.get(raw, 0) + 1
            stats["ambiguas"] += 1
        elif pid:
            matches.append((int(r["works_id"]), pid, role_id))
            resolved_ids.append(int(r["id"]))
            stats["casadas"] += 1
        else:
            unmatched[raw] = unmatched.get(raw, 0) + 1
            stats["sin_match"] += 1

    print(stats)
    if ambiguous:
        print(f"ambiguas (distintas): {len(ambiguous)}; top:")
        for k, v in sorted(ambiguous.items(), key=lambda x: -x[1])[:10]:
            print(f"  {v:>6}  {k}")
    if unmatched:
        print(f"sin coincidencia (distintas): {len(unmatched)}; top:")
        for k, v in sorted(unmatched.items(), key=lambda x: -x[1])[:20]:
            print(f"  {v:>6}  {k}")

    if dry_run:
        await db.close()
        return

    async with db.transaction() as conn, conn.cursor() as cur:
        if matches:
            await cur.executemany(
                "INSERT IGNORE INTO works_person_roles "
                "(works_person_roles_work_id, works_person_roles_person_id, "
                " works_person_roles_role_id) VALUES (%s, %s, %s)",
                matches,
            )
        # Marca como resueltas las filas casadas (por lotes).
        for i in range(0, len(resolved_ids), 1000):
            chunk = resolved_ids[i : i + 1000]
            ph = ", ".join(["%s"] * len(chunk))
            await cur.execute(
                f"UPDATE works_person_import SET works_person_import_resolved = 1 "
                f"WHERE id IN ({ph})",
                chunk,
            )
    await db.close()
    print(f"enlazadas: {len(matches)} relaciones; {len(resolved_ids)} filas marcadas")


def main() -> None:
    with contextlib.suppress(AttributeError, ValueError):
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--db", default="osap-storage")
    ap.add_argument("--roles", default="composer", help="composer,artist (coma-separados)")
    ap.add_argument("--dry-run", action="store_true")
    args = ap.parse_args()
    roles = [r.strip() for r in args.roles.split(",") if r.strip()]
    asyncio.run(run(args.db, roles, args.dry_run))


if __name__ == "__main__":
    main()
