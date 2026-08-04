from __future__ import annotations

from typing import Any

from domain.entities.storage_provider import ProviderType
from domain.exceptions import UnsupportedProvider


class GoogleDriveBackend:
    """Punto de extensión para Google Drive (pendiente de implementación)."""

    provider_type = ProviderType.GOOGLE_DRIVE

    def __init__(self, config: dict[str, Any]) -> None:
        raise UnsupportedProvider(
            "Google Drive backend is not implemented yet; the domain is ready for it"
        )
