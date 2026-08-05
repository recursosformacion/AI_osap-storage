from __future__ import annotations

import os
from dataclasses import dataclass

from domain.entities.archive_entry import ArchiveEntryStatus
from domain.entities.work import Work
from domain.exceptions import EntityNotFound
from domain.ports.archive_repositories import ArchiveEntryRepository
from domain.ports.work_repository import WorkRepository


@dataclass(frozen=True)
class ResourceSummary:
    relative_path: str
    format: str | None
    file_id: int | None
    available: bool = False
    url: str | None = None


@dataclass(frozen=True)
class WorkDetail:
    work: Work
    resources: list[ResourceSummary]


_FORMAT_NAMES = {
    ".mxl": "MusicXML",
    ".musicxml": "MusicXML",
    ".xml": "MusicXML",
    ".pdf": "PDF",
    ".mid": "MIDI",
    ".midi": "MIDI",
    ".mscz": "MuseScore",
}


def _format_of(relative_path: str) -> str | None:
    suffix = os.path.splitext(relative_path)[1].lower()
    return _FORMAT_NAMES.get(suffix, suffix.lstrip(".").upper() or None)


class SearchWorks:
    """Busca obras por compositor/título/catálogo."""

    def __init__(self, works: WorkRepository) -> None:
        self._works = works

    async def execute(self, query: str, *, limit: int = 50, offset: int = 0) -> list[Work]:
        query = (query or "").strip()
        if not query:
            return await self._works.list(limit=limit, offset=offset)
        return await self._works.search(query, limit=limit, offset=offset)


class GetWork:
    """Devuelve una obra con sus representaciones (Resource)."""

    def __init__(
        self,
        works: WorkRepository,
        entries: ArchiveEntryRepository,
    ) -> None:
        self._works = works
        self._entries = entries

    async def execute(self, work_id: int) -> WorkDetail:
        work = await self._works.get_by_id(work_id)
        if work is None:
            raise EntityNotFound("work", work_id)
        resources = await self._entries.list_by_work(work_id)
        summaries = [
            ResourceSummary(
                relative_path=e.relative_path,
                format=_format_of(e.relative_path),
                file_id=e.file_id,
                available=e.status == ArchiveEntryStatus.READY and e.file_id is not None,
            )
            for e in resources
        ]
        return WorkDetail(work=work, resources=summaries)
