from __future__ import annotations

from datetime import datetime
from typing import Any

from domain.entities.storage_provider import ProviderType
from pydantic import BaseModel, ConfigDict, Field


class Model(BaseModel):
    model_config = ConfigDict(from_attributes=True)


class ProviderCreate(BaseModel):
    name: str = Field(min_length=1, max_length=255)
    provider_type: ProviderType
    config: dict[str, Any] = Field(default_factory=dict)
    enabled: bool = True


class ProviderRead(Model):
    id: int
    name: str
    provider_type: ProviderType
    config: dict[str, Any]
    enabled: bool
    created_at: datetime
    updated_at: datetime


class FileCreate(BaseModel):
    sha256: str
    name: str = Field(min_length=1, max_length=512)
    mime_type: str | None = None
    size_bytes: int | None = None


class LocationRead(Model):
    id: int
    provider_id: int
    provider_name: str
    provider_type: ProviderType
    object_key: str
    status: str
    created_at: datetime
    updated_at: datetime


class FileRead(Model):
    id: int
    sha256: str
    name: str
    mime_type: str | None
    size_bytes: int | None
    status: str
    available: bool
    locations: list[LocationRead]
    created_at: datetime
    updated_at: datetime


class DownloadStart(BaseModel):
    source_url: str = Field(min_length=1)
    provider_id: int | None = None


class DownloadJobRead(Model):
    id: int
    file_id: int
    provider_id: int | None
    source_url: str
    status: str
    error_message: str | None
    created_at: datetime
    updated_at: datetime


class DownloadUrlRead(Model):
    url: str
    provider_id: int


class ArchiveRead(Model):
    id: int
    name: str
    url: str | None
    local_path: str | None
    status: str
    size: int | None
    sha256: str | None
    downloaded_at: datetime | None
    created_at: datetime
    updated_at: datetime


class ResolutionRead(Model):
    found: bool
    relative_path: str | None
    logical_id: str | None
    composer: str | None = None
    title: str | None = None
    archive_id: int | None
    archive_name: str | None
    status: str | None
    file_id: int | None
    available: bool
    url: str | None = None


class VerifyItemRead(Model):
    provider_id: int
    provider_name: str
    expected_sha256: str
    computed_sha256: str | None
    ok: bool


class VerifyResultRead(Model):
    file_id: int
    checks: list[VerifyItemRead]
    ok: bool


class StatisticsRead(Model):
    archives: int
    entries: int
    files: int
    downloaded_tar: int
    materialized: int
    pending: int
    bytes: int
    computed_at: datetime | None
    created_at: datetime | None
    updated_at: datetime | None


class WorkRead(Model):
    id: int
    composer: str | None = None
    title: str | None = None
    genre: str | None = None
    opus: str | None = None
    catalogue: str | None = None
    musical_key: str | None = None
    year: int | None = None
    instrumentation: str | None = None
    language: str | None = None
    tags: str | None = None
    work_key: str | None = None
    created_at: datetime | None = None
    updated_at: datetime | None = None


class ResourceRead(Model):
    relative_path: str
    format: str | None = None
    file_id: int | None = None
    available: bool = False
    url: str | None = None


class WorkDetailRead(Model):
    work: WorkRead
    resources: list[ResourceRead]
