"""Fuente de los JSON de metadata: disco local (dev/G:) o R2 (producción)."""
from __future__ import annotations

import json
import os

from infrastructure.config import Settings


class LocalMetadataReader:
    def __init__(self, metadata_dir: str) -> None:
        self._dir = metadata_dir

    def read(self, rel_path: str) -> dict:
        path = os.path.join(self._dir, rel_path.lstrip("./"))
        with open(path, encoding="utf-8") as fh:
            return json.load(fh)


class R2MetadataReader:
    """Lee los JSON de metadata desde Cloudflare R2 (producción)."""

    def __init__(self, settings: Settings) -> None:
        import boto3

        self._bucket = settings.r2_bucket
        self._prefix = settings.r2_path_prefix.strip("/")
        client_kwargs = {}
        if settings.r2_endpoint:
            client_kwargs["endpoint_url"] = settings.r2_endpoint
            client_kwargs["region_name"] = "auto"
        if settings.r2_access_key:
            client_kwargs["aws_access_key_id"] = settings.r2_access_key
        if settings.r2_secret_key:
            client_kwargs["aws_secret_access_key"] = settings.r2_secret_key
        self._client = boto3.client("s3", **client_kwargs)

    def read(self, rel_path: str) -> dict:
        rel = rel_path.lstrip("./")
        key = f"{self._prefix}/{rel}" if self._prefix else rel
        response = self._client.get_object(Bucket=self._bucket, Key=key)
        return json.loads(response["Body"].read().decode("utf-8"))
