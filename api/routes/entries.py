from __future__ import annotations

from dataclasses import asdict

from application.use_cases.resolve_file import ResolveFile
from fastapi import APIRouter, Depends, Query
from infrastructure.config import Settings

from api.dependencies import ResolveFileDep, get_settings
from api.schemas import ResolutionRead
from api.urls import build_resolution_url

router = APIRouter(prefix="/api/v1/entries", tags=["entries"])


@router.get(
    "/resolve",
    response_model=ResolutionRead,
    summary="Resolver una obra",
    description="Dada una relative_path o logical_id responde 'lo tengo / no lo tengo' "
    "y devuelve la URL de descarga (CDN) si la obra está disponible.",
)
async def resolve(
    relative_path: str | None = Query(default=None),
    logical_id: str | None = Query(default=None),
    uc: ResolveFile = Depends(ResolveFileDep),
    settings: Settings = Depends(get_settings),
) -> ResolutionRead:
    resolution = await uc.execute(relative_path=relative_path, logical_id=logical_id)
    available, url = build_resolution_url(resolution, settings)
    data = asdict(resolution)
    data["available"] = available
    data["url"] = url
    return ResolutionRead(**data)
