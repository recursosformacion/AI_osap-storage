from __future__ import annotations

from typing import Protocol

from domain.entities.composer import (
    Composer,
    ComposerAlias,
    ComposerDetail,
    ComposerSummary,
    ComposerWorkRef,
    MergeComposersResult,
)


class ComposerRepository(Protocol):
    """Acceso a la identidad canónica de compositores y sus alias."""

    async def create(self, composer: Composer) -> Composer: ...

    async def get_by_id(self, composer_id: str) -> Composer | None: ...

    async def add_alias(self, composer_id: str, alias: str, normalized_alias: str) -> ComposerAlias:
        """Añade un alias. Debe fallar si `normalized_alias` ya apunta a otro compositor."""

    async def resolve_by_normalized(self, normalized: str) -> tuple[str, str] | None:
        """Devuelve (composer_id, nombre canónico) para una forma normalizada, o None."""

    async def resolve_many_by_normalized(
        self, normalized: list[str]
    ) -> dict[str, tuple[str, str]]:
        """Resuelve varias formas normalizadas en una sola consulta (sin N+1)."""

    async def list_aliases(self, composer_id: str) -> list[ComposerAlias]: ...

    async def list_summaries(
        self, *, limit: int, offset: int, q: str | None = None
    ) -> list[ComposerSummary]:
        """Lista compositores activos (paginado). Si `q`, filtra por nombre/alias."""

    async def count(self, q: str | None = None) -> int:
        """Cuenta compositores activos (mismo criterio de filtro que `list_summaries`)."""

    async def get_detail(self, composer_id: str) -> ComposerDetail | None:
        """Detalle administrativo: aliases, works_count, estado y referencia de fusión."""

    async def list_works(
        self, composer_id: str, *, limit: int, offset: int
    ) -> list[ComposerWorkRef]:
        """Works asociadas a un compositor (paginado)."""

    async def merge(
        self, target_id: str, source_ids: list[str], *, merged_by: str | None = None
    ) -> MergeComposersResult:
        """Fusiona `source_ids` dentro de `target_id` de forma atómica (transaccional)."""
