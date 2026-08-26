from __future__ import annotations

from dataclasses import dataclass

from domain.entities.work import Work, WorkLists
from domain.exceptions import EntityNotFound
from domain.ports.work_repository import WorkRepository


@dataclass(frozen=True)
class WorkAdminDetail:
    work: Work
    tags: list[str]
    genres: list[str]
    instruments: list[str]
    parts_names: list[str]


@dataclass(frozen=True)
class WorkAdminListResult:
    items: list[WorkAdminDetail]
    total: int


class ListWorksAdmin:
    """Listado administrativo paginado de obras (sin resolver identidad)."""

    def __init__(self, works: WorkRepository) -> None:
        self._works = works

    async def execute(self, *, limit: int, offset: int, q: str | None = None) -> WorkAdminListResult:
        if q and (q := q.strip()):
            found = await self._works.search(q, limit=limit, offset=offset)
            total = len(found)
        else:
            found = await self._works.all_(limit=limit, offset=offset)
            total = await self._works.count()
        work_ids = [w.id for w in found if w.id is not None]
        lists = await self._works.get_lists_bulk(work_ids) if work_ids else {}
        items = [
            WorkAdminDetail(
                work=w,
                tags=lists.get(w.id, WorkLists()).tags,
                genres=lists.get(w.id, WorkLists()).genres,
                instruments=lists.get(w.id, WorkLists()).instruments,
                parts_names=lists.get(w.id, WorkLists()).parts_names,
            )
            for w in found
        ]
        return WorkAdminListResult(items=items, total=total)


class GetWorkAdmin:
    """Detalle administrativo de una obra (metadatos + listas, sin recursos)."""

    def __init__(self, works: WorkRepository) -> None:
        self._works = works

    async def execute(self, work_id: int) -> WorkAdminDetail:
        work = await self._works.get_by_id(work_id)
        if work is None:
            raise EntityNotFound("work", work_id)
        tags = await self._works.get_tags(work_id)
        genres = await self._works.get_genres(work_id)
        instruments = await self._works.get_instruments(work_id)
        parts = await self._works.get_parts(work_id)
        return WorkAdminDetail(work=work, tags=tags, genres=genres,
                               instruments=instruments, parts_names=parts)


class UpdateWorkAdmin:
    """Edita los metadatos de una obra y sus listas (tags/genres/instruments/parts)."""

    def __init__(self, works: WorkRepository) -> None:
        self._works = works

    async def execute(self, work_id: int, *, work: Work, tags: list[str] | None = None,
                      genres: list[str] | None = None, instruments: list[str] | None = None,
                      parts: list[str] | None = None) -> WorkAdminDetail:
        existing = await self._works.get_by_id(work_id)
        if existing is None:
            raise EntityNotFound("work", work_id)
        work.id = work_id
        await self._works.update(work)
        if tags is not None:
            await self._works.replace_tags(work_id, tags)
        if genres is not None:
            await self._works.replace_genres(work_id, genres)
        if instruments is not None:
            await self._works.replace_instruments(work_id, instruments)
        if parts is not None:
            await self._works.replace_parts(work_id, parts)
        updated = await self._works.get_by_id(work_id)
        assert updated is not None
        tags = await self._works.get_tags(work_id)
        genres = await self._works.get_genres(work_id)
        instruments = await self._works.get_instruments(work_id)
        parts_names = await self._works.get_parts(work_id)
        return WorkAdminDetail(work=updated, tags=tags, genres=genres,
                               instruments=instruments, parts_names=parts_names)
