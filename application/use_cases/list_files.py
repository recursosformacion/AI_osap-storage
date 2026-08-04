from __future__ import annotations

from domain.ports.repositories import (
    FileRepository,
    StorageLocationRepository,
    StorageProviderRepository,
)
from domain.services.availability import AvailabilityService

from application.use_cases.get_file import FileDetail, GetFile


class ListFiles:
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
        self._detail = GetFile(files, locations, providers, availability)

    async def execute(self, *, limit: int = 100, offset: int = 0) -> list[FileDetail]:
        files = await self._files.list(limit=limit, offset=offset)
        providers = await self._providers.list(enabled_only=False)
        details: list[FileDetail] = []
        for file in files:
            locations = await self._locations.list_by_file(file.id)
            result = self._availability.availability(file, locations)
            details.append(
                FileDetail(
                    file=result.file,
                    locations=result.stored_locations,
                    providers=providers,
                    available=result.available,
                )
            )
        return details
