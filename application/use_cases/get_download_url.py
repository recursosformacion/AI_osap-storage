from __future__ import annotations

from dataclasses import dataclass

from domain.entities.file import File
from domain.entities.storage_location import StorageLocation
from domain.entities.storage_provider import StorageProvider
from domain.exceptions import EntityNotFound, FileNotAvailable
from domain.ports.repositories import (
    FileRepository,
    StorageLocationRepository,
    StorageProviderRepository,
)
from domain.ports.storage import StorageBackendRegistry
from domain.services.availability import AvailabilityService


@dataclass(frozen=True)
class DownloadTarget:
    file: File
    provider: StorageProvider
    location: StorageLocation
    native_url: str | None


class GetDownloadUrl:
    """Resuelve la URL de descarga de un fichero en un proveedor.

    Devuelve la URL nativa del proveedor si la ofrece (presigned, mirror remoto);
    si no, None para que la API genere una URL propia de streaming.
    """

    def __init__(
        self,
        files: FileRepository,
        locations: StorageLocationRepository,
        providers: StorageProviderRepository,
        availability: AvailabilityService,
        registry: StorageBackendRegistry,
    ) -> None:
        self._files = files
        self._locations = locations
        self._providers = providers
        self._availability = availability
        self._registry = registry

    async def execute(self, file_id: int, provider_id: int | None = None) -> DownloadTarget:
        file = await self._files.get_by_id(file_id)
        if file is None:
            raise EntityNotFound("file", file_id)

        locations = await self._locations.list_by_file(file.id)
        result = self._availability.availability(file, locations)
        if not result.available:
            raise FileNotAvailable(f"file {file_id} is not available in any storage provider")

        location = self._select(result.stored_locations, provider_id)
        provider = await self._providers.get_by_id(location.provider_id)
        if provider is None:
            raise EntityNotFound("storage_provider", location.provider_id)

        native_url = await self._registry.backend_for(provider).url_for(location.object_key)
        return DownloadTarget(
            file=result.file,
            provider=provider,
            location=location,
            native_url=native_url,
        )

    @staticmethod
    def _select(locations: list[StorageLocation], provider_id: int | None) -> StorageLocation:
        if provider_id is not None:
            for loc in locations:
                if loc.provider_id == provider_id:
                    return loc
            raise FileNotAvailable(f"file is not available in provider {provider_id}")
        if not locations:
            raise FileNotAvailable("file is not available in any storage provider")
        return locations[0]
