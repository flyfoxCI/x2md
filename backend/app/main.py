"""FastAPI application factory."""

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from pydantic import BaseModel, Field

from app.api import artifacts_router, imports_router, sources_router
from app.config import Settings
from app.db import create_database_resources
from app.services.composition import compose_connector_resources


class HealthResponse(BaseModel):
    """Stable, non-secret health endpoint response."""

    status: str
    database: str
    ai_configured: bool = Field(serialization_alias="aiConfigured")


@asynccontextmanager
async def app_lifespan(app: FastAPI) -> AsyncIterator[None]:
    """Compose and close resources once for one deterministic application lifetime."""
    composed_resources = None
    try:
        if getattr(app.state, "connector_router", None) is None:
            composed_resources = compose_connector_resources(app.state.settings)
            app.state.connector_resources = composed_resources
            app.state.connector_router = composed_resources.router
        yield
    finally:
        try:
            if composed_resources is not None:
                await composed_resources.aclose()
        finally:
            if composed_resources is not None:
                if getattr(app.state, "connector_resources", None) is composed_resources:
                    del app.state.connector_resources
                if (
                    getattr(app.state, "connector_router", None)
                    is composed_resources.router
                ):
                    del app.state.connector_router
            database_resources = getattr(app.state, "database_resources", None)
            if database_resources is not None:
                database_resources.dispose()
                del app.state.database_resources
            if hasattr(app.state, "session_factory"):
                del app.state.session_factory


def create_app(settings: Settings | None = None) -> FastAPI:
    """Create the HTTP application with server-only runtime settings."""
    configured_settings = settings or Settings()
    app = FastAPI(title=configured_settings.app_name, lifespan=app_lifespan)
    app.state.settings = configured_settings
    app.state.database_resources = create_database_resources(
        configured_settings.database_url
    )
    app.state.session_factory = app.state.database_resources.session_factory
    app.include_router(imports_router)
    app.include_router(sources_router)
    app.include_router(artifacts_router)

    @app.get("/api/health", response_model=HealthResponse)
    def health() -> HealthResponse:
        return HealthResponse(
            status="ok",
            database="uninitialized",
            ai_configured=configured_settings.ai_configured,
        )

    @app.exception_handler(RequestValidationError)
    async def invalid_request(_: Request, __: RequestValidationError) -> JSONResponse:
        """Give malformed API requests the same documented safe error envelope."""
        return JSONResponse(
            status_code=422,
            content={
                "detail": {
                    "code": "invalid_request",
                    "message": "The request payload is invalid.",
                }
            },
        )

    return app


app = create_app()
