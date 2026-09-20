"""Rutas de personas (modelo nuevo): listado por rol, ficha y obras.

Público (`/api/v1/persons`) muestra solo personas visibles; admin (`/api/admin/persons`)
incluye ocultas. Los roles se piden por clave: `role=composer`, `role=arranger`,
`role=composer,arranger`. Rol desconocido → 400.
"""

from __future__ import annotations

from application.use_cases.persons import GetPerson, GetPersonWorks, ListPersons
from domain.services.person_roles import UnknownRoleError
from fastapi import APIRouter, Depends, HTTPException, Query

from api.dependencies import GetPersonDep, GetPersonWorksDep, ListPersonsDep
from api.schemas import PersonListRead, PersonPublicRead, PersonWorksResult

public_router = APIRouter(prefix="/api/v1/persons", tags=["persons"])
admin_router = APIRouter(prefix="/api/admin/persons", tags=["admin-persons"])


def _register_person_routes(router: APIRouter, *, include_hidden: bool) -> None:
    @router.get(
        "",
        response_model=PersonListRead,
        summary="Listado de personas por rol",
        description="Personas del catálogo filtradas por rol (`composer`, `arranger`, "
        "`performer`, `editor`…). Sin `role` se asume `composer`. Incluye, por persona, sus "
        "roles, nº de obras (para los roles pedidos), alias y datos de biografía.",
    )
    async def list_persons(
        role: str | None = Query(default=None, description="composer,arranger,…"),
        q: str | None = Query(default=None, description="texto en nombre o alias"),
        limit: int = Query(50, ge=1, le=500),
        offset: int = Query(0, ge=0),
        uc: ListPersons = Depends(ListPersonsDep),
    ) -> PersonListRead:
        try:
            data = await uc.execute(
                role=role, q=q, limit=limit, offset=offset, include_hidden=include_hidden
            )
        except UnknownRoleError as exc:
            raise HTTPException(status_code=400, detail=f"rol desconocido: {exc}") from exc
        return PersonListRead.model_validate(data)

    @router.get(
        "/{person_id}",
        response_model=PersonPublicRead,
        summary="Ficha de una persona",
        description="Persona con sus roles, alias y biografía (resumen, época, nacionalidad, "
        "obras clave y dato destacable).",
    )
    async def get_person(
        person_id: str,
        uc: GetPerson = Depends(GetPersonDep),
    ) -> PersonPublicRead:
        person = await uc.execute(person_id)
        if person is None:
            raise HTTPException(status_code=404, detail="persona no encontrada")
        return PersonPublicRead.model_validate(person)

    @router.get(
        "/{person_id}/works",
        response_model=PersonWorksResult,
        summary="Obras de una persona",
        description="Obras en las que participa la persona, con sus roles en cada obra y el "
        "género e instrumentos de la obra. `role` acota a las obras donde tiene ese rol.",
    )
    async def person_works(
        person_id: str,
        role: str | None = Query(default=None, description="composer,arranger,…"),
        limit: int = Query(50, ge=1, le=500),
        offset: int = Query(0, ge=0),
        uc: GetPersonWorks = Depends(GetPersonWorksDep),
    ) -> PersonWorksResult:
        try:
            data = await uc.execute(person_id=person_id, role=role, limit=limit, offset=offset)
        except UnknownRoleError as exc:
            raise HTTPException(status_code=400, detail=f"rol desconocido: {exc}") from exc
        return PersonWorksResult.model_validate(data)


_register_person_routes(public_router, include_hidden=False)
_register_person_routes(admin_router, include_hidden=True)
