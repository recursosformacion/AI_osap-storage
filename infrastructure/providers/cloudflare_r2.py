from __future__ import annotations

import asyncio
from collections.abc import AsyncIterator
from typing import Any

from domain.entities.storage_provider import ProviderType
from domain.exceptions import UnsupportedProvider


class CloudflareR2Backend:
    """Repositorio oficial en Cloudflare R2 (API compatible con S3).

    `public_url` + `path_prefix` permiten servir los ficheros directamente
    desde el CDN público (R2 custom domain).
    """

    provider_type = ProviderType.CLOUDFLARE_R2

    def __init__(self, config: dict[str, Any]) -> None:
        try:
            import boto3
        except ImportError as exc:
            raise UnsupportedProvider(
                "boto3 is not installed; install it with `pip install osap-storage[s3]`"
            ) from exc

        self._bucket = config.get("bucket")
        if not self._bucket:
            raise ValueError("cloudflare_r2 requires 'bucket' in config")

        client_kwargs: dict[str, Any] = {}
        if config.get("endpoint"):
            client_kwargs["endpoint_url"] = config["endpoint"]
            client_kwargs["region_name"] = "auto"
        if config.get("access_key"):
            client_kwargs["aws_access_key_id"] = config["access_key"]
        if config.get("secret_key"):
            client_kwargs["aws_secret_access_key"] = config["secret_key"]

        self._client = boto3.client("s3", **client_kwargs)
        self._public_url = (config.get("public_url") or "").rstrip("/") or None
        self._path_prefix = (config.get("path_prefix") or "").strip("/")

    def _key(self, object_key: str) -> str:
        key = object_key.lstrip("./")
        return f"{self._path_prefix}/{key}" if self._path_prefix else key

    async def store(self, local_path: str, object_key: str) -> None:
        await asyncio.to_thread(
            self._client.upload_file, local_path, self._bucket, self._key(object_key)
        )

    async def delete(self, object_key: str) -> None:
        await asyncio.to_thread(
            self._client.delete_object, Bucket=self._bucket, Key=self._key(object_key)
        )

    async def exists(self, object_key: str) -> bool:
        try:
            await asyncio.to_thread(
                self._client.head_object, Bucket=self._bucket, Key=self._key(object_key)
            )
            return True
        except Exception:
            return False

    async def url_for(self, object_key: str) -> str | None:
        if self._public_url is None:
            return None
        return f"{self._public_url}/{self._key(object_key)}"

    async def open_stream(self, object_key: str) -> AsyncIterator[bytes]:
        response = await asyncio.to_thread(
            self._client.get_object, Bucket=self._bucket, Key=self._key(object_key)
        )
        body = response["Body"]

        def _read() -> bytes:
            return body.read(1 << 16) or b""

        async def _gen() -> AsyncIterator[bytes]:
            while True:
                chunk = await asyncio.to_thread(_read)
                if not chunk:
                    break
                yield chunk

        return _gen()
