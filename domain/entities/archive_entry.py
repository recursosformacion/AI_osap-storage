from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from enum import StrEnum


class ArchiveEntryStatus(StrEnum):
    MISSING = "missing"
    READY = "ready"
    FAILED = "failed"


@dataclass
class ArchiveEntry:
    """Entrada del índice: "sé dónde está este fichero dentro de un archive"."""

    archive_id: int
    relative_path: str
    logical_id: str | None = None
    composer: str | None = None
    title: str | None = None
    file_id: int | None = None
    size: int | None = None
    offset: int | None = None
    status: ArchiveEntryStatus = ArchiveEntryStatus.MISSING
    id: int | None = None
    created_at: datetime | None = None
    updated_at: datetime | None = None
