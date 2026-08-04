from __future__ import annotations

from application.use_cases.providers import (
    CreateProvider,
    CreateProviderCommand,
    GetProvider,
    ListProviders,
)
from fastapi import APIRouter, Depends, Query

from api.dependencies import CreateProviderDep, GetProviderDep, ListProvidersDep
from api.schemas import ProviderCreate, ProviderRead

router = APIRouter(prefix="/api/v1/providers", tags=["providers"])


@router.post(
    "",
    response_model=ProviderRead,
    status_code=201,
    summary="Crear proveedor",
    description="Crea un proveedor de almacenamiento (local, cloudflare_r2...).",
)
async def create_provider(
    payload: ProviderCreate,
    uc: CreateProvider = Depends(CreateProviderDep),
) -> ProviderRead:
    provider = await uc.execute(
        CreateProviderCommand(
            name=payload.name,
            provider_type=payload.provider_type,
            config=payload.config,
            enabled=payload.enabled,
        )
    )
    return ProviderRead.model_validate(provider)


@router.get(
    "",
    response_model=list[ProviderRead],
    summary="Listar proveedores",
    description="Lista los proveedores de almacenamiento registrados.",
)
async def list_providers(
    enabled_only: bool = Query(False),
    uc: ListProviders = Depends(ListProvidersDep),
) -> list[ProviderRead]:
    providers = await uc.execute(enabled_only=enabled_only)
    return [ProviderRead.model_validate(p) for p in providers]


@router.get(
    "/{provider_id}",
    response_model=ProviderRead,
    summary="Detalle de un proveedor",
    description="Devuelve un proveedor de almacenamiento por su id.",
)
async def get_provider(
    provider_id: int,
    uc: GetProvider = Depends(GetProviderDep),
) -> ProviderRead:
    return ProviderRead.model_validate(await uc.execute(provider_id))
