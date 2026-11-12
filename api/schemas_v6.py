from __future__ import annotations

from typing import Any

from pydantic import BaseModel


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


class V6WorkDetail(BaseModel):
    work: V6WorkSummary
    resources: list[V6ResourceRead] = []
