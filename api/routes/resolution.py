from __future__ import annotations

from application.use_cases.resolution import ResolveWorkGrouping
from fastapi import APIRouter, Depends, Query

from api.dependencies import ResolveWorkGroupingDep
from api.schemas import ResolutionResultRead

router = APIRouter(
    prefix="/api/admin/resolution",
    tags=["admin-resolution"],
)


@router.get(
    "/works/{work_id}",
    response_model=ResolutionResultRead,
    summary="Resolver agrupación de una obra",
    description=(
        "Resuelve Resource → Representation → Work (agrupación inferida, solo lectura). "
        "Devuelve grupos, reglas aplicadas, reglas de bloqueo/revisión y atributos comunes."
    ),
)
async def resolve_work(
    work_id: int,
    candidate_limit: int = Query(50, ge=1, le=500),
    uc: ResolveWorkGrouping = Depends(ResolveWorkGroupingDep),
) -> ResolutionResultRead:
    result = await uc.execute(work_id, candidate_limit=candidate_limit)
    return ResolutionResultRead.model_validate(result)
