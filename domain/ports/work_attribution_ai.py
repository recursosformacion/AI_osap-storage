"""Puerto del resolvedor de atribución de obra asistido por IA (propuestas, no escrituras).

Gemini (u otro modelo) actúa como **investigador**: propone, nunca crea personas ni escribe
en `works_person_roles`. Dos capas distintas, que se guardan por separado:

- **Atribución de la obra**: `resolution` (`identified|anonymous|traditional|unknown`).
- **Personas relacionadas**: `relations` (persona × rol: compositor, arreglista, letrista…).

Una obra anónima o tradicional puede tener arreglista identificable: `anonymous`/`traditional`
no significa "sin personas". El matching del candidato contra `persons` (`person_match`) es una
tercera dimensión, también independiente.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Literal, Protocol

Resolution = Literal["identified", "anonymous", "traditional", "unknown"]
PersonMatch = Literal["matched", "ambiguous", "unresolved", "not_applicable"]
RelationDecision = Literal["pending", "accepted", "rejected", "uncertain"]
RelationOrigin = Literal["gemini", "existing", "human"]

PROMPT_VERSION = "v2"

# Claves de rol que el modelo puede proponer (subconjunto musical de `person_roles.ROLE_IDS`).
AI_ROLE_KEYS = (
    "composer",
    "arranger",
    "orchestrator",
    "transcriber",
    "librettist",
    "editor",
    "completer",
)


@dataclass(frozen=True)
class WorkContext:
    """Contexto que recibe el modelo (solo datos que ya tenemos; nada que inventar)."""

    work_id: int
    title: str | None
    source: str | None = None
    source_id: str | None = None
    catalogue: str | None = None
    year: int | None = None
    opus: str | None = None
    genre: str | None = None
    instrumentation: str | None = None
    attr_type: str | None = None
    attribution_note: str | None = None
    # Relaciones ya existentes en el catálogo, con su rol (`{"name": ..., "role": ...}`).
    existing_relations: list[dict[str, str]] = field(default_factory=list)


@dataclass(frozen=True)
class AiRelation:
    """Persona propuesta por el modelo para un rol (sin resolver contra `persons`)."""

    person_name: str
    role_key: str
    confidence: float | None = None
    evidence: list[dict[str, object]] = field(default_factory=list)
    reason: str | None = None


@dataclass(frozen=True)
class AiProposal:
    """Propuesta estructurada del modelo (aún sin resolver contra `persons`)."""

    resolution: Resolution
    person_name: str | None
    role_name: str | None
    confidence: float | None
    evidence: list[dict[str, object]] = field(default_factory=list)
    reason: str | None = None
    # Personas relacionadas con rol (incluye, si procede, compositor/arreglista/letrista…).
    relations: list[AiRelation] = field(default_factory=list)
    # Discrepancias que el revisor no debe perder (p. ej. título vs catálogo).
    contradictions: list[str] = field(default_factory=list)
    raw: dict[str, object] = field(default_factory=dict)


class IWorkAttributionResolver(Protocol):
    """Resolvedor IA. Debe devolver una propuesta estructurada o lanzar error."""

    model: str

    async def propose(self, context: WorkContext) -> AiProposal: ...
