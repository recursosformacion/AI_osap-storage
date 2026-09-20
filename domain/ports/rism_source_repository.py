from __future__ import annotations

from typing import Protocol

from domain.entities.rism import RismSource


class RismSourceRepository(Protocol):
    async def search(self, query: str, *, limit: int = 50, offset: int = 0) -> list[RismSource]: ...
