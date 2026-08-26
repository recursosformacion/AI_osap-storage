from __future__ import annotations

from application.use_cases.composer_admin import GetComposerDetail
from fastapi import APIRouter, Depends

from api.dependencies import GetComposerDetailDep
from api.schemas import ComposerPublicRead

router = APIRouter(prefix="/api/v1/composers", tags=["composers"])


@router.get(
    "/{composer_id}",
    response_model=ComposerPublicRead,
    summary="Detalle de un compositor",
    description="Devuelve el compositor con su biografía (resumen, época, nacionalidad, "
    "obras clave, dato destacable y referencias bibliográficas). Lo consume osap-api "
    "para mostrar la ficha de compositor.",
)
async def get_composer(
    composer_id: str,
    uc: GetComposerDetail = Depends(GetComposerDetailDep),
) -> ComposerPublicRead:
    return ComposerPublicRead.model_validate(await uc.execute(composer_id))
