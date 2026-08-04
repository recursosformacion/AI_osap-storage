from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime


@dataclass
class ImportSource:
    """Procedencia de un índice importado (PDMX v1, v2, OpenScore, IMSLP dump...)."""

    provider: str
    version: str | None = None
    csv_path: str | None = None
    notes: str | None = None
    imported_at: datetime | None = None
    id: int | None = None
    created_at: datetime | None = None
    updated_at: datetime | None = None
