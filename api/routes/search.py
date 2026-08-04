from __future__ import annotations

from dataclasses import asdict

from application.use_cases.search_entries import SearchEntries
from fastapi import APIRouter, Depends, Query
from infrastructure.config import Settings

from api.dependencies import SearchEntriesDep, get_settings
from api.schemas import ResolutionRead
from api.urls import build_resolution_url

router = APIRouter(tags=["search"])


@router.get(
    "/api/v1/search",
    response_model=list[ResolutionRead],
    summary="Buscar obras",
    description="Busca en el índice por texto (compositor, título, lógica) o ruta. Devuelve cada obra "
    "con su disponibilidad y URL de descarga.",
)
async def search(
    q: str = Query(..., min_length=1, description="Texto a buscar"),
    limit: int = Query(50, ge=1, le=200),
    offset: int = Query(0, ge=0),
    uc: SearchEntries = Depends(SearchEntriesDep),
    settings: Settings = Depends(get_settings),
) -> list[ResolutionRead]:
    results = await uc.execute(q, limit=limit, offset=offset)
    out: list[ResolutionRead] = []
    for resolution in results:
        available, url = build_resolution_url(resolution, settings)
        data = asdict(resolution)
        data["available"] = available
        data["url"] = url
        out.append(ResolutionRead(**data))
    return out
