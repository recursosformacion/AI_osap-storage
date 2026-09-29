"""Superficie pública de estadísticas de catálogo (solo agregados, sin métricas internas).

`/api/v1/statistics` permanece **interno** (requiere service token). Esta ruta publica
únicamente contadores de catálogo/almacenamiento; nunca usuarios, descargas ni funnel.
"""

from __future__ import annotations

from application.use_cases.statistics import GetStatistics
from fastapi import APIRouter, Depends

from api.dependencies import GetStatisticsDep
from api.schemas import StatisticsPublicRead

router = APIRouter(prefix="/api/v1/public/statistics", tags=["statistics"])


@router.get(
    "",
    response_model=StatisticsPublicRead,
    summary="Estadísticas públicas del catálogo",
    description="Agregados públicos de catálogo/almacenamiento: archives, entries, files y bytes.",
)
async def public_statistics(uc: GetStatistics = Depends(GetStatisticsDep)) -> StatisticsPublicRead:
    stats = await uc.execute(refresh=False)
    return StatisticsPublicRead(
        archives=stats.archives,
        entries=stats.entries,
        files=stats.files,
        bytes=stats.bytes,
        computed_at=stats.computed_at,
    )
