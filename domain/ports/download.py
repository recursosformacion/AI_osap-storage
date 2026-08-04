from __future__ import annotations

from typing import Protocol


class FileDownloader(Protocol):
    """Descarga una URL externa y la escribe en disco."""

    async def download(self, source_url: str, destination_path: str) -> None: ...
