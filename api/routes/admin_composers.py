from __future__ import annotations

from application.use_cases.composer_admin import (
    ComposerReviewStats,
    CreateComposer,
    GetComposerDetail,
    GetComposerWorks,
    ListComposers,
    MergeComposers,
    ReviewComposer,
)
from fastapi import APIRouter, Depends, Query

from api.dependencies import (
    ComposerReviewStatsDep,
    CreateComposerDep,
    GetComposerDetailDep,
    GetComposerWorksDep,
    ListComposersDep,
    MergeComposersDep,
    ReviewComposerDep,
)
from api.schemas import (
    ComposerAdminDetail,
    ComposerAdminListResult,
    ComposerAdminRead,
    ComposerReviewRequest,
    ComposerWorkRefRead,
    ComposerWorksResult,
    CreateComposerRequest,
    MergeComposersRequest,
    MergeComposersResultRead,
)

router = APIRouter(prefix="/api/admin/composers", tags=["admin-composers"])


@router.get(
    "/stats",
    summary="Composer review statistics",
    description="Conteo de compositores activos por review_status (total, correct, "
    "incorrect, reviewed, not_reviewed).",
)
async def composer_review_stats(uc: ComposerReviewStats = Depends(ComposerReviewStatsDep)) -> dict[str, int]:
    return await uc.execute()


@router.post(
    "",
    response_model=ComposerAdminRead,
    status_code=201,
    summary="Crear compositor",
    description="Crea un compositor con el nombre dado (para fusionar hacia un compositor "
    "inexistente). Si ya existe uno activo con ese nombre, devuelve ese.",
)
async def create_composer(
    payload: CreateComposerRequest,
    uc: CreateComposer = Depends(CreateComposerDep),
) -> ComposerAdminRead:
    result = await uc.execute(payload.name)
    return ComposerAdminRead.model_validate(result)


@router.get(
    "",
    response_model=ComposerAdminListResult,
    summary="Listar compositores",
    description="Listado administrativo paginado de compositores activos. "
    "Filtra por nombre o alias con la misma normalización del resolver, y opcionalmente "
    "por estado de revisión (?review=correct|false|pending).",
)
async def list_composers(
    q: str | None = Query(default=None, description="Filtro por nombre o alias"),
    review: str | None = Query(default=None, description="Filtro por review_status"),
    visible: str = Query(
        default="visible",
        pattern=r"^(visible|hidden|all)$",
        description="Filtro de visibilidad: visible (visible=1) | hidden (visible=0) | all (todos)",
    ),
    limit: int = Query(50, ge=1, le=500),
    offset: int = Query(0, ge=0),
    uc: ListComposers = Depends(ListComposersDep),
) -> ComposerAdminListResult:
    result = await uc.execute(limit=limit, offset=offset, q=q, review=review, visible=visible)
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


@router.post(
    "/{composer_id}/review",
    response_model=ComposerAdminDetail,
    summary="Marcar revisión de un compositor",
    description="Marca un compositor como correct/false/pending. No borra ni modifica la identidad.",
)
async def review_composer(
    composer_id: str,
    payload: ComposerReviewRequest,
    uc: ReviewComposer = Depends(ReviewComposerDep),
) -> ComposerAdminDetail:
    detail = await uc.execute(composer_id, payload.review_status)
    return ComposerAdminDetail.model_validate(detail)
