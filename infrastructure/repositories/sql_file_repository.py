from __future__ import annotations

from domain.entities.file import File, FileStatus
from domain.ports.repositories import FileRepository

from infrastructure.db.connection import Database


def _row_to_file(row: dict) -> File:
    return File(
        id=row["id"],
        sha256=row["sha256"],
        name=row["name"],
        mime_type=row["mime_type"],
        size_bytes=row["size_bytes"],
        status=FileStatus(row["status"]),
        created_at=row["created_at"],
        updated_at=row["updated_at"],
    )


class SqlFileRepository(FileRepository):
    def __init__(self, db: Database) -> None:
        self._db = db

    async def create(self, file: File) -> File:
        async with self._db.connection() as conn, conn.cursor() as cur:
            await cur.execute(
                "INSERT INTO files (sha256, name, mime_type, size_bytes, status) VALUES (%s, %s, %s, %s, %s)",
                (file.sha256, file.name, file.mime_type, file.size_bytes, file.status.value),
            )
            file.id = cur.lastrowid
            await cur.execute("SELECT * FROM files WHERE id = %s", (file.id,))
            return _row_to_file(await cur.fetchone())

    async def get_by_id(self, file_id: int) -> File | None:
        async with self._db.connection() as conn, conn.cursor() as cur:
            await cur.execute("SELECT * FROM files WHERE id = %s", (file_id,))
            row = await cur.fetchone()
            return _row_to_file(row) if row else None

    async def get_by_sha256(self, sha256: str) -> File | None:
        async with self._db.connection() as conn, conn.cursor() as cur:
            await cur.execute("SELECT * FROM files WHERE sha256 = %s", (sha256,))
            row = await cur.fetchone()
            return _row_to_file(row) if row else None

    async def save(self, file: File) -> None:
        async with self._db.connection() as conn, conn.cursor() as cur:
            await cur.execute(
                "UPDATE files SET name = %s, mime_type = %s, size_bytes = %s, status = %s WHERE id = %s",
                (file.name, file.mime_type, file.size_bytes, file.status.value, file.id),
            )

    async def delete(self, file_id: int) -> None:
        async with self._db.connection() as conn, conn.cursor() as cur:
            await cur.execute("DELETE FROM files WHERE id = %s", (file_id,))

    async def list(self, *, limit: int = 100, offset: int = 0) -> list[File]:
        async with self._db.connection() as conn, conn.cursor() as cur:
            await cur.execute(
                "SELECT * FROM files ORDER BY id DESC LIMIT %s OFFSET %s",
                (limit, offset),
            )
            return [_row_to_file(row) for row in await cur.fetchall()]

    async def count(self) -> int:
        async with self._db.connection() as conn, conn.cursor() as cur:
            await cur.execute("SELECT COUNT(*) AS total FROM files")
            return int((await cur.fetchone())["total"])

    async def sum_size(self) -> int:
        async with self._db.connection() as conn, conn.cursor() as cur:
            await cur.execute("SELECT COALESCE(SUM(size_bytes), 0) AS total FROM files")
            return int((await cur.fetchone())["total"])
