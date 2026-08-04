from __future__ import annotations

from dataclasses import dataclass

from domain.entities.archive_entry import ArchiveEntryStatus
from domain.ports.archive_repositories import ArchiveEntryRepository, ArchiveRepository


@dataclass(frozen=True)
class Resolution:
    found: bool
    relative_path: str | None = None
    logical_id: str | None = None
    archive_id: int | None = None
    archive_name: str | None = None
    status: str | None = None
    file_id: int | None = None
    available: bool = False


class ResolveFile:
    """Responde "lo tengo / no lo tengo" para una ruta o clave del índice."""

    def __init__(self, entries: ArchiveEntryRepository, archives: ArchiveRepository) -> None:
        self._entries = entries
        self._archives = archives

    async def execute(self, *, relative_path: str | None = None, logical_id: str | None = None) -> Resolution:
        entry = None
        if relative_path:
            entry = await self._entries.get_by_relative_path(relative_path)
        elif logical_id:
            entry = await self._entries.get_by_logical_id(logical_id)

        if entry is None:
            return Resolution(found=False, relative_path=relative_path, logical_id=logical_id)

        archive = await self._archives.get_by_id(entry.archive_id)
        available = entry.status == ArchiveEntryStatus.READY and entry.file_id is not None
        return Resolution(
            found=True,
            relative_path=entry.relative_path,
            logical_id=entry.logical_id,
            archive_id=entry.archive_id,
            archive_name=archive.name if archive else None,
            status=entry.status.value,
            file_id=entry.file_id,
            available=available,
        )
