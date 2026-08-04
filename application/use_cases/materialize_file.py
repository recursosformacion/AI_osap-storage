from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path

from domain.entities.archive import ArchiveStatus
from domain.entities.archive_entry import ArchiveEntry, ArchiveEntryStatus
from domain.entities.file import File
from domain.exceptions import EntityNotFound, InvalidFileData
from domain.ports.archive_repositories import ArchiveEntryRepository, ArchiveRepository
from domain.ports.archives import ArchiveReaderFactory
from domain.ports.hashing import FileHasher
from domain.services.file_registration import FileRegistrationService

from application.services.file_publisher import FilePublisher, PublishedFile
from application.services.tar_downloader import TarDownloader


@dataclass(frozen=True)
class MaterializeFileCommand:
    entry_id: int | None = None
    logical_id: str | None = None
    relative_path: str | None = None
    provider_id: int | None = None
    download: bool = True
    keep_tar: bool = True


@dataclass(frozen=True)
class MaterializedFile:
    entry: ArchiveEntry
    file: File
    published: PublishedFile


class MaterializeFile:
    """Materializa un único ArchiveEntry: TAR → extrae → SHA256 → File → publica → READY.

    Es el flujo central del mirror: materializa un fichero concreto bajo demanda
    (proceso offline/administrativo), descargando el TAR a la caché solo si hace falta.
    """

    def __init__(
        self,
        archives: ArchiveRepository,
        entries: ArchiveEntryRepository,
        reader_factory: ArchiveReaderFactory,
        hasher: FileHasher,
        registration: FileRegistrationService,
        publisher: FilePublisher,
        temp_dir: str,
        tar_downloader: TarDownloader,
    ) -> None:
        self._archives = archives
        self._entries = entries
        self._reader_factory = reader_factory
        self._hasher = hasher
        self._registration = registration
        self._publisher = publisher
        self._temp_dir = Path(temp_dir)
        self._tar_downloader = tar_downloader

    async def execute(self, command: MaterializeFileCommand) -> MaterializedFile:
        entry = await self._resolve_entry(command)
        archive = await self._archives.get_by_id(entry.archive_id)
        if archive is None:
            raise EntityNotFound("archive", entry.archive_id)

        local_path, downloaded_now = await self._tar_downloader.ensure(archive, download=command.download)
        if archive.local_path != local_path:
            archive.local_path = local_path
            if downloaded_now:
                archive.status = ArchiveStatus.DOWNLOADED
            await self._archives.save(archive)

        reader = self._reader_factory.open(local_path, archive.format)
        temp = self._temp_dir / f"mf-{entry.id}.part"
        try:
            if not reader.has_member(entry.relative_path):
                raise InvalidFileData(f"archive {archive.id} has no member {entry.relative_path}")
            await reader.extract(entry.relative_path, str(temp))

            sha256 = await self._hasher.sha256_file(str(temp))
            name = os.path.basename(entry.relative_path) or entry.relative_path
            file = await self._registration.register(sha256, name, size_bytes=os.path.getsize(temp))
            published = await self._publisher.publish(file, command.provider_id, str(temp))

            entry.file_id = file.id
            entry.size = os.path.getsize(temp)
            entry.status = ArchiveEntryStatus.READY
            await self._entries.save(entry)

            return MaterializedFile(entry=entry, file=file, published=published)
        finally:
            temp.unlink(missing_ok=True)
            reader.close()
            if downloaded_now and not command.keep_tar:
                await self._tar_downloader.discard(archive)
                await self._archives.save(archive)

    async def _resolve_entry(self, command: MaterializeFileCommand) -> ArchiveEntry:
        if command.entry_id is not None:
            entry = await self._entries.get_by_id(command.entry_id)
        elif command.logical_id:
            entry = await self._entries.get_by_logical_id(command.logical_id)
        elif command.relative_path:
            entry = await self._entries.get_by_relative_path(command.relative_path)
        else:
            raise InvalidFileData("must provide entry_id, logical_id or relative_path")
        if entry is None:
            raise EntityNotFound("archive_entry", command.entry_id or 0)
        return entry
