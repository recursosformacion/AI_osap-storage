"""Rutas de personas por rol: listado, ficha, obras y validación de roles.

Usa un repositorio de consulta falso inyectado en el contenedor (sin BBDD): comprueba el
contrato de la API (`/api/v1/persons`, `/api/persons/{id}`, `/persons/{id}/works`) y que el
filtro por rol y la visibilidad (admin) se pasan al repositorio.
"""

from __future__ import annotations

import dataclasses

from api.routes import persons as persons_routes
from application.use_cases.persons import GetPerson, GetPersonWorks, ListPersons
from fastapi import FastAPI
from fastapi.testclient import TestClient
from tests.api.test_admin_composers import _container
from tests.fakes import InMemoryComposerRepository

from api import errors


class _FakePersonQueries:
    def __init__(self) -> None:
        self.calls: list[tuple] = []

    async def list_persons(self, role_ids, *, q, limit, offset, include_hidden=False):
        self.calls.append(("list", role_ids, include_hidden))
        return (
            [
                {
                    "id": "p1",
                    "name": "Ada Byron",
                    "sort_name": "Byron, Ada",
                    "roles": ["composer"],
                    "works_count": 2,
                    "aliases_count": 1,
                    "birth_year": "1815",
                    "death_year": "1852",
                    "visible": True,
                    "review_status": "not_reviewed",
                    "biography_summary": "Resumen",
                    "biography_era": "Romanticismo",
                    "biography_nationality": "Reino Unido",
                }
            ],
            1,
        )

    async def get_person(self, person_id: str):
        if person_id != "p1":
            return None
        return {
            "id": "p1",
            "name": "Ada Byron",
            "roles": ["composer"],
            "aliases": ["A. Byron"],
            "works_count": 2,
            "visible": True,
            "biography_summary": "Resumen",
        }

    async def works_for_person(self, person_id: str, role_ids, *, limit, offset):
        return (
            [
                {
                    "work_id": 7,
                    "title": "Overture",
                    "subtitle": None,
                    "catalogue": "Op. 1",
                    "year": 1840,
                    "roles": ["composer"],
                    "genres": ["Obertura"],
                    "instruments": ["Orquesta"],
                }
            ],
            1,
        )


def _app(settings):
    fake = _FakePersonQueries()
    base = _container(settings, InMemoryComposerRepository())
    container = dataclasses.replace(
        base,
        person_queries=fake,  # type: ignore[arg-type]
        list_persons=ListPersons(fake),  # type: ignore[arg-type]
        get_person=GetPerson(fake),  # type: ignore[arg-type]
        get_person_works=GetPersonWorks(fake),  # type: ignore[arg-type]
    )
    app = FastAPI()
    app.state.container = container
    errors.register_exception_handlers(app)
    app.include_router(persons_routes.public_router)
    app.include_router(persons_routes.admin_router)
    return app, fake


def _client(settings) -> tuple[TestClient, _FakePersonQueries]:
    app, fake = _app(settings)
    return TestClient(app), fake


def test_listado_por_rol_publico(settings) -> None:
    client, fake = _client(settings)
    resp = client.get("/api/v1/persons?role=composer&limit=10&offset=0")
    assert resp.status_code == 200
    body = resp.json()
    assert body["total"] == 1
    assert body["items"][0]["roles"] == ["composer"]
    assert body["items"][0]["works_count"] == 2
    # Público: no incluye ocultas.
    assert fake.calls[0] == ("list", (1,), False)


def test_rol_desconocido_da_400(settings) -> None:
    client, _ = _client(settings)
    resp = client.get("/api/v1/persons?role=composer,pianist")
    assert resp.status_code == 400


def test_multi_rol_se_traduce(settings) -> None:
    client, fake = _client(settings)
    resp = client.get("/api/v1/persons?role=composer,arranger")
    assert resp.status_code == 200
    assert fake.calls[0][1] == (1, 3)


def test_admin_incluye_ocultas(settings) -> None:
    client, fake = _client(settings)
    resp = client.get("/api/admin/persons?role=composer")
    assert resp.status_code == 200
    assert fake.calls[0][2] is True


def test_ficha_y_404(settings) -> None:
    client, _ = _client(settings)
    ok = client.get("/api/v1/persons/p1")
    assert ok.status_code == 200
    assert ok.json()["name"] == "Ada Byron"
    assert ok.json()["aliases"] == ["A. Byron"]
    missing = client.get("/api/v1/persons/desconocido")
    assert missing.status_code == 404


def test_obras_con_genero_e_instrumentos(settings) -> None:
    client, _ = _client(settings)
    resp = client.get("/api/v1/persons/p1/works?role=composer")
    assert resp.status_code == 200
    item = resp.json()["items"][0]
    assert item["work_id"] == 7
    assert item["roles"] == ["composer"]
    assert item["genres"] == ["Obertura"]
    assert item["instruments"] == ["Orquesta"]
