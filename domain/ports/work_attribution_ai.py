"""Puerto del resolvedor de atribución de obra asistido por IA (propuestas, no escrituras).

Gemini (u otro modelo) actúa como **investigador**: propone, nunca crea personas ni escribe
en `works_person_roles`. La resolución semántica (`resolution`) y el matching del candidato
contra `persons` (`person_match`) son dimensiones distintas.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Literal, Protocol

Resolution = Literal["identified", "anonymous", "traditional", "unknown"]
PersonMatch = Literal["matched", "ambiguous", "unresolved", "not_applicable"]

PROMPT_VERSION = "v1"


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
    existing_persons: list[str] = field(default_factory=list)


@dataclass(frozen=True)
class AiProposal:
    """Propuesta estructurada del modelo (aún sin resolver contra `persons`)."""

    resolution: Resolution
    person_name: str | None
    role_name: str | None
    confidence: float | None
    evidence: list[dict[str, object]] = field(default_factory=list)
    reason: str | None = None
    raw: dict[str, object] = field(default_factory=dict)


class IWorkAttributionResolver(Protocol):
    """Resolvedor IA. Debe devolver una propuesta estructurada o lanzar error."""

    model: str

    async def propose(self, context: WorkContext) -> AiProposal: ...
