from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, Field


class V6WorkSummary(BaseModel):
    id: int
    title: str | None = None
    song_name: str | None = None
    catalogue: str | None = None
    musical_key: str | None = None
    resource_count: int = 0


class V6FileRead(BaseModel):
    id: int
    name: str
    mime_type: str | None = None
    size_bytes: int | None = None
    status: str


class V6ResourceRead(BaseModel):
    id: int
    work_id: int
    kind: str
    title: str | None = None
    source_system: str | None = None
    external_id: str | None = None
    external_url: str | None = None
    license: str | None = None
    rights_holder: str | None = None
    is_reference: bool = False
    visibility: str = "public"
    metadata: dict[str, Any] | None = None


class V6ResourceDetail(V6ResourceRead):
    files: list[V6FileRead] = []


class V6IndexResource(BaseModel):
    id: int
    kind: str
    source_system: str | None = None
    external_id: str | None = None
    external_url: str | None = None
    file_ids: list[int] = []


class V6IndexWork(BaseModel):
    work_id: str
    title: str
    song_name: str | None = None
    catalogue: str | None = None
    composer: str | None = None
    resources: list[V6IndexResource] = []


class V6IndexPage(BaseModel):
    items: list[V6IndexWork] = []
    next_cursor: int | None = None


class V6AccessRequest(BaseModel):
    action: Literal["download", "view"] = "download"
    ttl_seconds: int | None = Field(default=None, ge=60, le=86400)


class V6AccessRead(BaseModel):
    url: str
    action: str
    expires_at: str | None = None


class V6WorkDetail(BaseModel):
    work: V6WorkSummary
    resources: list[V6ResourceRead] = []
