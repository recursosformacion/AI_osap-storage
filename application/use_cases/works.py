from __future__ import annotations

import os
from dataclasses import dataclass, field

from domain.entities.representation import Representation, Resource
from domain.entities.work import Work, WorkLists
from domain.exceptions import EntityNotFound
from domain.ports.archive_repositories import ArchiveEntryRepository
from domain.ports.representation_repository import RepresentationRepository
from domain.ports.work_repository import WorkRepository
from domain.services.composer_resolver import ComposerResolver


@dataclass(frozen=True)
class ResourceSummary:
    relative_path: str | None
    format: str | None
    file_id: int | None = None
    available: bool = False
    url: str | None = None
    id: int | None = None
    name: str | None = None
    status: str | None = None
    representation_id: int | None = None


@dataclass(frozen=True)
class RepresentationDetail:
    """Una representación de la obra con sus recursos."""

    representation: Representation
    resources: list[ResourceSummary] = field(default_factory=list)


@dataclass(frozen=True)
class WorkDetail:
    work: Work
    resources: list[ResourceSummary]
    genres: list[str]
    instruments: list[str]
    parts_names: list[str]
    voices: list[str] = field(default_factory=list)
    ensembles: list[str] = field(default_factory=list)
    representations: list[RepresentationDetail] = field(default_factory=list)


_FORMAT_NAMES = {
    ".mxl": "MusicXML",
    ".musicxml": "MusicXML",
    ".xml": "MusicXML",
    ".pdf": "PDF",
    ".mid": "MIDI",
    ".midi": "MIDI",
    ".mscz": "MuseScore",
}


def _format_of(name: str | None) -> str | None:
    if not name:
        return None
    suffix = os.path.splitext(name)[1].lower()
    return _FORMAT_NAMES.get(suffix, suffix.lstrip(".").upper() or None)


def _summary_of_resource(resource: Resource) -> ResourceSummary:
    return ResourceSummary(
        relative_path=resource.relative_path,
        format=_format_of(resource.relative_path or resource.name) or (resource.type or None),
        file_id=resource.file_id,
        available=resource.file_id is not None or bool(resource.url),
        url=resource.url,
        id=resource.id,
        name=resource.name or None,
        status=resource.status or None,
        representation_id=resource.representation_id,
    )


def _summary_of_entry(entry) -> ResourceSummary:
    """Compatibilidad: vista plana desde `archive_entries` (modelo antiguo)."""
    return ResourceSummary(
        relative_path=entry.relative_path,
        format=_format_of(entry.relative_path),
        file_id=entry.file_id,
        available=entry.file_id is not None,
        status=getattr(entry.status, "value", None),
    )


def _group_resources(
    representations: list[Representation], resources: list[Resource]
) -> tuple[list[RepresentationDetail], list[ResourceSummary]]:
    by_representation: dict[int, list[ResourceSummary]] = {}
    flat: list[ResourceSummary] = []
    for resource in resources:
        summary = _summary_of_resource(resource)
        by_representation.setdefault(resource.representation_id, []).append(summary)
        flat.append(summary)
    details = [
        RepresentationDetail(
            representation=rep, resources=by_representation.get(rep.id or -1, [])
        )
        for rep in representations
    ]
    return details, flat


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
                work.person_id, work.composer = result


class GetWork:
    """Devuelve una obra con sus representaciones y los recursos de cada una.

    Con `representations` usa el modelo nuevo (Work → Representation → Resource). Si no se
    inyecta, cae al modelo antiguo (`archive_entries`), que se conserva como compatibilidad.
    """

    def __init__(
        self,
        works: WorkRepository,
        entries: ArchiveEntryRepository | None = None,
        resolver: ComposerResolver | None = None,
        representations: RepresentationRepository | None = None,
    ) -> None:
        self._works = works
        self._entries = entries
        self._resolver = resolver
        self._representations = representations

    async def execute(self, work_id: int) -> WorkDetail:
        work = await self._works.get_by_id(work_id)
        if work is None:
            raise EntityNotFound("work", work_id)
        if self._resolver is not None:
            resolved = await self._resolver.resolve(work.composer)
            if resolved:
                work.person_id, work.composer = resolved

        if self._representations is not None:
            reps = await self._representations.list_by_work(work_id)
            resources = await self._representations.list_resources_by_work_ids([work_id])
            representations, summaries = _group_resources(reps, resources)
        else:
            entries = await self._entries.list_by_work(work_id) if self._entries else []
            summaries = [_summary_of_entry(e) for e in entries]
            representations = []

        genres = await self._works.get_genres(work_id)
        instruments = await self._works.get_instruments(work_id)
        parts_names = await self._works.get_parts(work_id)
        return WorkDetail(
            work=work,
            resources=summaries,
            genres=genres,
            instruments=instruments,
            parts_names=parts_names,
            voices=await self._works.get_voices(work_id),
            ensembles=await self._works.get_ensembles(work_id),
            representations=representations,
        )


class SearchWorksFull:
    """Búsqueda de Works completas (metadatos + representaciones/recursos) sin N+1.

    Usa consultas por lote (una para representaciones, una para recursos, unas pocas para las
    listas) en lugar de consultar por cada obra.
    """

    def __init__(
        self,
        works: WorkRepository,
        entries: ArchiveEntryRepository | None = None,
        resolver: ComposerResolver | None = None,
        representations: RepresentationRepository | None = None,
    ) -> None:
        self._works = works
        self._entries = entries
        self._resolver = resolver
        self._representations = representations

    async def execute(
        self, query: str, *, limit: int = 50, offset: int = 0, origins: list[str] | None = None
    ) -> list[WorkDetail]:
        query = (query or "").strip()
        if query:
            found = await self._works.search(query, limit=limit, offset=offset, origins=origins)
        else:
            found = await self._works.all_(limit=limit, offset=offset, origins=origins)
        if not found:
            return []

        if self._resolver is not None:
            resolved = await self._resolver.resolve_many([w.composer for w in found])
            for work in found:
                result = resolved.get(work.composer)
                if result:
                    work.person_id, work.composer = result

        work_ids = [w.id for w in found if w.id is not None]
        if not work_ids:
            return []

        reps_by_work: dict[int, list[Representation]] = {}
        resources_by_work: dict[int, list[Resource]] = {}
        legacy_by_work: dict[int, list] = {}
        if self._representations is not None:
            reps = await self._representations.list_by_work_ids(work_ids)
            resources = await self._representations.list_resources_by_work_ids(work_ids)
            for rep in reps:
                reps_by_work.setdefault(rep.works_id, []).append(rep)
            for resource in resources:
                if resource.work_id is not None:
                    resources_by_work.setdefault(resource.work_id, []).append(resource)
        elif self._entries is not None:
            for entry in await self._entries.list_by_work_ids(work_ids):
                legacy_by_work.setdefault(entry.work_id, []).append(entry)

        lists = await self._works.get_lists_bulk(work_ids)

        details: list[WorkDetail] = []
        for w in found:
            if self._representations is not None:
                w_reps = reps_by_work.get(w.id, [])
                w_resources = resources_by_work.get(w.id, [])
                representations, summaries = _group_resources(w_reps, w_resources)
            else:
                representations = []
                summaries = [_summary_of_entry(e) for e in legacy_by_work.get(w.id, [])]
            wl = lists.get(w.id, WorkLists())
            details.append(
                WorkDetail(
                    work=w,
                    resources=summaries,
                    genres=wl.genres,
                    instruments=wl.instruments,
                    parts_names=wl.parts_names,
                    voices=wl.voices,
                    ensembles=wl.ensembles,
                    representations=representations,
                )
            )
        return details
