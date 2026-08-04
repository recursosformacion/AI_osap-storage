from __future__ import annotations

import hashlib

import pytest
from application.use_cases.start_download import StartDownload, StartDownloadCommand
from domain.entities.download_job import DownloadJobStatus
from domain.entities.file import File, FileStatus
from domain.entities.storage_location import LocationStatus
from domain.entities.storage_provider import ProviderType, StorageProvider
from domain.exceptions import EntityNotFound, UnsupportedProvider
from domain.services.integrity import IntegrityService
from infrastructure.hashing.hashlib_hasher import HashlibHasher
from infrastructure.providers.registry import StorageBackendRegistry
from tests.fakes import (
    FakeDownloader,
    InMemoryFileRepository,
    InMemoryJobRepository,
    InMemoryLocationRepository,
    InMemoryProviderRepository,
    MemoryBackend,
    SyncScheduler,
)

PAYLOAD = b"contenido de prueba"
SHA = hashlib.sha256(PAYLOAD).hexdigest()


def build_use_case(
    tmp_path,
    *,
    payload: bytes = PAYLOAD,
    expected_sha: str = SHA,
    download_fails: bool = False,
    provider_enabled: bool = True,
):
    files = InMemoryFileRepository()
    jobs = InMemoryJobRepository()
    locations = InMemoryLocationRepository()
    providers = InMemoryProviderRepository()

    registry = StorageBackendRegistry()
    registry.register(ProviderType.LOCAL_DISK, MemoryBackend)
    scheduler = SyncScheduler()

    use_case = StartDownload(
        files=files,
        jobs=jobs,
        locations=locations,
        providers=providers,
        downloader=FakeDownloader(payload, fail=download_fails),
        integrity=IntegrityService(HashlibHasher()),
        registry=registry,
        scheduler=scheduler,
        temp_dir=str(tmp_path),
    )
    return use_case, files, jobs, locations, providers, scheduler


async def test_successful_download_stores_and_verifies(tmp_path):
    use_case, files, jobs, locations, providers, scheduler = build_use_case(tmp_path)
    await files.create(File(sha256=SHA, name="prueba.txt"))
    await providers.create(
        StorageProvider(name="mem", provider_type=ProviderType.LOCAL_DISK, config={})
    )

    job = await use_case.execute(
        StartDownloadCommand(file_id=1, source_url="https://example.com/f")
    )

    assert job.status == DownloadJobStatus.PENDING
    assert len(scheduler.scheduled) == 1

    await scheduler.scheduled[0]

    final_job = await jobs.get_by_id(job.id)
    assert final_job.status == DownloadJobStatus.COMPLETED

    stored = await locations.list_by_file(1)
    assert len(stored) == 1
    assert stored[0].status == LocationStatus.STORED

    file = await files.get_by_id(1)
    assert file.status == FileStatus.AVAILABLE
    assert file.size_bytes == len(PAYLOAD)


async def test_sha256_mismatch_fails_job_and_file(tmp_path):
    wrong_sha = hashlib.sha256(b"otro contenido").hexdigest()
    use_case, files, jobs, locations, providers, scheduler = build_use_case(tmp_path)
    await files.create(File(sha256=wrong_sha, name="prueba.txt"))
    await providers.create(
        StorageProvider(name="mem", provider_type=ProviderType.LOCAL_DISK, config={})
    )

    job = await use_case.execute(
        StartDownloadCommand(file_id=1, source_url="https://example.com/f")
    )
    await scheduler.scheduled[0]

    final_job = await jobs.get_by_id(job.id)
    assert final_job.status == DownloadJobStatus.FAILED
    assert "sha256 mismatch" in final_job.error_message

    file = await files.get_by_id(1)
    assert file.status == FileStatus.FAILED
    assert await locations.list_by_file(1) == []


async def test_downloader_failure_fails_job(tmp_path):
    use_case, files, jobs, locations, providers, scheduler = build_use_case(
        tmp_path, download_fails=True
    )
    await files.create(File(sha256=SHA, name="prueba.txt"))
    await providers.create(
        StorageProvider(name="mem", provider_type=ProviderType.LOCAL_DISK, config={})
    )

    job = await use_case.execute(
        StartDownloadCommand(file_id=1, source_url="https://example.com/f")
    )
    await scheduler.scheduled[0]

    final_job = await jobs.get_by_id(job.id)
    assert final_job.status == DownloadJobStatus.FAILED
    assert final_job.error_message


async def test_unknown_file_raises(tmp_path):
    use_case, *_ = build_use_case(tmp_path)
    with pytest.raises(EntityNotFound):
        await use_case.execute(
            StartDownloadCommand(file_id=999, source_url="https://example.com/f")
        )


async def test_no_enabled_provider_raises(tmp_path):
    use_case, files, jobs, locations, providers, scheduler = build_use_case(tmp_path)
    providers._providers.clear()
    await files.create(File(sha256=SHA, name="prueba.txt"))

    with pytest.raises(UnsupportedProvider):
        await use_case.execute(
            StartDownloadCommand(file_id=1, source_url="https://example.com/f")
        )
