from __future__ import annotations

from typing import Protocol


class ArchiveReader(Protocol):
    """Lee el contenido de un archive (por ejemplo un TAR) sin extraer todo."""

    def has_member(self, name: str) -> bool: ...

    async def extract(self, name: str, destination_path: str) -> None: ...

    def close(self) -> None: ...


class ArchiveReaderFactory(Protocol):
    def open(self, path: str, format: str = "tar") -> ArchiveReader: ...
