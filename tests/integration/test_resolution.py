"""Resolutor de agrupación contra la BBDD nuevo modelo (solo lectura).

Se saltan salvo que se active `OSAP_TEST_DB=1` (usa la copia `osap-storage_test`).
"""

from __future__ import annotations

import os

import pytest
from application.use_cases.resolution import ResolveWorkGrouping
from domain.exceptions import EntityNotFound
from infrastructure.config import Settings
from infrastructure.db.connection import Database
from infrastructure.repositories.sql_resolution_source import SqlResolutionSource

pytestmark = pytest.mark.skipif(
    os.environ.get("OSAP_TEST_DB") != "1",
    reason="integración: requiere BBDD (define OSAP_TEST_DB=1)",
)

TEST_DB = os.environ.get("OSAP_TEST_DB_NAME", "osap-storage_test")


@pytest.fixture()
async def db():
    base = Settings()  # type: ignore[call-arg]
    database = Database(base.model_copy(update={"db_name": TEST_DB}))
    await database.connect()
    try:
        yield database
    finally:
        await database.close()


async def _scalar(db: Database, sql: str, params: tuple | None = None) -> object | None:
    async with db.connection() as conn, conn.cursor() as cur:
        if params is None:
            await cur.execute(sql)
        else:
            await cur.execute(sql, params)
        row = await cur.fetchone()
    return next(iter(row.values())) if row else None


async def test_load_pdmx_evidence(db: Database) -> None:
    wid = await _scalar(
        db,
        "SELECT works_resources_work_id FROM works_resources "
        "WHERE works_resources_file_id IS NOT NULL LIMIT 1",
    )
    assert wid is not None
    evidences = await SqlResolutionSource(db).load(int(wid))
    assert evidences
    seed = [e for e in evidences if e.work_id == int(wid)]
    assert seed
    assert all(e.origin.lower() == "pdmx" for e in seed)
    assert all(e.resource_type for e in seed)


async def test_load_cpdl_multi_edition_keeps_work_axes(db: Database) -> None:
    wid = await _scalar(
        db,
        "SELECT representations_works_id FROM representations "
        "WHERE representations_origin='cpdl' GROUP BY representations_works_id "
        "HAVING COUNT(*) > 1 ORDER BY COUNT(*) DESC LIMIT 1",
    )
    assert wid is not None
    evidences = await SqlResolutionSource(db).load(int(wid))
    seed = [e for e in evidences if e.work_id == int(wid)]
    assert len(seed) > 1
    assert all(e.origin == "cpdl" for e in seed)
    # los ejes son de la obra (página CPDL): idénticos entre ediciones
    assert len({repr(e.axes.as_dict()) for e in seed}) == 1


async def test_resolve_work_grouping_returns_groups_and_rules(db: Database) -> None:
    wid = await _scalar(
        db,
        "SELECT representations_works_id FROM representations "
        "WHERE representations_origin='cpdl' GROUP BY representations_works_id "
        "HAVING COUNT(*) > 1 ORDER BY COUNT(*) DESC LIMIT 1",
    )
    assert wid is not None
    result = await ResolveWorkGrouping(SqlResolutionSource(db)).execute(int(wid))
    assert result.groups
    assert any(r.rule == "origin_identity" for r in result.applied)
    grouped = next(g for g in result.groups if int(wid) in g.work_ids)
    assert grouped.resource_ids
    # las 46 ediciones comparten los ejes de la página => una sola representación agrupada
    assert len(grouped.representations) == 1
    assert len(grouped.representations[0].source_keys) > 1


async def test_resolve_missing_work_raises(db: Database) -> None:
    with pytest.raises(EntityNotFound):
        await ResolveWorkGrouping(SqlResolutionSource(db)).execute(0)
