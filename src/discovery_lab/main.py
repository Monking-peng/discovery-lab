from __future__ import annotations

from collections.abc import AsyncIterator, Callable
from contextlib import asynccontextmanager
from typing import Any, cast
from uuid import uuid4

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse, Response
from sqlalchemy import Engine, text
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session

from discovery_lab.api.claim_routes import router as claim_router
from discovery_lab.api.errors import AppError
from discovery_lab.api.evaluation_routes import router as evaluation_router
from discovery_lab.api.opportunity_routes import router as opportunity_router
from discovery_lab.api.retrieval_routes import router as retrieval_router
from discovery_lab.api.routes import router
from discovery_lab.config import Settings, get_settings
from discovery_lab.db.session import build_engine, build_session_factory
from discovery_lab.services.ingestion_runner import (
    IngestionRunner,
    build_ingestion_runner,
)
from discovery_lab.services.storage import BlobStore, LocalBlobStore

SessionFactory = Callable[[], Session]


def create_app(
    *,
    settings: Settings | None = None,
    session_factory: SessionFactory | None = None,
    blob_store: BlobStore | None = None,
    ingestion_runner: IngestionRunner | None = None,
) -> FastAPI:
    runtime_settings = settings or get_settings()
    owned_engine: Engine | None = None
    if session_factory is None:
        owned_engine = build_engine(runtime_settings.database_url)
        session_factory = build_session_factory(owned_engine)

    @asynccontextmanager
    async def lifespan(_app: FastAPI) -> AsyncIterator[None]:
        yield
        if owned_engine is not None:
            owned_engine.dispose()

    app = FastAPI(
        title=runtime_settings.app_name,
        version="0.1.0",
        lifespan=lifespan,
    )
    app.state.settings = runtime_settings
    app.state.session_factory = session_factory
    runtime_blob_store = blob_store or LocalBlobStore(runtime_settings.blob_root)
    app.state.blob_store = runtime_blob_store
    app.state.ingestion_runner = ingestion_runner or build_ingestion_runner(
        blob_store=runtime_blob_store,
        mode=runtime_settings.evidence_extractor,
        openai_model=runtime_settings.openai_model,
        openai_api_key=(
            runtime_settings.openai_api_key.get_secret_value()
            if runtime_settings.openai_api_key is not None
            else None
        ),
        prompt_version=runtime_settings.evidence_prompt_version,
    )

    app.add_middleware(
        CORSMiddleware,
        allow_origins=list(runtime_settings.cors_origins),
        allow_credentials=True,
        allow_methods=["GET", "POST", "PATCH", "DELETE", "OPTIONS"],
        allow_headers=["Authorization", "Content-Type", "X-Request-ID"],
        expose_headers=["X-Request-ID"],
    )

    @app.middleware("http")
    async def request_id_middleware(request: Request, call_next: Any) -> Response:
        request_id = request.headers.get("X-Request-ID") or str(uuid4())
        response = cast(Response, await call_next(request))
        response.headers["X-Request-ID"] = request_id
        return response

    @app.exception_handler(AppError)
    async def app_error_handler(_request: Request, exc: AppError) -> JSONResponse:
        return JSONResponse(
            status_code=exc.status_code,
            content={
                "error": {
                    "code": exc.code,
                    "message": exc.message,
                    "details": exc.details,
                },
                "detail": exc.message,
            },
        )

    @app.exception_handler(RequestValidationError)
    async def validation_error_handler(
        _request: Request, exc: RequestValidationError
    ) -> JSONResponse:
        issues = [
            {"location": list(error["loc"]), "message": error["msg"]} for error in exc.errors()
        ]
        return JSONResponse(
            status_code=422,
            content={
                "error": {
                    "code": "validation_error",
                    "message": "Request validation failed",
                    "details": {"issues": issues},
                },
                "detail": "Request validation failed",
            },
        )

    @app.get("/health", tags=["health"])
    def health(request: Request) -> dict[str, str]:
        try:
            with request.app.state.session_factory() as session:
                session.execute(text("SELECT 1"))
        except SQLAlchemyError as exc:
            raise AppError(
                code="database_unavailable",
                message="Database health check failed",
                status_code=503,
            ) from exc
        return {"status": "ok", "database": "ok"}

    app.include_router(router, prefix=runtime_settings.api_prefix)
    app.include_router(claim_router, prefix=runtime_settings.api_prefix)
    app.include_router(opportunity_router, prefix=runtime_settings.api_prefix)
    app.include_router(retrieval_router, prefix=runtime_settings.api_prefix)
    app.include_router(evaluation_router, prefix=runtime_settings.api_prefix)
    return app


app = create_app()
