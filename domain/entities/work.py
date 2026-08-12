from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime

from domain.entities.composer import UNKNOWN_COMPOSER


def display_composer(composer: str | None) -> str:
    """Devuelve el compositor o la etiqueta de compositor no indicado si está vacío."""
    return composer if composer and composer.strip() else UNKNOWN_COMPOSER


@dataclass
class WorkLists:
    tags: list[str] = field(default_factory=list)
    genres: list[str] = field(default_factory=list)
    instruments: list[str] = field(default_factory=list)
    parts_names: list[str] = field(default_factory=list)


@dataclass
class Work:
    """Una obra musical. Una sola vez; puede tener varias Resource (representaciones)."""

    composer: str | None = None
    composer_id: str | None = None
    title: str | None = None
    subtitle: str | None = None
    artist: str | None = None
    song_name: str | None = None
    genre: str | None = None
    opus: str | None = None
    catalogue: str | None = None
    musical_key: str | None = None
    year: int | None = None
    instrumentation: str | None = None
    language: str | None = None
    tags: str | None = None
    duration: str | None = None
    measures: int | None = None
    pages: int | None = None
    parts: int | None = None
    complexity: int | None = None
    license: str | None = None
    public_domain: bool = False
    description: str | None = None
    thumbnails: str | None = None
    work_key: str | None = None
    relative_path: str | None = None
    id: int | None = None
    created_at: datetime | None = None
    updated_at: datetime | None = None
