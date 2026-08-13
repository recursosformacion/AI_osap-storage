from __future__ import annotations

from application.use_cases.catalogues import CatalogueQueries
from fastapi import APIRouter, Depends, Query

from api.dependencies import CatalogueQueriesDep
from api.schemas import CatalogueRead

router = APIRouter(prefix="/api/v1/catalogues", tags=["catalogues"])


@router.get(
    "",
    response_model=list[CatalogueRead],
    summary="Catálogos musicales",
    description="Lista catálogos. Filtra por ?prefix= (sigla) o ?composer= (nombre). "
    "El catálogo identifica al compositor y ayuda a la limpieza de compositores.",
)
async def list_catalogues(
    prefix: str | None = Query(default=None, description="Sigla, p. ej. K, BWV, Hob"),
    composer: str | None = Query(default=None, description="Nombre del compositor"),
    limit: int = Query(100, ge=1, le=500),
    offset: int = Query(0, ge=0),
    uc: CatalogueQueries = Depends(CatalogueQueriesDep),
) -> list[CatalogueRead]:
    if prefix:
        items = await uc.by_prefix(prefix)
    elif composer:
        items = await uc.by_composer(composer)
    else:
        items = await uc.list(limit=limit, offset=offset)
    return [CatalogueRead.model_validate(c) for c in items]
