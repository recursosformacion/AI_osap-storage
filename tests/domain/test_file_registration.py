from __future__ import annotations

import pytest
from domain.entities.file import FileStatus
from domain.exceptions import InvalidFileData, InvalidSha256
from domain.services.file_registration import FileRegistrationService
from tests.fakes import InMemoryFileRepository

VALID_SHA = "a" * 64


def make_service() -> FileRegistrationService:
    return FileRegistrationService(InMemoryFileRepository())


async def test_register_valid_file():
    service = make_service()
    file = await service.register(VALID_SHA, "prueba.txt", "text/plain", 10)
    assert file.id == 1
    assert file.sha256 == VALID_SHA
    assert file.name == "prueba.txt"
    assert file.mime_type == "text/plain"
    assert file.size_bytes == 10
    assert file.status == FileStatus.REGISTERED


async def test_register_normalizes_sha256_to_lowercase():
    service = make_service()
    file = await service.register("A" * 64, "x.txt")
    assert file.sha256 == VALID_SHA


async def test_register_duplicate_returns_existing_file():
    service = make_service()
    first = await service.register(VALID_SHA, "x.txt")
    second = await service.register(VALID_SHA, "otro.txt")
    assert first.id == second.id
    assert second.name == "x.txt"


async def test_register_invalid_sha256_raises():
    service = make_service()
    with pytest.raises(InvalidSha256):
        await service.register("zzz", "x.txt")


async def test_register_short_sha256_raises():
    service = make_service()
    with pytest.raises(InvalidSha256):
        await service.register("ab" * 31, "x.txt")


async def test_register_empty_name_raises():
    service = make_service()
    with pytest.raises(InvalidFileData):
        await service.register(VALID_SHA, "   ")
