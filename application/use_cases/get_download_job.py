from __future__ import annotations

from domain.entities.download_job import DownloadJob
from domain.exceptions import EntityNotFound
from domain.ports.repositories import DownloadJobRepository


class GetDownloadJob:
    def __init__(self, jobs: DownloadJobRepository) -> None:
        self._jobs = jobs

    async def execute(self, job_id: int) -> DownloadJob:
        job = await self._jobs.get_by_id(job_id)
        if job is None:
            raise EntityNotFound("download_job", job_id)
        return job
