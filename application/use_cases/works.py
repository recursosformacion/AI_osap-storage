from __future__ import annotations

import os
from dataclasses import dataclass

from domain.entities.work import Work, WorkLists
from domain.exceptions import EntityNotFound
from domain.ports.archive_repositories import ArchiveEntryRepository
from domain.ports.work_repository import WorkRepository
from domain.services.composer_resolver import ComposerResolver


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
    genres: list[str]
    instruments: list[str]
    parts_names: list[str]


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

    def __init__(
        self,
        works: WorkRepository,
        resolver: ComposerResolver | None = None,
    ) -> None:
        self._works = works
        self._resolver = resolver

    async def execute(self, query: str, *, limit: int = 50, offset: int = 0) -> list[Work]:
        query = (query or "").strip()
        if not query:
            works = await self._works.all_(limit=limit, offset=offset)
        else:
            works = await self._works.search(query, limit=limit, offset=offset)
        await self._resolve_composers(works)
        return works

    async def _resolve_composers(self, works: list[Work]) -> None:
        if not works or self._resolver is None:
            return
        resolved = await self._resolver.resolve_many([w.composer for w in works])
        for work in works:
            result = resolved.get(work.composer)
            if result:
                work.composer_id, work.composer = result


class GetWork:
    """Devuelve una obra con sus representaciones (Resource)."""

    def __init__(
        self,
        works: WorkRepository,
        entries: ArchiveEntryRepository,
        resolver: ComposerResolver | None = None,
    ) -> None:
        self._works = works
        self._entries = entries
        self._resolver = resolver

    async def execute(self, work_id: int) -> WorkDetail:
        work = await self._works.get_by_id(work_id)
        if work is None:
            raise EntityNotFound("work", work_id)
        if self._resolver is not None:
            resolved = await self._resolver.resolve(work.composer)
            if resolved:
                work.composer_id, work.composer = resolved
        resources = await self._entries.list_by_work(work_id)
        summaries = [
            ResourceSummary(
                relative_path=e.relative_path,
                format=_format_of(e.relative_path),
                file_id=e.file_id,
                available=e.file_id is not None,
            )
            for e in resources
        ]
        genres = await self._works.get_genres(work_id)
        instruments = await self._works.get_instruments(work_id)
        parts_names = await self._works.get_parts(work_id)
        return WorkDetail(
            work=work,
            resources=summaries,
            genres=genres,
            instruments=instruments,
            parts_names=parts_names,
        )


class SearchWorksFull:
    """Búsqueda de Works completas (metadatos + recursos) sin llamadas N+1.

    Usa consultas por lote (una para recursos, unas pocas para las listas) en lugar de
    consultar por cada obra.
    """

    def __init__(
        self,
        works: WorkRepository,
        entries: ArchiveEntryRepository,
        resolver: ComposerResolver | None = None,
    ) -> None:
        self._works = works
        self._entries = entries
        self._resolver = resolver

    async def execute(self, query: str, *, limit: int = 50, offset: int = 0) -> list[WorkDetail]:
        query = (query or "").strip()
        if query:
            found = await self._works.search(query, limit=limit, offset=offset)
        else:
            found = await self._works.all_(limit=limit, offset=offset)
        if not found:
            return []

        if self._resolver is not None:
            resolved = await self._resolver.resolve_many([w.composer for w in found])
            for work in found:
                result = resolved.get(work.composer)
                if result:
                    work.composer_id, work.composer = result

        work_ids = [w.id for w in found if w.id is not None]
        if not work_ids:
            return []
        entries = await self._entries.list_by_work_ids(work_ids)
        by_work: dict[int, list] = {}
        for e in entries:
            by_work.setdefault(e.work_id, []).append(e)
        lists = await self._works.get_lists_bulk(work_ids)

        details: list[WorkDetail] = []
        for w in found:
            resources = [
                ResourceSummary(
                    relative_path=e.relative_path,
                    format=_format_of(e.relative_path),
                    file_id=e.file_id,
                    available=e.file_id is not None,
                )
                for e in by_work.get(w.id, [])
            ]
            wl = lists.get(w.id, WorkLists())
            details.append(
                WorkDetail(
                    work=w,
                    resources=resources,
                    genres=wl.genres,
                    instruments=wl.instruments,
                    parts_names=wl.parts_names,
                )
            )
        return details
