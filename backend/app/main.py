"""FastAPI application factory."""

import logging
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from fastapi import Depends, FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from pydantic import BaseModel, Field

from app.api import (
    artifacts_router,
    auth_router,
    imports_router,
    research_router,
    research_sources_router,
    settings_router,
    sources_router,
    tags_router,
)
from app.api.dependencies import require_authenticated_user
from app.config import Settings
from app.db import create_database_resources
from app.services.ai import AIService
from app.services.auth import AuthService
from app.services.composition import compose_connector_resources
from app.services.research.orchestrator import ResearchOrchestrator
from app.services.research.worker import ResearchWorker, auto_start_enabled

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
    research_worker = None
    body_error: BaseException | None = None
    try:
        settings: Settings = app.state.settings
        if settings.auth_enabled:
            with app.state.session_factory() as session:
                AuthService(
                    session,
                    session_ttl_seconds=settings.auth_session_ttl_seconds,
                ).bootstrap_admin(
                    username=settings.auth_initial_admin_username,
                    initial_password=settings.auth_initial_admin_password,
                    auth_enabled=True,
                )
        if getattr(app.state, "connector_router", None) is None:
            composed_resources = compose_connector_resources(app.state.settings)
            app.state.connector_resources = composed_resources
            app.state.connector_router = composed_resources.router
        if getattr(app.state, "research_orchestrator", None) is None:
            collectors = (
                getattr(composed_resources, "research_collectors", {})
                if composed_resources is not None
                else {}
            )
            app.state.research_orchestrator = ResearchOrchestrator(
                app.state.session_factory,
                collectors=collectors,
                ai=app.state.ai_service,
            )
        with app.state.session_factory() as session:
            should_start_research = auto_start_enabled(session)
        if should_start_research:
            research_worker = ResearchWorker(
                app.state.session_factory, app.state.research_orchestrator
            )
            app.state.research_worker = research_worker
            await research_worker.start()
        try:
            yield
        except BaseException as error:
            body_error = error
            raise
    finally:
        close_error: BaseException | None = None
        try:
            if research_worker is not None:
                try:
                    await research_worker.stop()
                except BaseException as error:
                    close_error = error
                    logger.exception("Failed to stop research worker during application shutdown")
        finally:
            try:
                ai_service = getattr(app.state, "ai_service", None)
                if ai_service is not None:
                    try:
                        await ai_service.aclose()
                    except BaseException as error:
                        if close_error is None:
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
                    if hasattr(app.state, "ai_service"):
                        del app.state.ai_service
                    if hasattr(app.state, "research_worker"):
                        del app.state.research_worker
                    if hasattr(app.state, "research_orchestrator"):
                        del app.state.research_orchestrator
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
    app.include_router(auth_router)
    app.include_router(imports_router, dependencies=[Depends(require_authenticated_user)])
    app.include_router(sources_router, dependencies=[Depends(require_authenticated_user)])
    app.include_router(
        research_sources_router, dependencies=[Depends(require_authenticated_user)]
    )
    app.include_router(research_router, dependencies=[Depends(require_authenticated_user)])
    app.include_router(artifacts_router, dependencies=[Depends(require_authenticated_user)])
    app.include_router(settings_router, dependencies=[Depends(require_authenticated_user)])
    app.include_router(tags_router, dependencies=[Depends(require_authenticated_user)])

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
