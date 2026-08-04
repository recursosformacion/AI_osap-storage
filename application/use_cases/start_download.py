from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path

from domain.entities.download_job import DownloadJob, DownloadJobStatus
from domain.entities.file import File, FileStatus
from domain.entities.storage_location import LocationStatus, StorageLocation
from domain.entities.storage_provider import StorageProvider
from domain.exceptions import (
    EntityNotFound,
    IntegrityVerificationError,
    InvalidFileData,
    UnsupportedProvider,
)
from domain.ports.download import FileDownloader
from domain.ports.repositories import (
    DownloadJobRepository,
    FileRepository,
    StorageLocationRepository,
    StorageProviderRepository,
)
from domain.ports.storage import StorageBackendRegistry
from domain.ports.tasks import TaskScheduler
from domain.services.integrity import IntegrityService


@dataclass(frozen=True)
class StartDownloadCommand:
    file_id: int
    source_url: str
    provider_id: int | None = None


class StartDownload:
    """Inicia la descarga de un fichero, la verifica contra su SHA256 y lo guarda en un proveedor."""

    def __init__(
        self,
        files: FileRepository,
        jobs: DownloadJobRepository,
        locations: StorageLocationRepository,
        providers: StorageProviderRepository,
        downloader: FileDownloader,
        integrity: IntegrityService,
        registry: StorageBackendRegistry,
        scheduler: TaskScheduler,
        temp_dir: str,
    ) -> None:
        self._files = files
        self._jobs = jobs
        self._locations = locations
        self._providers = providers
        self._downloader = downloader
        self._integrity = integrity
        self._registry = registry
        self._scheduler = scheduler
        self._temp_dir = Path(temp_dir)

    async def execute(self, command: StartDownloadCommand) -> DownloadJob:
        file = await self._files.get_by_id(command.file_id)
        if file is None:
            raise EntityNotFound("file", command.file_id)
        if not command.source_url:
            raise InvalidFileData("source_url is required")

        await self._validate_target_provider(command.provider_id)

        job = DownloadJob(
            file_id=file.id,
            source_url=command.source_url,
            provider_id=command.provider_id,
        )
        job = await self._jobs.create(job)
        self._scheduler.schedule(self._process_job(job.id))
        return job

    async def _validate_target_provider(self, provider_id: int | None) -> None:
        if provider_id is not None:
            provider = await self._providers.get_by_id(provider_id)
            if provider is None or not provider.enabled:
                raise EntityNotFound("storage_provider", provider_id)
        else:
            enabled = await self._providers.list(enabled_only=True)
            if not enabled:
                raise UnsupportedProvider("no enabled storage provider is available")

    async def _process_job(self, job_id: int) -> None:
        job = await self._jobs.get_by_id(job_id)
        if job is None:
            return
        file = await self._files.get_by_id(job.file_id)
        temp_path: Path | None = None
        try:
            if file is None:
                raise EntityNotFound("file", job.file_id)
            job.status = DownloadJobStatus.RUNNING
            file.status = FileStatus.DOWNLOADING
            await self._jobs.save(job)
            await self._files.save(file)

            self._temp_dir.mkdir(parents=True, exist_ok=True)
            temp_path = self._temp_dir / f"{file.id}-{job.id}.part"

            await self._downloader.download(job.source_url, str(temp_path))

            computed = await self._integrity.compute_sha256(str(temp_path))
            if computed != file.sha256:
                raise IntegrityVerificationError(
                    f"sha256 mismatch for file {file.id}: expected {file.sha256}, got {computed}"
                )

            provider = await self._select_provider(file, job.provider_id)
            backend = self._registry.backend_for(provider)
            object_key = file.storage_key()
            await backend.store(str(temp_path), object_key)

            location = await self._locations.get_by_file_and_provider(file.id, provider.id)
            if location is None:
                await self._locations.create(
                    StorageLocation(
                        file_id=file.id,
                        provider_id=provider.id,
                        object_key=object_key,
                        status=LocationStatus.STORED,
                    )
                )
            else:
                location.object_key = object_key
                location.status = LocationStatus.STORED
                await self._locations.save(location)

            if file.size_bytes is None:
                file.size_bytes = os.path.getsize(temp_path)
            file.status = FileStatus.AVAILABLE
            await self._files.save(file)

            job.status = DownloadJobStatus.COMPLETED
            await self._jobs.save(job)
        except Exception as exc:
            if job is not None:
                job.status = DownloadJobStatus.FAILED
                job.error_message = str(exc)
                await self._jobs.save(job)
            if file is not None and file.status in (FileStatus.REGISTERED, FileStatus.DOWNLOADING):
                file.status = FileStatus.FAILED
                await self._files.save(file)
        finally:
            if temp_path is not None:
                temp_path.unlink(missing_ok=True)

    async def _select_provider(self, file: File, provider_id: int | None) -> StorageProvider:
        if provider_id is not None:
            provider = await self._providers.get_by_id(provider_id)
            if provider is None or not provider.enabled:
                raise UnsupportedProvider(f"provider {provider_id} is not available")
            return provider
        enabled = await self._providers.list(enabled_only=True)
        if not enabled:
            raise UnsupportedProvider("no enabled storage provider is available")
        return enabled[0]
