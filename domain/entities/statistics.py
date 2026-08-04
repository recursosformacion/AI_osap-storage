from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime


@dataclass
class Statistics:
    """Instantánea de estadísticas del repositorio."""

    archives: int = 0
    entries: int = 0
    files: int = 0
    downloaded_tar: int = 0
    materialized: int = 0
    pending: int = 0
    bytes: int = 0
    computed_at: datetime | None = None
    id: int | None = None
    created_at: datetime | None = None
    updated_at: datetime | None = None
