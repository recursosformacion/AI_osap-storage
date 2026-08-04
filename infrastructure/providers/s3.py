from __future__ import annotations

import asyncio
from collections.abc import AsyncIterator
from typing import Any

from domain.entities.storage_provider import ProviderType
from domain.exceptions import UnsupportedProvider


class S3Backend:
    """Almacenamiento en un bucket S3 (AWS, MinIO u otros compatibles)."""

    provider_type = ProviderType.S3

    def __init__(self, config: dict[str, Any]) -> None:
        try:
            import boto3
        except ImportError as exc:
            raise UnsupportedProvider(
                "boto3 is not installed; install it with `pip install osap-storage[s3]`"
            ) from exc

        self._bucket = config.get("bucket")
        if not self._bucket:
            raise ValueError("s3 backend requires 'bucket' in config")

        self._client = boto3.client(
            "s3",
            endpoint_url=config.get("endpoint_url"),
            region_name=config.get("region"),
            aws_access_key_id=config.get("access_key_id"),
            aws_secret_access_key=config.get("secret_access_key"),
        )

    async def store(self, local_path: str, object_key: str) -> None:
        await asyncio.to_thread(self._client.upload_file, local_path, self._bucket, object_key)

    async def delete(self, object_key: str) -> None:
        await asyncio.to_thread(
            self._client.delete_object,
            Bucket=self._bucket,
            Key=object_key,
        )

    async def exists(self, object_key: str) -> bool:
        try:
            await asyncio.to_thread(
                self._client.head_object, Bucket=self._bucket, Key=object_key
            )
            return True
        except Exception:
            return False

    async def url_for(self, object_key: str) -> str | None:
        return await asyncio.to_thread(
            self._client.generate_presigned_url,
            "get_object",
            Params={"Bucket": self._bucket, "Key": object_key},
            ExpiresIn=3600,
        )

    async def open_stream(self, object_key: str) -> AsyncIterator[bytes]:
        response = await asyncio.to_thread(
            self._client.get_object,
            Bucket=self._bucket,
            Key=object_key,
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
