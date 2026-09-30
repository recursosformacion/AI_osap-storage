"""Endpoints admin de la atribución asistida por IA (propuestas y revisión humana).

Solo propone y revisa. Aceptar una propuesta `pending` asigna la persona por la vía canónica
y lo audita en `work_attribution_audit`, todo en una transacción. Sin
`OSAP_STORAGE_GEMINI_API_KEY` responde 503 "IA no configurada" sin afectar al resto de storage.

Los errores devuelven `detail` estructurado (`code` + `message`) para que osap-api pueda
propagar el código exacto al panel de revisión.
"""

from __future__ import annotations

from application.use_cases.work_attribution_ai import (
    GetWorkAttributionProposal,
    ListWorkAttributionProposals,
    ProposeWorkAttribution,
    ReviewProposal,
)
from domain.exceptions import ProposalAssignmentError, ProposalStateError
from fastapi import APIRouter, Body, Depends, HTTPException, Query
from infrastructure.ai.errors import AiNotConfiguredError, AiUpstreamError

from api.dependencies import (
    GetWorkAttributionProposalDep,
    ListWorkAttributionProposalsDep,
    ProposeWorkAttributionDep,
    ReviewProposalDep,
)

router = APIRouter(prefix="/api/admin/work-person-ai", tags=["admin-works"])


def _error(status_code: int, code: str, message: str) -> HTTPException:
    return HTTPException(status_code=status_code, detail={"code": code, "message": message})


@router.post(
    "/propose/{work_id}",
    summary="Genera (o reutiliza) la propuesta IA de la obra",
    description="Sin `force`, si la obra ya tiene propuesta devuelve la última con "
    "`reused=true` sin llamar a la IA. Con `force=true` consulta de nuevo y guarda una "
    "propuesta nueva (las anteriores quedan como historial).",
)
async def propose(
    work_id: int,
    payload: dict = Body(default_factory=dict),
    force: bool = Query(default=False),
    uc: ProposeWorkAttribution = Depends(ProposeWorkAttributionDep),
):
    try:
        return await uc.execute(work_id, payload.get("batch_id"), force)
    except AiNotConfiguredError as exc:
        raise _error(503, "AI_NOT_CONFIGURED", str(exc)) from exc
    except AiUpstreamError as exc:
        raise _error(503, "AI_UNAVAILABLE", str(exc)) from exc
    except LookupError as exc:
        raise _error(404, "NOT_FOUND", str(exc)) from exc


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
        raise _error(404, "NOT_FOUND", str(exc)) from exc


@router.post("/{proposal_id}/review", summary="Acepta / rechaza / marca dudosa una propuesta")
async def review(
    proposal_id: int,
    payload: dict = Body(...),
    uc: ReviewProposal = Depends(ReviewProposalDep),
):
    action = str(payload.get("action") or "")
    if action not in ("accept", "reject", "uncertain"):
        raise _error(422, "VALIDATION_ERROR", "action debe ser accept|reject|uncertain")
    try:
        return await uc.execute(
            proposal_id, action,
            reviewed_by=payload.get("reviewed_by"), note=payload.get("note"),
        )
    except LookupError as exc:
        raise _error(404, "NOT_FOUND", str(exc)) from exc
    except ProposalStateError as exc:
        raise _error(409, "PROPOSAL_NOT_PENDING", str(exc)) from exc
    except ProposalAssignmentError as exc:
        raise _error(409, "PROPOSAL_NOT_ASSIGNABLE", str(exc)) from exc
    except AiNotConfiguredError as exc:
        raise _error(503, "AI_NOT_CONFIGURED", str(exc)) from exc
