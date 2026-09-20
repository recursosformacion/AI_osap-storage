"""Migración paralela al modelo Work -> Representation -> Resource.

Rellena `representations` + `resources` (+ `representation_persons`) desde el esquema actual,
SIN tocar `archive_entries` ni `cpdl_*` (transición aditiva; ver
`docsNew/diseño-representaciones-recursos.md` §9).

- PDMX: 1 representación por obra (`origin='pdmx'`, `origin_id=works_key`, `type='score'`,
  `source_name=archive_entries.logical_id`, `license=works_license`) y su recurso MXL.
- CPDL: 1 representación por edición (`origin='cpdl'`, `origin_id=page_id:cpdlno`, `type='edition'`),
  sus recursos (inventario, sin fichero/URL todavía) y sus editores (rol 6).

Idempotente: borra las representaciones de estos orígenes (cascada) y las recrea.

Uso:
    .venv\\Scripts\\python.exe scripts/migrate_to_representations.py --dry-run
    .venv\\Scripts\\python.exe scripts/migrate_to_representations.py            # osap-storage
    .venv\\Scripts\\python.exe scripts/migrate_to_representations.py --db osap-storage_test
"""

from __future__ import annotations

import argparse
import asyncio
import contextlib
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from infrastructure.config import Settings  # noqa: E402
from infrastructure.db.connection import Database  # noqa: E402

PDMX_REPRESENTATIONS = """
INSERT INTO representations (representations_works_id, representations_origin,
  representations_origin_id, representations_origin_cpdlno, representations_type,
  representations_source_name, representations_license)
SELECT ae.work_id, 'pdmx', w.works_key, NULL, 'score', ae.logical_id, w.works_license
FROM archive_entries ae JOIN works w ON w.id = ae.work_id
"""

PDMX_RESOURCES = """
INSERT INTO works_resources (works_resources_representation_id, works_resources_type,
  works_resources_name, works_resources_relative_path, works_resources_status,
  works_resources_file_id, works_resources_url, works_resources_archive_id)
SELECT r.id, COALESCE(w.works_type_file, 'MXL'),
  COALESCE(f.name, SUBSTRING_INDEX(ae.relative_path, '/', -1)),
  ae.relative_path,
  CASE WHEN ae.file_id IS NOT NULL THEN 'stored' ELSE ae.status END,
  ae.file_id, NULL, ae.archive_id
FROM archive_entries ae
JOIN works w ON w.id = ae.work_id
JOIN representations r ON r.representations_works_id = w.id
  AND r.representations_origin = 'pdmx'
  AND r.representations_origin_id = w.works_key COLLATE utf8mb4_unicode_ci
LEFT JOIN files f ON f.id = ae.file_id
"""

CPDL_REPRESENTATIONS = """
INSERT INTO representations (representations_works_id, representations_origin,
  representations_origin_id, representations_origin_cpdlno, representations_type,
  representations_source_name, representations_license)
SELECT e.works_id, 'cpdl', CONCAT(w.works_origin_id, ':', e.cpdl_editions_cpdlno),
  e.cpdl_editions_cpdlno, 'edition', NULL, e.cpdl_editions_license
FROM cpdl_editions e JOIN works w ON w.id = e.works_id
"""

CPDL_RESOURCES = """
INSERT INTO works_resources (works_resources_representation_id, works_resources_type,
  works_resources_name, works_resources_relative_path, works_resources_status,
  works_resources_file_id, works_resources_url, works_resources_archive_id)
SELECT r.id, f.cpdl_edition_files_type, f.cpdl_edition_files_name, NULL, 'unknown',
  NULL, NULL, NULL
FROM cpdl_edition_files f
JOIN cpdl_editions e ON e.id = f.cpdl_editions_id
JOIN works w ON w.id = e.works_id
JOIN representations r ON r.representations_works_id = w.id
  AND r.representations_origin = 'cpdl'
  AND r.representations_origin_id = CONCAT(w.works_origin_id, ':', e.cpdl_editions_cpdlno) COLLATE utf8mb4_unicode_ci
"""

CPDL_PERSONS = """
INSERT INTO representation_persons (representation_persons_representation_id,
  representation_persons_person_id, representation_persons_role_id, representation_persons_name)
SELECT r.id, p.persons_id, p.roles_id, p.cpdl_edition_persons_name
FROM cpdl_edition_persons p
JOIN cpdl_editions e ON e.id = p.cpdl_editions_id
JOIN works w ON w.id = e.works_id
JOIN representations r ON r.representations_works_id = w.id
  AND r.representations_origin = 'cpdl'
  AND r.representations_origin_id = CONCAT(w.works_origin_id, ':', e.cpdl_editions_cpdlno) COLLATE utf8mb4_unicode_ci
"""

CHECKS = {
    "representations_pdmx": "SELECT COUNT(*) n FROM representations WHERE representations_origin='pdmx'",
    "representations_cpdl": "SELECT COUNT(*) n FROM representations WHERE representations_origin='cpdl'",
    "resources": "SELECT COUNT(*) n FROM works_resources",
    "resources_pdmx": ("SELECT COUNT(*) n FROM works_resources res JOIN representations r "
                       "ON r.id=res.works_resources_representation_id "
                       "WHERE r.representations_origin='pdmx'"),
    "resources_cpdl": ("SELECT COUNT(*) n FROM works_resources res JOIN representations r "
                       "ON r.id=res.works_resources_representation_id "
                       "WHERE r.representations_origin='cpdl'"),
    "representation_persons": "SELECT COUNT(*) n FROM representation_persons",
    "archive_entries_sin_representacion": (
        "SELECT COUNT(*) n FROM archive_entries ae JOIN works w ON w.id=ae.work_id "
        "WHERE NOT EXISTS (SELECT 1 FROM representations r WHERE r.representations_works_id=w.id "
        "AND r.representations_origin='pdmx' "
        "AND r.representations_origin_id=w.works_key COLLATE utf8mb4_unicode_ci)"
    ),
    "works_con_entry_sin_recurso": (
        "SELECT COUNT(*) n FROM works w WHERE EXISTS "
        "(SELECT 1 FROM archive_entries ae WHERE ae.work_id=w.id) AND NOT EXISTS "
        "(SELECT 1 FROM representations r "
        "JOIN works_resources res ON res.works_resources_representation_id=r.id "
        "WHERE r.representations_works_id=w.id AND r.representations_origin='pdmx')"
    ),
}


async def _counts(cur) -> dict[str, int]:
    out: dict[str, int] = {}
    for name, sql in CHECKS.items():
        await cur.execute(sql)
        out[name] = int((await cur.fetchone())["n"])
    return out


async def run(db_name: str, dry_run: bool) -> None:
    base = Settings()  # type: ignore[call-arg]
    db = Database(base.model_copy(update={"db_name": db_name}))
    await db.connect()

    async with db.connection() as conn, conn.cursor() as cur:
        await cur.execute("SELECT COUNT(*) n FROM archive_entries")
        n_entries = int((await cur.fetchone())["n"])
        await cur.execute("SELECT COUNT(*) n FROM cpdl_editions")
        n_editions = int((await cur.fetchone())["n"])
        await cur.execute("SELECT COUNT(*) n FROM cpdl_edition_files")
        n_files = int((await cur.fetchone())["n"])
        await cur.execute("SELECT COUNT(*) n FROM cpdl_edition_persons")
        n_persons = int((await cur.fetchone())["n"])

    print({
        "db": db_name, "archive_entries": n_entries, "cpdl_editions": n_editions,
        "cpdl_edition_files": n_files, "cpdl_edition_persons": n_persons,
        "esperado": {"representations": n_entries + n_editions,
                     "resources": n_entries + n_files,
                     "representation_persons": n_persons},
    })

    if dry_run:
        await db.close()
        return

    async with db.transaction() as conn, conn.cursor() as cur:
        await cur.execute("DELETE FROM representations")  # cascada: resources + persons
        for sql in (PDMX_REPRESENTATIONS, PDMX_RESOURCES,
                    CPDL_REPRESENTATIONS, CPDL_RESOURCES, CPDL_PERSONS):
            await cur.execute(sql)
            print(f"  {sql.splitlines()[0].strip()} -> rowcount={cur.rowcount}")
        checks = await _counts(cur)

    await db.close()
    print("checks:", checks)


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
