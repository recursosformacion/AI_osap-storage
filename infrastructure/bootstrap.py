from __future__ import annotations

from domain.entities.storage_provider import ProviderType, StorageProvider
from domain.exceptions import UnsupportedProvider
from domain.ports.repositories import StorageProviderRepository
from domain.ports.storage import StorageBackendRegistry

from infrastructure.config import Settings


def _repository_config(settings: Settings) -> tuple[ProviderType, dict]:
    """Traduce repository.provider a (ProviderType, config del proveedor)."""
    if settings.repository_provider == "local":
        return ProviderType.LOCAL_DISK, {"root": settings.repository_local_root}
    if settings.repository_provider == "cloudflare_r2":
        if not settings.r2_bucket:
            raise UnsupportedProvider("repository.cloudflare_r2.bucket es obligatorio")
        if not settings.r2_access_key or not settings.r2_secret_key:
            raise UnsupportedProvider("cloudflare_r2 requiere access_key y secret_key")
        return ProviderType.CLOUDFLARE_R2, {
            "bucket": settings.r2_bucket,
            "endpoint": settings.r2_endpoint,
            "account_id": settings.r2_account_id,
            "access_key": settings.r2_access_key,
            "secret_key": settings.r2_secret_key,
            "public_url": settings.r2_public_url,
            "path_prefix": settings.r2_path_prefix,
        }
    raise UnsupportedProvider(f"repository.provider desconocido: {settings.repository_provider}")


async def ensure_default_provider(
    providers: StorageProviderRepository,
    registry: StorageBackendRegistry,
    settings: Settings,
) -> None:
    """Crea el proveedor por defecto al arrancar según repository.provider, si no existe ninguno."""
    if not settings.bootstrap_create_default_provider:
        return
    existing = await providers.list(enabled_only=True)
    if existing:
        return
    provider_type, config = _repository_config(settings)
    provider = StorageProvider(name=settings.repository_provider, provider_type=provider_type, config=config)
    registry.backend_for(provider)
    await providers.create(provider)
