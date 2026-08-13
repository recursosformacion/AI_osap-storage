from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime

# Composer especial "Compositor sin indicar": las obras sin compositor (o que queden
# vacías) apuntan a esta identidad, que se define como un compositor más del sistema.
UNKNOWN_COMPOSER = "Compositor sin indicar"
UNKNOWN_COMPOSER_ID = "00000000-0000-0000-0000-000000000001"


class ComposerStatus:
    ACTIVE = "active"
    MERGED = "merged"


class ComposerResolutionDecision:
    RESOLVED = "resolved"
    AMBIGUOUS = "ambiguous"
    NOT_FOUND = "not_found"
    AUTO_CORRECT = "auto_correct"
    PENDING_HUMAN = "pending_human"
    REJECTED = "rejected"


@dataclass
class ComposerResolution:
    """Trazabilidad de una recuperación de identidad de compositor de una obra.

    Guarda el compositor anterior (posiblemente sospechoso), el candidato recuperado
    desde la obra (título/catálogo + evidencia externa), la confianza y la decisión.
    El dato original corrupto NO se destruye: queda como `old_composer_id` / evidencia.
    """

    work_id: int
    old_composer_id: str | None = None
    candidate_composer_id: str | None = None
    reason: str = ""
    evidence: str | None = None
    confidence: float = 0.0
    resolver_version: str = ""
    decision: str = ComposerResolutionDecision.PENDING_HUMAN
    id: int | None = None
    created_at: datetime | None = None


@dataclass
class Composer:
    """Identidad canónica de un compositor mantenida por Storage.

    `id` es un UUID estable y opaco; `name` es el nombre canónico que Storage
    devuelve en las Works. Los nombres procedentes de proveedores se resuelven
    contra la tabla de alias (ver composer_aliases).
    """

    id: str
    name: str
    musicbrainz_id: str | None = None
    status: str = ComposerStatus.ACTIVE
    merged_into: str | None = None
    merged_at: datetime | None = None
    review_status: str = "not_reviewed"
    reviewed_at: datetime | None = None
    suspicious: bool = False
    suspicious_reason: str | None = None
    created_at: datetime | None = None
    updated_at: datetime | None = None


@dataclass
class ComposerAlias:
    """Un nombre (alias) conocido que apunta a la identidad canónica de un compositor.

    `normalized_alias` es la forma normalizada de `alias`, usada para la resolución
    determinista. Un mismo `normalized_alias` no puede apuntar a dos compositores
    (restricción UNIQUE en BD).
    """

    composer_id: str
    alias: str
    normalized_alias: str
    id: int | None = None
    created_at: datetime | None = None


@dataclass
class ComposerCreationEvidence:
    """Trazabilidad de cómo un compositor fue creado a partir de una obra.

    Referencia a la obra que provocó la creación (o, en su ausencia, la referencia
    al recurso original), los datos de autor extraídos originalmente y el proveedor.
    No se copia la obra; se conserva una referencia. La evidencia nunca se borra en
    una fusión: se redirige al compositor destino.
    """

    composer_id: str
    extracted_author: str | None = None
    work_id: int | None = None
    work_title: str | None = None
    provider: str | None = None
    resource_reference: str | None = None
    id: int | None = None
    created_at: datetime | None = None


@dataclass(frozen=True)
class ComposerSummary:
    """Fila ligera del listado administrativo (sin cargar aliases ni Works)."""

    id: str
    name: str
    status: str
    aliases_count: int = 0
    works_count: int = 0
    review_status: str = "not_reviewed"


@dataclass(frozen=True)
class ComposerDetail:
    """Detalle administrativo de un compositor."""

    id: str
    name: str
    status: str
    aliases: list[str] = field(default_factory=list)
    works_count: int = 0
    merged_into: str | None = None
    merged_at: datetime | None = None
    review_status: str = "not_reviewed"
    reviewed_at: datetime | None = None
    creation_evidence: list[ComposerCreationEvidence] = field(default_factory=list)


@dataclass(frozen=True)
class ComposerWorkRef:
    """Referencia ligera de una Work asociada a un compositor."""

    work_id: int
    title: str | None = None
    composer_id: str | None = None


@dataclass(frozen=True)
class MergeComposersResult:
    target_id: str
    sources_merged: list[str]
    aliases_transferred: int
    works_moved: int
    merge_operation_id: str
