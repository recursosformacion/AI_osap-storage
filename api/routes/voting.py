from __future__ import annotations

from application.use_cases.voting import (
    GetComposerStatistics,
    GetWorkStatistics,
    RecordVote,
)
from fastapi import APIRouter, Depends

from api.dependencies import (
    GetComposerStatisticsDep,
    GetWorkStatisticsDep,
    RecordVoteDep,
)
from api.schemas import (
    ComposerStatisticsRead,
    VoteCreate,
    VoteRead,
    WorkStatisticsRead,
)

router = APIRouter(prefix="/api/v1", tags=["voting-statistics"])


@router.post(
    "/works/{work_id}/votes",
    response_model=VoteRead,
    status_code=201,
    summary="Registrar voto",
    description="Registra el voto de un usuario (1-5) sobre una obra. Un usuario solo puede "
    "votar una misma obra una vez al día (UTC).",
)
async def register_vote(
    work_id: int,
    payload: VoteCreate,
    uc: RecordVote = Depends(RecordVoteDep),
) -> VoteRead:
    vote = await uc.execute(payload.user_id, work_id, payload.vote)
    return VoteRead.model_validate(vote)


@router.get(
    "/works/{work_id}/statistics",
    response_model=WorkStatisticsRead,
    summary="Estadísticas de una Work",
    description="Votos y valoración media derivados de la obra.",
)
async def work_statistics(
    work_id: int,
    uc: GetWorkStatistics = Depends(GetWorkStatisticsDep),
) -> WorkStatisticsRead:
    return WorkStatisticsRead.model_validate(await uc.execute(work_id))


@router.get(
    "/composers/{composer_id}/statistics",
    response_model=ComposerStatisticsRead,
    summary="Valoración agregada de un Composer",
    description="Works, votos y valoración media del compositor canónico. Si el id es un "
    "compositor fusionado, devuelve la del compositor activo destino.",
)
async def composer_statistics(
    composer_id: str,
    uc: GetComposerStatistics = Depends(GetComposerStatisticsDep),
) -> ComposerStatisticsRead:
    return ComposerStatisticsRead.model_validate(await uc.execute(composer_id))
