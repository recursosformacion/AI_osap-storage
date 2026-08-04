from __future__ import annotations

import os
from dataclasses import dataclass

from domain.entities.archive_entry import ArchiveEntry
from domain.entities.file import File, FileStatus
from domain.entities.storage_location import LocationStatus, StorageLocation
from domain.entities.storage_provider import StorageProvider
from domain.ports.archive_repositories import ArchiveEntryRepository
from domain.ports.repositories import FileRepository, StorageLocationRepository


@dataclass(frozen=True)
class ResourceResult:
    files: int
    locations: int


class MirrorResourceRegistrar:
    """Registra File + StorageLocation por entrada, apuntando al mirror como primer proveedor.

    No calcula SHA256 ni copia nada: `StorageLocation.object_key` es la ruta dentro del
    mirror (relative_path) y el proveedor es el backend local/mirror.
    """

    def __init__(
        self,
        files: FileRepository,
        locations: StorageLocationRepository,
        entries: ArchiveEntryRepository,
        batch_size: int = 500,
    ) -> None:
        self._files = files
        self._locations = locations
        self._entries = entries
        self._batch_size = batch_size

    async def register(self, entries: list[ArchiveEntry], provider: StorageProvider) -> ResourceResult:
        todo = [entry for entry in entries if entry.file_id is None]
        if not todo:
            return ResourceResult(files=0, locations=0)

        for i in range(0, len(todo), self._batch_size):
            batch = todo[i : i + self._batch_size]
            files = [
                File(
                    sha256=None,
                    name=os.path.basename(entry.relative_path) or entry.relative_path,
                    status=FileStatus.REGISTERED,
                )
                for entry in batch
            ]
            files = await self._files.bulk_create(files)
            locations = [
                StorageLocation(
                    file_id=file.id,
                    provider_id=provider.id,
                    object_key=entry.relative_path,
                    status=LocationStatus.STORED,
                )
                for file, entry in zip(files, batch, strict=True)
            ]
            await self._locations.bulk_create(locations)
            for file, entry in zip(files, batch, strict=True):
                entry.file_id = file.id
            await self._entries.bulk_update_file_ids(batch)

        return ResourceResult(files=len(todo), locations=len(todo))
