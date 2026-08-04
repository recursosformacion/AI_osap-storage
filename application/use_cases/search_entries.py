from __future__ import annotations

from domain.entities.archive_entry import ArchiveEntryStatus
from domain.ports.archive_repositories import ArchiveEntryRepository, ArchiveRepository

from application.use_cases.resolve_file import Resolution


class SearchEntries:
    """Busca en el índice por texto (logical_id / relative_path)."""

    def __init__(self, entries: ArchiveEntryRepository, archives: ArchiveRepository) -> None:
        self._entries = entries
        self._archives = archives

    async def execute(self, query: str, *, limit: int = 50, offset: int = 0) -> list[Resolution]:
        query = (query or "").strip()
        if not query:
            return []
        found = await self._entries.search(query, limit=limit, offset=offset)
        results: list[Resolution] = []
        for entry in found:
            archive = await self._archives.get_by_id(entry.archive_id)
            available = entry.status == ArchiveEntryStatus.READY and entry.file_id is not None
            results.append(
                Resolution(
                    found=True,
                    relative_path=entry.relative_path,
                    logical_id=entry.logical_id,
                    composer=entry.composer,
                    title=entry.title,
                    archive_id=entry.archive_id,
                    archive_name=archive.name if archive else None,
                    status=entry.status.value,
                    file_id=entry.file_id,
                    available=available,
                )
            )
        return results
