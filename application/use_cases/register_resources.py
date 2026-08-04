from __future__ import annotations

from dataclasses import dataclass

from domain.entities.storage_provider import StorageProvider
from domain.exceptions import EntityNotFound, UnsupportedProvider
from domain.ports.archive_repositories import ArchiveEntryRepository, ArchiveRepository
from domain.ports.repositories import StorageProviderRepository

from application.services.mirror_resources import MirrorResourceRegistrar, ResourceResult


@dataclass(frozen=True)
class RegisterMirrorResourcesCommand:
    archive_id: int
    provider_id: int | None = None


class RegisterMirrorResources:
    """Registra File + StorageLocation por cada ArchiveEntry del mirror."""

    def __init__(
        self,
        archives: ArchiveRepository,
        entries: ArchiveEntryRepository,
        providers: StorageProviderRepository,
        registrar: MirrorResourceRegistrar,
    ) -> None:
        self._archives = archives
        self._entries = entries
        self._providers = providers
        self._registrar = registrar

    async def execute(self, command: RegisterMirrorResourcesCommand) -> ResourceResult:
        archive = await self._archives.get_by_id(command.archive_id)
        if archive is None:
            raise EntityNotFound("archive", command.archive_id)
        provider = await self._resolve_provider(command.provider_id)
        entries = await self._entries.list_by_archive(command.archive_id)
        return await self._registrar.register(entries, provider)

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
