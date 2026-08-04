from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from enum import StrEnum
from typing import Any


class ProviderType(StrEnum):
    LOCAL_DISK = "local_disk"
    S3 = "s3"
    GOOGLE_DRIVE = "google_drive"
    HTTP_REMOTE = "http_remote"
    CLOUDFLARE_R2 = "cloudflare_r2"


@dataclass
class StorageProvider:
    """Un proveedor de almacenamiento físico (disco local, S3, Drive, servidor remoto...)."""

    name: str
    provider_type: ProviderType
    config: dict[str, Any] = field(default_factory=dict)
    enabled: bool = True
    id: int | None = None
    created_at: datetime | None = None
    updated_at: datetime | None = None
