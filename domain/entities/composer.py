"""Compatibilidad: nombres antiguos `Composer*` → nuevos `Person*`.

La entidad canónica es ahora `Person` (`domain/entities/person.py`). Este módulo mantiene
los alias para no romper el código que aún usa la nomenclatura de compositor.
"""

# ruff: noqa: I001

from __future__ import annotations

from domain.entities.person import (
    UNKNOWN_PERSON as UNKNOWN_COMPOSER,
    UNKNOWN_PERSON_ID as UNKNOWN_COMPOSER_ID,
    MergePersonsResult as MergeComposersResult,
    Person as Composer,
    PersonAlias as ComposerAlias,
    PersonCreationEvidence as ComposerCreationEvidence,
    PersonDetail as ComposerDetail,
    PersonEvidence as ComposerEvidence,
    PersonIdentifier as ComposerIdentifier,
    PersonResolution as ComposerResolution,
    PersonResolutionDecision as ComposerResolutionDecision,
    PersonStatus as ComposerStatus,
    PersonSummary as ComposerSummary,
    PersonWorkRef as ComposerWorkRef,
)

__all__ = [
    "UNKNOWN_COMPOSER",
    "UNKNOWN_COMPOSER_ID",
    "Composer",
    "ComposerAlias",
    "ComposerCreationEvidence",
    "ComposerDetail",
    "ComposerEvidence",
    "ComposerIdentifier",
    "ComposerResolution",
    "ComposerResolutionDecision",
    "ComposerStatus",
    "ComposerSummary",
    "ComposerWorkRef",
    "MergeComposersResult",
]
