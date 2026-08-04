from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path

from domain.exceptions import InvalidFileData
from domain.ports.hashing import FileHasher
from domain.services.file_registration import FileRegistrationService

from application.services.file_publisher import FilePublisher, PublishedFile


@dataclass(frozen=True)
class RegisterExistingFileCommand:
    path: str
    name: str | None = None
    provider_id: int | None = None


class RegisterExistingFile:
    """Registra un fichero ya existente en disco: SHA256, deduplicación y publicación."""

    def __init__(
        self,
        hasher: FileHasher,
        registration: FileRegistrationService,
        publisher: FilePublisher,
    ) -> None:
        self._hasher = hasher
        self._registration = registration
        self._publisher = publisher

    async def execute(self, command: RegisterExistingFileCommand) -> PublishedFile:
        path = Path(command.path)
        if not path.is_file():
            raise InvalidFileData(f"path is not a file: {command.path}")
        sha256 = await self._hasher.sha256_file(str(path))
        name = command.name or path.name
        file = await self._registration.register(sha256, name, size_bytes=os.path.getsize(path))
        return await self._publisher.publish(file, command.provider_id, str(path))
