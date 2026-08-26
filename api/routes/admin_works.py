from __future__ import annotations

from application.use_cases.work_admin import (
    GetWorkAdmin,
    ListWorksAdmin,
    UpdateWorkAdmin,
)
from domain.entities.work import Work
from fastapi import APIRouter, Depends, Query

from api.dependencies import (
    GetWorkAdminDep,
    ListWorksAdminDep,
    UpdateWorkAdminDep,
)
from api.schemas import WorkAdminDetail, WorkAdminListResult, WorkAdminUpdateRequest

router = APIRouter(prefix="/api/admin/works", tags=["admin-works"])


def _to_detail(d: object) -> WorkAdminDetail:
    return WorkAdminDetail.model_validate(d)


@router.get(
    "",
    response_model=WorkAdminListResult,
    summary="Listar obras (admin)",
    description="Listado administrativo paginado de obras con sus tags/genres/"
    "instruments/parts. Filtra por q (compositor/título/catálogo).",
)
async def list_works(
    q: str | None = Query(default=None, description="Filtro por compositor/título/catálogo"),
    limit: int = Query(50, ge=1, le=500),
    offset: int = Query(0, ge=0),
    uc: ListWorksAdmin = Depends(ListWorksAdminDep),
) -> WorkAdminListResult:
    result = await uc.execute(limit=limit, offset=offset, q=q)
    return WorkAdminListResult(
        items=[_to_detail(i) for i in result.items],
        total=result.total,
    )


@router.get(
    "/{work_id}",
    response_model=WorkAdminDetail,
    summary="Detalle de una obra (admin)",
    description="Metadatos de la obra + tags/genres/instruments/parts. Sin resources.",
)
async def get_work(
    work_id: int,
    uc: GetWorkAdmin = Depends(GetWorkAdminDep),
) -> WorkAdminDetail:
    return _to_detail(await uc.execute(work_id))


@router.put(
    "/{work_id}",
    response_model=WorkAdminDetail,
    summary="Editar una obra (admin)",
    description="Actualiza los metadatos y las listas (tags/genres/instruments/parts) "
    "de una obra. Las listas se reemplazan por completo si se envían.",
)
async def update_work(
    work_id: int,
    payload: WorkAdminUpdateRequest,
    uc: UpdateWorkAdmin = Depends(UpdateWorkAdminDep),
) -> WorkAdminDetail:
    work = Work(
        composer=payload.composer,
        composer_id=payload.composer_id,
        title=payload.title,
        subtitle=payload.subtitle,
        artist=payload.artist,
        song_name=payload.song_name,
        genre=payload.genre,
        opus=payload.opus,
        catalogue=payload.catalogue,
        musical_key=payload.musical_key,
        year=payload.year,
        instrumentation=payload.instrumentation,
        language=payload.language,
        duration=payload.duration,
        measures=payload.measures,
        pages=payload.pages,
        parts=payload.parts,
        complexity=payload.complexity,
        license=payload.license,
        public_domain=bool(payload.public_domain),
        description=payload.description,
        thumbnails=payload.thumbnails,
        work_key=payload.work_key,
        relative_path=payload.relative_path,
        attribution_type=payload.attribution_type,
        attribution_note=payload.attribution_note,
    )
    detail = await uc.execute(
        work_id,
        work=work,
        tags=payload.tags,
        genres=payload.genres,
        instruments=payload.instruments,
        parts=payload.parts_names,
    )
    return _to_detail(detail)
