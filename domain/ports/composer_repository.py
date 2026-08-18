from __future__ import annotations

from typing import Protocol

from domain.entities.composer import (
    Composer,
    ComposerAlias,
    ComposerCreationEvidence,
    ComposerDetail,
    ComposerEvidence,
    ComposerIdentifier,
    ComposerResolution,
    ComposerSummary,
    ComposerWorkRef,
    MergeComposersResult,
)


class ComposerRepository(Protocol):
    """Acceso a la identidad canónica de compositores y sus alias."""

    async def create(self, composer: Composer) -> Composer: ...

    async def ensure_unknown_composer(self) -> Composer:
        """Garantiza que existe el compositor 'Compositor sin indicar' (id estable)."""

    async def get_by_id(self, composer_id: str) -> Composer | None: ...

    async def get_by_name(self, name: str) -> Composer | None:
        """Compositor activo con ese nombre exacto (insensible a mayúsculas) o None."""

    async def add_alias(self, composer_id: str, alias: str, normalized_alias: str) -> ComposerAlias:
        """Añade un alias. La UNIQUE es por (composer_id, normalized_alias): no se
        duplica dentro de la misma persona; el mismo alias puede existir en otras."""

    async def list_identifiers(self, composer_id: str) -> list[ComposerIdentifier]:
        """Identificadores externos del compositor (maestro)."""

    async def find_by_identifier(self, id_type: str, id_value: str) -> list[Composer]:
        """SELECT previo: compositores con ese identificador (puede haber varios).

        Es la guarda de idempotencia ANTES de crear un Composer nuevo por
        identificador: no se confía solo en el UNIQUE por compositor."""

    async def add_identifier(
        self, composer_id: str, id_type: str, id_value: str, *,
        is_identity_anchor: bool = False, source: str = "musicbrainz",
        strength: str | None = None, channels: list[str] | None = None,
    ) -> None:
        """Inserta un identificador (idempotente por (composer_id, id_type, id_value))."""

    async def add_evidence(
        self, composer_id: str, *, rule: str, decision: str, reason: str,
        anchor_type: str = "none", anchor_value: str = "none",
        channels: list | None = None, identifiers_used: list | None = None,
        matcher_version: str = "",
    ) -> None:
        """Inserta una evidencia (idempotente por (composer_id, rule, anchor)."""

    async def list_evidence(self, composer_id: str) -> list[ComposerEvidence]:
        """Evidencia de construcción/resolución del compositor (maestro)."""

    async def resolve_by_normalized(self, normalized: str) -> tuple[str, str] | None:
        """Devuelve (composer_id, nombre canónico) para una forma normalizada, o None."""

    async def resolve_many_by_normalized(
        self, normalized: list[str]
    ) -> dict[str, tuple[str, str]]:
        """Resuelve varias formas normalizadas en una sola consulta (sin N+1)."""

    async def list_aliases(self, composer_id: str) -> list[ComposerAlias]: ...

    async def add_creation_evidence(
        self,
        composer_id: str,
        *,
        work_id: int | None = None,
        work_title: str | None = None,
        extracted_author: str | None = None,
        provider: str | None = None,
        resource_reference: str | None = None,
    ) -> ComposerCreationEvidence:
        """Asocia una obra/referencia como evidencia de creación de un compositor."""

    async def list_creation_evidence(self, composer_id: str) -> list[ComposerCreationEvidence]:
        """Evidencia de creación del compositor (trazabilidad). Nunca se borra en una fusión."""

    async def backfill_creation_evidence(self, provider: str | None = None) -> int:
        """Crea evidencia de creación para compositores activos que aún no la tienen,
        derivada de una de sus Works. Idempotente. Devuelve cuántas se crearon."""

    async def prune_zero_work_composers(self) -> int:
        """Borra compositores activos sin ninguna obra asociada (salvo 'Compositor sin
        indicar'). Devuelve cuántos se eliminaron."""

    async def list_summaries(
        self, *, limit: int, offset: int, q: str | None = None, review: str | None = None,
        visible: str = "visible",
    ) -> list[ComposerSummary]:
        """Lista compositores (paginado). `visible` = visible|hidden|all:
        visible → visible=1 · hidden → visible=0 (candidatos y fusionados) ·
        all → todos (incl. merged). Si `q`, filtra por nombre/alias.
        Si `review`, filtra por review_status (correct/false/pending)."""

    async def count(
        self, q: str | None = None, review: str | None = None, visible: str = "visible"
    ) -> int:
        """Cuenta compositores (mismo criterio de filtro que `list_summaries`)."""

    async def review_counts(self) -> dict[str, int]:
        """Conteo de compositores activos por review_status (total, correct, incorrect, reviewed, not_reviewed)."""

    async def set_review_status(self, composer_id: str, review_status: str) -> None:
        """Marca el estado de revisión de un compositor (correct/false/pending)."""

    async def set_musicbrainz_id(self, composer_id: str, musicbrainz_id: str | None) -> None:
        """Guarda el identificador del artista en MusicBrainz (trazabilidad)."""

    async def set_suspicious(self, composer_id: str, suspicious: bool, reason: str | None = None) -> None:
        """Marca un compositor como sospechoso (con motivo) o lo desmarca."""

    async def record_resolution(self, resolution: ComposerResolution) -> ComposerResolution:
        """Guarda una recuperación de identidad (evidencia/auditoría)."""

    async def list_resolutions(self, work_id: int) -> list[ComposerResolution]:
        """Resoluciones de identidad registradas para una obra."""

    async def rename_composer(self, composer_id: str, new_name: str) -> None:
        """Actualiza el nombre canónico de un compositor y su alias canónico."""

    async def list_pending_review(self, *, limit: int, offset: int) -> list[ComposerSummary]:
        """Compositores activos pendientes de revisión (para clasificación heurística)."""

    async def list_suspicious(self, *, limit: int, offset: int) -> list[ComposerSummary]:
        """Compositores activos marcados como sospechosos (para recuperación de identidad)."""

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
