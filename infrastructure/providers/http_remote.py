from __future__ import annotations

from collections.abc import AsyncIterator
from typing import Any

import httpx
from domain.entities.storage_provider import ProviderType
from domain.exceptions import UnsupportedProvider


class HttpRemoteBackend:
    """Mirror remoto de solo lectura servido por otro servidor HTTP."""

    provider_type = ProviderType.HTTP_REMOTE

    def __init__(self, config: dict[str, Any]) -> None:
        self._base_url = (config.get("base_url") or "").rstrip("/")
        if not self._base_url:
            raise ValueError("http_remote backend requires 'base_url' in config")

    async def store(self, local_path: str, object_key: str) -> None:
        raise UnsupportedProvider("http_remote is a read-only mirror provider; store is not supported")

    async def delete(self, object_key: str) -> None:
        raise UnsupportedProvider("http_remote is a read-only mirror provider; delete is not supported")

    async def exists(self, object_key: str) -> bool:
        try:
            async with httpx.AsyncClient(follow_redirects=True, timeout=60) as client:
                response = await client.head(f"{self._base_url}/{object_key}")
                return response.status_code < 400
        except httpx.HTTPError:
            return False

    async def url_for(self, object_key: str) -> str | None:
        return f"{self._base_url}/{object_key}"

    async def open_stream(self, object_key: str) -> AsyncIterator[bytes]:
        url = f"{self._base_url}/{object_key}"

        async def _gen() -> AsyncIterator[bytes]:
            async with (
                httpx.AsyncClient(follow_redirects=True, timeout=60) as client,
                client.stream("GET", url) as response,
            ):
                response.raise_for_status()
                async for chunk in response.aiter_bytes():
                    yield chunk

        return _gen()
