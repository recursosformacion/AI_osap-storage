from __future__ import annotations

from typing import Protocol


class FileHasher(Protocol):
    """Calcula el SHA256 de un fichero en disco."""

    async def sha256_file(self, path: str) -> str: ...
