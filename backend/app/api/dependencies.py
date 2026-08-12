"""Request dependencies for knowledge API route handlers."""

from typing import Annotated

from fastapi import Depends, Request
from sqlalchemy.orm import Session

from app.db import get_db
from app.services.knowledge import ConnectorFetcher, KnowledgeService


def get_connector_router(request: Request) -> ConnectorFetcher:
    """Return the router composed at startup or deliberately injected by a test."""
    router = getattr(request.app.state, "connector_router", None)
    if router is None:
        raise RuntimeError("connector router is unavailable before application startup")
    return router


DatabaseSession = Annotated[Session, Depends(get_db)]
ConnectorRouterDependency = Annotated[ConnectorFetcher, Depends(get_connector_router)]


def get_knowledge_service(
    request: Request, session: DatabaseSession, router: ConnectorRouterDependency
) -> KnowledgeService:
    """Construct a request-scoped knowledge service with explicit dependencies."""
    return KnowledgeService(
        session,
        router,
        import_session_factory=request.app.state.session_factory,
    )


KnowledgeServiceDependency = Annotated[KnowledgeService, Depends(get_knowledge_service)]


def get_import_knowledge_service(
    request: Request, router: ConnectorRouterDependency
) -> KnowledgeService:
    """Construct an import-only service without opening a request DB session."""
    return KnowledgeService(
        None,
        router,
        import_session_factory=request.app.state.session_factory,
    )


ImportKnowledgeServiceDependency = Annotated[
    KnowledgeService, Depends(get_import_knowledge_service)
]
