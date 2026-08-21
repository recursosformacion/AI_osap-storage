from __future__ import annotations

import logging
import os
from contextlib import asynccontextmanager
from pathlib import Path

import uvicorn
import yaml
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
    admin_tables,
    archives,
    catalogues,
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


def _validate_config() -> None:
    try:
        from osap.bootstrap.configuration import validate_generic_service_config
    except ImportError:
        return

    config_path = Path(os.environ.get("OSAP_CONFIG", Path(__file__).resolve().parent.parent / "config.yaml"))
    data: dict[str, Any] = {}
    if config_path.exists():
        data = yaml.safe_load(config_path.read_text(encoding="utf-8")) or {}

    validate_generic_service_config("osap-storage", data, config_path)


def create_app() -> FastAPI:
    setup_logging()
    _validate_config()
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
    if settings.auth_enabled:
        from api.security import ServiceAuthMiddleware, ServiceTokenValidator

        app.add_middleware(
            ServiceAuthMiddleware,
            validator=ServiceTokenValidator(
                issuer=settings.auth_issuer,
                audience=settings.auth_audience,
                jwks_url=settings.auth_jwks_url,
                public_key=settings.auth_public_key,
                kid=settings.auth_kid,
                clock_skew_seconds=settings.auth_clock_skew_seconds,
            ),
        )
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
    app.include_router(admin_tables.router)
    app.include_router(voting.router)
    app.include_router(catalogues.router)
    app.include_router(metrics_router)
    return app


app = create_app()


def run() -> None:
    _validate_config()
    settings = Settings()  # type: ignore[call-arg]
    uvicorn.run("api.main:app", host=settings.http_host, port=settings.http_port, reload=True)
