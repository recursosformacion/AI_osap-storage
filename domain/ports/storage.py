from __future__ import annotations

from collections.abc import AsyncIterator
from typing import Protocol

from domain.entities.storage_provider import ProviderType, StorageProvider


class StorageBackend(Protocol):
    """Adaptador de un proveedor físico concreto."""

    provider_type: ProviderType

    async def store(self, local_path: str, object_key: str) -> None: ...

    async def delete(self, object_key: str) -> None: ...

    async def url_for(self, object_key: str) -> str | None: ...

    async def exists(self, object_key: str) -> bool: ...

    async def open_stream(self, object_key: str) -> AsyncIterator[bytes]: ...


class StorageBackendRegistry(Protocol):
    """Resuelve un backend a partir de un proveedor persistido."""

    def supports(self, provider_type: ProviderType) -> bool: ...

    def backend_for(self, provider: StorageProvider) -> StorageBackend: ...
