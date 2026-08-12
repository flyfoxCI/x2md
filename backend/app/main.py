"""FastAPI application factory."""

import logging
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from pydantic import BaseModel, Field

from app.api import artifacts_router, imports_router, settings_router, sources_router
from app.config import Settings
from app.db import create_database_resources
from app.services.ai import AIService
from app.services.composition import compose_connector_resources

logger = logging.getLogger(__name__)


class HealthResponse(BaseModel):
    """Stable, non-secret health endpoint response."""

    status: str
    database: str
    ai_configured: bool = Field(serialization_alias="aiConfigured")


@asynccontextmanager
async def app_lifespan(app: FastAPI) -> AsyncIterator[None]:
    """Compose and close resources once for one deterministic application lifetime."""
    composed_resources = None
    body_error: BaseException | None = None
    try:
        if getattr(app.state, "connector_router", None) is None:
            composed_resources = compose_connector_resources(app.state.settings)
            app.state.connector_resources = composed_resources
            app.state.connector_router = composed_resources.router
        try:
            yield
        except BaseException as error:
            body_error = error
            raise
    finally:
        close_error: BaseException | None = None
        try:
            ai_service = getattr(app.state, "ai_service", None)
            if ai_service is not None:
                try:
                    await ai_service.aclose()
                except BaseException as error:
                    close_error = error
                    logger.exception("Failed to close AI service during application shutdown")
        finally:
            try:
                if composed_resources is not None:
                    try:
                        await composed_resources.aclose()
                    except BaseException as error:
                        if close_error is None:
                            close_error = error
                        logger.exception("Failed to close connector resources during shutdown")
            finally:
                try:
                    database_resources = getattr(app.state, "database_resources", None)
                    if database_resources is not None:
                        try:
                            database_resources.dispose()
                        except BaseException as error:
                            if close_error is None:
                                close_error = error
                            logger.exception("Failed to dispose database resources during shutdown")
                finally:
                    if hasattr(app.state, "ai_service"):
                        del app.state.ai_service
                    if composed_resources is not None:
                        if getattr(app.state, "connector_resources", None) is composed_resources:
                            del app.state.connector_resources
                        if (
                            getattr(app.state, "connector_router", None)
                            is composed_resources.router
                        ):
                            del app.state.connector_router
                    if hasattr(app.state, "database_resources"):
                        del app.state.database_resources
                    if hasattr(app.state, "session_factory"):
                        del app.state.session_factory
        if body_error is None and close_error is not None:
            raise close_error


def create_app(settings: Settings | None = None) -> FastAPI:
    """Create the HTTP application with server-only runtime settings."""
    configured_settings = settings or Settings()
    app = FastAPI(title=configured_settings.app_name, lifespan=app_lifespan)
    app.state.settings = configured_settings
    app.state.database_resources = create_database_resources(
        configured_settings.database_url
    )
    app.state.session_factory = app.state.database_resources.session_factory
    app.state.ai_service = AIService(configured_settings)
    app.include_router(imports_router)
    app.include_router(sources_router)
    app.include_router(artifacts_router)
    app.include_router(settings_router)

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
