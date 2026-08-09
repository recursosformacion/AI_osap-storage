from __future__ import annotations

import logging
from contextlib import asynccontextmanager

import uvicorn
from fastapi import FastAPI
from infrastructure.bootstrap import ensure_default_provider
from infrastructure.config import Settings
from infrastructure.container import Container, build_container
from infrastructure.db.migrate import migrate

from api import errors
from api.logging_config import setup_logging
from api.metrics import MetricsMiddleware
from api.metrics import router as metrics_router
from api.routes import (
    admin_composers,
    archives,
    downloads,
    entries,
    files,
    health,
    pages,
    provider,
    providers,
    search,
    statistics,
    voting,
    works,
)


def create_app() -> FastAPI:
    setup_logging()
    settings = Settings()  # type: ignore[call-arg]
    container: Container = build_container(settings)
    logger = logging.getLogger(__name__)

    @asynccontextmanager
    async def lifespan(_: FastAPI):
        await container.db.connect()
        await migrate(container.db)
        await ensure_default_provider(container.provider_repo, container.registry, settings)
        # Recálculo de estadísticas de votación en cada arranque (idempotente). En producción
        # también lo ejecuta el cron diario; en desarrollo basta con lanzarlo aquí.
        try:
            run = await container.refresh_voting_statistics.execute()
            logger.info(
                "recompute statistics on startup: works=%s composers=%s",
                run.works_updated,
                run.composers_updated,
            )
        except Exception as exc:  # noqa: BLE001
            logger.warning("no se pudo recalcular estadísticas al arrancar: %s", exc)
        yield
        await container.db.close()

    app = FastAPI(
        title="Open Music Repository",
        description=(
            "Repositorio oficial de partituras públicas: índice de obras, resolución "
            "('lo tengo' -> URL), búsqueda, verificación del mirror y estadísticas. "
            "Respuesta a una consulta: ¿Existe? -> Sí -> URL de descarga (CDN)."
        ),
        version="1.1.0",
        lifespan=lifespan,
    )
    app.state.container = container
    errors.register_exception_handlers(app)
    app.add_middleware(MetricsMiddleware)
    app.include_router(pages.router)
    app.include_router(search.router)
    app.include_router(health.router)
    app.include_router(providers.router)
    app.include_router(files.router)
    app.include_router(downloads.router)
    app.include_router(entries.router)
    app.include_router(archives.router)
    app.include_router(statistics.router)
    app.include_router(works.router)
    app.include_router(provider.router)
    app.include_router(admin_composers.router)
    app.include_router(voting.router)
    app.include_router(metrics_router)
    return app


app = create_app()


def run() -> None:
    settings = Settings()  # type: ignore[call-arg]
    uvicorn.run("api.main:app", host=settings.http_host, port=settings.http_port, reload=True)
