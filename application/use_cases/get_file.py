from __future__ import annotations

from dataclasses import dataclass

from domain.entities.file import File
from domain.entities.storage_location import StorageLocation
from domain.entities.storage_provider import StorageProvider
from domain.exceptions import EntityNotFound
from domain.ports.repositories import (
    FileRepository,
    StorageLocationRepository,
    StorageProviderRepository,
)
from domain.services.availability import AvailabilityService


@dataclass(frozen=True)
class FileDetail:
    file: File
    locations: list[StorageLocation]
    providers: list[StorageProvider]
    available: bool


class GetFile:
    def __init__(
        self,
        files: FileRepository,
        locations: StorageLocationRepository,
        providers: StorageProviderRepository,
        availability: AvailabilityService,
    ) -> None:
        self._files = files
        self._locations = locations
        self._providers = providers
        self._availability = availability

    async def execute(self, file_id: int) -> FileDetail:
        file = await self._files.get_by_id(file_id)
        if file is None:
            raise EntityNotFound("file", file_id)

        locations = await self._locations.list_by_file(file.id)
        result = self._availability.availability(file, locations)
        providers = await self._providers.list(enabled_only=False)
        return FileDetail(
            file=result.file,
            locations=result.stored_locations,
            providers=providers,
            available=result.available,
        )
