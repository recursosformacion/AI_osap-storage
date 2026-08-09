from __future__ import annotations

from application.use_cases.works import GetWork, SearchWorks
from fastapi import APIRouter, Depends, Query
from infrastructure.config import Settings

from api.dependencies import GetWorkDep, SearchWorksDep, get_settings
from api.schemas import ResourceRead, WorkDetailRead, WorkRead
from api.urls import build_resource_url

router = APIRouter(tags=["works"])


@router.get(
    "/api/v1/works",
    response_model=list[WorkRead],
    summary="Buscar obras",
    description="Busca obras por compositor, título o catálogo. Devuelve la lista de Works.",
)
async def list_works(
    q: str = Query(default="", description="Texto a buscar (compositor, título, catálogo)"),
    limit: int = Query(50, ge=1, le=200),
    offset: int = Query(0, ge=0),
    uc: SearchWorks = Depends(SearchWorksDep),
) -> list[WorkRead]:
    works = await uc.execute(q, limit=limit, offset=offset)
    return [WorkRead.model_validate(w) for w in works]


@router.get(
    "/api/v1/works/{work_id}",
    response_model=WorkDetailRead,
    summary="Obra y sus representaciones",
    description="Devuelve una Work con todas sus Resource (representaciones) y sus URLs de descarga.",
)
async def get_work(
    work_id: int,
    uc: GetWork = Depends(GetWorkDep),
    settings: Settings = Depends(get_settings),
) -> WorkDetailRead:
    detail = await uc.execute(work_id)
    resources = []
    for r in detail.resources:
        url, available = build_resource_url(r.relative_path, r.file_id, settings)
        resources.append(
            ResourceRead(
                relative_path=r.relative_path,
                format=r.format,
                file_id=r.file_id,
                available=available,
                url=url,
            )
        )
    work_read = WorkRead.model_validate(detail.work)
    work_read.genres = detail.genres
    work_read.instruments = detail.instruments
    work_read.parts_names = detail.parts_names
    return WorkDetailRead(work=work_read, resources=resources)
