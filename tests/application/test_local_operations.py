from __future__ import annotations

import hashlib

import pytest
from application.services.file_publisher import FilePublisher
from application.use_cases.delete_file import DeleteFile
from application.use_cases.register_existing_file import RegisterExistingFile, RegisterExistingFileCommand
from application.use_cases.verify_file import VerifyFile
from domain.entities.storage_provider import ProviderType, StorageProvider
from domain.exceptions import InvalidFileData
from domain.services.file_registration import FileRegistrationService
from infrastructure.hashing.hashlib_hasher import HashlibHasher
from infrastructure.providers.registry import StorageBackendRegistry
from tests.fakes import (
    InMemoryFileRepository,
    InMemoryLocationRepository,
    InMemoryProviderRepository,
    MemoryBackend,
)


async def build_ctx(tmp_path):
    files = InMemoryFileRepository()
    locations = InMemoryLocationRepository()
    providers = InMemoryProviderRepository()
    await providers.create(StorageProvider(name="mem", provider_type=ProviderType.LOCAL_DISK, config={}))
    registry = StorageBackendRegistry()
    registry.register(ProviderType.LOCAL_DISK, MemoryBackend)
    publisher = FilePublisher(files, locations, providers, registry)
    hasher = HashlibHasher()
    registration = FileRegistrationService(files)
    return files, locations, providers, registry, publisher, hasher, registration


async def test_register_existing_computes_sha256_and_deduplicates(tmp_path):
    path = tmp_path / "f.txt"
    payload = b"contenido local"
    path.write_bytes(payload)
    files, locations, providers, registry, publisher, hasher, registration = await build_ctx(tmp_path)

    use_case = RegisterExistingFile(hasher, registration, publisher)
    first = await use_case.execute(RegisterExistingFileCommand(path=str(path)))
    second = await use_case.execute(RegisterExistingFileCommand(path=str(path)))

    expected = hashlib.sha256(payload).hexdigest()
    assert first.file.sha256 == expected
    assert first.file.id == second.file.id  # deduplicación por SHA256
    assert len(await locations.list_by_file(first.file.id)) == 1


async def test_register_existing_missing_path_raises(tmp_path):
    files, locations, providers, registry, publisher, hasher, registration = await build_ctx(tmp_path)
    use_case = RegisterExistingFile(hasher, registration, publisher)
    with pytest.raises(InvalidFileData):
        await use_case.execute(RegisterExistingFileCommand(path=str(tmp_path / "no-existe.txt")))


async def test_verify_ok_then_delete(tmp_path):
    path = tmp_path / "f.txt"
    payload = b"contenido a verificar"
    path.write_bytes(payload)
    files, locations, providers, registry, publisher, hasher, registration = await build_ctx(tmp_path)

    register_uc = RegisterExistingFile(hasher, registration, publisher)
    published = await register_uc.execute(RegisterExistingFileCommand(path=str(path)))

    verify_uc = VerifyFile(files, locations, providers, registry, hasher, str(tmp_path))
    result = await verify_uc.execute(published.file.id)
    assert result.ok is True
    assert result.checks[0].ok is True

    delete_uc = DeleteFile(files, locations, providers, registry)
    await delete_uc.execute(published.file.id)
    assert await files.get_by_id(published.file.id) is None
    assert await locations.list_by_file(published.file.id) == []
