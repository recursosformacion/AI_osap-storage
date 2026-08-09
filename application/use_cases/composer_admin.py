from __future__ import annotations

from dataclasses import dataclass

from domain.entities.composer import (
    ComposerDetail,
    ComposerSummary,
    ComposerWorkRef,
    MergeComposersResult,
)
from domain.exceptions import EntityNotFound
from domain.ports.composer_repository import ComposerRepository


@dataclass(frozen=True)
class ComposerListResult:
    items: list[ComposerSummary]
    total: int


class ListComposers:
    """Listado administrativo paginado de compositores activos (con búsqueda por nombre/alias)."""

    def __init__(self, composers: ComposerRepository) -> None:
        self._composers = composers

    async def execute(self, *, limit: int, offset: int, q: str | None = None) -> ComposerListResult:
        items = await self._composers.list_summaries(limit=limit, offset=offset, q=q)
        total = await self._composers.count(q=q)
        return ComposerListResult(items=items, total=total)


class GetComposerDetail:
    def __init__(self, composers: ComposerRepository) -> None:
        self._composers = composers

    async def execute(self, composer_id: str) -> ComposerDetail:
        detail = await self._composers.get_detail(composer_id)
        if detail is None:
            raise EntityNotFound("composer", composer_id)
        return detail


class GetComposerWorks:
    def __init__(self, composers: ComposerRepository) -> None:
        self._composers = composers

    async def execute(
        self, composer_id: str, *, limit: int, offset: int
    ) -> tuple[list[ComposerWorkRef], int]:
        if await self._composers.get_detail(composer_id) is None:
            raise EntityNotFound("composer", composer_id)
        works = await self._composers.list_works(composer_id, limit=limit, offset=offset)
        detail = await self._composers.get_detail(composer_id)
        return works, (detail.works_count if detail else 0)


class MergeComposers:
    """Fusión manual de uno o varios compositores dentro de un target (atómica)."""

    def __init__(self, composers: ComposerRepository) -> None:
        self._composers = composers

    async def execute(
        self, target_id: str, source_ids: list[str], *, merged_by: str | None = None
    ) -> MergeComposersResult:
        return await self._composers.merge(target_id, source_ids, merged_by=merged_by)
