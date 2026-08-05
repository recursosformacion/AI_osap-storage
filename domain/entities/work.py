from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime


@dataclass
class Work:
    """Una obra musical. Una sola vez; puede tener varias Resource (representaciones)."""

    composer: str | None = None
    title: str | None = None
    genre: str | None = None
    opus: str | None = None
    catalogue: str | None = None
    musical_key: str | None = None
    year: int | None = None
    instrumentation: str | None = None
    language: str | None = None
    tags: str | None = None
    work_key: str | None = None
    id: int | None = None
    created_at: datetime | None = None
    updated_at: datetime | None = None
