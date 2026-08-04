from __future__ import annotations

from domain.entities.statistics import Statistics
from domain.ports.statistics_repository import StatisticsRepository

from infrastructure.db.connection import Database


def _row_to_statistics(row: dict) -> Statistics:
    return Statistics(
        id=row["id"],
        archives=row["archives"],
        entries=row["entries"],
        files=row["files"],
        downloaded_tar=row["downloaded_tar"],
        materialized=row["materialized"],
        pending=row["pending"],
        bytes=row["bytes"],
        computed_at=row["computed_at"],
        created_at=row["created_at"],
        updated_at=row["updated_at"],
    )


class SqlStatisticsRepository(StatisticsRepository):
    def __init__(self, db: Database) -> None:
        self._db = db

    async def get_latest(self) -> Statistics | None:
        async with self._db.connection() as conn, conn.cursor() as cur:
            await cur.execute("SELECT * FROM statistics ORDER BY id DESC LIMIT 1")
            row = await cur.fetchone()
            return _row_to_statistics(row) if row else None

    async def save(self, stats: Statistics) -> Statistics:
        async with self._db.connection() as conn, conn.cursor() as cur:
            await cur.execute(
                "INSERT INTO statistics (archives, entries, files, downloaded_tar, materialized, "
                "pending, bytes, computed_at) VALUES (%s, %s, %s, %s, %s, %s, %s, %s)",
                (
                    stats.archives,
                    stats.entries,
                    stats.files,
                    stats.downloaded_tar,
                    stats.materialized,
                    stats.pending,
                    stats.bytes,
                    stats.computed_at,
                ),
            )
            stats.id = cur.lastrowid
            return stats
