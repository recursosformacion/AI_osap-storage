from __future__ import annotations

from domain.entities.storage_location import LocationStatus, StorageLocation
from domain.ports.repositories import StorageLocationRepository

from infrastructure.db.connection import Database


def _row_to_location(row: dict) -> StorageLocation:
    return StorageLocation(
        id=row["id"],
        file_id=row["file_id"],
        provider_id=row["provider_id"],
        object_key=row["object_key"],
        status=LocationStatus(row["status"]),
        created_at=row["created_at"],
        updated_at=row["updated_at"],
    )


class SqlStorageLocationRepository(StorageLocationRepository):
    def __init__(self, db: Database) -> None:
        self._db = db

    async def create(self, location: StorageLocation) -> StorageLocation:
        async with self._db.connection() as conn, conn.cursor() as cur:
            await cur.execute(
                "INSERT INTO storage_locations (file_id, provider_id, object_key, status) VALUES (%s, %s, %s, %s)",
                (location.file_id, location.provider_id, location.object_key, location.status.value),
            )
            location.id = cur.lastrowid
            await cur.execute("SELECT * FROM storage_locations WHERE id = %s", (location.id,))
            return _row_to_location(await cur.fetchone())

    async def bulk_create(self, locations: list[StorageLocation]) -> None:
        if not locations:
            return
        placeholders = ", ".join(["(%s, %s, %s, %s)"] * len(locations))
        params: list = []
        for location in locations:
            params.extend(
                [location.file_id, location.provider_id, location.object_key, location.status.value]
            )
        async with self._db.connection() as conn, conn.cursor() as cur:
            await cur.execute(
                "INSERT INTO storage_locations (file_id, provider_id, object_key, status) VALUES "
                + placeholders,
                params,
            )

    async def get_by_id(self, location_id: int) -> StorageLocation | None:
        async with self._db.connection() as conn, conn.cursor() as cur:
            await cur.execute("SELECT * FROM storage_locations WHERE id = %s", (location_id,))
            row = await cur.fetchone()
            return _row_to_location(row) if row else None

    async def get_by_file_and_provider(self, file_id: int, provider_id: int) -> StorageLocation | None:
        async with self._db.connection() as conn, conn.cursor() as cur:
            await cur.execute(
                "SELECT * FROM storage_locations WHERE file_id = %s AND provider_id = %s",
                (file_id, provider_id),
            )
            row = await cur.fetchone()
            return _row_to_location(row) if row else None

    async def list_by_file(self, file_id: int) -> list[StorageLocation]:
        async with self._db.connection() as conn, conn.cursor() as cur:
            await cur.execute(
                "SELECT * FROM storage_locations WHERE file_id = %s ORDER BY id",
                (file_id,),
            )
            return [_row_to_location(row) for row in await cur.fetchall()]

    async def count(self) -> int:
        async with self._db.connection() as conn, conn.cursor() as cur:
            await cur.execute("SELECT COUNT(*) AS total FROM storage_locations")
            return int((await cur.fetchone())["total"])

    async def list_all(self, *, limit: int = 1000, offset: int = 0) -> list[StorageLocation]:
        async with self._db.connection() as conn, conn.cursor() as cur:
            await cur.execute(
                "SELECT * FROM storage_locations ORDER BY id LIMIT %s OFFSET %s",
                (limit, offset),
            )
            return [_row_to_location(row) for row in await cur.fetchall()]

    async def delete_by_file(self, file_id: int) -> None:
        async with self._db.connection() as conn, conn.cursor() as cur:
            await cur.execute("DELETE FROM storage_locations WHERE file_id = %s", (file_id,))

    async def save(self, location: StorageLocation) -> None:
        async with self._db.connection() as conn, conn.cursor() as cur:
            await cur.execute(
                "UPDATE storage_locations SET object_key = %s, status = %s WHERE id = %s",
                (location.object_key, location.status.value, location.id),
            )
