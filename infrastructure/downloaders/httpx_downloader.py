from __future__ import annotations

import httpx
from domain.exceptions import DownloadFailed


class HttpxDownloader:
    """Descarga una URL externa escribiendo el contenido en disco."""

    def __init__(self, timeout_seconds: float = 60.0, chunk_size: int = 1 << 16) -> None:
        self._timeout = timeout_seconds
        self._chunk_size = chunk_size

    async def download(self, source_url: str, destination_path: str) -> None:
        try:
            async with (
                httpx.AsyncClient(follow_redirects=True, timeout=self._timeout) as client,
                client.stream("GET", source_url) as response,
            ):
                response.raise_for_status()
                with open(destination_path, "wb") as fh:
                    async for chunk in response.aiter_bytes(self._chunk_size):
                        fh.write(chunk)
        except (httpx.HTTPError, httpx.TimeoutException, OSError) as exc:
            raise DownloadFailed(f"failed to download {source_url}: {exc}") from exc
