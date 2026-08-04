from __future__ import annotations

from dataclasses import dataclass

from domain.entities.file import File, FileStatus
from domain.entities.storage_location import LocationStatus, StorageLocation


@dataclass(frozen=True)
class Availability:
    file: File
    stored_locations: list[StorageLocation]
    available: bool


class AvailabilityService:
    """Reglas de disponibilidad: un fichero está disponible si tiene al menos una copia almacenada."""

    def availability(self, file: File, locations: list[StorageLocation]) -> Availability:
        stored = [loc for loc in locations if loc.status == LocationStatus.STORED]
        available = file.status != FileStatus.FAILED and bool(stored)
        return Availability(file=file, stored_locations=stored, available=available)
