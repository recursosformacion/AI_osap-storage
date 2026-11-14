from __future__ import annotations

from application.use_cases.composer_admin import GetComposerDetail
from fastapi import APIRouter, Depends, Query

from api.dependencies import GetComposerDetailDep, ListComposersDep
from api.schemas import ComposerAdminListResult, ComposerAdminRead, ComposerPublicRead

router = APIRouter(prefix="/api/v1/composers", tags=["composers"])


@router.get("", response_model=ComposerAdminListResult, summary="Listado público de compositores")
async def list_composers(
    q: str | None = Query(default=None),
    limit: int = Query(50, ge=1, le=500),
    offset: int = Query(0, ge=0),
    uc=Depends(ListComposersDep),
) -> ComposerAdminListResult:
    result = await uc.execute(
        limit=limit, offset=offset, q=q, visible="visible", include_all=False
    )
    return ComposerAdminListResult(
        items=[ComposerAdminRead.model_validate(item) for item in result.items],
        total=result.total,
    )


@router.get(
    "/{person_id}",
    response_model=ComposerPublicRead,
    summary="Detalle de un compositor",
    description="Devuelve el compositor con su biografía (resumen, época, nacionalidad, "
    "obras clave, dato destacable y referencias bibliográficas). Lo consume osap-api "
    "para mostrar la ficha de compositor.",
)
async def get_composer(
    person_id: str,
    uc: GetComposerDetail = Depends(GetComposerDetailDep),
) -> ComposerPublicRead:
    return ComposerPublicRead.model_validate(await uc.execute(person_id))
