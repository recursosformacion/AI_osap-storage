from __future__ import annotations

from typing import Protocol


class MusicBrainzCacheRepository(Protocol):
    """Cache de respuestas del API de MusicBrainz por consulta."""

    async def get(self, query: str) -> str | None:
        """Devuelve el payload JSON cacheado para la consulta, o None si no existe."""

    async def set(self, query: str, payload: str) -> None:
        """Guarda (o actualiza) el payload JSON para la consulta."""
