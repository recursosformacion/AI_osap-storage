from __future__ import annotations

from domain.entities.download_job import DownloadJob, DownloadJobStatus
from domain.ports.repositories import DownloadJobRepository

from infrastructure.db.connection import Database


def _row_to_job(row: dict) -> DownloadJob:
    return DownloadJob(
        id=row["id"],
        file_id=row["file_id"],
        provider_id=row["provider_id"],
        source_url=row["source_url"],
        status=DownloadJobStatus(row["status"]),
        error_message=row["error_message"],
        created_at=row["created_at"],
        updated_at=row["updated_at"],
    )


class SqlDownloadJobRepository(DownloadJobRepository):
    def __init__(self, db: Database) -> None:
        self._db = db

    async def create(self, job: DownloadJob) -> DownloadJob:
        async with self._db.connection() as conn, conn.cursor() as cur:
            await cur.execute(
                "INSERT INTO download_jobs (file_id, provider_id, source_url, status) VALUES (%s, %s, %s, %s)",
                (job.file_id, job.provider_id, job.source_url, job.status.value),
            )
            job.id = cur.lastrowid
            await cur.execute("SELECT * FROM download_jobs WHERE id = %s", (job.id,))
            return _row_to_job(await cur.fetchone())

    async def get_by_id(self, job_id: int) -> DownloadJob | None:
        async with self._db.connection() as conn, conn.cursor() as cur:
            await cur.execute("SELECT * FROM download_jobs WHERE id = %s", (job_id,))
            row = await cur.fetchone()
            return _row_to_job(row) if row else None

    async def save(self, job: DownloadJob) -> None:
        async with self._db.connection() as conn, conn.cursor() as cur:
            await cur.execute(
                "UPDATE download_jobs SET provider_id = %s, status = %s, error_message = %s WHERE id = %s",
                (job.provider_id, job.status.value, job.error_message, job.id),
            )

    async def list_by_file(self, file_id: int) -> list[DownloadJob]:
        async with self._db.connection() as conn, conn.cursor() as cur:
            await cur.execute(
                "SELECT * FROM download_jobs WHERE file_id = %s ORDER BY id DESC",
                (file_id,),
            )
            return [_row_to_job(row) for row in await cur.fetchall()]
