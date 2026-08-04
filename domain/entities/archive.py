from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from enum import StrEnum


class ArchiveStatus(StrEnum):
    IMPORTED = "imported"
    DOWNLOADED = "downloaded"
    MATERIALIZED = "materialized"
    FAILED = "failed"


@dataclass
class Archive:
    """Un archivo contenedor de un proveedor externo (tar, zip, directory...).

    No conoce a PDMX: es un contenedor abstracto. `provider_id` y `format`
    permiten ingestar cualquier dataset sin tocar el dominio.
    """

    name: str
    url: str | None = None
    provider_id: int | None = None
    format: str = "tar"
    local_path: str | None = None
    status: ArchiveStatus = ArchiveStatus.IMPORTED
    size: int | None = None
    sha256: str | None = None
    downloaded_at: datetime | None = None
    id: int | None = None
    created_at: datetime | None = None
    updated_at: datetime | None = None
