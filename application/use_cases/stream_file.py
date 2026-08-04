from __future__ import annotations

from collections.abc import AsyncIterator
from dataclasses import dataclass

from domain.entities.file import File
from domain.entities.storage_location import StorageLocation
from domain.entities.storage_provider import StorageProvider
from domain.ports.storage import StorageBackendRegistry

from application.use_cases.get_download_url import GetDownloadUrl


@dataclass(frozen=True)
class FileStream:
    file: File
    provider: StorageProvider
    location: StorageLocation
    content: AsyncIterator[bytes]


class StreamFile:
    """Prepara el contenido de un fichero para ser servido por la API mediante streaming."""

    def __init__(self, resolver: GetDownloadUrl, registry: StorageBackendRegistry) -> None:
        self._resolver = resolver
        self._registry = registry

    async def execute(self, file_id: int, provider_id: int | None = None) -> FileStream:
        target = await self._resolver.execute(file_id, provider_id)
        content = await self._registry.backend_for(target.provider).open_stream(target.location.object_key)
        return FileStream(
            file=target.file,
            provider=target.provider,
            location=target.location,
            content=content,
        )
