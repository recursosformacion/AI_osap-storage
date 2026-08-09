from __future__ import annotations

from application.use_cases.composer_admin import (
    GetComposerDetail,
    GetComposerWorks,
    ListComposers,
    MergeComposers,
)
from fastapi import APIRouter, Depends, Query

from api.dependencies import (
    GetComposerDetailDep,
    GetComposerWorksDep,
    ListComposersDep,
    MergeComposersDep,
)
from api.schemas import (
    ComposerAdminDetail,
    ComposerAdminListResult,
    ComposerAdminRead,
    ComposerWorkRefRead,
    ComposerWorksResult,
    MergeComposersRequest,
    MergeComposersResultRead,
)

router = APIRouter(prefix="/api/admin/composers", tags=["admin-composers"])


@router.get(
    "",
    response_model=ComposerAdminListResult,
    summary="Listar compositores",
    description="Listado administrativo paginado de compositores activos. "
    "Filtra por nombre o alias con la misma normalización del resolver.",
)
async def list_composers(
    q: str | None = Query(default=None, description="Filtro por nombre o alias"),
    limit: int = Query(50, ge=1, le=500),
    offset: int = Query(0, ge=0),
    uc: ListComposers = Depends(ListComposersDep),
) -> ComposerAdminListResult:
    result = await uc.execute(limit=limit, offset=offset, q=q)
    return ComposerAdminListResult(
        items=[ComposerAdminRead.model_validate(i) for i in result.items],
        total=result.total,
    )


@router.get(
    "/candidates",
    response_model=ComposerAdminListResult,
    summary="Candidatos a fusión",
    description="Asistencia a la revisión manual: devuelve compositores activos que "
    "coinciden con la búsqueda por nombre o alias. Nunca ejecuta fusiones automáticas.",
)
async def composer_candidates(
    q: str = Query(default="", description="Texto a buscar por nombre o alias"),
    limit: int = Query(50, ge=1, le=500),
    offset: int = Query(0, ge=0),
    uc: ListComposers = Depends(ListComposersDep),
) -> ComposerAdminListResult:
    result = await uc.execute(limit=limit, offset=offset, q=q or None)
    return ComposerAdminListResult(
        items=[ComposerAdminRead.model_validate(i) for i in result.items],
        total=result.total,
    )


@router.get(
    "/{composer_id}",
    response_model=ComposerAdminDetail,
    summary="Detalle de un compositor",
    description="Devuelve el compositor con sus aliases, works_count, estado y referencia de fusión.",
)
async def get_composer(
    composer_id: str,
    uc: GetComposerDetail = Depends(GetComposerDetailDep),
) -> ComposerAdminDetail:
    return ComposerAdminDetail.model_validate(await uc.execute(composer_id))


@router.get(
    "/{composer_id}/works",
    response_model=ComposerWorksResult,
    summary="Works de un compositor",
    description="Works asociadas al compositor (paginado). Sirve para revisar el impacto de una fusión.",
)
async def composer_works(
    composer_id: str,
    limit: int = Query(50, ge=1, le=500),
    offset: int = Query(0, ge=0),
    uc: GetComposerWorks = Depends(GetComposerWorksDep),
) -> ComposerWorksResult:
    works, total = await uc.execute(composer_id, limit=limit, offset=offset)
    return ComposerWorksResult(
        items=[ComposerWorkRefRead.model_validate(w) for w in works],
        total=total,
    )


@router.post(
    "/{target_id}/merge",
    response_model=MergeComposersResultRead,
    summary="Fusionar compositores",
    description="Fusiona `source_ids` dentro de `target_id` de forma atómica. El target "
    "permanece activo; los source quedan `merged` con `merged_into = target`.",
)
async def merge_composers(
    target_id: str,
    payload: MergeComposersRequest,
    uc: MergeComposers = Depends(MergeComposersDep),
) -> MergeComposersResultRead:
    result = await uc.execute(target_id, payload.source_ids)
    return MergeComposersResultRead.model_validate(result)
