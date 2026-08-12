from __future__ import annotations

from typing import Any

from application.use_cases.works import GetWork, ResourceSummary, SearchWorks, SearchWorksFull, WorkDetail
from domain.entities.work import display_composer
from domain.ports.archive_repositories import ArchiveEntryRepository
from fastapi import APIRouter, Depends, HTTPException, Query
from fastapi.responses import RedirectResponse
from infrastructure.config import Settings

from api.dependencies import (
    GetWorkDep,
    SearchWorksDep,
    SearchWorksFullDep,
    get_archive_entry_repo,
    get_settings,
)
from api.schemas import (
    ProviderLookupItem,
    ProviderLookupResult,
    ProviderResourceResult,
    ProviderSearchResult,
    ProviderVersion,
    ProviderWorkRead,
)
from api.urls import build_resource_url

router = APIRouter(tags=["provider"])

_MIME = {
    "MusicXML": "application/vnd.recordare.musicxml+xml",
    "PDF": "application/pdf",
    "MIDI": "audio/midi",
}


def _mime(fmt: str | None) -> str | None:
    return _MIME.get(fmt or "")


def _resource_id(r: ResourceSummary) -> str:
    if r.file_id:
        return str(r.file_id)
    return f"res-{r.relative_path.split('/')[-1]}"


def _metadata(detail: WorkDetail) -> dict:
    w = detail.work
    tags = [t.strip() for t in (w.tags or "").split(",") if t.strip()]
    return {
        "subtitle": w.subtitle,
        "artist": w.artist,
        "song_name": w.song_name,
        "opus": w.opus,
        "musical_key": w.musical_key,
        "duration": w.duration,
        "measures": w.measures,
        "pages": w.pages,
        "parts": w.parts,
        "complexity": w.complexity,
        "license": w.license,
        "public_domain": w.public_domain,
        "description": w.description,
        "thumbnails": w.thumbnails,
        "genres": detail.genres,
        "tags": tags,
        "instruments": detail.instruments,
        "parts_names": detail.parts_names,
    }


def _statistics() -> dict:
    return {"favorites": None, "downloads": None, "views": None, "rating": None}


def _resources(detail: WorkDetail) -> list[dict]:
    out = []
    for r in detail.resources:
        if not r.available:
            continue
        rid = _resource_id(r)
        out.append(
            {
                "id": rid,
                "format": r.format,
                "mime_type": _mime(r.format),
                "available": r.available,
                "license": detail.work.license,
                "links": {"download": f"/api/download/{rid}", "view": None, "thumbnail": None},
            }
        )
    return out


def _work(detail: WorkDetail) -> dict[str, Any]:
    w = detail.work
    return {
        "id": w.id,
        "title": w.title,
        "composer": display_composer(w.composer),
        "composer_id": w.composer_id,
        "catalogue": w.catalogue,
        "aliases": [],
        "metadata": _metadata(detail),
        "statistics": _statistics(),
        "resources": _resources(detail),
    }


@router.get(
    "/api/version",
    response_model=ProviderVersion,
    summary="Versión del contrato",
)
async def version() -> ProviderVersion:
    return ProviderVersion(contract="osap-provider-v1", version="1.0")


@router.get(
    "/api/lookup",
    response_model=ProviderLookupResult,
    summary="Lookup (autocompletado)",
    description="Solo el índice: id, title, composer, catalogue, confidence. Sin metadata ni recursos.",
)
async def lookup(
    q: str = Query("", description="Texto de búsqueda"),
    limit: int = Query(20, ge=1, le=50),
    uc: SearchWorks = Depends(SearchWorksDep),
) -> ProviderLookupResult:
    works = await uc.execute(q, limit=limit)
    items = [
        ProviderLookupItem(
            id=w.id,
            title=w.title,
            composer=display_composer(w.composer),
            catalogue=w.catalogue,
            confidence=1.0,
        )
        for w in works
    ]
    return ProviderLookupResult(works=items)


@router.get(
    "/api/search",
    response_model=ProviderSearchResult,
    summary="Buscar (Works completas)",
    description="Devuelve Works completas (identidad + metadata + statistics + resources). Sin llamadas posteriores.",
)
async def search(
    q: str = Query("", description="Texto de búsqueda"),
    limit: int = Query(50, ge=1, le=200),
    uc: SearchWorksFull = Depends(SearchWorksFullDep),
) -> ProviderSearchResult:
    details = await uc.execute(q, limit=limit)
    return ProviderSearchResult(works=[ProviderWorkRead.model_validate(_work(d)) for d in details])


@router.get(
    "/api/resource/{work_id}",
    response_model=ProviderResourceResult,
    summary="Obtener una Work completa",
    description="Mismo DTO que search, para un único id.",
)
async def resource(work_id: int, uc: GetWork = Depends(GetWorkDep)) -> ProviderResourceResult:
    detail = await uc.execute(work_id)
    return ProviderResourceResult(work=ProviderWorkRead.model_validate(_work(detail)))


@router.get(
    "/api/download/{resource_id}",
    summary="Descargar un recurso",
    description="Storage resuelve el recurso físico internamente (CDN/R2/disco). Nunca expone hashes ni rutas internas.",
)
async def download(
    resource_id: str,
    entries: ArchiveEntryRepository = Depends(get_archive_entry_repo),
    settings: Settings = Depends(get_settings),
) -> RedirectResponse:
    try:
        file_id = int(resource_id)
    except ValueError:
        raise HTTPException(status_code=404, detail="recurso no encontrado") from None
    entry = await entries.get_by_file_id(file_id)
    if entry is None:
        raise HTTPException(status_code=404, detail="recurso no encontrado")
    url, available = build_resource_url(entry.relative_path, file_id, settings)
    if not available or not url:
        raise HTTPException(status_code=404, detail="recurso no disponible")
    return RedirectResponse(url, status_code=302)
