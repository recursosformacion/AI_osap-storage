from __future__ import annotations

from application.use_cases.archives import GetArchive, ListArchives
from fastapi import APIRouter, Depends, Query

from api.dependencies import GetArchiveDep, ListArchivesDep
from api.schemas import ArchiveRead

router = APIRouter(prefix="/api/v1/archives", tags=["archives"])


@router.get("", response_model=list[ArchiveRead])
async def list_archives(
    limit: int = Query(100, ge=1, le=500),
    offset: int = Query(0, ge=0),
    uc: ListArchives = Depends(ListArchivesDep),
) -> list[ArchiveRead]:
    archives = await uc.execute(limit=limit, offset=offset)
    return [ArchiveRead.model_validate(a) for a in archives]


@router.get("/{archive_id}", response_model=ArchiveRead)
async def get_archive(
    archive_id: int,
    uc: GetArchive = Depends(GetArchiveDep),
) -> ArchiveRead:
    return ArchiveRead.model_validate(await uc.execute(archive_id))
