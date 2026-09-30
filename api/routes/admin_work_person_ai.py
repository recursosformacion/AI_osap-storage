"""Endpoints admin de la atribución asistida por IA (propuestas y revisión humana).

Solo propone y revisa. Aceptar una propuesta `pending` asigna la persona por la vía canónica
y lo audita en `work_attribution_audit`, todo en una transacción. Sin
`OSAP_STORAGE_GEMINI_API_KEY` responde 503 "IA no configurada" sin afectar al resto de storage.

Los errores devuelven `detail` estructurado (`code` + `message`) para que osap-api pueda
propagar el código exacto al panel de revisión.
"""

from __future__ import annotations

from application.use_cases.work_attribution_ai import (
    AddReviewRelation,
    GetWorkAttributionProposal,
    GetWorkReview,
    ListWorkAttributionProposals,
    ListWorkReviews,
    ProposeWorkAttribution,
    ReviewProposal,
    ReviewRelation,
    SetWorkAttribution,
)
from domain.exceptions import ProposalAssignmentError, ProposalStateError
from fastapi import APIRouter, Body, Depends, HTTPException, Query
from infrastructure.ai.errors import AiNotConfiguredError, AiUpstreamError

from api.dependencies import (
    AddReviewRelationDep,
    GetWorkAttributionProposalDep,
    GetWorkReviewDep,
    ListWorkAttributionProposalsDep,
    ListWorkReviewsDep,
    ProposeWorkAttributionDep,
    ReviewProposalDep,
    ReviewRelationDep,
    SetWorkAttributionDep,
)

router = APIRouter(prefix="/api/admin/work-person-ai", tags=["admin-works"])


def _error(status_code: int, code: str, message: str) -> HTTPException:
    return HTTPException(status_code=status_code, detail={"code": code, "message": message})


# --- revisión humana: artefacto de decisiones (atribución + personas) ----------
#
# Se declaran antes de `/{proposal_id}` para que las rutas literales no se interpreten como id.


@router.get(
    "/reviews",
    summary="Lista revisiones de atribución IA",
    description="Conjunto de decisiones por obra (atribución + personas relacionadas).",
)
async def list_reviews(
    status: str | None = Query(default=None, pattern=r"^(pending|reviewed)$"),
    limit: int = Query(50, ge=1, le=500),
    offset: int = Query(0, ge=0),
    uc: ListWorkReviews = Depends(ListWorkReviewsDep),
):
    return await uc.execute(status, limit, offset)


@router.get(
    "/reviews/{work_id}",
    summary="Revisión de una obra (atribución + personas relacionadas)",
    description="Incluye el contexto congelado, contradicciones y la decisión de cada "
    "relación (`pending|accepted|rejected|uncertain`). Nada de esto escribe en "
    "`works_person_roles`.",
)
async def get_review(work_id: int, uc: GetWorkReview = Depends(GetWorkReviewDep)):
    try:
        return await uc.execute(work_id)
    except LookupError as exc:
        raise _error(404, "NOT_FOUND", str(exc)) from exc


@router.post(
    "/reviews/{work_id}/attribution",
    summary="Decide la atribución de la obra (revisión humana)",
    description="Fija `identified|anonymous|traditional|unknown` + nota y marca la revisión "
    "como `reviewed`. No escribe en `works_person_roles`.",
)
async def set_attribution(
    work_id: int,
    payload: dict = Body(...),
    uc: SetWorkAttribution = Depends(SetWorkAttributionDep),
):
    status = str(payload.get("attribution_status") or "")
    if status not in ("identified", "anonymous", "traditional", "unknown"):
        raise _error(422, "VALIDATION_ERROR", "attribution_status inválido")
    try:
        return await uc.execute(work_id, status, payload.get("note"), payload.get("reviewed_by"))
    except LookupError as exc:
        raise _error(404, "NOT_FOUND", str(exc)) from exc


@router.post(
    "/reviews/{work_id}/relations",
    summary="Añade una relación persona×rol decidida por una persona (revisión humana)",
    description="Permite lo que el modelo no encontró («aquí hay un arreglista»): `origin=human`, "
    "idempotente, con `decided_by`. Acepta `person_id` o `person_name` (resuelto con las mismas "
    "reglas canónicas; nunca crea personas) + `role_id` + `decision` + `evidence`. Nunca escribe "
    "en `works_person_roles`.",
)
async def add_review_relation(
    work_id: int,
    payload: dict = Body(...),
    uc: AddReviewRelation = Depends(AddReviewRelationDep),
):
    try:
        return await uc.execute(
            work_id,
            person_id=payload.get("person_id"),
            person_name=payload.get("person_name"),
            role_id=int(payload.get("role_id") or 0),
            decision=str(payload.get("decision") or "accepted"),
            evidence=payload.get("evidence"),
            reviewed_by=payload.get("reviewed_by"),
        )
    except ValueError as exc:
        raise _error(422, "VALIDATION_ERROR", str(exc)) from exc
    except LookupError as exc:
        raise _error(404, "NOT_FOUND", str(exc)) from exc


@router.post(
    "/reviews/relations/{relation_id}",
    summary="Decide una relación persona×rol (revisión humana)",
    description="`decision` = pending|accepted|rejected|uncertain. No escribe en "
    "`works_person_roles`: la aplicación la hará el programa de Fase 6.",
)
async def review_relation(
    relation_id: int,
    payload: dict = Body(...),
    uc: ReviewRelation = Depends(ReviewRelationDep),
):
    decision = str(payload.get("decision") or "")
    if decision not in ("pending", "accepted", "rejected", "uncertain"):
        raise _error(422, "VALIDATION_ERROR", "decision inválida")
    try:
        return await uc.execute(relation_id, decision, payload.get("reviewed_by"))
    except LookupError as exc:
        raise _error(404, "NOT_FOUND", str(exc)) from exc


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
