from __future__ import annotations

from domain.entities.rism import RismSource
from domain.ports.rism_source_repository import RismSourceRepository


class SearchRismSources:
    """Busca en el corpus RISM local (read-only)."""

    def __init__(self, sources: RismSourceRepository) -> None:
        self._sources = sources

    async def execute(self, query: str, *, limit: int = 50, offset: int = 0) -> list[RismSource]:
        return await self._sources.search(query, limit=limit, offset=offset)
