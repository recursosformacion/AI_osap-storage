from __future__ import annotations

from domain.entities.archive import Archive, ArchiveStatus
from domain.ports.archive_repositories import ArchiveRepository

from infrastructure.db.connection import Database


def _row_to_archive(row: dict) -> Archive:
    return Archive(
        id=row["id"],
        name=row["name"],
        url=row["url"],
        provider_id=row["provider_id"],
        format=row["format"],
        local_path=row["local_path"],
        status=ArchiveStatus(row["status"]),
        size=row["size"],
        sha256=row["sha256"],
        downloaded_at=row["downloaded_at"],
        created_at=row["created_at"],
        updated_at=row["updated_at"],
    )


class SqlArchiveRepository(ArchiveRepository):
    def __init__(self, db: Database) -> None:
        self._db = db

    async def create(self, archive: Archive) -> Archive:
        async with self._db.connection() as conn, conn.cursor() as cur:
            await cur.execute(
                "INSERT INTO archives (name, url, provider_id, format, local_path, status, size, "
                "sha256, downloaded_at) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s)",
                (
                    archive.name,
                    archive.url,
                    archive.provider_id,
                    archive.format,
                    archive.local_path,
                    archive.status.value,
                    archive.size,
                    archive.sha256,
                    archive.downloaded_at,
                ),
            )
            archive.id = cur.lastrowid
            await cur.execute("SELECT * FROM archives WHERE id = %s", (archive.id,))
            return _row_to_archive(await cur.fetchone())

    async def get_by_id(self, archive_id: int) -> Archive | None:
        async with self._db.connection() as conn, conn.cursor() as cur:
            await cur.execute("SELECT * FROM archives WHERE id = %s", (archive_id,))
            row = await cur.fetchone()
            return _row_to_archive(row) if row else None

    async def get_by_name(self, name: str) -> Archive | None:
        async with self._db.connection() as conn, conn.cursor() as cur:
            await cur.execute("SELECT * FROM archives WHERE name = %s", (name,))
            row = await cur.fetchone()
            return _row_to_archive(row) if row else None

    async def list(self, *, limit: int = 100, offset: int = 0) -> list[Archive]:
        async with self._db.connection() as conn, conn.cursor() as cur:
            await cur.execute(
                "SELECT * FROM archives ORDER BY id DESC LIMIT %s OFFSET %s",
                (limit, offset),
            )
            return [_row_to_archive(row) for row in await cur.fetchall()]

    async def count(self) -> int:
        async with self._db.connection() as conn, conn.cursor() as cur:
            await cur.execute("SELECT COUNT(*) AS total FROM archives")
            return int((await cur.fetchone())["total"])

    async def count_downloaded(self) -> int:
        async with self._db.connection() as conn, conn.cursor() as cur:
            await cur.execute(
                "SELECT COUNT(*) AS total FROM archives WHERE local_path IS NOT NULL AND local_path <> ''"
            )
            return int((await cur.fetchone())["total"])

    async def save(self, archive: Archive) -> None:
        async with self._db.connection() as conn, conn.cursor() as cur:
            await cur.execute(
                "UPDATE archives SET name = %s, url = %s, provider_id = %s, format = %s, "
                "local_path = %s, status = %s, size = %s, sha256 = %s, downloaded_at = %s WHERE id = %s",
                (
                    archive.name,
                    archive.url,
                    archive.provider_id,
                    archive.format,
                    archive.local_path,
                    archive.status.value,
                    archive.size,
                    archive.sha256,
                    archive.downloaded_at,
                    archive.id,
                ),
            )
