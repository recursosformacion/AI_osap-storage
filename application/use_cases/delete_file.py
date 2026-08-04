from __future__ import annotations

from domain.exceptions import EntityNotFound
from domain.ports.repositories import (
    FileRepository,
    StorageLocationRepository,
    StorageProviderRepository,
)
from domain.ports.storage import StorageBackendRegistry


class DeleteFile:
    """Borra un fichero: elimina sus copias físicas y su registro."""

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

    async def execute(self, file_id: int) -> None:
        file = await self._files.get_by_id(file_id)
        if file is None:
            raise EntityNotFound("file", file_id)

        for location in await self._locations.list_by_file(file_id):
            provider = await self._providers.get_by_id(location.provider_id)
            if provider is not None:
                await self._registry.backend_for(provider).delete(location.object_key)

        await self._locations.delete_by_file(file_id)
        await self._files.delete(file_id)
