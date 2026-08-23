"""HTTP routers for the persisted knowledge-library workflow."""

from app.api.artifacts import router as artifacts_router
from app.api.imports import router as imports_router
from app.api.research import router as research_router
from app.api.research import sources_router as research_sources_router
from app.api.settings import router as settings_router
from app.api.sources import router as sources_router
from app.api.tags import router as tags_router

__all__ = [
    "artifacts_router",
    "imports_router",
    "research_router",
    "research_sources_router",
    "settings_router",
    "sources_router",
    "tags_router",
]
