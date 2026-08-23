"""Request dependencies for knowledge API route handlers."""

from typing import Annotated

from fastapi import Depends, Request
from sqlalchemy.orm import Session

from app.db import get_db
from app.services.ai import AIService
from app.services.knowledge import ConnectorFetcher, KnowledgeService
from app.services.research.orchestrator import ResearchOrchestrator


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


def get_ai_knowledge_service(
    request: Request, router: ConnectorRouterDependency
) -> KnowledgeService:
    """Construct an isolated service so provider waits never retain a DB session."""
    return KnowledgeService(
        None,
        router,
        import_session_factory=request.app.state.session_factory,
    )


AIKnowledgeServiceDependency = Annotated[
    KnowledgeService, Depends(get_ai_knowledge_service)
]


def get_ai_service(request: Request) -> AIService:
    """Return the application-owned server-only provider adapter."""
    return request.app.state.ai_service


AIServiceDependency = Annotated[AIService, Depends(get_ai_service)]


def get_research_orchestrator(request: Request) -> ResearchOrchestrator:
    """Return the application-owned durable research state-machine service."""
    orchestrator = getattr(request.app.state, "research_orchestrator", None)
    if orchestrator is None:
        orchestrator = ResearchOrchestrator(
            request.app.state.session_factory,
            collectors={},
            ai=request.app.state.ai_service,
        )
        request.app.state.research_orchestrator = orchestrator
    return orchestrator


ResearchOrchestratorDependency = Annotated[
    ResearchOrchestrator, Depends(get_research_orchestrator)
]
