from __future__ import annotations

import asyncio
import hashlib


class HashlibHasher:
    """Calcula el SHA256 de un fichero en disco usando hashlib."""

    @staticmethod
    async def sha256_file(path: str) -> str:
        return await asyncio.to_thread(HashlibHasher._sha256_sync, path)

    @staticmethod
    def _sha256_sync(path: str) -> str:
        digest = hashlib.sha256()
        with open(path, "rb") as fh:
            while chunk := fh.read(1 << 20):
                digest.update(chunk)
        return digest.hexdigest()
