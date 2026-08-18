"""End-to-end contracts for administrator browser sessions."""

from __future__ import annotations

import asyncio
import threading
from collections.abc import AsyncIterator, Generator
from contextlib import asynccontextmanager
from http.cookies import SimpleCookie
from pathlib import Path

import httpx
import pytest
from fastapi import FastAPI, Request
from sqlalchemy import select

from app.api.dependencies import require_authenticated_user
from app.config import Settings
from app.main import create_app
from app.models import AuthSession, Base, Source, User
from app.services.auth import AuthService
from tests.api.conftest import FakeConnectorRouter

_COOKIE_NAME = "expert_content_studio_session"
_BOOTSTRAP_USERNAME = "test-admin"
_BOOTSTRAP_PASSWORD = "test-only-bootstrap-password"
_REPLACEMENT_PASSWORD = "test-only-replacement-password"
_INVALID_CREDENTIALS = {
    "detail": {
        "code": "invalid_credentials",
        "message": "Invalid username or password.",
    }
}
_AUTHENTICATION_REQUIRED = {
    "detail": {
        "code": "authentication_required",
        "message": "Authentication is required.",
    }
}
_CSRF_INVALID = {
    "detail": {
        "code": "csrf_invalid",
        "message": "The CSRF token is invalid.",
    }
}


@pytest.fixture
def enabled_auth_app(tmp_path: Path) -> Generator[FastAPI, None, None]:
    """Create one enabled-auth application with an isolated prepared database."""
    app = create_app(
        Settings(
            database_url=f"sqlite+pysqlite:///{tmp_path / 'auth-api.db'}",
            auth_enabled=True,
            auth_initial_admin_username=_BOOTSTRAP_USERNAME,
            auth_initial_admin_password=_BOOTSTRAP_PASSWORD,
            auth_cookie_secure=True,
        )
    )
    Base.metadata.create_all(app.state.database_resources.engine)
    app.state.connector_router = FakeConnectorRouter()
    yield app
    database_resources = getattr(app.state, "database_resources", None)
    if database_resources is not None:
        database_resources.dispose()


@asynccontextmanager
async def application_client(app: FastAPI) -> AsyncIterator[httpx.AsyncClient]:
    """Run the production lifespan while httpx manages response cookies normally."""
    async with app.router.lifespan_context(app), httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app), base_url="https://testserver"
    ) as client:
        yield client


async def login(
    client: httpx.AsyncClient, password: str = _BOOTSTRAP_PASSWORD
) -> httpx.Response:
    """Sign in through the HTTP contract and return its safe session body."""
    response = await client.post(
        "/api/auth/login",
        json={"username": _BOOTSTRAP_USERNAME, "password": password},
    )
    assert response.status_code == 200
    assert set(response.json()) == {"user", "csrfToken"}
    return response


def csrf_token(body: dict[str, object]) -> str:
    """Extract only the intentionally browser-visible CSRF value from a safe body."""
    token = body["csrfToken"]
    assert isinstance(token, str)
    assert bool(token)
    return token


@pytest.mark.asyncio
async def test_login_me_logout_and_cookie_contract(enabled_auth_app: FastAPI) -> None:
    """A valid login establishes one cookie session that logout invalidates."""
    async with application_client(enabled_auth_app) as client:
        logged_in = await login(client)
        cookie = SimpleCookie()
        cookie.load(logged_in.headers["set-cookie"])
        morsel = cookie[_COOKIE_NAME]
        assert bool(morsel["httponly"])
        assert bool(morsel["secure"])
        assert morsel["samesite"] == "strict"
        assert morsel["path"] == "/"
        assert morsel["domain"] == ""
        assert morsel["max-age"] == "43200"

        current = await client.get("/api/auth/me")
        assert current.status_code == 200
        assert current.json()["user"] == logged_in.json()["user"]
        csrf_token(current.json())

        logged_out = await client.post(
            "/api/auth/logout",
            headers={"X-CSRF-Token": csrf_token(logged_in.json())},
        )
        assert logged_out.status_code == 204
        assert logged_out.content == b""
        cleared_cookie = SimpleCookie()
        cleared_cookie.load(logged_out.headers["set-cookie"])
        cleared_morsel = cleared_cookie[_COOKIE_NAME]
        assert cleared_morsel["max-age"] == "0"
        assert bool(cleared_morsel["httponly"])
        assert bool(cleared_morsel["secure"])
        assert cleared_morsel["samesite"] == "strict"
        assert cleared_morsel["path"] == "/"
        assert cleared_morsel["domain"] == ""

        after_logout = await client.get("/api/auth/me")
        assert after_logout.status_code == 401
        assert after_logout.json() == _AUTHENTICATION_REQUIRED


@pytest.mark.asyncio
async def test_login_credential_failures_have_one_safe_response(
    enabled_auth_app: FastAPI,
) -> None:
    """Unknown, incorrect, and inactive identities stay indistinguishable to callers."""
    async with application_client(enabled_auth_app) as client:
        unknown = await client.post(
            "/api/auth/login",
            json={"username": "unknown-user", "password": _BOOTSTRAP_PASSWORD},
        )
        wrong_password = await client.post(
            "/api/auth/login",
            json={"username": _BOOTSTRAP_USERNAME, "password": "wrong-test-password"},
        )
        with enabled_auth_app.state.session_factory() as session:
            user = session.scalar(select(User).where(User.username == _BOOTSTRAP_USERNAME))
            assert user is not None
            user.is_active = False
            session.commit()
        inactive = await client.post(
            "/api/auth/login",
            json={"username": _BOOTSTRAP_USERNAME, "password": _BOOTSTRAP_PASSWORD},
        )

    assert unknown.status_code == wrong_password.status_code == inactive.status_code == 401
    assert unknown.json() == wrong_password.json() == inactive.json() == _INVALID_CREDENTIALS


@pytest.mark.asyncio
async def test_all_legacy_knowledge_routes_reject_anonymous_requests(
    enabled_auth_app: FastAPI,
) -> None:
    """The only unauthenticated API surface is health plus the public auth routes."""
    requests = [
        ("POST", "/api/imports", {"url": "https://example.com/protected"}),
        ("GET", "/api/sources", None),
        ("GET", "/api/sources/1", None),
        ("POST", "/api/sources/1/derive", {"kind": "summary"}),
        ("POST", "/api/sources/1/chat", {"question": "Safe question?"}),
        ("PATCH", "/api/artifacts/1", {"markdown": "# Protected edit"}),
        ("GET", "/api/artifacts/1/download", None),
        ("GET", "/api/settings", None),
        (
            "PATCH",
            "/api/settings",
            {"presentation": {"theme": "dark", "preview_device": "mobile"}},
        ),
    ]
    async with application_client(enabled_auth_app) as client:
        health = await client.get("/api/health")
        assert health.status_code == 200
        for method, path, payload in requests:
            response = await client.request(method, path, json=payload)
            assert response.status_code == 401
            assert response.json() == _AUTHENTICATION_REQUIRED


@pytest.mark.asyncio
async def test_every_legacy_write_requires_matching_csrf_and_accepts_a_valid_write(
    enabled_auth_app: FastAPI,
) -> None:
    """State-changing knowledge paths reject missing or mismatched browser intent."""
    writes = [
        ("POST", "/api/imports", {"url": "https://example.com/protected"}),
        ("POST", "/api/sources/1/derive", {"kind": "summary"}),
        ("POST", "/api/sources/1/chat", {"question": "Safe question?"}),
        ("PATCH", "/api/artifacts/1", {"markdown": "# Protected edit"}),
        (
            "PATCH",
            "/api/settings",
            {"presentation": {"theme": "dark", "preview_device": "mobile"}},
        ),
    ]
    async with application_client(enabled_auth_app) as client:
        session = await login(client)
        for method, path, payload in writes:
            missing = await client.request(method, path, json=payload)
            mismatched = await client.request(
                method,
                path,
                json=payload,
                headers={"X-CSRF-Token": "wrong-csrf-token"},
            )
            assert missing.status_code == mismatched.status_code == 403
            assert missing.json() == mismatched.json() == _CSRF_INVALID

        accepted = await client.post(
            "/api/imports",
            json={"url": "https://example.com/protected"},
            headers={"X-CSRF-Token": csrf_token(session.json())},
        )
        assert accepted.status_code == 200


@pytest.mark.asyncio
async def test_change_password_rotates_every_session_and_establishes_one_replacement(
    enabled_auth_app: FastAPI,
) -> None:
    """A password change revokes a second browser session and replaces the current one."""
    async with application_client(enabled_auth_app) as first_client:
        first_session = await login(first_client)
        async with httpx.AsyncClient(
            transport=httpx.ASGITransport(app=enabled_auth_app), base_url="https://testserver"
        ) as second_client:
            await login(second_client)
            changed = await first_client.post(
                "/api/auth/change-password",
                json={
                    "currentPassword": _BOOTSTRAP_PASSWORD,
                    "newPassword": _REPLACEMENT_PASSWORD,
                },
                headers={"X-CSRF-Token": csrf_token(first_session.json())},
            )
            assert changed.status_code == 200
            assert set(changed.json()) == {"user", "csrfToken"}
            assert csrf_token(changed.json())

            stale = await second_client.get("/api/auth/me")
            assert stale.status_code == 401
            assert stale.json() == _AUTHENTICATION_REQUIRED

        async with httpx.AsyncClient(
            transport=httpx.ASGITransport(app=enabled_auth_app), base_url="https://testserver"
        ) as old_password:
            rejected = await old_password.post(
                "/api/auth/login",
                json={"username": _BOOTSTRAP_USERNAME, "password": _BOOTSTRAP_PASSWORD},
            )
            accepted = await old_password.post(
                "/api/auth/login",
                json={"username": _BOOTSTRAP_USERNAME, "password": _REPLACEMENT_PASSWORD},
            )

    assert rejected.status_code == 401
    assert rejected.json() == _INVALID_CREDENTIALS
    assert accepted.status_code == 200


@pytest.mark.asyncio
async def test_wrong_current_password_uses_the_generic_credential_error(
    enabled_auth_app: FastAPI,
) -> None:
    """Password-change verification does not disclose a more specific failure."""
    async with application_client(enabled_auth_app) as client:
        session = await login(client)
        response = await client.post(
            "/api/auth/change-password",
            json={
                "currentPassword": "wrong-test-password",
                "newPassword": _REPLACEMENT_PASSWORD,
            },
            headers={"X-CSRF-Token": csrf_token(session.json())},
        )

    assert response.status_code == 401
    assert response.json() == _INVALID_CREDENTIALS


@pytest.mark.asyncio
async def test_login_does_not_issue_an_old_password_session_after_rotation_wins(
    enabled_auth_app: FastAPI, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A verified old password cannot survive a concurrent password rotation."""
    verification_barrier = threading.Barrier(2)
    allow_login_to_continue = threading.Event()
    with enabled_auth_app.state.session_factory() as session:
        password_hasher = AuthService(
            session,
            session_ttl_seconds=enabled_auth_app.state.settings.auth_session_ttl_seconds,
        )._password_hash
    original_verify = password_hasher.verify

    def pause_the_http_login(password: str, password_hash: str) -> bool:
        verified = original_verify(password, password_hash)
        if (
            threading.current_thread().name != "MainThread"
            and password == _BOOTSTRAP_PASSWORD
        ):
            verification_barrier.wait(timeout=10)
            assert allow_login_to_continue.wait(timeout=10)
        return verified

    async with application_client(enabled_auth_app) as client:
        await login(client)
        monkeypatch.setattr(password_hasher, "verify", pause_the_http_login)
        racing_login = asyncio.create_task(
            client.post(
                "/api/auth/login",
                json={"username": _BOOTSTRAP_USERNAME, "password": _BOOTSTRAP_PASSWORD},
            )
        )
        await asyncio.to_thread(verification_barrier.wait, 10)
        with enabled_auth_app.state.session_factory() as session:
            service = AuthService(
                session,
                session_ttl_seconds=enabled_auth_app.state.settings.auth_session_ttl_seconds,
            )
            user = service.authenticate(
                username=_BOOTSTRAP_USERNAME,
                password=_BOOTSTRAP_PASSWORD,
            )
            assert user is not None
            replacement = service.change_password(
                user,
                current_password=_BOOTSTRAP_PASSWORD,
                new_password=_REPLACEMENT_PASSWORD,
            )
            assert replacement is not None
        allow_login_to_continue.set()
        response = await asyncio.wait_for(racing_login, timeout=10)

        assert response.status_code == 401
        assert response.json() == _INVALID_CREDENTIALS
        with enabled_auth_app.state.session_factory() as session:
            sessions = session.scalars(select(AuthSession)).all()
            assert [item.id for item in sessions] == [replacement.session_id]


@pytest.mark.asyncio
async def test_csrf_rechecks_the_live_session_after_authentication(
    enabled_auth_app: FastAPI,
) -> None:
    """A revoked session cannot mutate state using an earlier auth dependency snapshot."""
    original_authentication = require_authenticated_user

    def authenticate_then_revoke(request: Request):
        auth_session = original_authentication(request)
        assert auth_session is not None
        raw_token = request.cookies[_COOKIE_NAME]
        with request.app.state.session_factory() as session:
            service = AuthService(
                session,
                session_ttl_seconds=request.app.state.settings.auth_session_ttl_seconds,
            )
            assert service.revoke_session(raw_token)
        return auth_session

    enabled_auth_app.dependency_overrides[require_authenticated_user] = authenticate_then_revoke
    try:
        async with application_client(enabled_auth_app) as client:
            session = await login(client)
            response = await client.post(
                "/api/imports",
                json={"url": "https://example.com/revoked-before-csrf"},
                headers={"X-CSRF-Token": csrf_token(session.json())},
            )
            with enabled_auth_app.state.session_factory() as database_session:
                persisted_sources = database_session.scalars(select(Source)).all()
    finally:
        enabled_auth_app.dependency_overrides.clear()

    assert response.status_code == 401
    assert response.json() == _AUTHENTICATION_REQUIRED
    assert persisted_sources == []


@pytest.mark.asyncio
async def test_logout_and_change_password_reject_missing_or_mismatched_csrf(
    enabled_auth_app: FastAPI,
) -> None:
    """Auth-state mutations reject CSRF failures without revoking or rotating anything."""
    async with application_client(enabled_auth_app) as client:
        logged_in = await login(client)
        rejected_requests = [
            ("/api/auth/logout", None),
            ("/api/auth/logout", "wrong-csrf-token"),
            (
                "/api/auth/change-password",
                None,
            ),
            (
                "/api/auth/change-password",
                "wrong-csrf-token",
            ),
        ]
        for path, token in rejected_requests:
            headers = {} if token is None else {"X-CSRF-Token": token}
            if path == "/api/auth/logout":
                response = await client.post(path, headers=headers)
            else:
                response = await client.post(
                    path,
                    headers=headers,
                    json={
                        "currentPassword": _BOOTSTRAP_PASSWORD,
                        "newPassword": _REPLACEMENT_PASSWORD,
                    },
                )
            assert response.status_code == 403
            assert response.json() == _CSRF_INVALID
            current = await client.get("/api/auth/me")
            assert current.status_code == 200
            assert current.json()["user"] == logged_in.json()["user"]

        async with httpx.AsyncClient(
            transport=httpx.ASGITransport(app=enabled_auth_app), base_url="https://testserver"
        ) as verification_client:
            verified = await verification_client.post(
                "/api/auth/login",
                json={"username": _BOOTSTRAP_USERNAME, "password": _BOOTSTRAP_PASSWORD},
            )

    assert verified.status_code == 200
