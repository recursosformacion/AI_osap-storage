"""Endpoints admin de la atribución asistida por IA (propuestas y revisión humana).

Solo propone y revisa. La asignación efectiva ocurre al aceptar una propuesta y se audita
en `work_attribution_history`. Sin `OSAP_STORAGE_GEMINI_API_KEY` responde 503 "IA no
configurada" sin afectar al resto de storage.
"""

from __future__ import annotations

from application.use_cases.work_attribution_ai import (
    GetWorkAttributionProposal,
    ListWorkAttributionProposals,
    ProposeWorkAttribution,
    ReviewProposal,
)
from fastapi import APIRouter, Body, Depends, HTTPException, Query
from infrastructure.ai.errors import AiNotConfiguredError

from api.dependencies import (
    GetWorkAttributionProposalDep,
    ListWorkAttributionProposalsDep,
    ProposeWorkAttributionDep,
    ReviewProposalDep,
)

router = APIRouter(prefix="/api/admin/work-person-ai", tags=["admin-works"])


@router.post("/propose/{work_id}", summary="Genera y guarda una propuesta IA para la obra")
async def propose(
    work_id: int,
    payload: dict = Body(default_factory=dict),
    uc: ProposeWorkAttribution = Depends(ProposeWorkAttributionDep),
):
    try:
        return await uc.execute(work_id, payload.get("batch_id"))
    except AiNotConfiguredError as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc
    except LookupError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


@router.get("", summary="Lista propuestas (filtro por estado)")
async def list_proposals(
    status: str | None = Query(default=None, pattern=r"^(pending|accepted|rejected|uncertain)$"),
    limit: int = Query(50, ge=1, le=500),
    offset: int = Query(0, ge=0),
    uc: ListWorkAttributionProposals = Depends(ListWorkAttributionProposalsDep),
):
    return await uc.execute(status, limit, offset)


@router.get("/{proposal_id}", summary="Detalle de una propuesta")
async def get_proposal(
    proposal_id: int,
    uc: GetWorkAttributionProposal = Depends(GetWorkAttributionProposalDep),
):
    try:
        return await uc.execute(proposal_id)
    except LookupError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


@router.post("/{proposal_id}/review", summary="Acepta / rechaza / marca dudosa una propuesta")
async def review(
    proposal_id: int,
    payload: dict = Body(...),
    uc: ReviewProposal = Depends(ReviewProposalDep),
):
    action = str(payload.get("action") or "")
    if action not in ("accept", "reject", "uncertain"):
        raise HTTPException(status_code=422, detail="action debe ser accept|reject|uncertain")
    try:
        return await uc.execute(
            proposal_id, action,
            reviewed_by=payload.get("reviewed_by"), note=payload.get("note"),
        )
    except LookupError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except AiNotConfiguredError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
