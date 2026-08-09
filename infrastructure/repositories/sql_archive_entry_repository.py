from __future__ import annotations

from domain.entities.archive_entry import ArchiveEntry, ArchiveEntryStatus
from domain.ports.archive_repositories import ArchiveEntryRepository

from infrastructure.db.connection import Database


def _row_to_entry(row: dict) -> ArchiveEntry:
    return ArchiveEntry(
        id=row["id"],
        archive_id=row["archive_id"],
        logical_id=row["logical_id"],
        composer=row["composer"],
        title=row["title"],
        work_id=row["work_id"],
        relative_path=row["relative_path"],
        file_id=row["file_id"],
        size=row["size"],
        offset=row["offset_bytes"],
        status=ArchiveEntryStatus(row["status"]),
        created_at=row["created_at"],
        updated_at=row["updated_at"],
    )


class SqlArchiveEntryRepository(ArchiveEntryRepository):
    def __init__(self, db: Database) -> None:
        self._db = db

    async def create(self, entry: ArchiveEntry) -> ArchiveEntry:
        async with self._db.connection() as conn, conn.cursor() as cur:
            await cur.execute(
                "INSERT INTO archive_entries (archive_id, logical_id, composer, title, relative_path, status) "
                "VALUES (%s, %s, %s, %s, %s, %s)",
                (
                    entry.archive_id,
                    entry.logical_id,
                    entry.composer,
                    entry.title,
                    entry.relative_path,
                    entry.status.value,
                ),
            )
            entry.id = cur.lastrowid
            await cur.execute("SELECT * FROM archive_entries WHERE id = %s", (entry.id,))
            return _row_to_entry(await cur.fetchone())

    async def bulk_create(self, entries: list[ArchiveEntry]) -> int:
        if not entries:
            return 0
        placeholders = ", ".join(["(%s, %s, %s, %s, %s, %s)"] * len(entries))
        params: list = []
        for entry in entries:
            params.extend(
                [
                    entry.archive_id,
                    entry.logical_id,
                    entry.composer,
                    entry.title,
                    entry.relative_path,
                    entry.status.value,
                ]
            )
        # Upsert: en re-importación actualiza logical_id/composer/title sin duplicar.
        sql = (
            "INSERT INTO archive_entries (archive_id, logical_id, composer, title, relative_path, status) "
            f"VALUES {placeholders} "
            "ON DUPLICATE KEY UPDATE logical_id = VALUES(logical_id), "
            "composer = VALUES(composer), title = VALUES(title)"
        )
        async with self._db.connection() as conn, conn.cursor() as cur:
            await cur.execute(sql, params)
            return cur.rowcount

    async def bulk_update_file_ids(self, entries: list[ArchiveEntry]) -> None:
        for batch in [entries[i : i + 500] for i in range(0, len(entries), 500)]:
            if not batch:
                continue
            cases = " ".join(["WHEN %s THEN %s"] * len(batch))
            params: list = []
            ids: list = []
            for entry in batch:
                params.extend([entry.id, entry.file_id])
                ids.append(entry.id)
            id_placeholders = ", ".join(["%s"] * len(ids))
            sql = (
                f"UPDATE archive_entries SET file_id = CASE id {cases} END "
                f"WHERE id IN ({id_placeholders})"
            )
            async with self._db.connection() as conn, conn.cursor() as cur:
                await cur.execute(sql, params + ids)

    async def get_by_id(self, entry_id: int) -> ArchiveEntry | None:
        async with self._db.connection() as conn, conn.cursor() as cur:
            await cur.execute("SELECT * FROM archive_entries WHERE id = %s", (entry_id,))
            row = await cur.fetchone()
            return _row_to_entry(row) if row else None

    async def get_by_relative_path(self, relative_path: str) -> ArchiveEntry | None:
        async with self._db.connection() as conn, conn.cursor() as cur:
            await cur.execute(
                "SELECT * FROM archive_entries WHERE relative_path = %s ORDER BY id LIMIT 1",
                (relative_path,),
            )
            row = await cur.fetchone()
            return _row_to_entry(row) if row else None

    async def get_by_logical_id(self, logical_id: str) -> ArchiveEntry | None:
        async with self._db.connection() as conn, conn.cursor() as cur:
            await cur.execute(
                "SELECT * FROM archive_entries WHERE logical_id = %s ORDER BY id LIMIT 1",
                (logical_id,),
            )
            row = await cur.fetchone()
            return _row_to_entry(row) if row else None

    async def get_by_file_id(self, file_id: int) -> ArchiveEntry | None:
        async with self._db.connection() as conn, conn.cursor() as cur:
            await cur.execute(
                "SELECT * FROM archive_entries WHERE file_id = %s ORDER BY id LIMIT 1",
                (file_id,),
            )
            row = await cur.fetchone()
            return _row_to_entry(row) if row else None

    async def list_by_archive(self, archive_id: int) -> list[ArchiveEntry]:
        async with self._db.connection() as conn, conn.cursor() as cur:
            await cur.execute(
                "SELECT * FROM archive_entries WHERE archive_id = %s ORDER BY id",
                (archive_id,),
            )
            return [_row_to_entry(row) for row in await cur.fetchall()]

    async def list_by_work(self, work_id: int) -> list[ArchiveEntry]:
        async with self._db.connection() as conn, conn.cursor() as cur:
            await cur.execute(
                "SELECT * FROM archive_entries WHERE work_id = %s ORDER BY id",
                (work_id,),
            )
            return [_row_to_entry(row) for row in await cur.fetchall()]

    async def list_by_work_ids(self, work_ids: list[int]) -> list[ArchiveEntry]:
        if not work_ids:
            return []
        placeholders = ", ".join(["%s"] * len(work_ids))
        async with self._db.connection() as conn, conn.cursor() as cur:
            await cur.execute(
                f"SELECT * FROM archive_entries WHERE work_id IN ({placeholders}) ORDER BY id",
                work_ids,
            )
            return [_row_to_entry(row) for row in await cur.fetchall()]

    async def list_all(self, *, limit: int = 1000, offset: int = 0) -> list[ArchiveEntry]:
        async with self._db.connection() as conn, conn.cursor() as cur:
            await cur.execute(
                "SELECT * FROM archive_entries ORDER BY id LIMIT %s OFFSET %s",
                (limit, offset),
            )
            return [_row_to_entry(row) for row in await cur.fetchall()]

    async def bulk_update_work_ids(self, entries: list[ArchiveEntry]) -> None:
        for batch in [entries[i : i + 500] for i in range(0, len(entries), 500)]:
            if not batch:
                continue
            cases = " ".join(["WHEN %s THEN %s"] * len(batch))
            params: list = []
            ids: list = []
            for entry in batch:
                params.extend([entry.id, entry.work_id])
                ids.append(entry.id)
            id_placeholders = ", ".join(["%s"] * len(ids))
            sql = (
                f"UPDATE archive_entries SET work_id = CASE id {cases} END "
                f"WHERE id IN ({id_placeholders})"
            )
            async with self._db.connection() as conn, conn.cursor() as cur:
                await cur.execute(sql, params + ids)

    async def search(self, query: str, *, limit: int = 50, offset: int = 0) -> list[ArchiveEntry]:
        pattern = f"%{query}%"
        async with self._db.connection() as conn, conn.cursor() as cur:
            await cur.execute(
                "SELECT * FROM archive_entries "
                "WHERE logical_id LIKE %s OR relative_path LIKE %s "
                "OR composer LIKE %s OR title LIKE %s "
                "ORDER BY id LIMIT %s OFFSET %s",
                (pattern, pattern, pattern, pattern, limit, offset),
            )
            return [_row_to_entry(row) for row in await cur.fetchall()]

    async def list_relative_paths(self) -> list[str]:
        async with self._db.connection() as conn, conn.cursor() as cur:
            await cur.execute("SELECT relative_path FROM archive_entries")
            return [row["relative_path"] for row in await cur.fetchall()]

    async def save(self, entry: ArchiveEntry) -> None:
        async with self._db.connection() as conn, conn.cursor() as cur:
            await cur.execute(
                "UPDATE archive_entries SET logical_id = %s, file_id = %s, size = %s, "
                "offset_bytes = %s, status = %s WHERE id = %s",
                (
                    entry.logical_id,
                    entry.file_id,
                    entry.size,
                    entry.offset,
                    entry.status.value,
                    entry.id,
                ),
            )

    async def count_total(self) -> int:
        async with self._db.connection() as conn, conn.cursor() as cur:
            await cur.execute("SELECT COUNT(*) AS total FROM archive_entries")
            return int((await cur.fetchone())["total"])

    async def count_by_status(self, status: ArchiveEntryStatus) -> int:
        async with self._db.connection() as conn, conn.cursor() as cur:
            await cur.execute(
                "SELECT COUNT(*) AS total FROM archive_entries WHERE status = %s",
                (status.value,),
            )
            return int((await cur.fetchone())["total"])

    async def count_by_archive(self, archive_id: int) -> int:
        async with self._db.connection() as conn, conn.cursor() as cur:
            await cur.execute(
                "SELECT COUNT(*) AS total FROM archive_entries WHERE archive_id = %s",
                (archive_id,),
            )
            return int((await cur.fetchone())["total"])
