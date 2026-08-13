from __future__ import annotations

import asyncio
import json

import httpx
from domain.ports.musicbrainz_cache_repository import MusicBrainzCacheRepository

_USER_AGENT = "osap-storage/0.1 (contacto: admin@osap.local)"


class MusicBrainzClient:
    """Cliente ligero del API público de MusicBrainz.

    Respeta el rate limit (~1 petición/segundo) y envía un User-Agent identificativo.
    """

    BASE = "https://musicbrainz.org/ws/2"

    def __init__(self) -> None:
        self._last = 0.0

    async def search_artists(self, name: str) -> list[dict]:
        """Busca artistas por nombre. Devuelve la lista cruda del API."""
        # Rate limit: mínimo 1 s entre peticiones.
        now = asyncio.get_event_loop().time()
        wait = 1.0 - (now - self._last)
        if wait > 0:
            await asyncio.sleep(wait)
        self._last = now

        async with httpx.AsyncClient(timeout=20) as client:
            resp = await client.get(
                f"{self.BASE}/artist",
                params={"query": f'artist:"{name}"', "fmt": "json", "limit": "10"},
                headers={"User-Agent": _USER_AGENT},
            )
            resp.raise_for_status()
            data = resp.json()
            return data.get("artists", [])

    async def search_works(self, title: str) -> list[dict]:
        """Busca obras por título (MusicBrainz `work`), con sus relaciones de compositor."""
        now = asyncio.get_event_loop().time()
        wait = 1.0 - (now - self._last)
        if wait > 0:
            await asyncio.sleep(wait)
        self._last = now

        async with httpx.AsyncClient(timeout=20) as client:
            resp = await client.get(
                f"{self.BASE}/work",
                params={"query": f'work:"{title}"', "fmt": "json", "limit": "10",
                        "inc": "artist-rels"},
                headers={"User-Agent": _USER_AGENT},
            )
            resp.raise_for_status()
            data = resp.json()
            return data.get("works", [])


class CachedMusicBrainzClient:
    """Envuelve MusicBrainzClient con una caché en BD.

    La primera consulta de un nombre llama al API y guarda el resultado; las siguientes
    usan la caché, por lo que se puede procesar sin repetir peticiones ni rate limit.
    """

    def __init__(self, real: MusicBrainzClient, cache: MusicBrainzCacheRepository) -> None:
        self._real = real
        self._cache = cache

    async def search_artists(self, name: str) -> list[dict]:
        cached = await self._cache.get(name)
        if cached is not None:
            try:
                return json.loads(cached)
            except json.JSONDecodeError:
                pass
        artists = await self._real.search_artists(name)
        await self._cache.set(name, json.dumps(artists))
        return artists
