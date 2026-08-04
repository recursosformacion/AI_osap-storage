from __future__ import annotations

import os
from pathlib import Path

from domain.entities.archive import Archive
from domain.exceptions import InvalidFileData
from domain.ports.download import FileDownloader


class TarDownloader:
    """Descarga el archive a la caché de mirrors si no existe, y lo reutiliza."""

    def __init__(self, downloader: FileDownloader | None, cache_dir: str | None) -> None:
        self._downloader = downloader
        self._cache_dir = Path(cache_dir) if cache_dir else None

    async def ensure(self, archive: Archive, download: bool = True) -> tuple[str, bool]:
        """Devuelve (local_path, downloaded_ahora). Usa el archive ya presente si existe."""
        if archive.local_path and os.path.exists(archive.local_path):
            return archive.local_path, False
        if not download or self._downloader is None or self._cache_dir is None:
            raise InvalidFileData(f"archive {archive.id} has no local file and download is not available")
        if not archive.url:
            raise InvalidFileData(f"archive {archive.id} has no url to download")
        self._cache_dir.mkdir(parents=True, exist_ok=True)
        destination = self._cache_dir / archive.name
        if os.path.exists(destination):
            return str(destination), False
        await self._downloader.download(archive.url, str(destination))
        return str(destination), True

    async def discard(self, archive: Archive) -> None:
        if archive.local_path and os.path.exists(archive.local_path):
            os.remove(archive.local_path)
        archive.local_path = None
