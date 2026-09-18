"""Registra los compositores de CPDL en el catálogo de autoridad y completa sus enlaces.

Los nombres de compositor de CPDL son **fiables**: se normalizan y se incorporan al
catálogo de autoridad (`persons_identity`, `identity_source='cpdl'`),
enlazando el candidato con la persona correspondiente. Si un nombre no tuviera persona
(las obras CPDL sin enlace), se crea y se enlazan sus obras en `works_person_roles` (rol 1).

Uso:
    .venv\\Scripts\\python.exe scripts/incorporate_cpdl_composers.py --dry-run
    .venv\\Scripts\\python.exe scripts/incorporate_cpdl_composers.py
"""

from __future__ import annotations

import argparse
import asyncio
import contextlib
import sys
import uuid
from collections import defaultdict
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from domain.services.composer_names import normalize_composer_name  # noqa: E402
from infrastructure.config import Settings  # noqa: E402
from infrastructure.db.connection import Database  # noqa: E402

sys.path.insert(0, str(ROOT / "scripts"))
from link_works_person_import import clean_raw, compact, composer_key  # noqa: E402

ROLE_COMPOSER = 1
SOURCE_SYSTEM = "cpdl"
_NOISE = {
    "", "na", "n a", "nan", "null", "none", "unknown", "desconocido", "anon", "anonimo",
    "anonymous", "trad", "tradicional", "traditional", "various", "attrib", "attributed",
}


async def run(db_name: str, dry_run: bool) -> None:
    base = Settings()  # type: ignore[call-arg]
    db = Database(base.model_copy(update={"db_name": db_name}))
    await db.connect()

    by_norm: dict[str, set[str]] = defaultdict(set)
    by_compact: dict[str, set[str]] = defaultdict(set)
    auth_person: dict[str, str | None] = {}

    async with db.connection() as conn, conn.cursor() as cur:
        await cur.execute("SELECT persons_id, persons_name FROM persons")
        for r in await cur.fetchall():
            by_norm[normalize_composer_name(r["persons_name"])].add(r["persons_id"])
            by_compact[compact(r["persons_name"])].add(r["persons_id"])
        await cur.execute("SELECT person_id, person_aliases_normalized_alias FROM persons_aliases")
        for r in await cur.fetchall():
            by_norm[str(r["person_aliases_normalized_alias"])].add(r["person_id"])
        # Candidatos/personas de autoridad en `persons_identity` (clave = identity_name_norm).
        await cur.execute(
            "SELECT identity_name_norm AS k, persons_id FROM persons_identity "
            "WHERE identity_type = ''"
        )
        for r in await cur.fetchall():
            k = str(r["k"] or "")
            if k:
                auth_person.setdefault(k, r["persons_id"])

        # Nombres CPDL distintos y la persona ya enlazada (si existe).
        await cur.execute(
            "SELECT i.works_person_import_name AS name, COUNT(DISTINCT i.works_id) AS obras, "
            " (SELECT r.works_person_roles_person_id FROM works_person_import i2 "
            "  JOIN works_person_roles r ON r.works_person_roles_work_id = i2.works_id "
            "   AND r.works_person_roles_role_id = 1 "
            "  WHERE i2.works_person_import_source = 'cpdl' "
            "   AND i2.works_person_import_name = i.works_person_import_name LIMIT 1) AS pid "
            "FROM works_person_import i "
            "WHERE i.works_person_import_source = 'cpdl' AND i.works_person_import_role = 'composer' "
            "GROUP BY i.works_person_import_name ORDER BY obras DESC"
        )
        rows = await cur.fetchall()

    # Obras CPDL sin relación, por nombre (para enlazarlas si creamos persona).
    pend_works: dict[str, list[int]] = defaultdict(list)
    async with db.connection() as conn, conn.cursor() as cur:
        await cur.execute(
            "SELECT i.works_person_import_name AS name, i.works_id FROM works_person_import i "
            "LEFT JOIN works_person_roles r ON r.works_person_roles_work_id = i.works_id "
            " AND r.works_person_roles_role_id = 1 "
            "WHERE i.works_person_import_source = 'cpdl' AND i.works_person_import_role = 'composer' "
            "AND r.works_person_roles_id IS NULL"
        )
        for r in await cur.fetchall():
            pend_works[str(r["name"])].append(int(r["works_id"]))

    new_persons: list[tuple[str, str]] = []
    new_auth: list[tuple[str, str, str]] = []   # (pid, nombre, normalizado)
    link_auth: list[tuple[str, str]] = []
    links: list[tuple[int, str, int]] = []
    cache: dict[str, str] = {}
    stats = {"nombres": len(rows), "con_persona": 0, "personas_nuevas": 0,
             "autoridades_nuevas": 0, "autoridades_ya_existentes": 0, "ruido": 0,
             "obras_enlazadas": 0}

    for r in rows:
        raw = clean_raw(str(r["name"]))
        key = normalize_composer_name(raw)
        if not key or key in _NOISE or len(key.replace(" ", "")) < 4:
            stats["ruido"] += 1
            continue
        ckey = composer_key(raw)
        pid = r["pid"] or cache.get(key)
        if not pid:
            pids = by_norm.get(key) or by_compact.get(compact(raw))
            if pids:
                pid = sorted(pids)[0]
            elif ckey in auth_person:
                pid = auth_person.get(ckey)
        if pid:
            stats["con_persona"] += 1
        else:
            pid = str(uuid.uuid4())
            new_persons.append((pid, raw))
            stats["personas_nuevas"] += 1
        cache[key] = str(pid)
        by_norm.setdefault(key, set()).add(str(pid))

        if ckey in auth_person:
            if auth_person.get(ckey) is None:
                link_auth.append((ckey, str(pid)))
            stats["autoridades_ya_existentes"] += 1
        else:
            new_auth.append((str(pid), raw, ckey))
            stats["autoridades_nuevas"] += 1

        for wid in pend_works.get(str(r["name"]), []):
            links.append((wid, str(pid), ROLE_COMPOSER))
            stats["obras_enlazadas"] += 1

    print(stats)

    if dry_run:
        for _pid, name in new_persons[:10]:
            print("   nueva persona:", name)
        await db.close()
        return

    async with db.transaction() as conn, conn.cursor() as cur:
        for pid, name in new_persons:
            await cur.execute(
                "INSERT IGNORE INTO persons (persons_id, persons_name, persons_visible, "
                "persons_status, persons_source_system) VALUES (%s, %s, 1, 'active', %s)",
                (pid, name[:255], SOURCE_SYSTEM),
            )
            await cur.execute(
                "INSERT IGNORE INTO persons_aliases (person_id, person_aliases_alias, "
                "person_aliases_normalized_alias) VALUES (%s, %s, %s)",
                (pid, name[:255], normalize_composer_name(name)[:255]),
            )
        for pid, name, key in new_auth:
            await cur.execute(
                "INSERT INTO persons_identity "
                "(persons_id, identity_name, identity_name_norm, identity_type, "
                " identity_value, identity_source, identity_is_anchor) "
                "VALUES (%s, %s, %s, '', '', 'cpdl', 1)",
                (pid, name[:255], key[:128]),
            )
        for key, pid in link_auth:
            await cur.execute(
                "UPDATE persons_identity SET persons_id = %s "
                "WHERE identity_name_norm = %s AND persons_id IS NULL",
                (pid, key),
            )
        if links:
            await cur.executemany(
                "INSERT IGNORE INTO works_person_roles (works_person_roles_work_id, "
                "works_person_roles_person_id, works_person_roles_role_id) VALUES (%s,%s,%s)",
                links,
            )
    await db.close()
    print(f"personas: {len(new_persons)} | autoridades: {len(new_auth)} | "
          f"obras enlazadas: {len(links)}")


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
