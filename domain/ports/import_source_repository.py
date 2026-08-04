from __future__ import annotations

from typing import Protocol

from domain.entities.import_source import ImportSource


class ImportSourceRepository(Protocol):
    async def create(self, source: ImportSource) -> ImportSource: ...

    async def get_by_id(self, source_id: int) -> ImportSource | None: ...

    async def list(self, *, limit: int = 100, offset: int = 0) -> list[ImportSource]: ...
