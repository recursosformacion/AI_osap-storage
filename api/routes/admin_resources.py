from __future__ import annotations

from application.use_cases.resource_admin import ResourceAdminCrud
from domain.exceptions import EntityNotFound
from fastapi import APIRouter, Depends, HTTPException, Query

from api.dependencies import ResourceAdminDep
from api.schemas import ResourceDetailRead, ResourceListResult, ResourceUpsertRequest

router = APIRouter(prefix="/api/admin/resources", tags=["admin-resources"])


@router.get("", response_model=ResourceListResult, summary="Listar recursos de obras")
async def list_resources(
    work_id: int | None = Query(None),
    representation_id: int | None = Query(None),
    type: str | None = Query(None),
    status: str | None = Query(None),
    has_url: bool | None = Query(None),
    q: str | None = Query(None, description="name / url"),
    limit: int = Query(50, ge=1, le=200),
    offset: int = Query(0, ge=0),
    uc: ResourceAdminCrud = Depends(ResourceAdminDep),
) -> ResourceListResult:
    items, total = await uc.list(work_id=work_id, representation_id=representation_id,
                                 type_=type, status=status, has_url=has_url, q=q,
                                 limit=limit, offset=offset)
    return ResourceListResult(items=items, total=total)


@router.get("/{resource_id}", response_model=ResourceDetailRead,
            summary="Ficha de recurso (obra + representación)")
async def get_resource(
    resource_id: int,
    uc: ResourceAdminCrud = Depends(ResourceAdminDep),
) -> ResourceDetailRead:
    try:
        return ResourceDetailRead.model_validate(await uc.detail(resource_id))
    except EntityNotFound as exc:
        raise HTTPException(status_code=404, detail="recurso no encontrado") from exc


@router.post("", response_model=ResourceDetailRead, status_code=201, summary="Crear recurso")
async def create_resource(
    payload: ResourceUpsertRequest,
    uc: ResourceAdminCrud = Depends(ResourceAdminDep),
) -> ResourceDetailRead:
    return ResourceDetailRead.model_validate(await uc.create(payload.model_dump(exclude_none=True)))


@router.put("/{resource_id}", response_model=ResourceDetailRead, summary="Editar recurso")
async def update_resource(
    resource_id: int,
    payload: ResourceUpsertRequest,
    uc: ResourceAdminCrud = Depends(ResourceAdminDep),
) -> ResourceDetailRead:
    return ResourceDetailRead.model_validate(
        await uc.update(resource_id, payload.model_dump(exclude_none=True)))


@router.delete("/{resource_id}", summary="Borrar recurso")
async def delete_resource(
    resource_id: int,
    uc: ResourceAdminCrud = Depends(ResourceAdminDep),
) -> dict[str, int]:
    return {"deleted": await uc.delete(resource_id)}
