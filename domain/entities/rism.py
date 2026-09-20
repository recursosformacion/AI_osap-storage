from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class RismSource:
    """Fuente RISM (corpus local, read-only). No es una obra nuestra; sus enlaces son externos."""

    source_id: str
    composer_name: str | None = None
    uniform_title: str | None = None
    title: str | None = None
    reliability: str | None = None
    source_type: str | None = None
    shelfmark: str | None = None
    institution_id: str | None = None
    language: str | None = None
    has_incipit: bool = False
    links: tuple[str, ...] = ()
