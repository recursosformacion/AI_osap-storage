from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from enum import StrEnum


class LocationStatus(StrEnum):
    STORED = "stored"
    FAILED = "failed"
    REMOVED = "removed"


@dataclass
class StorageLocation:
    """Copia de un fichero dentro de un proveedor concreto."""

    file_id: int
    provider_id: int
    object_key: str
    status: LocationStatus = LocationStatus.STORED
    id: int | None = None
    created_at: datetime | None = None
    updated_at: datetime | None = None
