"""Tests de S3: restricciones del CRUD administrativo genérico (osap-storage).

Campos sensibles no escribibles y borrado bloqueado cuando hay dependencias ON DELETE
CASCADE. Se ejercita el repositorio SQL con un cursor falso (sin BD real).
"""

from __future__ import annotations

import asyncio

import pytest
from domain.exceptions import InvalidTableCrud
from infrastructure.repositories.sql_table_crud_repository import (
    NON_WRITABLE_COLUMNS,
    SqlTableCrudRepository,
)


class _Cursor:
    def __init__(self, row: dict | None) -> None:
        self._row = row
        self.executed: list[tuple[str, object]] = []
        self.rowcount = 0

    async def __aenter__(self) -> _Cursor:
        return self

    async def __aexit__(self, *_: object) -> bool:
        return False

    async def execute(self, sql: str, params: object = None) -> None:
        self.executed.append((sql, params))

    async def fetchone(self) -> dict | None:
        return self._row


class _Conn:
    def __init__(self, cursor: _Cursor) -> None:
        self._cursor = cursor

    async def __aenter__(self) -> _Conn:
        return self

    async def __aexit__(self, *_: object) -> bool:
        return False

    def cursor(self) -> _Cursor:
        return self._cursor


class _Db:
    def __init__(self, cursor: _Cursor) -> None:
        self._cursor = cursor

    def connection(self) -> _Conn:
        return _Conn(self._cursor)


def _repo(cascade: int = 0, columns: list[str] | None = None) -> tuple[SqlTableCrudRepository, _Cursor]:
    cursor = _Cursor({"n": cascade})
    repo = SqlTableCrudRepository(_Db(cursor))  # type: ignore[arg-type]
    if columns is not None:

        async def _cols(_table: str) -> list[str]:
            return list(columns)

        repo.columns = _cols  # type: ignore[method-assign]
    return repo, cursor


def test_columnas_sensibles_no_son_escribibles() -> None:
    repo, _ = _repo(columns=["id", "name", "persons_visible", "persons_status", "created_at", "updated_at"])
    valid = asyncio.run(
        repo._valid_columns(
            "persons",
            {
                "name": "Mozart",
                "persons_visible": 1,
                "persons_status": "active",
                "created_at": "2020-01-01",
                "updated_at": "2020-01-01",
                "id": 5,
            },
        )
    )
    assert valid == ["name", "id"]


def test_columnas_desconocidas_se_siguen_filtrando() -> None:
    repo, _ = _repo(columns=["id", "name"])
    valid = asyncio.run(repo._valid_columns("persons", {"name": "x", "bogus": 1}))
    assert valid == ["name"]


def test_conjunto_de_columnas_protegidas_cubre_lo_sensible() -> None:
    assert {"persons_visible", "persons_status", "persons_merged_into", "created_at", "updated_at", "sha256"} <= set(
        NON_WRITABLE_COLUMNS
    )


def test_borrado_bloqueado_si_hay_cascada() -> None:
    repo, cursor = _repo(cascade=1)
    with pytest.raises(InvalidTableCrud):
        asyncio.run(repo.delete("persons", 1))
    assert not any(sql.startswith("DELETE") for sql, _ in cursor.executed)


def test_borrado_permitido_sin_cascada() -> None:
    repo, cursor = _repo(cascade=0)
    deleted = asyncio.run(repo.delete("votes", 7))
    assert deleted == 0
    assert any(sql.startswith("DELETE") for sql, _ in cursor.executed)
