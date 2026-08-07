from __future__ import annotations

import os

from application.use_cases.works import GetWork, ResourceSummary, SearchWorks, WorkDetail
from fastapi import APIRouter, Depends, HTTPException, Query
from fastapi.responses import RedirectResponse
from infrastructure.config import Settings

from api.dependencies import GetWorkDep, SearchWorksDep, get_settings
from api.urls import build_resource_url

router = APIRouter(tags=["provider"])

_MIME = {
    "MusicXML": "application/vnd.recordare.musicxml+xml",
    "PDF": "application/pdf",
    "MIDI": "audio/midi",
}


def _mime(fmt: str | None) -> str | None:
    return _MIME.get(fmt or "")


def _rid(r: ResourceSummary) -> str:
    if r.file_id:
        return f"rep-{r.file_id}"
    return f"rep-{os.path.basename(r.relative_path)}"


def _parse_include(include: str) -> set[str]:
    if include.strip().lower() == "all":
        return {"metadata", "statistics", "representations"}
    return {part.strip().lower() for part in include.split(",") if part.strip()}


def _metadata(detail: WorkDetail) -> dict:
    w = detail.work
    tags = [t.strip() for t in (w.tags or "").split(",") if t.strip()]
    return {
        "subtitle": w.subtitle,
        "song_name": w.song_name,
        "opus": w.opus,
        "musical_key": w.musical_key,
        "duration": w.duration,
        "measures": w.measures,
        "pages": w.pages,
        "parts": w.parts,
        "license": w.license,
        "public_domain": w.public_domain,
        "description": w.description,
        "thumbnails": w.thumbnails,
        "genres": detail.genres,
        "tags": tags,
        "instruments": detail.instruments,
        "parts_names": detail.parts_names,
    }


def _representations(detail: WorkDetail) -> list[dict]:
    out = []
    for r in detail.resources:
        out.append(
            {
                "id": _rid(r),
                "format": r.format,
                "available": r.available,
                "license": detail.work.license,
                "mime_type": _mime(r.format),
                "links": {
                    "download": f"/api/resource/{detail.work.id}/representations/{_rid(r)}/download",
                    "view": None,
                    "thumbnail": None,
                },
            }
        )
    return out


@router.get(
    "/api/search",
    summary="Buscar (Works ligeras)",
    description="Contrato v1.3: devuelve únicamente lo mínimo para localizar (id, title, composer, catalogue, confidence).",
)
async def search(
    q: str = Query("", description="Texto de búsqueda"),
    limit: int = Query(50, ge=1, le=200),
    uc: SearchWorks = Depends(SearchWorksDep),
) -> dict:
    works = await uc.execute(q, limit=limit)
    return {
        "works": [
            {
                "id": w.id,
                "title": w.title,
                "composer": w.composer,
                "catalogue": w.catalogue,
                "confidence": 1.0,
            }
            for w in works
        ]
    }


@router.get(
    "/api/resource/{work_id}",
    summary="Obtener una Work completa",
    description="Contrato v1.3: devuelve work + metadata/statistics/representations según include=. "
    "include = metadata[,representations][,statistics] | all",
)
async def resource(
    work_id: int,
    include: str = Query("", description="Qué incluir"),
    uc: GetWork = Depends(GetWorkDep),
) -> dict:
    detail = await uc.execute(work_id)
    wanted = _parse_include(include)
    body: dict = {
        "work": {
            "id": detail.work.id,
            "title": detail.work.title,
            "composer": detail.work.composer,
            "catalogue": detail.work.catalogue,
        }
    }
    if "metadata" in wanted:
        body["metadata"] = _metadata(detail)
    if "statistics" in wanted:
        body["statistics"] = {}
    if "representations" in wanted:
        body["representations"] = _representations(detail)
    return body


@router.get(
    "/api/resource/{work_id}/representations/{rid}/download",
    summary="Descargar una representación",
    description="Contrato v1.3: redirige o transmite la representación (el cliente no conoce el CDN).",
)
async def download_representation(
    work_id: int,
    rid: str,
    uc: GetWork = Depends(GetWorkDep),
    settings: Settings = Depends(get_settings),
) -> RedirectResponse:
    detail = await uc.execute(work_id)
    for r in detail.resources:
        if _rid(r) == rid:
            url, available = build_resource_url(r.relative_path, r.file_id, settings)
            if not available or not url:
                raise HTTPException(status_code=404, detail="representación no disponible")
            return RedirectResponse(url, status_code=302)
    raise HTTPException(status_code=404, detail="representación no encontrada")
