from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path

from domain.entities.archive import Archive, ArchiveStatus
from domain.entities.archive_entry import ArchiveEntry, ArchiveEntryStatus
from domain.exceptions import EntityNotFound, InvalidFileData
from domain.ports.archive_repositories import ArchiveEntryRepository, ArchiveRepository
from domain.ports.archives import ArchiveReaderFactory
from domain.ports.hashing import FileHasher
from domain.services.file_registration import FileRegistrationService

from application.services.file_publisher import FilePublisher
from application.services.tar_downloader import TarDownloader


@dataclass(frozen=True)
class MaterializeArchiveCommand:
    archive_id: int
    provider_id: int | None = None
    local_path: str | None = None
    download: bool = False
    keep_tar: bool = True


@dataclass(frozen=True)
class MaterializeResult:
    archive_id: int
    total: int
    ready: int
    failed: int


class MaterializeArchive:
    """Descomprime un archive completo, registra cada fichero y lo publica en un proveedor.

    Proceso offline. Si `download` está activo y no hay TAR local, lo descarga a la
    caché de mirrors reutilizando las ejecuciones siguientes.
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

    async def execute(self, command: MaterializeArchiveCommand) -> MaterializeResult:
        archive = await self._archives.get_by_id(command.archive_id)
        if archive is None:
            raise EntityNotFound("archive", command.archive_id)

        downloaded_now = False
        if command.local_path:
            archive.local_path = command.local_path
            await self._archives.save(archive)
        elif command.download:
            local_path, downloaded_now = await self._tar_downloader.ensure(archive, download=True)
            if archive.local_path != local_path:
                archive.local_path = local_path
                if downloaded_now:
                    archive.status = ArchiveStatus.DOWNLOADED
                await self._archives.save(archive)

        if not archive.local_path or not os.path.exists(archive.local_path):
            raise InvalidFileData(f"archive {archive.id} has no local file at local_path")

        reader = self._reader_factory.open(archive.local_path, archive.format)
        try:
            entry_list = await self._entries.list_by_archive(archive.id)
            ready = 0
            failed = 0
            for entry in entry_list:
                if await self._materialize_one(archive, entry, command.provider_id, reader):
                    ready += 1
                else:
                    failed += 1
            archive.status = self._final_status(len(entry_list), ready, failed)
            await self._archives.save(archive)
            return MaterializeResult(archive_id=archive.id, total=len(entry_list), ready=ready, failed=failed)
        finally:
            reader.close()
            if downloaded_now and not command.keep_tar:
                await self._tar_downloader.discard(archive)
                await self._archives.save(archive)

    async def _materialize_one(
        self,
        archive: Archive,
        entry: ArchiveEntry,
        provider_id: int | None,
        reader,
    ) -> bool:
        temp = self._temp_dir / f"mat-{archive.id}-{entry.id}.part"
        try:
            if not reader.has_member(entry.relative_path):
                raise FileNotFoundError(entry.relative_path)
            await reader.extract(entry.relative_path, str(temp))

            sha256 = await self._hasher.sha256_file(str(temp))
            name = os.path.basename(entry.relative_path) or entry.relative_path
            file = await self._registration.register(sha256, name, size_bytes=os.path.getsize(temp))
            await self._publisher.publish(file, provider_id, str(temp))

            entry.file_id = file.id
            entry.size = os.path.getsize(temp)
            entry.status = ArchiveEntryStatus.READY
            await self._entries.save(entry)
            return True
        except Exception:
            entry.status = ArchiveEntryStatus.FAILED
            await self._entries.save(entry)
            return False
        finally:
            if temp.exists():
                temp.unlink()

    @staticmethod
    def _final_status(total: int, ready: int, failed: int) -> ArchiveStatus:
        if ready > 0:
            return ArchiveStatus.MATERIALIZED
        if failed > 0 and total > 0:
            return ArchiveStatus.FAILED
        return ArchiveStatus.IMPORTED
