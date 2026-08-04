from __future__ import annotations

import re
from collections.abc import AsyncIterator
from dataclasses import dataclass
from pathlib import Path

from domain.entities.archive_entry import ArchiveEntry
from domain.entities.file import File
from domain.entities.storage_location import StorageLocation
from domain.entities.storage_provider import StorageProvider
from domain.ports.archive_repositories import ArchiveEntryRepository
from domain.ports.storage import StorageBackendRegistry

from application.use_cases.get_download_url import GetDownloadUrl


@dataclass(frozen=True)
class FileStream:
    file: File
    provider: StorageProvider
    location: StorageLocation
    content: AsyncIterator[bytes]
    friendly_name: str


def friendly_filename(file: File, entry: ArchiveEntry | None = None) -> str:
    """Nombre de descarga legible (título/compositor) en lugar del hash."""
    ext = Path(file.name or "").suffix or ".mxl"
    base = file.name or "file"
    if entry is not None and (entry.title or entry.logical_id):
        label = entry.title or entry.logical_id or ""
        if entry.composer and entry.composer not in label:
            label = f"{entry.composer} - {label}"
        label = re.sub(r'[\\/:*?"<>|\x00-\x1f]+', "-", label).strip().strip(".")
        if label:
            return f"{label}{ext}"
    return base


class StreamFile:
    """Prepara el contenido de un fichero para ser servido por la API mediante streaming."""

    def __init__(
        self,
        resolver: GetDownloadUrl,
        registry: StorageBackendRegistry,
        entries: ArchiveEntryRepository,
    ) -> None:
        self._resolver = resolver
        self._registry = registry
        self._entries = entries

    async def execute(self, file_id: int, provider_id: int | None = None) -> FileStream:
        target = await self._resolver.execute(file_id, provider_id)
        content = await self._registry.backend_for(target.provider).open_stream(target.location.object_key)
        entry = await self._entries.get_by_file_id(file_id)
        return FileStream(
            file=target.file,
            provider=target.provider,
            location=target.location,
            content=content,
            friendly_name=friendly_filename(target.file, entry),
        )
