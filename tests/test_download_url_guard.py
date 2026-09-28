"""Tests de S4: validación anti-SSRF de descargas (osap-storage).

Bloqueo de loopback/privadas/link-local/internas y de esquemas no http(s), tanto en la URL
inicial como al seguir redirecciones (que no se siguen automáticamente).
"""

from __future__ import annotations

import asyncio
from pathlib import Path

import httpx
import pytest
from domain.exceptions import DownloadFailed
from infrastructure.downloaders import httpx_downloader
from infrastructure.downloaders.url_guard import validate_public_url

_BLOCKED_URLS = [
    "file:///etc/passwd",
    "ftp://93.184.216.34/file",
    "gopher://93.184.216.34/",
    "http://127.0.0.1/",
    "http://localhost/",
    "http://0.0.0.0/",
    "http://10.0.0.1/",
    "http://172.16.0.1/",
    "http://192.168.1.1/",
    "http://100.64.0.1/",
    "http://169.254.169.254/latest/meta-data/",
    "http://[::1]/",
    "http://[::ffff:127.0.0.1]/",
]

_ALLOWED_URLS = [
    "http://93.184.216.34/path",
    "https://8.8.8.8/",
]


@pytest.mark.parametrize("url", _BLOCKED_URLS)
def test_urls_internas_o_no_http_bloqueadas(url: str) -> None:
    with pytest.raises(DownloadFailed):
        validate_public_url(url)


@pytest.mark.parametrize("url", _ALLOWED_URLS)
def test_urls_publicas_permitidas(url: str) -> None:
    validate_public_url(url)


def test_host_no_resoluble_bloqueado() -> None:
    with pytest.raises(DownloadFailed):
        validate_public_url("http://no-such-host.invalid/")


class _FakeResponse:
    def __init__(self, status_code: int, headers: dict[str, str] | None = None, body: bytes = b"") -> None:
        self.status_code = status_code
        self.headers = {k.lower(): v for k, v in (headers or {}).items()}
        self._body = body

    @property
    def is_redirect(self) -> bool:
        return self.status_code in (301, 302, 303, 307, 308) and "location" in self.headers

    def raise_for_status(self) -> None:
        if self.status_code >= 400:
            raise httpx.HTTPStatusError(
                "error", request=httpx.Request("GET", "http://x"), response=httpx.Response(self.status_code)
            )

    async def aiter_bytes(self, _size: int):
        yield self._body

    async def __aenter__(self) -> _FakeResponse:
        return self

    async def __aexit__(self, *_: object) -> bool:
        return False


class _FakeClient:
    def __init__(self, *responses: _FakeResponse) -> None:
        self._queue = list(responses)
        self.requested: list[str] = []

    async def __aenter__(self) -> _FakeClient:
        return self

    async def __aexit__(self, *_: object) -> bool:
        return False

    def stream(self, _method: str, url: str) -> _FakeResponse:
        self.requested.append(str(url))
        return self._queue.pop(0)


def _patch_client(monkeypatch: pytest.MonkeyPatch, client: _FakeClient) -> None:
    monkeypatch.setattr(httpx_downloader.httpx, "AsyncClient", lambda *a, **k: client)


def test_redireccion_a_destino_interno_bloqueada(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    client = _FakeClient(_FakeResponse(302, {"Location": "http://169.254.169.254/meta"}))
    _patch_client(monkeypatch, client)

    with pytest.raises(DownloadFailed):
        asyncio.run(
            httpx_downloader.HttpxDownloader().download(
                "http://93.184.216.34/hop", str(tmp_path / "out.bin")
            )
        )
    # Solo se pidió el primer salto público; el destino interno nunca se consultó.
    assert client.requested == ["http://93.184.216.34/hop"]


def test_redireccion_publica_descarga(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    client = _FakeClient(
        _FakeResponse(302, {"Location": "https://8.8.8.8/next"}),
        _FakeResponse(200, body=b"DATA"),
    )
    _patch_client(monkeypatch, client)

    dest = tmp_path / "out.bin"
    asyncio.run(httpx_downloader.HttpxDownloader().download("http://93.184.216.34/hop", str(dest)))
    assert dest.read_bytes() == b"DATA"
    assert client.requested == ["http://93.184.216.34/hop", "https://8.8.8.8/next"]
