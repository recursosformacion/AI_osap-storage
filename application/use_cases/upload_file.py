"""Caso de uso: subir bytes a storage (capacidad NUEVA, service-to-service).

No cambia el comportamiento del import existente: es una vía adicional para que osap-api
reciba un fichero de usuario y lo deposite en el almacenamiento.

- Escribe el stream a un temporal y calcula su `sha256`.
- **Deduplica por `sha256`**: si el `File` ya existe, se reutiliza.
- Guarda el contenido en un proveedor (local/VPS, R2…) y registra su `StorageLocation`.
- El fichero queda con bytes disponibles (`FileStatus.AVAILABLE`), lo que **NO** implica
  publicación: la publicidad es por `works_resources`, que **no** se crea aquí.
"""

from __future__ import annotations

import uuid
from collections.abc import AsyncIterator
from dataclasses import dataclass
from pathlib import Path

from domain.entities.file import File, FileStatus
from domain.exceptions import InvalidFileData
from domain.ports.repositories import FileRepository
from domain.services.file_registration import FileRegistrationService
from domain.services.integrity import IntegrityService

from application.services.file_publisher import FilePublisher


@dataclass(frozen=True)
class UploadFileCommand:
    name: str
    mime_type: str | None = None
    provider_id: int | None = None


class UploadFile:
    def __init__(
        self,
        *,
        files: FileRepository,
        registration: FileRegistrationService,
        publisher: FilePublisher,
        integrity: IntegrityService,
        temp_dir: str,
    ) -> None:
        self._files = files
        self._registration = registration
        self._publisher = publisher
        self._integrity = integrity
        self._temp_dir = Path(temp_dir)

    async def execute(self, command: UploadFileCommand, chunks: AsyncIterator[bytes]) -> File:
        self._temp_dir.mkdir(parents=True, exist_ok=True)
        temp_path = self._temp_dir / f"upload-{uuid.uuid4().hex}.part"
        size = 0
        try:
            with temp_path.open("wb") as fh:
                async for chunk in chunks:
                    if not chunk:
                        continue
                    fh.write(chunk)
                    size += len(chunk)

            if size == 0:
                raise InvalidFileData("el contenido subido está vacío")

            sha256 = await self._integrity.compute_sha256(str(temp_path))
            file = await self._registration.register(
                sha256=sha256,
                name=command.name,
                mime_type=command.mime_type,
                size_bytes=size,
            )

            published = await self._publisher.publish(file, command.provider_id, str(temp_path))
            file = published.file
            if file.size_bytes is None:
                file.size_bytes = size
            file.status = FileStatus.AVAILABLE
            await self._files.save(file)
            return file
        finally:
            temp_path.unlink(missing_ok=True)
