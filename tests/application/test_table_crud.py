from __future__ import annotations

import asyncio

import pytest
from application.use_cases.table_crud import TableCrud
from domain.exceptions import InvalidTableCrud
from tests.fakes import InMemoryTableCrudRepository


def _repo():
    repo = InMemoryTableCrudRepository()
    repo.register("composers", ["id", "name", "status", "review_status"], "id")
    repo.seed("composers", [
        {"id": 1, "name": "Wolfgang Amadeus Mozart", "status": "active", "review_status": "not_reviewed"},
        {"id": 2, "name": "J. S. Bach", "status": "active", "review_status": "not_reviewed"},
    ])
    return repo


def test_list_tables():
    repo = _repo()
    tables = asyncio.run(TableCrud(repo).list_tables())
    assert "composers" in tables


def test_read_and_read_one():
    repo = _repo()
    uc = TableCrud(repo)
    rows = asyncio.run(uc.read("composers", limit=10, offset=0))
    assert len(rows) == 2
    row = asyncio.run(uc.read_one("composers", 1))
    assert row["name"] == "Wolfgang Amadeus Mozart"
    assert asyncio.run(uc.read_one("composers", 999)) is None


def test_create_filters_invalid_columns():
    repo = _repo()
    uc = TableCrud(repo)
    row = asyncio.run(uc.create("composers", {"name": "Bach", "status": "active",
                                              "columna_inexistente": "x"}))
    assert row["name"] == "Bach"
    assert "columna_inexistente" not in row
    assert row["id"] == 3


def test_update():
    repo = _repo()
    uc = TableCrud(repo)
    row = asyncio.run(uc.update("composers", 2, {"name": "Johann Sebastian Bach", "bogus": 1}))
    assert row["name"] == "Johann Sebastian Bach"
    assert "bogus" not in row
    assert asyncio.run(uc.update("composers", 999, {"name": "x"})) is None


def test_delete():
    repo = _repo()
    uc = TableCrud(repo)
    assert asyncio.run(uc.delete("composers", 1)) == 1
    assert asyncio.run(uc.read_one("composers", 1)) is None
    assert asyncio.run(uc.delete("composers", 999)) == 0


def test_invalid_table_rejected():
    repo = _repo()
    with pytest.raises(InvalidTableCrud):
        asyncio.run(TableCrud(repo).read_one("tabla_secreta", 1))
