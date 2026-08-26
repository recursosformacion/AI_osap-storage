from __future__ import annotations

from datetime import date, datetime
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
    composer_id: str | None = None
    title: str | None = None
    subtitle: str | None = None
    artist: str | None = None
    song_name: str | None = None
    genre: str | None = None
    opus: str | None = None
    catalogue: str | None = None
    musical_key: str | None = None
    year: int | None = None
    instrumentation: str | None = None
    language: str | None = None
    tags: str | None = None
    duration: str | None = None
    measures: int | None = None
    pages: int | None = None
    parts: int | None = None
    complexity: int | None = None
    license: str | None = None
    public_domain: bool = False
    description: str | None = None
    thumbnails: str | None = None
    work_key: str | None = None
    relative_path: str | None = None
    attribution_type: str | None = None
    attribution_note: str | None = None
    genres: list[str] = []
    instruments: list[str] = []
    parts_names: list[str] = []
    created_at: datetime | None = None
    updated_at: datetime | None = None


class WorkAdminDetail(Model):
    id: int
    composer: str | None = None
    composer_id: str | None = None
    title: str | None = None
    subtitle: str | None = None
    artist: str | None = None
    song_name: str | None = None
    genre: str | None = None
    opus: str | None = None
    catalogue: str | None = None
    musical_key: str | None = None
    year: int | None = None
    instrumentation: str | None = None
    language: str | None = None
    tags_csv: str | None = None
    duration: str | None = None
    measures: int | None = None
    pages: int | None = None
    parts: int | None = None
    complexity: int | None = None
    license: str | None = None
    public_domain: bool = False
    description: str | None = None
    thumbnails: str | None = None
    work_key: str | None = None
    relative_path: str | None = None
    attribution_type: str | None = None
    attribution_note: str | None = None
    tags: list[str] = []
    genres: list[str] = []
    instruments: list[str] = []
    parts_names: list[str] = []
    created_at: datetime | None = None
    updated_at: datetime | None = None


class WorkAdminListResult(Model):
    items: list[WorkAdminDetail]
    total: int


class WorkAdminUpdateRequest(Model):
    composer: str | None = None
    composer_id: str | None = None
    title: str | None = None
    subtitle: str | None = None
    artist: str | None = None
    song_name: str | None = None
    genre: str | None = None
    opus: str | None = None
    catalogue: str | None = None
    musical_key: str | None = None
    year: int | None = None
    instrumentation: str | None = None
    language: str | None = None
    duration: str | None = None
    measures: int | None = None
    pages: int | None = None
    parts: int | None = None
    complexity: int | None = None
    license: str | None = None
    public_domain: bool | None = None
    description: str | None = None
    thumbnails: str | None = None
    work_key: str | None = None
    relative_path: str | None = None
    attribution_type: str | None = None
    attribution_note: str | None = None
    tags: list[str] | None = None
    genres: list[str] | None = None
    instruments: list[str] | None = None
    parts_names: list[str] | None = None


class ResourceRead(Model):
    relative_path: str
    format: str | None = None
    file_id: int | None = None
    available: bool = False
    url: str | None = None


class WorkDetailRead(Model):
    work: WorkRead
    resources: list[ResourceRead]


class ComposerPublicRead(Model):
    """Ficha pública de compositor con biografía (desde la entidad ComposerDetail)."""
    model_config = ConfigDict(from_attributes=True)

    id: str
    name: str
    biography_summary: str | None = None
    biography_era: str | None = None
    biography_nationality: str | None = None
    biography_key_works: list[str] = []
    biography_key_fact: str | None = None
    biography_references: list[dict[str, str]] = []
    works_count: int = 0
    aliases: list[str] = []
    birth_year: str | None = None
    death_year: str | None = None


class ProviderResourceDTO(Model):
    id: str
    format: str | None = None
    mime_type: str | None = None
    available: bool = False
    license: str | None = None
    links: dict[str, str | None]


class ProviderWorkRead(Model):
    id: int
    title: str | None = None
    composer: str | None = None
    composer_id: str | None = None
    catalogue: str | None = None
    aliases: list[str] = []
    metadata: dict[str, Any] = {}
    statistics: dict[str, Any] = {}
    resources: list[ProviderResourceDTO] = []


class ProviderSearchResult(Model):
    works: list[ProviderWorkRead]


class ProviderResourceResult(Model):
    work: ProviderWorkRead


class ProviderLookupItem(Model):
    id: int
    title: str | None = None
    composer: str | None = None
    catalogue: str | None = None
    confidence: float = 1.0


class ProviderLookupResult(Model):
    works: list[ProviderLookupItem]


class ProviderVersion(Model):
    contract: str
    version: str


class ComposerAdminRead(Model):
    id: str
    name: str
    status: str
    aliases_count: int = 0
    works_count: int = 0
    review_status: str = "pending"
    visible: bool = True
    birth_year: str | None = None
    death_year: str | None = None
    biography_summary: str | None = None
    biography_era: str | None = None
    biography_nationality: str | None = None


class ComposerAdminListResult(Model):
    items: list[ComposerAdminRead]
    total: int


class ComposerIdentifierRead(Model):
    composer_id: str
    id_type: str
    id_value: str
    is_identity_anchor: bool = False
    source: str = "musicbrainz"
    strength: str | None = None
    channels: list[str] | None = None


class ComposerEvidenceRead(Model):
    composer_id: str
    rule: str
    decision: str
    reason: str
    anchor_type: str = "none"
    anchor_value: str = "none"
    channels: list | None = None
    identifiers_used: list | None = None
    matcher_version: str = ""
    id: int | None = None
    created_at: datetime | None = None


class ComposerCreationEvidenceRead(Model):
    id: int | None = None
    composer_id: str
    work_id: int | None = None
    work_title: str | None = None
    extracted_author: str | None = None
    provider: str | None = None
    resource_reference: str | None = None
    created_at: datetime | None = None


class ComposerAdminDetail(Model):
    id: str
    name: str
    status: str
    aliases: list[str] = []
    works_count: int = 0
    merged_into: str | None = None
    merged_at: datetime | None = None
    review_status: str = "pending"
    reviewed_at: datetime | None = None
    visible: bool = True
    birth_year: str | None = None
    death_year: str | None = None
    cluster_id: str | None = None
    review_reason: str | None = None
    biography_summary: str | None = None
    biography_era: str | None = None
    biography_nationality: str | None = None
    biography_key_works: list[str] = []
    biography_key_fact: str | None = None
    biography_references: list[dict[str, str]] = []
    identifiers: list[ComposerIdentifierRead] = []
    evidence: list[ComposerEvidenceRead] = []
    creation_evidence: list[ComposerCreationEvidenceRead] = []


class ComposerReviewRequest(BaseModel):
    review_status: str = Field(pattern="^(correct|incorrect|reviewed|not_reviewed)$")


class ComposerUpdateRequest(BaseModel):
    name: str | None = Field(default=None, min_length=1, max_length=1024)
    status: str | None = Field(default=None, pattern="^(active|merged|candidate)$")
    visible: bool | None = None
    birth_year: str | None = None
    death_year: str | None = None
    cluster_id: str | None = None
    review_status: str | None = Field(
        default=None, pattern="^(correct|incorrect|reviewed|not_reviewed|review_required)$"
    )
    review_reason: str | None = None
    musicbrainz_id: str | None = None


class BiographyUpdateRequest(BaseModel):
    summary: str | None = None
    era: str | None = None
    nationality: str | None = None
    key_works: list[str] | None = None
    key_fact: str | None = None
    references: list[dict[str, str]] | None = None


class ComposerWorkRefRead(Model):
    work_id: int
    title: str | None = None
    composer_id: str | None = None


class ComposerWorksResult(Model):
    items: list[ComposerWorkRefRead]
    total: int


class MergeComposersRequest(BaseModel):
    source_ids: list[str]


class CreateComposerRequest(BaseModel):
    name: str = Field(min_length=1)


class MergeComposersResultRead(Model):
    target_id: str
    sources_merged: list[str]
    aliases_transferred: int
    works_moved: int
    merge_operation_id: str


class AddAliasRequest(BaseModel):
    alias: str = Field(min_length=1, max_length=1024)


class MoveAliasRequest(BaseModel):
    target_composer_id: str = Field(min_length=1)
    from_composer_id: str = Field(min_length=1)


class AliasRead(Model):
    id: int
    alias: str
    normalized_alias: str


class MoveAliasResultRead(Model):
    alias: AliasRead


class PromoteAliasResultRead(Model):
    composer_id: str
    name: str


class SetAttributionRequest(BaseModel):
    composer_ids: list[str] = Field(min_length=1)
    attribution_type: str = Field(min_length=1, max_length=64)


class SetAttributionResultRead(Model):
    works_affected: int


class VoteCreate(BaseModel):
    user_id: str = Field(min_length=1, max_length=255)
    vote: int = Field(ge=1, le=5, description="Valoración 1-5")


class VoteRead(Model):
    id: int | None = None
    user_id: str
    work_id: int
    vote: int
    voted_at: datetime | None = None
    vote_day: date | None = None


class WorkStatisticsRead(Model):
    work_id: int
    rating: float | None = None
    adjusted_rating: float | None = None
    vote_count: int = 0
    work_count: int = 1
    confidence: float | None = None
    calculated_at: datetime | None = None


class ComposerStatisticsRead(Model):
    composer_id: str
    rating: float | None = None
    adjusted_rating: float | None = None
    vote_count: int = 0
    work_count: int = 0
    confidence: float | None = None
    calculated_at: datetime | None = None


class CatalogueRead(Model):
    id: int | None = None
    prefix: str
    composer: str
    catalogue_name: str
    creator: str
    ordering_criterion: str
    created_at: datetime | None = None


class TableCrudRow(Model):
    table: str
    row: dict[str, Any] = {}


class TableCrudRows(Model):
    table: str
    total: int
    rows: list[dict[str, Any]] = []


class TableCrudTables(Model):
    tables: list[str] = []
