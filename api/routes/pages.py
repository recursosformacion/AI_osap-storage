from __future__ import annotations

import time
from urllib.parse import parse_qs

from application.use_cases.search_entries import SearchEntries
from application.use_cases.statistics import GetStatistics
from application.use_cases.works import GetWork, SearchWorks
from domain.ports.repositories import FileRepository
from fastapi import APIRouter, Depends, Query, Request
from fastapi.responses import HTMLResponse, JSONResponse, RedirectResponse
from infrastructure.config import Settings

_ADMIN_SESSION_COOKIE = "osap_storage_admin"

from api.dependencies import (
    GetStatisticsDep,
    GetWorkDep,
    SearchEntriesDep,
    SearchWorksDep,
    get_file_repo,
    get_settings,
)
from api.web import about as about_view
from api.web import admin_composers_crud as admin_composers_crud_view
from api.web import admin_maintenance as admin_view
from api.web import admin_works_crud as admin_works_crud_view
from api.web import api_doc, landing, search, statistics, works

router = APIRouter(tags=["pages"])


@router.get(
    "/",
    response_class=HTMLResponse,
    summary="Página principal",
    description="Landing pública de Open Music Repository con cifras reales del mirror.",
)
async def landing_page(
    uc: GetStatistics = Depends(GetStatisticsDep),
    files: FileRepository = Depends(get_file_repo),
) -> HTMLResponse:
    stats = await uc.execute()
    sample_list = await files.list(limit=1)
    sample_url = f"/api/v1/files/{sample_list[0].id}/content" if sample_list else "/docs"
    return HTMLResponse(landing.landing_page(musicxml=stats.entries, archives=stats.archives, sample_url=sample_url))


@router.get(
    "/about",
    response_class=HTMLResponse,
    summary="Sobre el proyecto",
    description="Página que explica en pocos minutos qué es Open Music Repository.",
)
async def about() -> HTMLResponse:
    return HTMLResponse(about_view.about_page())


@router.get(
    "/api",
    response_class=HTMLResponse,
    summary="API con ejemplos",
    description="Página con ejemplos sencillos de la API (buscar, resolver, descargar).",
)
async def api_doc_page() -> HTMLResponse:
    return HTMLResponse(api_doc.api_page())


@router.get(
    "/search",
    response_class=HTMLResponse,
    summary="Buscador web",
    description="Página HTML que busca en el índice y muestra resultados con botón de descarga.",
)
async def search_page(
    q: str = Query(default=""),
    uc: SearchEntries = Depends(SearchEntriesDep),
    settings: Settings = Depends(get_settings),
) -> HTMLResponse:
    results = await uc.execute(q, limit=50) if q.strip() else []
    return HTMLResponse(search.search_page(q, results, settings))


@router.get(
    "/statistics",
    response_class=HTMLResponse,
    summary="Página de estadísticas",
    description="Página HTML con las estadísticas del repositorio.",
)
async def statistics_page(uc: GetStatistics = Depends(GetStatisticsDep)) -> HTMLResponse:
    stats = await uc.execute()
    return HTMLResponse(statistics.statistics_page(stats))


@router.get(
    "/works",
    response_class=HTMLResponse,
    summary="Buscador de obras",
    description="Página HTML que busca obras y muestra sus representaciones.",
)
async def works_page(
    q: str = Query(default=""),
    uc: SearchWorks = Depends(SearchWorksDep),
) -> HTMLResponse:
    works_list = await uc.execute(q, limit=50)
    return HTMLResponse(works.works_page(q, works_list))


@router.get(
    "/works/{work_id}",
    response_class=HTMLResponse,
    summary="Detalle de una obra",
    description="Página HTML de una obra con sus representaciones y URLs de descarga.",
)
async def work_detail(
    work_id: int,
    uc: GetWork = Depends(GetWorkDep),
    settings: Settings = Depends(get_settings),
) -> HTMLResponse:
    detail = await uc.execute(work_id)
    return HTMLResponse(works.work_detail_page(detail, settings))


@router.post("/admin/session", include_in_schema=False)
async def create_admin_session(request: Request, settings: Settings = Depends(get_settings)):
    """Intercambia un service token por una cookie de sesión del panel."""
    validator = getattr(request.app.state, "service_token_validator", None)
    if validator is None:
        return JSONResponse(status_code=503, content={"detail": "autenticación de servicio no disponible"})
    allowed_origins = {item.strip().rstrip("/") for item in settings.admin_handoff_origins.split(",") if item.strip()}
    origin = request.headers.get("origin", "").rstrip("/")
    if not origin or origin not in allowed_origins:
        return JSONResponse(status_code=403, content={"detail": "origen de handoff no permitido"})
    content_type = request.headers.get("content-type", "").split(";", 1)[0].strip().lower()
    if content_type != "application/x-www-form-urlencoded":
        return JSONResponse(status_code=415, content={"detail": "se requiere application/x-www-form-urlencoded"})
    body = await request.body()
    if len(body) > 16384:
        return JSONResponse(status_code=413, content={"detail": "solicitud demasiado grande"})
    fields = parse_qs(body.decode("utf-8", errors="strict"), keep_blank_values=True)
    token = (fields.get("token") or [""])[0].strip()
    next_path = (fields.get("next") or ["/admin"])[0].strip() or "/admin"
    if not token:
        return JSONResponse(status_code=400, content={"detail": "falta el token de servicio"})
    if not next_path.startswith("/admin") or next_path.startswith("//") or "\\" in next_path:
        return JSONResponse(status_code=400, content={"detail": "destino no permitido"})
    try:
        claims = await validator.validate(token, "storage:admin")
    except Exception as exc:
        from api.security import ServiceAuthError
        if isinstance(exc, ServiceAuthError):
            return JSONResponse(status_code=exc.status_code, content={"detail": exc.message})
        return JSONResponse(status_code=503, content={"detail": "no se pudo validar el token"})
    expires_at = int(claims.get("exp", 0))
    max_age = expires_at - int(time.time())
    if max_age <= 0:
        return JSONResponse(status_code=401, content={"detail": "token expirado"})
    response = RedirectResponse(url=next_path, status_code=303)
    response.set_cookie(
        key=_ADMIN_SESSION_COOKIE, value=token, max_age=max_age, path="/",
        httponly=True, secure=True, samesite="lax"
    )
    response.headers["Cache-Control"] = "no-store"
    response.headers["Referrer-Policy"] = "no-referrer"
    return response
@router.get(
    "/admin",
    response_class=HTMLResponse,
    summary="Gestión de storage (mantenimiento de datos)",
    description="Pantalla web completa de mantenimiento de osap-storage: pestañas "
    "Compositores, Obras y Tablas (CRUD genérico). osap-api la invoca con un enlace "
    "'Mantenimiento'. Requiere un service token storage:admin (se pasa por ?token=... "
    "o se pega en la pantalla).",
)
async def admin_page(token: str = Query(default="")) -> HTMLResponse:
    return HTMLResponse(admin_view.admin_maintenance_page(token=token))


@router.get(
    "/admin/mantenimiento",
    response_class=HTMLResponse,
    summary="Mantenimiento (opciones) de storage",
    description="Página curada de opciones de mantenimiento de osap-storage (Compositores, "
    "Obras, Tablas), distinta del multimantenimiento de la SPA. osap-api la enlaza como "
    "'Mantenimiento'.",
)
async def admin_mantenimiento_page(token: str = Query(default="")) -> HTMLResponse:
    return HTMLResponse(admin_view.admin_maintenance_page(token=token))


@router.get(
    "/admin/maestros",
    response_class=HTMLResponse,
    summary="Mantenimiento compositores (CRUD convencional)",
    description="Página standalone (fuera del multimantenimiento) con el listado de "
    "composers a 30/página y detalle Ver/Editar. Si llega ?id=...&mode=view|edit, abre "
    "directamente ese compositor en el modo indicado (lo usa la pantalla de "
    "correcciones de osap-app). Requiere service token storage:admin por ?token=...",
)
async def admin_maestros_page(token: str = Query(default="")) -> HTMLResponse:
    return HTMLResponse(admin_composers_crud_view.admin_composers_crud_page(token=token))


@router.get(
    "/admin/obras",
    response_class=HTMLResponse,
    summary="Mantenimiento de obras (CRUD convencional)",
    description="Página standalone con el listado de obras a 30/página y detalle "
    "Ver/Editar (metadatos + tags/genres/instruments/parts). Requiere service token "
    "storage:admin por ?token=...; el API /api/admin/works sí exige el Bearer.",
)
async def admin_obras_page(token: str = Query(default="")) -> HTMLResponse:
    return HTMLResponse(admin_works_crud_view.admin_works_crud_page(token=token))
