"""FastAPI application factory."""

from fastapi import FastAPI
from pydantic import BaseModel, Field

from app.config import Settings


class HealthResponse(BaseModel):
    """Stable, non-secret health endpoint response."""

    status: str
    database: str
    ai_configured: bool = Field(serialization_alias="aiConfigured")


def create_app(settings: Settings | None = None) -> FastAPI:
    """Create the HTTP application with server-only runtime settings."""
    configured_settings = settings or Settings()
    app = FastAPI(title=configured_settings.app_name)
    app.state.settings = configured_settings

    @app.get("/api/health", response_model=HealthResponse)
    def health() -> HealthResponse:
        return HealthResponse(
            status="ok",
            database="uninitialized",
            ai_configured=configured_settings.ai_configured,
        )

    return app


app = create_app()
