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

    async def execute(
        self, *, limit: int, offset: int, q: str | None = None, review: str | None = None
    ) -> ComposerListResult:
        items = await self._composers.list_summaries(limit=limit, offset=offset, q=q, review=review)
        total = await self._composers.count(q=q, review=review)
        return ComposerListResult(items=items, total=total)


class ReviewComposer:
    """Marca el estado de revisión de un compositor (correct/false/pending)."""

    _VALID = {"correct", "incorrect", "reviewed", "not_reviewed"}

    def __init__(self, composers: ComposerRepository) -> None:
        self._composers = composers

    async def execute(self, composer_id: str, review_status: str) -> ComposerDetail:
        if review_status not in self._VALID:
            raise ValueError(f"review_status must be one of {sorted(self._VALID)}")
        if await self._composers.get_detail(composer_id) is None:
            raise EntityNotFound("composer", composer_id)
        await self._composers.set_review_status(composer_id, review_status)
        detail = await self._composers.get_detail(composer_id)
        assert detail is not None
        return detail


class ComposerReviewStats:
    """Conteo de compositores por estado de revisión (para el resumen de admin)."""

    def __init__(self, composers: ComposerRepository) -> None:
        self._composers = composers

    async def execute(self) -> dict[str, int]:
        return await self._composers.review_counts()


class ClassifyComposers:
    """Clasifica heurísticamente los compositores pendientes como correct/false."""

    def __init__(self, composers: ComposerRepository) -> None:
        self._composers = composers

    async def execute(self, *, limit: int = 1000) -> dict[str, int]:
        from domain.services.composer_quality import (
            REVIEW_CORRECT,
            REVIEW_INCORRECT,
            classify_composer_name,
        )

        counts = {REVIEW_CORRECT: 0, REVIEW_INCORRECT: 0}
        # Pasadas repetidas hasta converger: al marcar un compositor correct/incorrect
        # sale del conjunto not_reviewed y la paginación por offset se desplaza, saltando
        # compositores. Se repite hasta una pasada sin cambios.
        while True:
            pass_changes = 0
            offset = 0
            while True:
                pending = await self._composers.list_pending_review(limit=limit, offset=offset)
                if not pending:
                    break
                for item in pending:
                    verdict = classify_composer_name(item.name)
                    if verdict in counts:
                        await self._composers.set_review_status(item.id, verdict)
                        counts[verdict] += 1
                        pass_changes += 1
                offset += limit
            if pass_changes == 0:
                break
        return counts


class CleanComposerNames:
    """Limpia los nombres de compositor existentes y fusiona colisiones.

    Aplica `clean_composer_name` a cada compositor activo. Si el nombre limpio coincide con
    otro compositor existente, se fusiona este en aquel (dejándolo `merged`). Si no hay
    colisión, se renombra con el nombre limpio.
    """

    def __init__(self, composers: ComposerRepository) -> None:
        self._composers = composers

    async def execute(self, *, limit: int = 1000) -> dict[str, int]:
        from domain.services.composer_names import normalize_composer_name
        from domain.services.composer_quality import clean_composer_name

        total = {"changed": 0, "renamed": 0, "merged": 0}
        while True:
            changed = renamed = merged = 0
            offset = 0
            while True:
                batch = await self._composers.list_summaries(limit=limit, offset=offset)
                if not batch:
                    break
                for item in batch:
                    cleaned = clean_composer_name(item.name)
                    if not cleaned:
                        continue
                    if cleaned == item.name:
                        continue
                    changed += 1
                    existing = await self._composers.get_by_name(cleaned)
                    if existing is None:
                        resolved = await self._composers.resolve_by_normalized(
                            normalize_composer_name(cleaned)
                        )
                        if resolved is not None:
                            existing = await self._composers.get_by_id(resolved[0])
                    if existing is not None and existing.id != item.id:
                        await self._composers.merge(existing.id, [item.id])
                        merged += 1
                    else:
                        await self._composers.rename_composer(item.id, cleaned)
                        renamed += 1
                offset += limit
            total["changed"] += changed
            total["renamed"] += renamed
            total["merged"] += merged
            if changed == 0:
                break
        return total


class PruneComposers:
    """Elimina compositores activos sin ninguna obra asociada (fantasmas).

    Un compositor sin obras no es un compositor: no tiene ninguna obra que lo respalde.
    Se elimina (salvo 'Compositor sin indicar'), junto con sus alias y evidencia (cascade).
    """

    def __init__(self, composers: ComposerRepository) -> None:
        self._composers = composers

    async def execute(self) -> int:
        return await self._composers.prune_zero_work_composers()


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


class CreateComposer:
    """Crea un compositor nuevo con el nombre dado (para fusiones hacia compositores inexistentes)."""

    def __init__(self, composers: ComposerRepository) -> None:
        self._composers = composers

    async def execute(self, name: str) -> ComposerSummary:
        from domain.entities.composer import Composer

        name = (name or "").strip()
        if not name:
            raise ValueError("name cannot be empty")
        existing = await self._composers.get_by_name(name)
        if existing is not None:
            return ComposerSummary(
                id=existing.id,
                name=existing.name,
                status=existing.status,
                aliases_count=0,
                works_count=0,
            )
        created = await self._composers.create(Composer(id="", name=name))
        return ComposerSummary(
            id=created.id,
            name=created.name,
            status=created.status,
            aliases_count=0,
            works_count=0,
        )
