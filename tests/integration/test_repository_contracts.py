"""Contratos de repositorios contra el esquema NUEVO (BBDD real).

Complementa a `test_sql_repositories.py`: allí se comprueba que la BBDD tiene la forma
esperada; aquí que cada repositorio **lee y escribe** en el modelo nuevo
(`persons`, `persons_identity`, `persons_aliases`, `persons_evidence`,
`works_person_roles`, `work_genres`, `work_instruments`, `cpdl_editions`…).

Algunas pruebas escriben, así que se ejecutan contra una **copia** (`osap-storage_test`),
nunca contra la principal. Se saltan salvo que se active explícitamente:

    $env:OSAP_TEST_DB = "1"; .venv\\Scripts\\python.exe -m pytest tests/integration -q

Variables opcionales: `OSAP_TEST_DB_NAME` (por defecto `osap-storage_test`).
"""

from __future__ import annotations

import os
import uuid

import pytest
from infrastructure.config import Settings
from infrastructure.db.connection import Database
from infrastructure.repositories.sql_catalogue_repository import SqlCatalogueRepository
from infrastructure.repositories.sql_person_repository import SqlPersonRepository
from infrastructure.repositories.sql_representation_repository import SqlRepresentationRepository
from infrastructure.repositories.sql_table_crud_repository import TABLES, SqlTableCrudRepository
from infrastructure.repositories.sql_voting_repository import SqlVotingRepository
from infrastructure.repositories.sql_work_repository import SqlWorkRepository

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


async def _exec(db: Database, sql: str, params: tuple | None = None) -> None:
    async with db.connection() as conn, conn.cursor() as cur:
        if params is None:
            await cur.execute(sql)
        else:
            await cur.execute(sql, params)


# ---------------------------------------------------------------- works


async def test_work_key_roundtrip(db: Database) -> None:
    repo = SqlWorkRepository(db)
    works = await repo.list_all(limit=10)
    assert works
    checked = 0
    for work in works:
        if work.id and work.work_key:
            again = await repo.get_by_work_key(work.work_key)
            assert again is not None
            assert again.id == work.id
            checked += 1
    assert checked >= 1


async def test_work_lists_come_from_new_tables(db: Database) -> None:
    wid = await _scalar(
        db,
        "SELECT w.id FROM works w "
        "WHERE EXISTS (SELECT 1 FROM work_genres g WHERE g.works_id = w.id) "
        "AND EXISTS (SELECT 1 FROM work_instruments i WHERE i.works_id = w.id) LIMIT 1",
    )
    assert wid is not None
    repo = SqlWorkRepository(db)
    genres = await repo.get_genres(int(wid))  # type: ignore[arg-type]
    instruments = await repo.get_instruments(int(wid))  # type: ignore[arg-type]
    assert genres and instruments

    lists = await repo.get_lists_bulk([int(wid)])  # type: ignore[arg-type]
    assert lists[int(wid)].genres == genres  # type: ignore[arg-type]
    assert set(lists[int(wid)].instruments) == set(instruments)  # type: ignore[arg-type]


async def test_replace_genres_and_instruments_roundtrip(db: Database) -> None:
    wid = await _scalar(db, "SELECT works_id FROM work_genres LIMIT 1")
    assert wid is not None
    repo = SqlWorkRepository(db)
    work_id = int(wid)  # type: ignore[arg-type]
    before_g = await repo.get_genres(work_id)
    before_i = await repo.get_instruments(work_id)
    assert before_g
    try:
        await repo.replace_genres(work_id, ["Música Clásica / Docta"])
        await repo.replace_instruments(work_id, ["Violin"])
        assert await repo.get_genres(work_id) == ["Música Clásica / Docta"]
        assert await repo.get_instruments(work_id) == ["Violin"]
    finally:
        await repo.replace_genres(work_id, before_g)
        await repo.replace_instruments(work_id, before_i)
    assert await repo.get_genres(work_id) == before_g


async def test_list_by_composer_matches_role_1(db: Database) -> None:
    pid = await _scalar(
        db,
        "SELECT works_person_roles_person_id FROM works_person_roles "
        "WHERE works_person_roles_role_id = 1 LIMIT 1",
    )
    assert pid is not None
    repo = SqlWorkRepository(db)
    works = await repo.list_by_composer(str(pid), limit=20, offset=0)
    assert works
    assert all(w.person_id == str(pid) for w in works)


async def test_search_finds_known_title(db: Database) -> None:
    wid = await _scalar(db, "SELECT id FROM works WHERE works_title LIKE '%Handel%' LIMIT 1")
    assert wid is not None
    repo = SqlWorkRepository(db)
    results = await repo.search("Handel", limit=50)
    assert any(w.id == int(wid) for w in results)  # type: ignore[arg-type]


# ---------------------------------------------------------------- persons / composer


async def test_summaries_are_only_people_with_works(db: Database) -> None:
    repo = SqlPersonRepository(db)
    rows = await repo.list_summaries(limit=20, offset=0)
    assert rows
    assert all(s.works_count >= 1 for s in rows)


async def test_detail_reads_identity_aliases_and_evidence(db: Database) -> None:
    pid = await _scalar(
        db,
        "SELECT p.persons_id FROM persons p "
        "WHERE EXISTS (SELECT 1 FROM persons_identity i "
        "              WHERE i.persons_id = p.persons_id AND i.identity_type <> '') "
        "AND EXISTS (SELECT 1 FROM persons_aliases a WHERE a.person_id = p.persons_id) "
        "LIMIT 1",
    )
    assert pid is not None
    repo = SqlPersonRepository(db)
    person_id = str(pid)

    detail = await repo.get_detail(person_id)
    assert detail is not None and detail.id == person_id

    idents = await repo.list_identifiers(person_id)
    aliases = await repo.list_aliases(person_id)
    assert idents and aliases
    assert {(i.id_type, i.id_value) for i in detail.identifiers} >= {
        (i.id_type, i.id_value) for i in idents
    }
    assert set(detail.aliases) >= {a.alias for a in aliases}


async def test_add_alias_resolve_and_cleanup(db: Database) -> None:
    pid = await _scalar(
        db, "SELECT works_person_roles_person_id FROM works_person_roles WHERE works_person_roles_role_id = 1 LIMIT 1"
    )
    assert pid is not None
    repo = SqlPersonRepository(db)
    norm = f"zztest{uuid.uuid4().hex}"
    alias = await repo.add_alias(str(pid), "ZZ Test Alias", norm)
    try:
        assert alias.id is not None
        resolved = await repo.resolve_by_normalized(norm)
        assert resolved is not None and resolved[0] == str(pid)
        assert any(a.normalized_alias == norm for a in await repo.list_aliases(str(pid)))
    finally:
        await _exec(db, "DELETE FROM persons_aliases WHERE id = %s", (alias.id,))


async def test_find_by_identifier(db: Database) -> None:
    async with db.connection() as conn, conn.cursor() as cur:
        await cur.execute(
            "SELECT identity_type AS t, identity_value AS v, persons_id AS pid "
            "FROM persons_identity WHERE persons_id IS NOT NULL "
            "AND identity_type <> '' AND identity_value <> '' LIMIT 1"
        )
        row = await cur.fetchone()
    assert row is not None
    repo = SqlPersonRepository(db)
    found = await repo.find_by_identifier(str(row["t"]), str(row["v"]))
    assert any(c.id == str(row["pid"]) for c in found)


async def test_add_identifier_and_cleanup(db: Database) -> None:
    pid = await _scalar(db, "SELECT persons_id FROM persons LIMIT 1")
    assert pid is not None
    person_id = str(pid)
    value = uuid.uuid4().hex
    repo = SqlPersonRepository(db)
    await repo.add_identifier(person_id, "isni", value, source="test")
    try:
        assert any(
            i.id_type == "isni" and i.id_value == value
            for i in await repo.list_identifiers(person_id)
        )
    finally:
        await _exec(
            db,
            "DELETE FROM persons_identity WHERE persons_id = %s "
            "AND identity_type = 'isni' AND identity_value = %s",
            (person_id, value),
        )


async def test_add_evidence_and_cleanup(db: Database) -> None:
    pid = await _scalar(db, "SELECT persons_id FROM persons LIMIT 1")
    assert pid is not None
    person_id = str(pid)
    rule = f"zz-test-{uuid.uuid4().hex[:8]}"
    repo = SqlPersonRepository(db)
    await repo.add_evidence(person_id, rule=rule, decision="test", reason="contract")
    try:
        assert any(e.rule == rule for e in await repo.list_evidence(person_id))
    finally:
        await _exec(db, "DELETE FROM persons_evidence WHERE persons_evidence_rule = %s", (rule,))


# ---------------------------------------------------------------- voting


async def test_vote_flow_updates_work_statistics(db: Database) -> None:
    wid = await _scalar(db, "SELECT id FROM works LIMIT 1")
    assert wid is not None
    repo = SqlVotingRepository(db)
    user = f"zz-{uuid.uuid4().hex}"
    try:
        vote = await repo.add_vote(user, int(wid), 5)  # type: ignore[arg-type]
        assert vote.id is not None
        await repo.recompute_all()
        stats = await repo.get_work_statistics(int(wid))  # type: ignore[arg-type]
        assert stats is not None and stats.vote_count >= 1
    finally:
        await _exec(db, "DELETE FROM votes WHERE user_id = %s", (user,))
        await repo.recompute_all()


# ---------------------------------------------------------------- catalogue


async def test_catalogue_prefix_lookup(db: Database) -> None:
    repo = SqlCatalogueRepository(db)
    rows = await repo.list_all(limit=5, offset=0)
    assert rows and rows[0].prefix
    prefix = rows[0].prefix
    by_prefix = await repo.get_by_prefix(prefix)
    assert by_prefix and all(c.prefix == prefix for c in by_prefix)


# ---------------------------------------------------------------- table CRUD


async def test_whitelist_covers_cpdl_editions(db: Database) -> None:
    crud = SqlTableCrudRepository(db)
    assert {"cpdl_editions", "cpdl_edition_files", "cpdl_edition_persons"} <= set(TABLES)
    assert set(await crud.list_tables()) == set(TABLES)


async def test_relations_report_new_fks(db: Database) -> None:
    crud = SqlTableCrudRepository(db)
    rel = await crud.relations("cpdl_editions")
    assert any(r["ref_table"] == "works" for r in rel)

    # Las uniones N:N no están en la whitelist del CRUD genérico: se comprueban por SQL.
    async with db.connection() as conn, conn.cursor() as cur:
        await cur.execute(
            "SELECT referenced_table_name AS t FROM information_schema.key_column_usage "
            "WHERE table_schema = DATABASE() AND table_name = 'work_instruments' "
            "AND referenced_table_name IS NOT NULL"
        )
        refs = {r["t"] for r in await cur.fetchall()}
    assert refs >= {"works", "instruments"}


async def test_schema_exposes_new_columns(db: Database) -> None:
    crud = SqlTableCrudRepository(db)
    works_cols = {c["name"] for c in await crud.schema("works")}
    assert {"id", "works_key", "works_origin", "works_origin_id"} <= works_cols
    persons_cols = {c["name"] for c in await crud.schema("persons")}
    assert {"persons_id", "persons_name"} <= persons_cols


async def test_read_one_returns_row(db: Database) -> None:
    crud = SqlTableCrudRepository(db)
    wid = await _scalar(db, "SELECT id FROM works LIMIT 1")
    assert wid is not None
    row = await crud.read_one("works", int(wid))  # type: ignore[arg-type]
    assert row is not None and int(row["id"]) == int(wid)  # type: ignore[arg-type]


# ------------------------------------------------- representations/resources


async def test_representation_repository_reads_new_model(db: Database) -> None:
    repo = SqlRepresentationRepository(db)

    cpdl_wid = await _scalar(
        db,
        "SELECT representations_works_id FROM representations "
        "WHERE representations_origin='cpdl' LIMIT 1",
    )
    assert cpdl_wid is not None
    reps = await repo.list_by_work(int(cpdl_wid))
    assert reps and all(r.works_id == int(cpdl_wid) for r in reps)
    rep_ids = [r.id for r in reps if r.id is not None]
    resources = await repo.list_resources_by_representation_ids(rep_ids)
    assert all(x.representation_id in rep_ids for x in resources)

    bulk = await repo.list_by_work_ids([int(cpdl_wid)])
    assert {r.id for r in bulk} == set(rep_ids)

    resource_id = await _scalar(
        db, "SELECT id FROM works_resources WHERE works_resources_file_id IS NOT NULL LIMIT 1"
    )
    assert resource_id is not None
    resource = await repo.get_resource(int(resource_id))
    assert resource is not None and resource.file_id is not None
    by_file = await repo.get_resource_by_file_id(resource.file_id)
    assert by_file is not None and by_file.id == resource.id
