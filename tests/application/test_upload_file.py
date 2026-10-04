from __future__ import annotations

import hashlib

import pytest
from application.services.file_publisher import FilePublisher
from application.use_cases.upload_file import UploadFile, UploadFileCommand
from domain.entities.file import FileStatus
from domain.entities.storage_location import LocationStatus
from domain.entities.storage_provider import ProviderType, StorageProvider
from domain.exceptions import InvalidFileData
from domain.services.file_registration import FileRegistrationService
from domain.services.integrity import IntegrityService
from infrastructure.hashing.hashlib_hasher import HashlibHasher
from infrastructure.providers.registry import StorageBackendRegistry
from tests.fakes import (
    InMemoryFileRepository,
    InMemoryLocationRepository,
    InMemoryProviderRepository,
    MemoryBackend,
)

PAYLOAD = b"<score>upload</score>"
SHA = hashlib.sha256(PAYLOAD).hexdigest()


async def _chunks(data: bytes, part: int = 5):
    for i in range(0, len(data), part):
        yield data[i : i + part]


async def build(tmp_path):
    files = InMemoryFileRepository()
    locations = InMemoryLocationRepository()
    providers = InMemoryProviderRepository()
    await providers.create(
        StorageProvider(name="local", provider_type=ProviderType.LOCAL_DISK, config={})
    )
    registry = StorageBackendRegistry()
    registry.register(ProviderType.LOCAL_DISK, MemoryBackend)
    publisher = FilePublisher(files, locations, providers, registry)
    use_case = UploadFile(
        files=files,
        registration=FileRegistrationService(files),
        publisher=publisher,
        integrity=IntegrityService(HashlibHasher()),
        temp_dir=str(tmp_path),
    )
    return use_case, files, locations


async def test_upload_stores_non_public_file(tmp_path):
    use_case, files, locations = await build(tmp_path)

    file = await use_case.execute(
        UploadFileCommand(name="score.musicxml", mime_type="application/xml"), _chunks(PAYLOAD)
    )

    assert file.sha256 == SHA
    assert file.size_bytes == len(PAYLOAD)
    # Bytes disponibles (no implica publicación; la publicidad es por works_resources).
    assert file.status == FileStatus.AVAILABLE
    assert await files.count() == 1
    stored = await locations.list_by_file(file.id)
    assert stored and stored[0].status == LocationStatus.STORED


async def test_upload_deduplicates_by_sha256(tmp_path):
    use_case, files, _ = await build(tmp_path)

    first = await use_case.execute(UploadFileCommand(name="a.musicxml"), _chunks(PAYLOAD))
    second = await use_case.execute(UploadFileCommand(name="b.musicxml"), _chunks(PAYLOAD))

    assert first.id == second.id  # mismo contenido -> mismo File (dedup por sha256)
    assert await files.count() == 1


async def test_upload_rejects_empty(tmp_path):
    use_case, _, _ = await build(tmp_path)

    with pytest.raises(InvalidFileData):
        await use_case.execute(UploadFileCommand(name="empty"), _chunks(b""))
