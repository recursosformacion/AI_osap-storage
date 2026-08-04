from __future__ import annotations

from domain.ports.hashing import FileHasher


class IntegrityService:
    """Verificación de integridad de un fichero mediante SHA256."""

    def __init__(self, hasher: FileHasher) -> None:
        self._hasher = hasher

    async def compute_sha256(self, path: str) -> str:
        return await self._hasher.sha256_file(path)

    async def verify(self, expected_sha256: str, path: str) -> bool:
        computed = await self._hasher.sha256_file(path)
        return computed.lower() == expected_sha256.strip().lower()
