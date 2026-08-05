from __future__ import annotations

from application.use_cases.search_entries import SearchEntries
from application.use_cases.statistics import GetStatistics
from application.use_cases.works import GetWork, SearchWorks
from domain.ports.repositories import FileRepository
from fastapi import APIRouter, Depends, Query
from fastapi.responses import HTMLResponse
from infrastructure.config import Settings

from api.dependencies import (
    GetStatisticsDep,
    GetWorkDep,
    SearchEntriesDep,
    SearchWorksDep,
    get_file_repo,
    get_settings,
)
from api.web import about as about_view
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
