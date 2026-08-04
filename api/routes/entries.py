from __future__ import annotations

from dataclasses import asdict

from application.use_cases.resolve_file import ResolveFile
from fastapi import APIRouter, Depends, Query
from infrastructure.config import Settings

from api.dependencies import ResolveFileDep, get_settings
from api.schemas import ResolutionRead

router = APIRouter(prefix="/api/v1/entries", tags=["entries"])


@router.get("/resolve", response_model=ResolutionRead)
async def resolve(
    relative_path: str | None = Query(default=None),
    logical_id: str | None = Query(default=None),
    uc: ResolveFile = Depends(ResolveFileDep),
    settings: Settings = Depends(get_settings),
) -> ResolutionRead:
    resolution = await uc.execute(relative_path=relative_path, logical_id=logical_id)
    url = None
    if resolution.available and resolution.file_id is not None:
        url = f"{settings.public_base_url.rstrip('/')}/api/v1/files/{resolution.file_id}/content"
    return ResolutionRead(**asdict(resolution), url=url)
