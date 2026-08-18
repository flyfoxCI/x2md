"""Request dependencies for knowledge API route handlers."""

from typing import Annotated

from fastapi import Depends, HTTPException, Request, status
from sqlalchemy.orm import Session

from app.config import Settings
from app.db import get_db
from app.models import AuthSession
from app.services.ai import AIService
from app.services.auth import AuthService
from app.services.knowledge import ConnectorFetcher, KnowledgeService

SESSION_COOKIE_NAME = "expert_content_studio_session"
_AUTHENTICATION_REQUIRED = {
    "code": "authentication_required",
    "message": "Authentication is required.",
}
_CSRF_INVALID = {
    "code": "csrf_invalid",
    "message": "The CSRF token is invalid.",
}


def get_connector_router(request: Request) -> ConnectorFetcher:
    """Return the router composed at startup or deliberately injected by a test."""
    router = getattr(request.app.state, "connector_router", None)
    if router is None:
        raise RuntimeError("connector router is unavailable before application startup")
    return router


DatabaseSession = Annotated[Session, Depends(get_db)]
ConnectorRouterDependency = Annotated[ConnectorFetcher, Depends(get_connector_router)]


def get_auth_service(request: Request, session: DatabaseSession) -> AuthService:
    """Build an AuthService around a short-lived route-local database session."""
    settings: Settings = request.app.state.settings
    return AuthService(session, session_ttl_seconds=settings.auth_session_ttl_seconds)


AuthServiceDependency = Annotated[AuthService, Depends(get_auth_service)]


def require_authenticated_user(request: Request) -> AuthSession | None:
    """Resolve one enabled-auth browser session before any knowledge route can run."""
    settings: Settings = request.app.state.settings
    if not settings.auth_enabled:
        return None

    raw_token = request.cookies.get(SESSION_COOKIE_NAME)
    if not raw_token:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail=_AUTHENTICATION_REQUIRED)

    with request.app.state.session_factory() as session:
        service = AuthService(session, session_ttl_seconds=settings.auth_session_ttl_seconds)
        auth_session = service.get_current_session(raw_token)
        if auth_session is None:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail=_AUTHENTICATION_REQUIRED,
            )
        return auth_session


AuthenticatedSessionDependency = Annotated[
    AuthSession | None, Depends(require_authenticated_user)
]


def require_csrf(
    request: Request, auth_session: AuthenticatedSessionDependency
) -> None:
    """Require the server-bound browser-intent token for every unsafe API operation."""
    settings: Settings = request.app.state.settings
    if not settings.auth_enabled:
        return

    csrf_token = request.headers.get("X-CSRF-Token")
    if not csrf_token or auth_session is None:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail=_CSRF_INVALID)

    with request.app.state.session_factory() as session:
        service = AuthService(session, session_ttl_seconds=settings.auth_session_ttl_seconds)
        if not service.is_csrf_valid(auth_session, csrf_token):
            raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail=_CSRF_INVALID)


CsrfDependency = Annotated[None, Depends(require_csrf)]


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
