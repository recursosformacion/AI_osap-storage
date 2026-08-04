from __future__ import annotations

from dataclasses import dataclass

from domain.entities.file import File
from domain.services.file_registration import FileRegistrationService


@dataclass(frozen=True)
class RegisterFileCommand:
    sha256: str
    name: str
    mime_type: str | None = None
    size_bytes: int | None = None


class RegisterFile:
    def __init__(self, registration: FileRegistrationService) -> None:
        self._registration = registration

    async def execute(self, command: RegisterFileCommand) -> File:
        return await self._registration.register(
            sha256=command.sha256,
            name=command.name,
            mime_type=command.mime_type,
            size_bytes=command.size_bytes,
        )
