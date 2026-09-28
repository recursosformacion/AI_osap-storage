from __future__ import annotations

import httpx
from domain.exceptions import DownloadFailed

from infrastructure.downloaders.url_guard import validate_public_url

_MAX_REDIRECTS = 5


class HttpxDownloader:
    """Descarga una URL externa escribiendo el contenido en disco.

    No sigue redirecciones automáticamente: las resuelve a mano validando cada destino
    contra SSRF (`validate_public_url`) antes de volver a pedir.
    """

    def __init__(self, timeout_seconds: float = 60.0, chunk_size: int = 1 << 16) -> None:
        self._timeout = timeout_seconds
        self._chunk_size = chunk_size

    async def download(self, source_url: str, destination_path: str) -> None:
        try:
            async with httpx.AsyncClient(
                follow_redirects=False, timeout=self._timeout
            ) as client:
                url = source_url
                for _ in range(_MAX_REDIRECTS + 1):
                    validate_public_url(url)
                    async with client.stream("GET", url) as response:
                        if response.is_redirect:
                            location = response.headers.get("location")
                            if not location:
                                raise DownloadFailed(f"redirección sin Location desde {url}")
                            url = str(httpx.URL(url).join(location))
                            continue
                        response.raise_for_status()
                        with open(destination_path, "wb") as fh:
                            async for chunk in response.aiter_bytes(self._chunk_size):
                                fh.write(chunk)
                        return
                raise DownloadFailed("demasiadas redirecciones")
        except (httpx.HTTPError, httpx.TimeoutException, OSError) as exc:
            raise DownloadFailed(f"failed to download {source_url}: {exc}") from exc
