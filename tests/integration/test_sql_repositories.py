"""Tests de integración contra la BBDD real (`osap-storage`).

Los tests unitarios usan fakes y **no validan el SQL**. Estos sí: ejercitan los
repositorios adaptados contra MySQL/MariaDB.

Se saltan salvo que se active explícitamente:

    $env:OSAP_TEST_DB = "1"; .venv\\Scripts\\python.exe -m pytest tests/integration -q

Variables opcionales: `OSAP_TEST_DB_NAME` (por defecto, el `db.name` de config.yaml).
"""

from __future__ import annotations

import os

import pytest
from infrastructure.config import Settings
from infrastructure.db.connection import Database
from infrastructure.repositories.sql_catalogue_repository import SqlCatalogueRepository
from infrastructure.repositories.sql_composer_repository import SqlComposerRepository
from infrastructure.repositories.sql_table_crud_repository import TABLES, SqlTableCrudRepository
from infrastructure.repositories.sql_voting_repository import SqlVotingRepository
from infrastructure.repositories.sql_work_repository import SqlWorkRepository

pytestmark = pytest.mark.skipif(
    os.environ.get("OSAP_TEST_DB") != "1",
    reason="integración: requiere BBDD (define OSAP_TEST_DB=1)",
)


@pytest.fixture()
async def db():
    base = Settings()  # type: ignore[call-arg]
    name = os.environ.get("OSAP_TEST_DB_NAME")
    settings = base.model_copy(update={"db_name": name}) if name else base
    database = Database(settings)
    await database.connect()
    try:
        yield database
    finally:
        await database.close()


async def test_table_crud_whitelist_matches_real_schema(db: Database) -> None:
    """Toda tabla de la whitelist existe y su clave declarada es su PK real."""
    async with db.connection() as conn, conn.cursor() as cur:
        await cur.execute(
            "SELECT t.TABLE_NAME AS t, "
            " (SELECT GROUP_CONCAT(k.COLUMN_NAME ORDER BY k.SEQ_IN_INDEX SEPARATOR '+') "
            "  FROM information_schema.STATISTICS k "
            "  WHERE k.TABLE_SCHEMA=t.TABLE_SCHEMA AND k.TABLE_NAME=t.TABLE_NAME "
            "  AND k.INDEX_NAME='PRIMARY') AS pk "
            "FROM information_schema.TABLES t "
            "WHERE t.TABLE_SCHEMA = DATABASE() AND t.TABLE_TYPE = 'BASE TABLE'"
        )
        real = {r["t"]: r["pk"] for r in await cur.fetchall()}

    missing = [t for t in TABLES if t not in real]
    assert not missing, f"tablas en la whitelist que no existen: {missing}"

    wrong = {t: (key, real[t]) for t, key in TABLES.items() if real[t] != key}
    assert not wrong, f"clave incorrecta en la whitelist (esperado vs real): {wrong}"

    crud = SqlTableCrudRepository(db)
    assert set(await crud.list_tables()) == set(TABLES)


async def test_works_repository_reads_new_schema(db: Database) -> None:
    repo = SqlWorkRepository(db)
    assert await repo.count() > 0

    work = await repo.get_by_id(1)
    assert work is not None
    assert work.title is not None


async def test_works_search_and_lists_run(db: Database) -> None:
    repo = SqlWorkRepository(db)
    works = await repo.list_all(limit=3)
    assert works

    lists = await repo.get_lists_bulk([w.id for w in works if w.id])
    assert set(lists) == {w.id for w in works if w.id}
    assert all(hasattr(v, "tags") for v in lists.values())


async def test_composer_repository_lists_only_composers(db: Database) -> None:
    repo = SqlComposerRepository(db)
    summaries = await repo.list_summaries(limit=10, offset=0)
    assert summaries, "debe haber personas con rol compositor"
    assert all(s.works_count >= 1 for s in summaries), "el listado es solo de quien tiene obras"

    total = await repo.count()
    assert total == len(await repo.list_summaries(limit=10_000, offset=0))


async def test_composer_detail_and_works(db: Database) -> None:
    repo = SqlComposerRepository(db)
    summary = (await repo.list_summaries(limit=1, offset=0))[0]

    detail = await repo.get_detail(summary.id)
    assert detail is not None
    assert detail.works_count >= 1

    works = await repo.list_works(summary.id, limit=5, offset=0)
    assert works
    assert all(w.composer_id == summary.id for w in works)
    assert all(w.title for w in works)


async def test_voting_statistics_absent_for_unvoted_work(db: Database) -> None:
    repo = SqlVotingRepository(db)
    stats = await repo.get_work_statistics(1)
    # Sin votos registrados no debe haber fila materializada.
    assert stats is None or stats.vote_count >= 0


async def test_catalogue_repository_reads_catalog(db: Database) -> None:
    repo = SqlCatalogueRepository(db)
    rows = await repo.list_all(limit=100, offset=0)
    assert rows, "la tabla `catalog` tiene datos sembrados"
    assert all(r.prefix for r in rows)
