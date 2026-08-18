"""Administrator password and opaque session persistence workflows."""

from __future__ import annotations

import hmac
import secrets
from collections.abc import Callable
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from functools import lru_cache
from hashlib import sha256

from pwdlib import PasswordHash
from pydantic import SecretStr
from sqlalchemy import delete, select, update
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session, joinedload

from app.models import AuthSession, User, utc_now

type Now = Callable[[], datetime]


@dataclass(frozen=True, slots=True)
class IssuedSession:
    """The short-lived values an HTTP boundary needs to establish a browser session."""

    session_id: int
    user_id: int
    username: str
    token: str
    csrf_token: str
    expires_at: datetime


class AuthService:
    """The sole owner of password hashing and revocable session primitives."""

    def __init__(
        self,
        session: Session,
        *,
        session_ttl_seconds: int,
        now: Now = utc_now,
    ) -> None:
        self._session = session
        self._session_ttl = timedelta(seconds=session_ttl_seconds)
        self._now = now
        self._password_hash, self._unknown_password_hash = _password_material()

    def bootstrap_admin(
        self,
        *,
        username: str,
        initial_password: SecretStr | None,
        auth_enabled: bool,
    ) -> User | None:
        """Create the first administrator once, failing closed when its seed is absent."""
        if not _is_valid_username(username):
            raise ValueError("username must be printable without leading or trailing whitespace")
        existing_user = self._session.scalar(select(User).order_by(User.id).limit(1))
        if existing_user is not None:
            return existing_user
        if not auth_enabled:
            return None
        if initial_password is None or not initial_password.get_secret_value().strip():
            raise RuntimeError(
                "AUTH_INITIAL_ADMIN_PASSWORD must be set before starting an empty database"
            )

        administrator = User(
            username=username,
            password_hash=self._password_hash.hash(initial_password.get_secret_value()),
            is_active=True,
        )
        self._session.add(administrator)
        try:
            self._session.commit()
        except IntegrityError:
            self._session.rollback()
            winning_user = self._session.scalar(
                select(User).where(User.username == username)
            )
            if winning_user is None:
                raise
            return winning_user
        return administrator

    def authenticate(self, *, username: str, password: str) -> User | None:
        """Return the active matching administrator, or one safe invalid result."""
        if not _is_valid_username(username):
            self._password_hash.verify(password, self._unknown_password_hash)
            return None
        user = self._session.scalar(select(User).where(User.username == username))
        if user is None or not user.is_active:
            self._password_hash.verify(password, self._unknown_password_hash)
            return None
        if not self._password_hash.verify(password, user.password_hash):
            return None
        return user

    def create_session(self, user: User) -> IssuedSession:
        """Persist a digest-only opaque session and return its browser-bound values."""
        return self._persist_session(user)

    def get_current_session(self, raw_token: str) -> AuthSession | None:
        """Resolve an active unexpired session from an opaque browser token."""
        token_hash = _token_hash(raw_token)
        auth_session = self._session.scalar(
            select(AuthSession)
            .options(joinedload(AuthSession.user))
            .where(AuthSession.token_hash == token_hash)
        )
        if auth_session is None or not hmac.compare_digest(auth_session.token_hash, token_hash):
            return None
        if _is_expired(auth_session.expires_at, self._now()):
            self._session.delete(auth_session)
            self._session.commit()
            return None
        if not auth_session.user.is_active:
            return None
        return auth_session

    def revoke_session(self, raw_token: str) -> bool:
        """Delete one matching session so its bearer token cannot be reused."""
        token_hash = _token_hash(raw_token)
        auth_session = self._session.scalar(
            select(AuthSession).where(AuthSession.token_hash == token_hash)
        )
        if auth_session is None or not hmac.compare_digest(auth_session.token_hash, token_hash):
            return False
        self._session.delete(auth_session)
        self._session.commit()
        return True

    def is_csrf_valid(self, auth_session: AuthSession, csrf_token: str) -> bool:
        """Compare a state-changing request's CSRF value without early-exit timing leaks."""
        return hmac.compare_digest(auth_session.csrf_token, csrf_token)

    def change_password(
        self,
        user: User,
        *,
        current_password: str,
        new_password: str,
    ) -> IssuedSession | None:
        """Verify the current password, revoke every session, and issue one replacement."""
        locked_user = self._session.scalar(
            select(User)
            .where(User.id == user.id)
            .execution_options(populate_existing=True)
            .with_for_update()
        )
        if locked_user is None or not self._password_hash.verify(
            current_password, locked_user.password_hash
        ):
            return None

        verified_hash = locked_user.password_hash
        new_password_hash = self._password_hash.hash(new_password)
        password_update = self._session.execute(
            update(User)
            .where(User.id == locked_user.id, User.password_hash == verified_hash)
            .values(password_hash=new_password_hash)
            .execution_options(synchronize_session="fetch")
        )
        if password_update.rowcount != 1:
            self._session.rollback()
            return None

        self._session.execute(delete(AuthSession).where(AuthSession.user_id == locked_user.id))
        return self._persist_session(locked_user)

    def _persist_session(self, user: User) -> IssuedSession:
        raw_token = secrets.token_urlsafe(32)
        csrf_token = secrets.token_urlsafe(32)
        expires_at = self._now() + self._session_ttl
        auth_session = AuthSession(
            user_id=user.id,
            token_hash=_token_hash(raw_token),
            csrf_token=csrf_token,
            expires_at=expires_at,
        )
        self._session.add(auth_session)
        self._session.commit()
        return IssuedSession(
            session_id=auth_session.id,
            user_id=user.id,
            username=user.username,
            token=raw_token,
            csrf_token=csrf_token,
            expires_at=expires_at,
        )


def _token_hash(raw_token: str) -> str:
    """Return the fixed-size server-side digest for a high-entropy bearer value."""
    return sha256(raw_token.encode("utf-8")).hexdigest()


@lru_cache(maxsize=1)
def _password_material() -> tuple[PasswordHash, str]:
    """Build one process-wide Argon2 hasher and dummy hash for timing-safe failures."""
    password_hash = PasswordHash.recommended()
    return password_hash, password_hash.hash(secrets.token_urlsafe(32))


def _is_valid_username(username: str) -> bool:
    """Return whether an authentication username has an unambiguous printable form."""
    return bool(username.strip()) and username == username.strip() and username.isprintable()


def _is_expired(expires_at: datetime, now: datetime) -> bool:
    """Compare SQLite's naive timestamps and PostgreSQL aware timestamps uniformly."""
    if expires_at.tzinfo is None:
        expires_at = expires_at.replace(tzinfo=UTC)
    if now.tzinfo is None:
        now = now.replace(tzinfo=UTC)
    return expires_at <= now
