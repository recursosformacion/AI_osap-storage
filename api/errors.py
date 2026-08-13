from __future__ import annotations

import logging

from domain.exceptions import (
    DomainError,
    DuplicateComposerAlias,
    DuplicateVote,
    EntityNotFound,
    FileNotAvailable,
    IntegrityVerificationError,
    InvalidFileData,
    InvalidMerge,
    InvalidSha256,
    InvalidTableCrud,
    UnsupportedProvider,
)
from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse

logger = logging.getLogger(__name__)


def register_exception_handlers(app: FastAPI) -> None:
    @app.exception_handler(EntityNotFound)
    async def _not_found(_: Request, exc: EntityNotFound) -> JSONResponse:
        return JSONResponse(status_code=404, content={"detail": str(exc)})

    @app.exception_handler(InvalidSha256)
    @app.exception_handler(InvalidFileData)
    @app.exception_handler(InvalidMerge)
    @app.exception_handler(InvalidTableCrud)
    async def _bad_request(_: Request, exc: DomainError) -> JSONResponse:
        return JSONResponse(status_code=400, content={"detail": str(exc)})

    @app.exception_handler(DuplicateComposerAlias)
    async def _conflict_alias(_: Request, exc: DuplicateComposerAlias) -> JSONResponse:
        return JSONResponse(status_code=409, content={"detail": str(exc)})

    @app.exception_handler(DuplicateVote)
    async def _conflict_vote(_: Request, exc: DuplicateVote) -> JSONResponse:
        return JSONResponse(status_code=409, content={"detail": str(exc)})

    @app.exception_handler(IntegrityVerificationError)
    async def _integrity(_: Request, exc: IntegrityVerificationError) -> JSONResponse:
        return JSONResponse(status_code=422, content={"detail": str(exc)})

    @app.exception_handler(FileNotAvailable)
    async def _conflict(_: Request, exc: FileNotAvailable) -> JSONResponse:
        return JSONResponse(status_code=409, content={"detail": str(exc)})

    @app.exception_handler(UnsupportedProvider)
    async def _unsupported(_: Request, exc: UnsupportedProvider) -> JSONResponse:
        return JSONResponse(status_code=400, content={"detail": str(exc)})

    @app.exception_handler(DomainError)
    async def _domain(_: Request, exc: DomainError) -> JSONResponse:
        logger.exception("unhandled domain error")
        return JSONResponse(status_code=500, content={"detail": str(exc)})

    @app.exception_handler(Exception)
    async def _unexpected(_: Request, exc: Exception) -> JSONResponse:
        logger.exception("unexpected error")
        return JSONResponse(status_code=500, content={"detail": "internal server error"})
