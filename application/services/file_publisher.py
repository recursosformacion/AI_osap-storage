from __future__ import annotations

import os
from dataclasses import dataclass

from domain.entities.file import File
from domain.entities.storage_location import LocationStatus, StorageLocation
from domain.entities.storage_provider import StorageProvider
from domain.exceptions import UnsupportedProvider
from domain.ports.repositories import (
    FileRepository,
    StorageLocationRepository,
    StorageProviderRepository,
)
from domain.ports.storage import StorageBackendRegistry


@dataclass(frozen=True)
class PublishedFile:
    file: File
    provider: StorageProvider
    location: StorageLocation


class FilePublisher:
    """Guarda un fichero físico en un proveedor y registra su StorageLocation."""

    def __init__(
        self,
        files: FileRepository,
        locations: StorageLocationRepository,
        providers: StorageProviderRepository,
        registry: StorageBackendRegistry,
    ) -> None:
        self._files = files
        self._locations = locations
        self._providers = providers
        self._registry = registry

    async def publish(
        self,
        file: File,
        provider_id: int | None,
        local_path: str,
        object_key: str | None = None,
    ) -> PublishedFile:
        provider = await self._resolve_provider(provider_id)
        backend = self._registry.backend_for(provider)
        key = object_key or file.storage_key()
        await backend.store(local_path, key)

        if file.size_bytes is None:
            file.size_bytes = os.path.getsize(local_path)
            await self._files.save(file)

        location = await self._locations.get_by_file_and_provider(file.id, provider.id)
        if location is None:
            location = await self._locations.create(
                StorageLocation(
                    file_id=file.id,
                    provider_id=provider.id,
                    object_key=key,
                    status=LocationStatus.STORED,
                )
            )
        else:
            location.object_key = key
            location.status = LocationStatus.STORED
            await self._locations.save(location)

        return PublishedFile(file=file, provider=provider, location=location)

    async def _resolve_provider(self, provider_id: int | None) -> StorageProvider:
        if provider_id is not None:
            provider = await self._providers.get_by_id(provider_id)
            if provider is None or not provider.enabled:
                raise UnsupportedProvider(f"provider {provider_id} is not available")
            return provider
        enabled = await self._providers.list(enabled_only=True)
        if not enabled:
            raise UnsupportedProvider("no enabled storage provider is available")
        return enabled[0]
