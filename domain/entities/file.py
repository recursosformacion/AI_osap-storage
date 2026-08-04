from __future__ import annotations

import re
from dataclasses import dataclass
from datetime import datetime
from enum import StrEnum

SHA256_PATTERN = re.compile(r"^[0-9a-f]{64}$")


class FileStatus(StrEnum):
    REGISTERED = "registered"
    DOWNLOADING = "downloading"
    AVAILABLE = "available"
    FAILED = "failed"


@dataclass
class File:
    """Un fichero registrado, identificado de forma unívoca por su SHA256."""

    sha256: str
    name: str
    mime_type: str | None = None
    size_bytes: int | None = None
    status: FileStatus = FileStatus.REGISTERED
    id: int | None = None
    created_at: datetime | None = None
    updated_at: datetime | None = None

    def storage_key(self) -> str:
        """Clave de objeto utilizada dentro de un proveedor, derivada del SHA256."""
        return f"{self.sha256[:2]}/{self.sha256}"
