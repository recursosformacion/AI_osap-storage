from __future__ import annotations

from domain.entities.import_source import ImportSource
from domain.ports.import_source_repository import ImportSourceRepository

from infrastructure.db.connection import Database


def _row_to_source(row: dict) -> ImportSource:
    return ImportSource(
        id=row["id"],
        provider=row["provider"],
        version=row["version"],
        csv_path=row["csv_path"],
        notes=row["notes"],
        imported_at=row["imported_at"],
        created_at=row["created_at"],
        updated_at=row["updated_at"],
    )


class SqlImportSourceRepository(ImportSourceRepository):
    def __init__(self, db: Database) -> None:
        self._db = db

    async def create(self, source: ImportSource) -> ImportSource:
        async with self._db.connection() as conn, conn.cursor() as cur:
            await cur.execute(
                "INSERT INTO import_sources (provider, version, csv_path, notes, imported_at) "
                "VALUES (%s, %s, %s, %s, %s)",
                (source.provider, source.version, source.csv_path, source.notes, source.imported_at),
            )
            source.id = cur.lastrowid
            await cur.execute("SELECT * FROM import_sources WHERE id = %s", (source.id,))
            return _row_to_source(await cur.fetchone())

    async def get_by_id(self, source_id: int) -> ImportSource | None:
        async with self._db.connection() as conn, conn.cursor() as cur:
            await cur.execute("SELECT * FROM import_sources WHERE id = %s", (source_id,))
            row = await cur.fetchone()
            return _row_to_source(row) if row else None

    async def list(self, *, limit: int = 100, offset: int = 0) -> list[ImportSource]:
        async with self._db.connection() as conn, conn.cursor() as cur:
            await cur.execute(
                "SELECT * FROM import_sources ORDER BY id DESC LIMIT %s OFFSET %s",
                (limit, offset),
            )
            return [_row_to_source(row) for row in await cur.fetchall()]
