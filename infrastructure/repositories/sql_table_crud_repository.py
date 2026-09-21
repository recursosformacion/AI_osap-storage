from __future__ import annotations

from domain.exceptions import EntityNotFound, InvalidTableCrud
from domain.ports.table_crud_repository import TableCrudRepository

from infrastructure.db.connection import Database

# Whitelist de tablas expuestas al CRUD genérico (excluye tablas internas/sistema).
# Valor: columna clave primaria de cada tabla.
TABLES: dict[str, str] = {
    "archives": "id",
    "archive_entries": "id",
    "authority_sync_state": "source",
    "catalog": "id",
    "category": "id",
    "categoryrol": "id",
    "cpdl_edition_files": "id",
    "cpdl_edition_persons": "id",
    "cpdl_editions": "id",
    "download_jobs": "id",
    "ensembles": "id",
    "epochs": "id",
    "files": "id",
    "genres": "id",
    "genre_mappings": "code",
    "import_sources": "id",
    "instruments": "id",
    "instrument_categories": "id",
    "languages": "id",
    "persons": "persons_id",
    "persons_aliases": "id",
    "persons_evidence": "id",
    "persons_identity": "id",
    "persons_merge_history": "id",
    "representation_persons": "id",
    "representations": "id",
    "works_resources": "id",
    "roles": "id",
    "schema_migrations": "id",
    "statistics": "id",
    "statistics_runs": "id",
    "storage_locations": "id",
    "storage_providers": "id",
    "tag_work": "id",
    "voices": "id",
    "votes": "id",
    "works": "id",
    "works_person_import": "id",
    "works_person_roles": "works_person_roles_id",
    "work_parts": "id",
    "work_statistics": "works_id",
}
# Las tablas de unión con PK compuesta no se exponen en el CRUD genérico
# (no tienen una clave de fila única): ensemble_voices, roles_categoria,
# work_ensembles, work_genres, work_instruments, work_language, work_tag, work_voices.


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

    async def schema(self, table: str) -> list[dict]:
        self._require_table(table)
        async with self._db.connection() as conn, conn.cursor() as cur:
            await cur.execute(
                "SELECT column_name AS name, column_type AS type, is_nullable AS nullable, "
                "column_key AS `key`, column_default AS `default`, extra "
                "FROM information_schema.columns "
                "WHERE table_schema = DATABASE() AND table_name = %s "
                "ORDER BY ordinal_position",
                (table,),
            )
            return [dict(r) for r in await cur.fetchall()]

    async def relations(self, table: str) -> list[dict]:
        self._require_table(table)
        async with self._db.connection() as conn, conn.cursor() as cur:
            await cur.execute(
                "SELECT column_name AS `column`, referenced_table_name AS ref_table, "
                "referenced_column_name AS ref_column, constraint_name AS name "
                "FROM information_schema.key_column_usage "
                "WHERE table_schema = DATABASE() AND table_name = %s "
                "AND referenced_table_name IS NOT NULL ORDER BY column_name",
                (table,),
            )
            return [dict(r) for r in await cur.fetchall()]

    async def read_filtered(
        self, table: str, column: str, value: str, *, limit: int, offset: int
    ) -> list[dict]:
        """Filas con igualdad en una columna (validada contra el esquema real)."""
        self._require_table(table)
        if column not in await self.columns(table):
            raise InvalidTableCrud(f"columna no válida: {column}")
        async with self._db.connection() as conn, conn.cursor() as cur:
            await cur.execute(
                f"SELECT * FROM `{table}` WHERE `{column}` = %s LIMIT %s OFFSET %s",
                (value, limit, offset),
            )
            return [dict(r) for r in await cur.fetchall()]

    async def count_filtered(self, table: str, column: str, value: str) -> int:
        self._require_table(table)
        if column not in await self.columns(table):
            raise InvalidTableCrud(f"columna no válida: {column}")
        async with self._db.connection() as conn, conn.cursor() as cur:
            await cur.execute(
                f"SELECT COUNT(*) AS n FROM `{table}` WHERE `{column}` = %s", (value,)
            )
            row = await cur.fetchone()
            return int(row["n"] or 0)

    async def read(self, table: str, *, limit: int, offset: int) -> list[dict]:
        self._require_table(table)
        async with self._db.connection() as conn, conn.cursor() as cur:
            await cur.execute(
                f"SELECT * FROM `{table}` LIMIT %s OFFSET %s", (limit, offset)
            )
            return [dict(r) for r in await cur.fetchall()]

    async def count(self, table: str) -> int:
        self._require_table(table)
        async with self._db.connection() as conn, conn.cursor() as cur:
            await cur.execute(f"SELECT COUNT(*) AS total FROM `{table}`")
            return int((await cur.fetchone())["total"])

    async def _text_columns(self, table: str) -> list[str]:
        async with self._db.connection() as conn, conn.cursor() as cur:
            await cur.execute(
                "SELECT column_name FROM information_schema.columns "
                "WHERE table_schema = DATABASE() AND table_name = %s "
                "AND data_type IN ('varchar','char') "
                "ORDER BY ordinal_position",
                (table,),
            )
            return [r["column_name"] for r in await cur.fetchall()]

    async def _search_where(self, table: str, q: str) -> tuple[str, list]:
        cols = await self._text_columns(table)
        if not cols:
            return "", []
        clause = " OR ".join(f"`{c}` LIKE %s" for c in cols)
        return f"({clause})", [f"%{q}%"] * len(cols)

    async def search(self, table: str, q: str, *, limit: int, offset: int) -> list[dict]:
        self._require_table(table)
        where, params = await self._search_where(table, q)
        if not where:
            return []
        async with self._db.connection() as conn, conn.cursor() as cur:
            await cur.execute(
                f"SELECT * FROM `{table}` WHERE {where} LIMIT %s OFFSET %s",
                [*params, limit, offset],
            )
            return [dict(r) for r in await cur.fetchall()]

    async def count_search(self, table: str, q: str) -> int:
        self._require_table(table)
        where, params = await self._search_where(table, q)
        if not where:
            return 0
        async with self._db.connection() as conn, conn.cursor() as cur:
            await cur.execute(f"SELECT COUNT(*) AS total FROM `{table}` WHERE {where}", params)
            return int((await cur.fetchone())["total"])

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
