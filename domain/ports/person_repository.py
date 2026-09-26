from __future__ import annotations

from datetime import datetime
from typing import Protocol

from domain.entities.person import (
    MergePersonsResult,
    Person,
    PersonAlias,
    PersonCreationEvidence,
    PersonDetail,
    PersonEvidence,
    PersonIdentifier,
    PersonResolution,
    PersonSummary,
    PersonWorkRef,
)

# NOTA DE MIGRACIÓN (2026-09-17): el puerto pasa a `PersonRepository`, pero los NOMBRES DE
# MÉTODO conservan la nomenclatura histórica (`rename_composer`, `update_composer`…) para no
# romper implementaciones ni llamadas. Su renombrado queda como paso posterior.


class PersonRepository(Protocol):
    """Acceso a la identidad canónica de personas y sus alias."""

    async def create(self, composer: Person) -> Person: ...

    async def ensure_unknown_composer(self) -> Person:
        """Garantiza que existe la persona 'Compositor sin indicar' (id estable)."""

    async def get_by_id(self, person_id: str) -> Person | None: ...

    async def get_by_name(self, name: str) -> Person | None:
        """Persona activa con ese nombre exacto (insensible a mayúsculas) o None."""

    async def add_alias(self, person_id: str, alias: str, normalized_alias: str) -> PersonAlias:
        """Añade un alias. La UNIQUE es por (person_id, normalized_alias): no se
        duplica dentro de la misma persona; el mismo alias puede existir en otras."""

    async def list_identifiers(self, person_id: str) -> list[PersonIdentifier]:
        """Identificadores externos de la persona (maestro)."""

    async def find_by_identifier(self, id_type: str, id_value: str) -> list[Person]:
        """SELECT previo: personas con ese identificador (puede haber varias).

        Es la guarda de idempotencia ANTES de crear una Person nueva por
        identificador: no se confía solo en el UNIQUE por persona."""

    async def add_identifier(
        self, person_id: str, id_type: str, id_value: str, *,
        is_identity_anchor: bool = False, source: str = "musicbrainz",
        strength: str | None = None, channels: list[str] | None = None,
        confidence: float = 0.0, retrieved_at: datetime | None = None,
    ) -> None:
        """Inserta un identificador (idempotente por (person_id, id_type, id_value))."""

    async def add_evidence(
        self, person_id: str, *, rule: str, decision: str, reason: str,
        anchor_type: str = "none", anchor_value: str = "none",
        channels: list | None = None, identifiers_used: list | None = None,
        matcher_version: str = "",
    ) -> None:
        """Inserta una evidencia (idempotente por (person_id, rule, anchor)."""

    async def list_evidence(self, person_id: str) -> list[PersonEvidence]:
        """Evidencia de construcción/resolución de la persona (maestro)."""

    async def resolve_by_normalized(self, normalized: str) -> tuple[str, str] | None:
        """Devuelve (person_id, nombre canónico) para una forma normalizada, o None."""

    async def resolve_many_by_normalized(
        self, normalized: list[str]
    ) -> dict[str, tuple[str, str]]:
        """Resuelve varias formas normalizadas en una sola consulta (sin N+1)."""

    async def list_aliases(self, person_id: str) -> list[PersonAlias]: ...

    async def add_creation_evidence(
        self,
        person_id: str,
        *,
        work_id: int | None = None,
        work_title: str | None = None,
        extracted_author: str | None = None,
        provider: str | None = None,
        resource_reference: str | None = None,
    ) -> PersonCreationEvidence:
        """Asocia una obra/referencia como evidencia de creación de una persona."""

    async def list_creation_evidence(self, person_id: str) -> list[PersonCreationEvidence]:
        """Evidencia de creación de la persona (trazabilidad). Nunca se borra en una fusión."""

    async def backfill_creation_evidence(self, provider: str | None = None) -> int:
        """Crea evidencia de creación para personas activas que aún no la tienen,
        derivada de una de sus Works. Idempotente. Devuelve cuántas se crearon."""

    async def prune_zero_work_composers(self) -> int:
        """Borra personas activas sin ninguna obra asociada (salvo 'Compositor sin
        indicar'). Devuelve cuántas se eliminaron."""

    async def list_summaries(
        self, *, limit: int, offset: int, q: str | None = None, review: str | None = None,
        visible: str = "visible",
    ) -> list[PersonSummary]:
        """Lista personas (paginado). `visible` = visible|hidden|all:
        visible → visible=1 · hidden → visible=0 (candidatas y fusionadas) ·
        all → todas (incl. merged). Si `q`, filtra por nombre/alias.
        Si `review`, filtra por review_status (correct/false/pending)."""

    async def count(
        self, q: str | None = None, review: str | None = None, visible: str = "visible"
    ) -> int:
        """Cuenta personas (mismo criterio de filtro que `list_summaries`)."""

    async def review_counts(self) -> dict[str, int]:
        """Conteo de personas activas por review_status (total, correct, incorrect, reviewed, not_reviewed)."""

    async def set_review_status(self, person_id: str, review_status: str) -> None:
        """Marca el estado de revisión de una persona (correct/false/pending)."""

    async def set_musicbrainz_id(self, person_id: str, musicbrainz_id: str | None) -> None:
        """Guarda el identificador del artista en MusicBrainz (trazabilidad)."""

    async def set_suspicious(self, person_id: str, suspicious: bool, reason: str | None = None) -> None:
        """Marca una persona como sospechosa (con motivo) o la desmarca."""

    async def record_resolution(self, resolution: PersonResolution) -> PersonResolution:
        """Guarda una recuperación de identidad (evidencia/auditoría)."""

    async def list_resolutions(self, work_id: int) -> list[PersonResolution]:
        """Resoluciones de identidad registradas para una obra."""

    async def rename_composer(self, person_id: str, new_name: str) -> None:
        """Actualiza el nombre canónico de una persona y su alias canónico."""

    async def update_composer(
        self, person_id: str, *,
        name: str | None = None,
        birth_year: str | None = None,
        death_year: str | None = None,
        homepage: str | None = None,
        given_name: str | None = None,
        family_name: str | None = None,
        sort_name: str | None = None,
        nationality: str | None = None,
        image_url: str | None = None,
        person_type: str | None = None,
        attribution_note: str | None = None,
        visible: bool | None = None,
        cluster_id: str | None = None,
        review_status: str | None = None,
        review_reason: str | None = None,
        musicbrainz_id: str | None = None,
        status: str | None = None,
    ) -> None:
        """Edita campos de identidad de una persona (solo los que no sean None)."""

    async def get_biography(self, person_id: str) -> PersonDetail | None:
        """Devuelve el detalle con la biografía (alias de get_detail)."""

    async def upsert_biography(
        self, person_id: str, *,
        summary: str | None = None,
        era: str | None = None,
        nationality: str | None = None,
        key_works: list[str] | None = None,
        key_fact: str | None = None,
        references: list[dict[str, str]] | None = None,
    ) -> None:
        """Crea o actualiza la biografía de una persona en composer_biographies."""

    async def delete_identifier(self, person_id: str, identifier_id: int) -> None:
        """Elimina un identificador externo de una persona."""

    async def list_pending_review(self, *, limit: int, offset: int) -> list[PersonSummary]:
        """Personas activas pendientes de revisión (para clasificación heurística)."""

    async def list_suspicious(self, *, limit: int, offset: int) -> list[PersonSummary]:
        """Personas activas marcadas como sospechosas (para recuperación de identidad)."""

    async def get_detail(self, person_id: str) -> PersonDetail | None:
        """Detalle administrativo: aliases, works_count, estado y referencia de fusión."""

    async def list_works(
        self, person_id: str, *, limit: int, offset: int
    ) -> list[PersonWorkRef]:
        """Works asociadas a una persona (paginado)."""

    async def merge(
        self, target_id: str, source_ids: list[str], *, merged_by: str | None = None
    ) -> MergePersonsResult:
        """Fusiona `source_ids` dentro de `target_id` de forma atómica (transaccional)."""

    async def move_alias(self, alias_id: int, target_id: str, from_person_id: str) -> PersonAlias:
        """Mueve un alias a otra persona y reasigna las obras que lo aportaron (no se borra)."""

    async def promote_alias(self, alias_id: int, from_person_id: str) -> Person:
        """Promueve un alias a su propia Person y reasigna las obras que lo aportaron."""

    async def set_attribution(self, person_ids: list[str], attribution_type: str) -> int:
        """Convierte personas a atribución: obras guardan tipo/nota y se retiran."""
