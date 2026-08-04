from __future__ import annotations

from collections.abc import Iterable
from dataclasses import dataclass
from datetime import UTC, datetime

from domain.entities.archive import Archive, ArchiveStatus
from domain.entities.archive_entry import ArchiveEntry, ArchiveEntryStatus
from domain.entities.import_source import ImportSource
from domain.ports.archive_repositories import ArchiveEntryRepository, ArchiveRepository
from domain.ports.import_source_repository import ImportSourceRepository


@dataclass(frozen=True)
class PdmxRow:
    relative_path: str
    archive_name: str
    archive_url: str | None = None
    logical_id: str | None = None
    composer: str | None = None
    title: str | None = None


@dataclass(frozen=True)
class PdmxImportResult:
    archives: int
    entries: int


class PdmxImporter:
    """Construye el índice de archives y archive_entries sin descargar nada."""

    def __init__(
        self,
        archives: ArchiveRepository,
        entries: ArchiveEntryRepository,
        batch_size: int = 1000,
        sources: ImportSourceRepository | None = None,
    ) -> None:
        self._archives = archives
        self._entries = entries
        self._batch_size = batch_size
        self._sources = sources

    async def import_rows(
        self,
        rows: Iterable[PdmxRow],
        source: ImportSource | None = None,
    ) -> PdmxImportResult:
        if source is not None and self._sources is not None:
            if source.imported_at is None:
                source.imported_at = datetime.now(UTC)
            await self._sources.create(source)

        cache: dict[str, int] = {}
        new_archives = 0
        entries_created = 0
        pending: list[ArchiveEntry] = []

        for row in rows:
            if not row.relative_path or not row.archive_name:
                continue
            archive_id = cache.get(row.archive_name)
            if archive_id is None:
                archive = await self._archives.get_by_name(row.archive_name)
                if archive is None:
                    archive = await self._archives.create(
                        Archive(name=row.archive_name, url=row.archive_url, status=ArchiveStatus.IMPORTED)
                    )
                    new_archives += 1
                cache[row.archive_name] = archive.id
                archive_id = archive.id

            pending.append(
                ArchiveEntry(
                    archive_id=archive_id,
                    relative_path=row.relative_path,
                    logical_id=row.logical_id,
                    composer=row.composer,
                    title=row.title,
                    status=ArchiveEntryStatus.MISSING,
                )
            )
            if len(pending) >= self._batch_size:
                entries_created += await self._entries.bulk_create(pending)
                pending = []

        if pending:
            entries_created += await self._entries.bulk_create(pending)

        return PdmxImportResult(archives=new_archives, entries=entries_created)
