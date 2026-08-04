from __future__ import annotations

from application.use_cases.statistics import GetStatistics
from fastapi import APIRouter, Depends, Query

from api.dependencies import GetStatisticsDep
from api.schemas import StatisticsRead

router = APIRouter(prefix="/api/v1/statistics", tags=["statistics"])


@router.get(
    "",
    response_model=StatisticsRead,
    summary="Estadísticas del repositorio",
    description="Contadores del mirror (archives, entries, files, bytes...). "
    "Con ?refresh=true recalcula la instantánea.",
)
async def statistics(
    refresh: bool = Query(False),
    uc: GetStatistics = Depends(GetStatisticsDep),
) -> StatisticsRead:
    return StatisticsRead.model_validate(await uc.execute(refresh=refresh))
