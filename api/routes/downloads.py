from __future__ import annotations

from application.use_cases.get_download_job import GetDownloadJob
from fastapi import APIRouter, Depends

from api.dependencies import GetDownloadJobDep
from api.schemas import DownloadJobRead

router = APIRouter(prefix="/api/v1/downloads", tags=["downloads"])


@router.get("/{job_id}", response_model=DownloadJobRead)
async def get_download_job(
    job_id: int,
    uc: GetDownloadJob = Depends(GetDownloadJobDep),
) -> DownloadJobRead:
    return DownloadJobRead.model_validate(await uc.execute(job_id))
