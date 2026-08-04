from __future__ import annotations

import asyncio
import shutil
from collections.abc import AsyncIterator
from pathlib import Path
from typing import Any

from domain.entities.storage_provider import ProviderType


class LocalDiskBackend:
    """Almacenamiento en un directorio del disco local."""

    provider_type = ProviderType.LOCAL_DISK

    def __init__(self, config: dict[str, Any]) -> None:
        root = config.get("root") or config.get("path")
        if not root:
            raise ValueError("local_disk backend requires 'root' in config")
        self._root = Path(root)
        self._public_base_url = config.get("public_base_url")

    async def store(self, local_path: str, object_key: str) -> None:
        destination = self._root / object_key
        destination.parent.mkdir(parents=True, exist_ok=True)
        await asyncio.to_thread(shutil.copy2, local_path, destination)

    async def delete(self, object_key: str) -> None:
        (self._root / object_key).unlink(missing_ok=True)

    async def url_for(self, object_key: str) -> str | None:
        if self._public_base_url:
            return f"{self._public_base_url.rstrip('/')}/{object_key}"
        return None

    async def open_stream(self, object_key: str) -> AsyncIterator[bytes]:
        path = self._root / object_key

        async def _gen() -> AsyncIterator[bytes]:
            with open(path, "rb") as fh:
                while chunk := fh.read(1 << 16):
                    yield chunk

        return _gen()
