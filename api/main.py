from __future__ import annotations

from contextlib import asynccontextmanager

import uvicorn
from fastapi import FastAPI
from infrastructure.bootstrap import ensure_default_provider
from infrastructure.config import Settings
from infrastructure.container import Container, build_container
from infrastructure.db.migrate import migrate

from api import errors
from api.routes import archives, downloads, entries, files, health, providers, statistics


def create_app() -> FastAPI:
    settings = Settings()
    container: Container = build_container(settings)

    @asynccontextmanager
    async def lifespan(_: FastAPI):
        await container.db.connect()
        await migrate(container.db)
        await ensure_default_provider(container.provider_repo, container.registry, settings)
        yield
        await container.db.close()

    app = FastAPI(title="osap-storage", version="0.1.0", lifespan=lifespan)
    app.state.container = container
    errors.register_exception_handlers(app)
    app.include_router(health.router)
    app.include_router(providers.router)
    app.include_router(files.router)
    app.include_router(downloads.router)
    app.include_router(entries.router)
    app.include_router(archives.router)
    app.include_router(statistics.router)
    return app


app = create_app()


def run() -> None:
    settings = Settings()
    uvicorn.run("api.main:app", host=settings.http_host, port=settings.http_port, reload=True)
