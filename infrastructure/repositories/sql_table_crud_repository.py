from __future__ import annotations

from domain.exceptions import EntityNotFound, InvalidTableCrud
from domain.ports.table_crud_repository import TableCrudRepository

from infrastructure.db.connection import Database

# Whitelist de tablas expuestas al CRUD genérico (excluye tablas internas/sistema).
# Valor: columna clave primaria de cada tabla.
TABLES: dict[str, str] = {
    "archives": "id",
    "archive_entries": "id",
    "composers": "id",
    "composer_aliases": "id",
    "composer_biographies": "composer_id",
    "composer_identifiers": "id",
    "composer_evidence": "id",
    "composer_creation_evidence": "id",
    "composer_merge_history": "id",
    "catalogues": "id",
    "download_jobs": "id",
    "files": "id",
    "import_sources": "id",
    "musicbrainz_cache": "id",
    "statistics": "id",
    "statistics_runs": "id",
    "storage_locations": "id",
    "storage_providers": "id",
    "votes": "id",
    "works": "id",
    "work_genres": "id",
    "work_instruments": "id",
    "work_parts": "id",
    "work_statistics": "work_id",
    "work_tags": "id",
}


class SqlTableCrudRepository(TableCrudRepository):
    def __init__(self, db: Database) -> None:
        self._db = db
        self._cols_cache: dict[str, list[str]] = {}

    async def list_tables(self) -> list[str]:
        return sorted(TABLES)

    async def columns(self, table: str) -> list[str]:
        if table in self._cols_cache:
            return self._cols_cache[table]
        async with self._db.connection() as conn, conn.cursor() as cur:
            await cur.execute(
                "SELECT column_name FROM information_schema.columns "
                "WHERE table_schema = DATABASE() AND table_name = %s ORDER BY ordinal_position",
                (table,),
            )
            cols = [r["column_name"] for r in await cur.fetchall()]
        self._cols_cache[table] = cols
        return cols

    async def pk_column(self, table: str) -> str:
        if table not in TABLES:
            raise InvalidTableCrud(f"tabla no permitida: {table}")
        return TABLES[table]

    async def read(self, table: str, *, limit: int, offset: int) -> list[dict]:
        self._require_table(table)
        async with self._db.connection() as conn, conn.cursor() as cur:
            await cur.execute(
                f"SELECT * FROM `{table}` LIMIT %s OFFSET %s", (limit, offset)
            )
            return [dict(r) for r in await cur.fetchall()]

    async def read_one(self, table: str, pk_value: object) -> dict | None:
        pk = await self.pk_column(table)
        async with self._db.connection() as conn, conn.cursor() as cur:
            await cur.execute(
                f"SELECT * FROM `{table}` WHERE `{pk}` = %s LIMIT 1", (pk_value,)
            )
            row = await cur.fetchone()
            return dict(row) if row else None

    async def create(self, table: str, data: dict) -> dict:
        cols = await self._valid_columns(table, data)
        if not cols:
            raise InvalidTableCrud("no hay columnas válidas para insertar")
        placeholders = ", ".join(["%s"] * len(cols))
        names = ", ".join(f"`{c}`" for c in cols)
        values = [data[c] for c in cols]
        async with self._db.connection() as conn, conn.cursor() as cur:
            await cur.execute(
                f"INSERT INTO `{table}` ({names}) VALUES ({placeholders})", values
            )
            pk = await self.pk_column(table)
            pk_value = data.get(pk, cur.lastrowid)
        row = await self.read_one(table, pk_value)
        if row is None:
            raise EntityNotFound("row", str(pk_value))
        return row

    async def update(self, table: str, pk_value: object, data: dict) -> dict | None:
        pk = await self.pk_column(table)
        cols = [c for c in await self._valid_columns(table, data) if c != pk]
        if not cols:
            raise InvalidTableCrud("no hay columnas válidas para actualizar")
        sets = ", ".join(f"`{c}` = %s" for c in cols)
        values = [data[c] for c in cols] + [pk_value]
        async with self._db.connection() as conn, conn.cursor() as cur:
            await cur.execute(
                f"UPDATE `{table}` SET {sets} WHERE `{pk}` = %s", values
            )
        return await self.read_one(table, pk_value)

    async def delete(self, table: str, pk_value: object) -> int:
        pk = await self.pk_column(table)
        async with self._db.connection() as conn, conn.cursor() as cur:
            await cur.execute(
                f"DELETE FROM `{table}` WHERE `{pk}` = %s", (pk_value,)
            )
            return cur.rowcount

    def _require_table(self, table: str) -> None:
        if table not in TABLES:
            raise InvalidTableCrud(f"tabla no permitida: {table}")

    async def _valid_columns(self, table: str, data: dict) -> list[str]:
        self._require_table(table)
        allowed = set(await self.columns(table))
        return [k for k in data if k in allowed]
