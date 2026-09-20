from __future__ import annotations

from dataclasses import dataclass, field

# Resultados de una regla
APPLIED = "applied"
BLOCKED = "blocked"
REVIEW = "review"

# Niveles (según docsNew/diseño-resolutor-agrupacion.md: solo dos resoluciones)
LEVEL_RESOURCE_REPRESENTATION = "resource->representation"
LEVEL_REPRESENTATION_WORK = "representation->work"

# Identificadores de regla
ORIGIN_IDENTITY = "origin_identity"
ORIGIN_IDENTITY_MISSING = "origin_identity_missing"
ORIGIN_METADATA = "origin_metadata"
AXES_CONFIRM = "axes_confirm"
AXES_CONFLICT_REVIEW = "axes_conflict_review"
WORK_IDENTITY = "work_identity"
CATALOGUE_CONFLICT = "catalogue_conflict"
COMPOSER_MISMATCH = "composer_mismatch"
INSUFFICIENT_EVIDENCE = "insufficient_evidence"
AMBIGUOUS_CANDIDATES = "ambiguous_candidates"
RISM_ATTRIBUTION = "rism_attribution"
RISM_AMBIGUOUS = "rism_ambiguous"
RISM_UNCLASSIFIED = "rism_unclassified"


@dataclass(frozen=True)
class AxisValues:
    """Ejes musicales: criterio interno para resolver la representación (no un nivel)."""

    voicing: tuple[str, ...] = ()
    ensembles: tuple[str, ...] = ()
    instruments: tuple[str, ...] = ()
    languages: tuple[str, ...] = ()
    key: str | None = None

    def as_dict(self) -> dict[str, object]:
        return {
            "voicing": list(self.voicing),
            "ensembles": list(self.ensembles),
            "instruments": list(self.instruments),
            "languages": list(self.languages),
            "key": self.key,
        }


@dataclass(frozen=True)
class ResourceEvidence:
    """Evidencia persistente de un recurso y su contexto de origen/obra."""

    resource_id: int
    resource_type: str
    representation_id: int | None
    origin: str
    origin_id: str | None
    license: str
    editors: tuple[str, ...]
    work_id: int
    title: str | None
    catalogue: str | None
    composer: str | None
    composer_id: str | None = None
    composer_aliases: tuple[str, ...] = ()
    axes: AxisValues = field(default_factory=AxisValues)


@dataclass(frozen=True)
class ResolutionRule:
    rule: str
    level: str
    outcome: str
    evidence: dict[str, object]
    explanation: str


@dataclass(frozen=True)
class ResolvedRepresentation:
    """Representación presentada: recursos agrupados por igualdad de ejes musicales."""

    key: str
    source_keys: tuple[str, ...]
    resource_ids: tuple[int, ...]
    attributes_common: dict[str, object]
    attributes_divergent: dict[str, list[object]]


@dataclass(frozen=True)
class ResolvedGroup:
    key: str
    work_ids: tuple[int, ...]
    representations: list[ResolvedRepresentation]
    resource_ids: tuple[int, ...]
    identity: dict[str, str]
    attributes_common: dict[str, object]
    attributes_divergent: dict[str, list[object]]


@dataclass(frozen=True)
class ResolutionResult:
    groups: list[ResolvedGroup]
    applied: list[ResolutionRule]
    blocked: list[ResolutionRule]
    review: list[ResolutionRule]
