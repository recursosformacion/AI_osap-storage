from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import Protocol


@dataclass
class SyncState:
    source: str
    last_packet: int = 0
    last_success_at: datetime | None = None
    last_error: str | None = None
    metadata: dict | None = None


class AuthoritySyncStateRepository(Protocol):
    async def get(self, source: str) -> SyncState:
        ...

    async def save(
        self,
        source: str,
        *,
        last_packet: int | None = None,
        last_success_at: datetime | None = None,
        last_error: str | None = None,
        metadata: dict | None = None,
    ) -> None:
        ...
