from __future__ import annotations

from domain.entities.storage_provider import ProviderType, StorageProvider
from domain.exceptions import UnsupportedProvider
from domain.ports.repositories import StorageProviderRepository
from domain.ports.storage import StorageBackendRegistry

from infrastructure.config import Settings


def _backend_config(settings: Settings) -> tuple[ProviderType, dict]:
    if settings.storage_backend == "local":
        return ProviderType.LOCAL_DISK, {"root": settings.storage_local_root}
    if settings.storage_backend == "google_drive":
        return ProviderType.GOOGLE_DRIVE, {
            "credentials": settings.google_drive_credentials,
            "folder_id": settings.google_drive_folder_id,
        }
    if settings.storage_backend == "s3":
        return ProviderType.S3, {}
    raise UnsupportedProvider(f"unknown storage.backend: {settings.storage_backend}")


async def ensure_default_provider(
    providers: StorageProviderRepository,
    registry: StorageBackendRegistry,
    settings: Settings,
) -> None:
    """Crea el proveedor por defecto al arrancar según storage.backend, si no existe ninguno."""
    if not settings.bootstrap_default_provider:
        return
    existing = await providers.list(enabled_only=True)
    if existing:
        return
    provider_type, config = _backend_config(settings)
    provider = StorageProvider(name=settings.storage_backend, provider_type=provider_type, config=config)
    registry.backend_for(provider)
    await providers.create(provider)
