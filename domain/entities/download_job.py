from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from enum import StrEnum


class DownloadJobStatus(StrEnum):
    PENDING = "pending"
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"


@dataclass
class DownloadJob:
    """Trabajo de descarga de un fichero desde una fuente externa."""

    file_id: int
    source_url: str
    provider_id: int | None = None
    status: DownloadJobStatus = DownloadJobStatus.PENDING
    error_message: str | None = None
    id: int | None = None
    created_at: datetime | None = None
    updated_at: datetime | None = None
