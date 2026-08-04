from __future__ import annotations

from domain.entities.archive import Archive
from domain.exceptions import EntityNotFound
from domain.ports.archive_repositories import ArchiveEntryRepository, ArchiveRepository


class ListArchives:
    def __init__(self, archives: ArchiveRepository) -> None:
        self._archives = archives

    async def execute(self, *, limit: int = 100, offset: int = 0) -> list[Archive]:
        return await self._archives.list(limit=limit, offset=offset)


class GetArchive:
    def __init__(self, archives: ArchiveRepository) -> None:
        self._archives = archives

    async def execute(self, archive_id: int) -> Archive:
        archive = await self._archives.get_by_id(archive_id)
        if archive is None:
            raise EntityNotFound("archive", archive_id)
        return archive


class CountMissingEntries:
    def __init__(self, entries: ArchiveEntryRepository) -> None:
        self._entries = entries

    async def execute(self, archive_id: int) -> int:
        return await self._entries.count_by_archive(archive_id)
