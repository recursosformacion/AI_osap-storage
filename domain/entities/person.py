from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime

# Persona especial "Compositor sin indicar": las obras sin compositor (o que queden
# vacías) apuntan a esta identidad, que se define como una persona más del sistema.
UNKNOWN_PERSON = "Compositor sin indicar"
UNKNOWN_PERSON_ID = "00000000-0000-0000-0000-000000000001"

# NOTA DE MIGRACIÓN (2026-09-17): las entidades se renombran a `Person*`, pero los
# CAMPOS conservan el nombre histórico `person_id` para no romper el código que aún
# usa la nomenclatura de compositor. El renombrado de campos (`person_id` → `person_id`)
# queda como paso posterior (ver `docsNew/fork-plan-migracion.md` §9).


class PersonStatus:
    ACTIVE = "active"
    MERGED = "merged"


class PersonResolutionDecision:
    RESOLVED = "resolved"
    AMBIGUOUS = "ambiguous"
    NOT_FOUND = "not_found"
    AUTO_CORRECT = "auto_correct"
    PENDING_HUMAN = "pending_human"
    REJECTED = "rejected"


class PersonType:
    """Tipo de entidad que `Person` representa.

    - `person`: entidad humana real o imaginaria.
    - `anonymous`: atribución anónima (sin nombre).
    - `traditional`: obra tradicional/folclórica sin autor conocido.
    - `pseudonym`: nombre artístico sin identidad conocida.
    - `corporate`: entidad colectiva (orquesta, editorial, etc.).
    """

    PERSON = "person"
    ANONYMOUS = "anonymous"
    TRADITIONAL = "traditional"
    PSEUDONYM = "pseudonym"
    CORPORATE = "corporate"


@dataclass
class PersonResolution:
    """Trazabilidad de una recuperación de identidad de compositor de una obra.

    Guarda el compositor anterior (posiblemente sospechoso), el candidato recuperado
    desde la obra (título/catálogo + evidencia externa), la confianza y la decisión.
    El dato original corrupto NO se destruye: queda como `old_person_id` / evidencia.
    """

    work_id: int
    old_person_id: str | None = None
    candidate_person_id: str | None = None
    reason: str = ""
    evidence: str | None = None
    confidence: float = 0.0
    resolver_version: str = ""
    decision: str = PersonResolutionDecision.PENDING_HUMAN
    id: int | None = None
    created_at: datetime | None = None


@dataclass
class Person:
    """Identidad canónica de una persona (compositor) mantenida por Storage.

    `id` es un UUID estable y opaco; `name` es el nombre canónico que Storage
    devuelve en las Works. Los nombres procedentes de proveedores se resuelven
    contra la tabla de alias (ver `persons_aliases`).

    Añade: `visible` (1 = utilizable públicamente), `birth_year`/`death_year`,
    `cluster_id` (unidad de identidad), `review_reason` (motivo conservado) y
    `source_system` (maestro|app).

    Los campos `given_name`/`family_name`/`sort_name` provienen de la autoridad
    externa y se normalizan en la importación. `person_type` distingue
    personas reales de atribuciones anónimas/tradicionales/pseudónimo/corporativas.
    `attribution_note` conserva el texto original cuando `person_type != person`.
    """

    id: str
    name: str
    musicbrainz_id: str | None = None
    homepage: str | None = None
    status: str = PersonStatus.ACTIVE
    visible: bool = True
    birth_year: str | None = None
    death_year: str | None = None
    given_name: str | None = None
    family_name: str | None = None
    sort_name: str | None = None
    nationality: str | None = None
    image_url: str | None = None
    person_type: str = PersonType.PERSON
    attribution_note: str | None = None
    cluster_id: str | None = None
    review_reason: str | None = None
    source_system: str = "maestro"
    merged_into: str | None = None
    merged_at: datetime | None = None
    review_status: str = "not_reviewed"
    reviewed_at: datetime | None = None
    suspicious: bool = False
    suspicious_reason: str | None = None
    created_at: datetime | None = None
    updated_at: datetime | None = None


@dataclass
class PersonAlias:
    """Un nombre (alias) conocido que apunta a la identidad canónica de una persona.

    `normalized_alias` es la forma normalizada de `alias`. La restricción UNIQUE
    es por `(person_id, normalized_alias)`: el mismo alias puede existir en
    personas distintas (los homónimos no se fusionan por nombre), pero no se
    duplica dentro de la misma persona.
    """

    person_id: str
    alias: str
    normalized_alias: str
    name_type: str = "alias"
    language: str | None = None
    source: str = "musicbrainz"
    id: int | None = None
    created_at: datetime | None = None


@dataclass(frozen=True)
class PersonIdentifier:
    """Identificador externo de una persona (maestro).

    `is_identity_anchor` marca el identificador elegido como ancla de identidad
    por las reglas de resolución. Discogs nunca es ancla.
    """

    person_id: str
    id_type: str
    id_value: str
    is_identity_anchor: bool = False
    source: str = "musicbrainz"
    strength: str | None = None
    channels: list[str] | None = None
    confidence: float = 0.0
    retrieved_at: datetime | None = None


@dataclass(frozen=True)
class PersonEvidence:
    """Evidencia de construcción/resolución de una persona (maestro).

    `rule` es la regla que lo resolvió (p. ej. 07-viaf-multi-anchor, 07-review,
    creation, resolution). `anchor_type`/`anchor_value` siempre no-nulos.
    """

    person_id: str
    rule: str
    decision: str
    reason: str
    anchor_type: str = "none"
    anchor_value: str = "none"
    channels: list | None = None
    identifiers_used: list | None = None
    matcher_version: str = ""
    id: int | None = None
    created_at: datetime | None = None


@dataclass
class PersonCreationEvidence:
    """Trazabilidad de cómo una persona fue creada a partir de una obra.

    Referencia a la obra que provocó la creación (o, en su ausencia, la referencia
    al recurso original), los datos de autor extraídos originalmente y el proveedor.
    No se copia la obra; se conserva una referencia. La evidencia nunca se borra en
    una fusión: se redirige a la persona destino.
    """

    person_id: str
    extracted_author: str | None = None
    work_id: int | None = None
    work_title: str | None = None
    provider: str | None = None
    resource_reference: str | None = None
    id: int | None = None
    created_at: datetime | None = None


@dataclass(frozen=True)
class PersonSummary:
    """Fila ligera del listado administrativo (sin cargar aliases ni Works)."""

    id: str
    name: str
    status: str
    aliases_count: int = 0
    works_count: int = 0
    review_status: str = "not_reviewed"
    visible: bool = True
    given_name: str | None = None
    family_name: str | None = None
    sort_name: str | None = None
    nationality: str | None = None
    person_type: str = PersonType.PERSON
    biography_summary: str | None = None
    biography_era: str | None = None
    biography_nationality: str | None = None


@dataclass(frozen=True)
class PersonDetail:
    """Detalle administrativo de una persona."""

    id: str
    name: str
    status: str
    aliases: list[str] = field(default_factory=list)
    works_count: int = 0
    merged_into: str | None = None
    merged_at: datetime | None = None
    review_status: str = "not_reviewed"
    reviewed_at: datetime | None = None
    visible: bool = True
    birth_year: str | None = None
    death_year: str | None = None
    homepage: str | None = None
    cluster_id: str | None = None
    review_reason: str | None = None
    given_name: str | None = None
    family_name: str | None = None
    sort_name: str | None = None
    nationality: str | None = None
    image_url: str | None = None
    person_type: str = PersonType.PERSON
    attribution_note: str | None = None
    biography_summary: str | None = None
    biography_era: str | None = None
    biography_nationality: str | None = None
    biography_key_works: list[str] = field(default_factory=list)
    biography_key_fact: str | None = None
    biography_references: list[dict[str, str]] = field(default_factory=list)
    identifiers: list[PersonIdentifier] = field(default_factory=list)
    evidence: list[PersonEvidence] = field(default_factory=list)
    creation_evidence: list[PersonCreationEvidence] = field(default_factory=list)


@dataclass(frozen=True)
class PersonWorkRef:
    """Referencia ligera de una Work asociada a una persona."""

    work_id: int
    title: str | None = None
    person_id: str | None = None


@dataclass(frozen=True)
class MergePersonsResult:
    target_id: str
    sources_merged: list[str]
    aliases_transferred: int
    works_moved: int
    merge_operation_id: str
