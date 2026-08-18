"""Public administrator authentication routes and browser-cookie translation."""

from fastapi import APIRouter, HTTPException, Request, Response, status

from app.api.dependencies import (
    SESSION_COOKIE_NAME,
    AuthenticatedSessionDependency,
    AuthServiceDependency,
    CsrfDependency,
)
from app.config import Settings
from app.schemas import (
    ApiErrorResponse,
    AuthSessionRead,
    AuthUserRead,
    ChangePasswordRequest,
    LoginRequest,
)
from app.services.auth import IssuedSession

router = APIRouter(prefix="/api/auth", tags=["auth"])

_INVALID_CREDENTIALS = {
    "code": "invalid_credentials",
    "message": "Invalid username or password.",
}
_AUTHENTICATION_REQUIRED = {
    "code": "authentication_required",
    "message": "Authentication is required.",
}


def _session_body(issued: IssuedSession) -> AuthSessionRead:
    """Translate only the browser-safe portion of an issued server session."""
    return AuthSessionRead(
        user=AuthUserRead(id=issued.user_id, username=issued.username),
        csrf_token=issued.csrf_token,
    )


def _set_session_cookie(response: Response, issued: IssuedSession, settings: Settings) -> None:
    """Set the single intentional opaque browser cookie without a Domain attribute."""
    response.set_cookie(
        key=SESSION_COOKIE_NAME,
        value=issued.token,
        max_age=settings.auth_session_ttl_seconds,
        httponly=True,
        secure=settings.auth_cookie_secure,
        samesite="strict",
        path="/",
    )


def _clear_session_cookie(response: Response, settings: Settings) -> None:
    """Clear the same opaque cookie with its original browser security attributes."""
    response.delete_cookie(
        key=SESSION_COOKIE_NAME,
        httponly=True,
        secure=settings.auth_cookie_secure,
        samesite="strict",
        path="/",
    )


def _invalid_credentials() -> HTTPException:
    """Create the one credential failure envelope used by login and password change."""
    return HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail=_INVALID_CREDENTIALS)


@router.post(
    "/login",
    response_model=AuthSessionRead,
    responses={401: {"model": ApiErrorResponse, "description": "Credentials are invalid."}},
)
def login(
    payload: LoginRequest,
    response: Response,
    service: AuthServiceDependency,
    request: Request,
) -> AuthSessionRead:
    """Authenticate an administrator and issue a new opaque browser session."""
    issued = service.authenticate_and_create_session(
        username=payload.username,
        password=payload.password,
    )
    if issued is None:
        raise _invalid_credentials()
    _set_session_cookie(response, issued, request.app.state.settings)
    return _session_body(issued)


@router.get(
    "/me",
    response_model=AuthSessionRead,
    responses={401: {"model": ApiErrorResponse, "description": "Authentication is required."}},
)
def get_current_user(auth_session: AuthenticatedSessionDependency) -> AuthSessionRead:
    """Return current safe session state while keeping the opaque token in its cookie."""
    if auth_session is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail=_AUTHENTICATION_REQUIRED,
        )
    return AuthSessionRead(
        user=AuthUserRead(id=auth_session.user.id, username=auth_session.user.username),
        csrf_token=auth_session.csrf_token,
    )


@router.post("/logout", status_code=status.HTTP_204_NO_CONTENT, response_class=Response)
def logout(
    request: Request,
    auth_session: AuthenticatedSessionDependency,
    csrf: CsrfDependency,
    service: AuthServiceDependency,
) -> Response:
    """Revoke the browser session server-side and remove its matching browser cookie."""
    if auth_session is not None:
        raw_token = request.cookies.get(SESSION_COOKIE_NAME)
        if raw_token:
            service.revoke_session(raw_token)
    response = Response(status_code=status.HTTP_204_NO_CONTENT)
    _clear_session_cookie(response, request.app.state.settings)
    return response


@router.post(
    "/change-password",
    response_model=AuthSessionRead,
    responses={401: {"model": ApiErrorResponse, "description": "Credentials are invalid."}},
)
def change_password(
    payload: ChangePasswordRequest,
    response: Response,
    request: Request,
    auth_session: AuthenticatedSessionDependency,
    csrf: CsrfDependency,
    service: AuthServiceDependency,
) -> AuthSessionRead:
    """Rotate the administrator password, all old sessions, and this browser cookie."""
    if auth_session is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail=_AUTHENTICATION_REQUIRED,
        )
    issued = service.change_password(
        auth_session.user,
        current_password=payload.current_password,
        new_password=payload.new_password,
    )
    if issued is None:
        raise _invalid_credentials()
    _set_session_cookie(response, issued, request.app.state.settings)
    return _session_body(issued)
