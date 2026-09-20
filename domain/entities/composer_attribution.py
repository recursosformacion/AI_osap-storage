from __future__ import annotations

from dataclasses import dataclass

SOURCE_RISM = "rism"

STATE_RESOLVED = "resolved"
STATE_INFERRED = "inferred"
STATE_AMBIGUOUS = "ambiguous"
STATE_UNCLASSIFIED = "unclassified"

# Contrato `100 $j` → estado (docsNew/diseño-resolutor-agrupacion.md §14).
STATE_BY_RELIABILITY = {
    "verified": STATE_RESOLVED,
    "ascertained": STATE_INFERRED,
    "conjectural": STATE_AMBIGUOUS,
    "alleged": STATE_AMBIGUOUS,
    "doubtful": STATE_AMBIGUOUS,
}


def state_for_reliability(reliability: str | None) -> str:
    return STATE_BY_RELIABILITY.get((reliability or "").strip().lower(), STATE_UNCLASSIFIED)


@dataclass(frozen=True)
class ComposerAttribution:
    """Evidencia externa (RISM) que relaciona una obra con una persona y su grado de autoría."""

    person_id: str | None
    person_name: str | None
    state: str
    reliability: str | None = None
    source: str = SOURCE_RISM
    matched_title: str | None = None
    via: str | None = None

    @property
    def usable_for_identity(self) -> bool:
        """Solo `resolved`/`inferred` pueden aportar identidad al resolver."""
        return self.state in (STATE_RESOLVED, STATE_INFERRED) and bool(self.person_id)
