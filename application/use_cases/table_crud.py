from __future__ import annotations

from domain.ports.table_crud_repository import TableCrudRepository


class TableCrud:
    """CRUD genérico sobre tablas de osap-storage (para osap-api)."""

    def __init__(self, repo: TableCrudRepository) -> None:
        self._repo = repo

    async def list_tables(self) -> list[str]:
        return await self._repo.list_tables()

    async def read(self, table: str, *, limit: int, offset: int) -> list[dict]:
        return await self._repo.read(table, limit=limit, offset=offset)

    async def read_one(self, table: str, pk_value: object) -> dict | None:
        return await self._repo.read_one(table, pk_value)

    async def create(self, table: str, data: dict) -> dict:
        return await self._repo.create(table, data)

    async def update(self, table: str, pk_value: object, data: dict) -> dict | None:
        return await self._repo.update(table, pk_value, data)

    async def delete(self, table: str, pk_value: object) -> int:
        return await self._repo.delete(table, pk_value)
