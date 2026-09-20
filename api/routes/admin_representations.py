from __future__ import annotations

from application.use_cases.representation_admin import RepresentationAdminCrud
from domain.exceptions import EntityNotFound
from fastapi import APIRouter, Depends, HTTPException, Query

from api.dependencies import RepresentationAdminDep
from api.schemas import (
    RepresentationDetailRead,
    RepresentationListResult,
    RepresentationUpsertRequest,
)

router = APIRouter(prefix="/api/admin/representations", tags=["admin-representations"])


@router.get("", response_model=RepresentationListResult, summary="Listar representaciones")
async def list_representations(
    origin: str | None = Query(None),
    license: str | None = Query(None),
    works_id: int | None = Query(None),
    q: str | None = Query(None, description="origin_id / source_name"),
    limit: int = Query(50, ge=1, le=200),
    offset: int = Query(0, ge=0),
    uc: RepresentationAdminCrud = Depends(RepresentationAdminDep),
) -> RepresentationListResult:
    items, total = await uc.list(origin=origin, license_=license, works_id=works_id, q=q,
                                 limit=limit, offset=offset)
    return RepresentationListResult(items=items, total=total)


@router.get("/{representation_id}", response_model=RepresentationDetailRead,
            summary="Ficha de representación (recursos + editores + obra)")
async def get_representation(
    representation_id: int,
    uc: RepresentationAdminCrud = Depends(RepresentationAdminDep),
) -> RepresentationDetailRead:
    try:
        return RepresentationDetailRead.model_validate(await uc.detail(representation_id))
    except EntityNotFound as exc:
        raise HTTPException(status_code=404, detail="representación no encontrada") from exc


@router.post("", response_model=RepresentationDetailRead, status_code=201,
             summary="Crear representación")
async def create_representation(
    payload: RepresentationUpsertRequest,
    uc: RepresentationAdminCrud = Depends(RepresentationAdminDep),
) -> RepresentationDetailRead:
    return RepresentationDetailRead.model_validate(
        await uc.create(payload.model_dump(exclude_none=True)))


@router.put("/{representation_id}", response_model=RepresentationDetailRead,
            summary="Editar representación")
async def update_representation(
    representation_id: int,
    payload: RepresentationUpsertRequest,
    uc: RepresentationAdminCrud = Depends(RepresentationAdminDep),
) -> RepresentationDetailRead:
    return RepresentationDetailRead.model_validate(
        await uc.update(representation_id, payload.model_dump(exclude_none=True)))


@router.delete("/{representation_id}", summary="Borrar representación")
async def delete_representation(
    representation_id: int,
    uc: RepresentationAdminCrud = Depends(RepresentationAdminDep),
) -> dict[str, int]:
    return {"deleted": await uc.delete(representation_id)}
