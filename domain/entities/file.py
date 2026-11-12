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
    DELETED = "deleted"


@dataclass
class File:
    """Un fichero registrado, identificado de forma unívoca por su SHA256."""

    sha256: str | None
    name: str
    mime_type: str | None = None
    size_bytes: int | None = None
    status: FileStatus = FileStatus.REGISTERED
    id: int | None = None
    created_at: datetime | None = None
    updated_at: datetime | None = None
    storage_key: str | None = None
    resource_id: int | None = None

    def object_key(self) -> str:
        """Clave física opaca del objeto.

        V6 exige copiarla literalmente desde el backend. El fallback por SHA256
        solo se mantiene para ficheros antiguos hasta completar la migración.
        """
        if self.storage_key:
            return self.storage_key
        if self.sha256:
            return f"{self.sha256[:2]}/{self.sha256}"
        raise ValueError(f"file {self.id or self.name!r} has no storage key")
