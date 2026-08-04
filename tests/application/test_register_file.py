from __future__ import annotations

from application.use_cases.register_file import RegisterFile, RegisterFileCommand
from domain.entities.file import FileStatus
from domain.services.file_registration import FileRegistrationService
from tests.fakes import InMemoryFileRepository

SHA = "a" * 64


async def test_register_file_use_case():
    repo = InMemoryFileRepository()
    use_case = RegisterFile(FileRegistrationService(repo))
    file = await use_case.execute(RegisterFileCommand(sha256=SHA, name="x.txt"))
    assert file.id == 1
    assert file.status == FileStatus.REGISTERED
    assert await repo.count() == 1


async def test_register_file_is_idempotent_by_sha256():
    repo = InMemoryFileRepository()
    use_case = RegisterFile(FileRegistrationService(repo))
    first = await use_case.execute(RegisterFileCommand(sha256=SHA, name="x.txt"))
    second = await use_case.execute(
        RegisterFileCommand(sha256=SHA, name="x.txt", mime_type="text/plain", size_bytes=3)
    )
    assert first.id == second.id
    assert await repo.count() == 1
