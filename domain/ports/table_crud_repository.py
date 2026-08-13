from __future__ import annotations

from typing import Protocol


class TableCrudRepository(Protocol):
    """CRUD genérico y seguro sobre tablas de osap-storage (para osap-api).

    La tabla y las columnas se validan contra un whitelist / information_schema;
    todos los valores van parametrizados (sin inyección SQL).
    """

    async def list_tables(self) -> list[str]: ...

    async def columns(self, table: str) -> list[str]:
        """Columnas reales de la tabla (para validar la entrada)."""

    async def pk_column(self, table: str) -> str:
        """Columna clave primaria de la tabla."""

    async def read(self, table: str, *, limit: int, offset: int) -> list[dict]:
        """Lee filas (paginado)."""

    async def read_one(self, table: str, pk_value: object) -> dict | None: ...

    async def create(self, table: str, data: dict) -> dict:
        """Inserta una fila y la devuelve."""

    async def update(self, table: str, pk_value: object, data: dict) -> dict | None:
        """Actualiza por clave primaria y devuelve la fila, o None si no existe."""

    async def delete(self, table: str, pk_value: object) -> int:
        """Borra por clave primaria. Devuelve nº de filas borradas."""
