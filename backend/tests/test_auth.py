"""Password, bootstrap, and opaque-session contracts."""

import importlib
import importlib.util
import secrets
import threading
from collections.abc import Generator
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from hashlib import sha256

import pytest
from pydantic import SecretStr, ValidationError
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.config import Settings
from app.db import create_database_engine
from app.models import AuthSession, Base, User


@dataclass
class Clock:
    """A deterministic application clock for expiry assertions."""

    value: datetime

    def now(self) -> datetime:
        return self.value


@pytest.fixture
def session() -> Generator[Session, None, None]:
    """Provide an isolated database for the password/session service."""
    engine = create_database_engine("sqlite+pysqlite:///:memory:")
    Base.metadata.create_all(engine)
    with Session(engine) as database_session:
        yield database_session
    engine.dispose()


def auth_service(session: Session, clock: Clock, *, ttl_seconds: int = 3_600) -> object:
    """Construct the intended domain owner without importing it before RED."""
    module_spec = importlib.util.find_spec("app.services.auth")

    assert module_spec is not None, "AuthService must own password and session behavior"
    module = importlib.import_module("app.services.auth")
    service_type = getattr(module, "AuthService", None)

    assert service_type is not None
    return service_type(session, session_ttl_seconds=ttl_seconds, now=clock.now)


def test_auth_settings_default_aliases_and_secret_repr(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Authentication configuration is fail-closed and supports both env styles."""
    for name in (
        "AUTH_ENABLED",
        "AUTH_INITIAL_ADMIN_USERNAME",
        "AUTH_INITIAL_ADMIN_PASSWORD",
        "AUTH_SESSION_TTL_SECONDS",
        "AUTH_COOKIE_SECURE",
        "APP_AUTH_ENABLED",
        "APP_AUTH_INITIAL_ADMIN_USERNAME",
        "APP_AUTH_INITIAL_ADMIN_PASSWORD",
        "APP_AUTH_SESSION_TTL_SECONDS",
        "APP_AUTH_COOKIE_SECURE",
    ):
        monkeypatch.delenv(name, raising=False)

    defaults = Settings()

    assert getattr(defaults, "auth_enabled", None) is True
    assert getattr(defaults, "auth_initial_admin_username", None) == "admin"
    assert getattr(defaults, "auth_initial_admin_password", None) is None
    assert getattr(defaults, "auth_session_ttl_seconds", None) == 43_200
    assert getattr(defaults, "auth_cookie_secure", None) is True

    seed_value = secrets.token_urlsafe(24)
    monkeypatch.setenv("AUTH_ENABLED", "false")
    monkeypatch.setenv("AUTH_INITIAL_ADMIN_USERNAME", "operator")
    monkeypatch.setenv("AUTH_INITIAL_ADMIN_PASSWORD", seed_value)
    monkeypatch.setenv("AUTH_SESSION_TTL_SECONDS", "900")
    monkeypatch.setenv("AUTH_COOKIE_SECURE", "false")

    direct = Settings()

    assert direct.auth_enabled is False
    assert direct.auth_initial_admin_username == "operator"
    assert isinstance(direct.auth_initial_admin_password, SecretStr)
    assert direct.auth_initial_admin_password.get_secret_value() == seed_value
    assert direct.auth_session_ttl_seconds == 900
    assert direct.auth_cookie_secure is False
    assert seed_value not in repr(direct)

    for name in (
        "AUTH_ENABLED",
        "AUTH_INITIAL_ADMIN_USERNAME",
        "AUTH_INITIAL_ADMIN_PASSWORD",
        "AUTH_SESSION_TTL_SECONDS",
        "AUTH_COOKIE_SECURE",
    ):
        monkeypatch.delenv(name)
    monkeypatch.setenv("APP_AUTH_ENABLED", "true")
    monkeypatch.setenv("APP_AUTH_INITIAL_ADMIN_USERNAME", "prefixed-operator")
    monkeypatch.setenv("APP_AUTH_SESSION_TTL_SECONDS", "2592000")
    monkeypatch.setenv("APP_AUTH_COOKIE_SECURE", "true")

    prefixed = Settings()

    assert prefixed.auth_enabled is True
    assert prefixed.auth_initial_admin_username == "prefixed-operator"
    assert prefixed.auth_initial_admin_password is None
    assert prefixed.auth_session_ttl_seconds == 2_592_000
    assert prefixed.auth_cookie_secure is True


@pytest.mark.parametrize("ttl_seconds", ["899", "2592001"])
def test_auth_settings_reject_session_ttl_outside_safe_bounds(
    monkeypatch: pytest.MonkeyPatch, ttl_seconds: str
) -> None:
    """Absolute session policy rejects values outside its documented range."""
    monkeypatch.setenv("AUTH_SESSION_TTL_SECONDS", ttl_seconds)

    with pytest.raises(ValidationError):
        Settings()


@pytest.mark.parametrize("username", [" ", " admin", "admin ", "admin\nname"])
def test_auth_settings_reject_unsafe_initial_administrator_usernames(
    username: str,
) -> None:
    """Bootstrap identity values cannot contain boundary whitespace or controls."""
    with pytest.raises(ValidationError):
        Settings(auth_initial_admin_username=username)

    assert Settings(auth_initial_admin_username="管理员").auth_initial_admin_username == "管理员"


def test_auth_services_share_process_password_material_without_rehashing(
    session: Session, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Request-scoped services reuse the one dummy hash prepared for timing safety."""
    module = importlib.import_module("app.services.auth")
    password_material = getattr(module, "_password_material", None)

    assert password_material is not None
    recommended_calls: list[None] = []
    hash_inputs: list[str] = []

    class RecordingHasher:
        def hash(self, value: str) -> str:
            hash_inputs.append(value)
            return "recorded-hash"

        def verify(self, _: str, __: str) -> bool:
            return False

    hasher = RecordingHasher()

    class RecordingPasswordHash:
        @staticmethod
        def recommended() -> RecordingHasher:
            recommended_calls.append(None)
            return hasher

    password_material.cache_clear()
    try:
        monkeypatch.setattr(module, "PasswordHash", RecordingPasswordHash)
        first = module.AuthService(
            session, session_ttl_seconds=900, now=Clock(datetime(2026, 8, 18, tzinfo=UTC)).now
        )
        second = module.AuthService(
            session, session_ttl_seconds=900, now=Clock(datetime(2026, 8, 18, tzinfo=UTC)).now
        )

        assert first._password_hash is second._password_hash
        assert first._unknown_password_hash == second._unknown_password_hash
        assert recommended_calls == [None]
        assert len(hash_inputs) == 1
    finally:
        password_material.cache_clear()


def test_bootstrap_creates_one_argon2_administrator_without_plaintext(
    session: Session,
) -> None:
    """The deployment seed is consumed into an Argon2id hash exactly once."""
    service = auth_service(session, Clock(datetime(2026, 8, 18, tzinfo=UTC)))
    seed = SecretStr(secrets.token_urlsafe(24))

    created = service.bootstrap_admin(
        username="admin", initial_password=seed, auth_enabled=True
    )
    repeated = service.bootstrap_admin(
        username="admin", initial_password=seed, auth_enabled=True
    )
    persisted_hash = session.scalar(select(User.password_hash))

    assert created is not None
    assert repeated is not None
    assert created.id == repeated.id
    assert persisted_hash is not None
    assert persisted_hash.startswith("$argon2id$")
    assert seed.get_secret_value() not in persisted_hash
    assert service.authenticate(username="admin", password=seed.get_secret_value()) == created
    assert session.scalar(select(User).where(User.username == "admin")) == created


def test_bootstrap_rejects_an_empty_seed_only_for_an_enabled_empty_database(
    session: Session,
) -> None:
    """An unset bootstrap secret fails closed before public runtime starts."""
    service = auth_service(session, Clock(datetime(2026, 8, 18, tzinfo=UTC)))

    with pytest.raises(RuntimeError, match="AUTH_INITIAL_ADMIN_PASSWORD"):
        service.bootstrap_admin(username="admin", initial_password=None, auth_enabled=True)

    assert session.scalar(select(User)) is None
    assert (
        service.bootstrap_admin(username="admin", initial_password=None, auth_enabled=False)
        is None
    )


def test_bootstrap_rejects_invalid_username_but_accepts_printable_unicode(
    session: Session,
) -> None:
    """Service callers cannot bypass the bootstrap username configuration policy."""
    service = auth_service(session, Clock(datetime(2026, 8, 18, tzinfo=UTC)))
    seed = SecretStr(secrets.token_urlsafe(24))

    with pytest.raises(ValueError, match="username"):
        service.bootstrap_admin(
            username=" admin", initial_password=seed, auth_enabled=True
        )

    administrator = service.bootstrap_admin(
        username="管理员", initial_password=seed, auth_enabled=True
    )

    assert administrator is not None
    assert administrator.username == "管理员"


def test_authenticate_rejects_an_invalid_username_even_if_a_legacy_row_exists(
    session: Session,
) -> None:
    """Malformed historical names never become a valid authenticated identity."""
    service = auth_service(session, Clock(datetime(2026, 8, 18, tzinfo=UTC)))
    seed = secrets.token_urlsafe(24)
    session.add(
        User(
            username=" admin",
            password_hash=service._password_hash.hash(seed),
            is_active=True,
        )
    )
    session.commit()

    assert service.authenticate(username=" admin", password=seed) is None


def test_bootstrap_returns_the_winning_administrator_after_a_unique_key_race(
    tmp_path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A concurrent first deployment returns the committed winner with a usable session."""
    engine = create_database_engine(f"sqlite+pysqlite:///{tmp_path / 'bootstrap-race.db'}")
    Base.metadata.create_all(engine)
    seed = SecretStr(secrets.token_urlsafe(24))
    clock = Clock(datetime(2026, 8, 18, tzinfo=UTC))

    with Session(engine) as losing_session:
        service = auth_service(losing_session, clock)
        original_commit = losing_session.commit
        commit_attempts = 0

        def commit_after_winner() -> None:
            nonlocal commit_attempts

            commit_attempts += 1
            if commit_attempts == 1:
                with Session(engine) as winning_session:
                    winning_session.add(
                        User(
                            username="admin",
                            password_hash=service._password_hash.hash(
                                seed.get_secret_value()
                            ),
                            is_active=True,
                        )
                    )
                    winning_session.commit()
            original_commit()

        monkeypatch.setattr(losing_session, "commit", commit_after_winner)
        winner = service.bootstrap_admin(
            username="admin", initial_password=seed, auth_enabled=True
        )
        monkeypatch.setattr(losing_session, "commit", original_commit)

        assert winner is not None
        assert winner.username == "admin"
        issued = service.create_session(winner)
        assert service.get_current_session(issued.token) is not None

    engine.dispose()


def test_authenticate_rejects_unknown_and_wrong_credentials_identically(
    session: Session,
) -> None:
    """The HTTP layer can map both invalid credential inputs to one outcome."""
    service = auth_service(session, Clock(datetime(2026, 8, 18, tzinfo=UTC)))
    seed = SecretStr(secrets.token_urlsafe(24))
    created = service.bootstrap_admin(
        username="admin", initial_password=seed, auth_enabled=True
    )

    assert created is not None
    assert service.authenticate(username="unknown", password=seed.get_secret_value()) is None
    assert (
        service.authenticate(
            username="admin", password=f"{seed.get_secret_value()}-incorrect"
        )
        is None
    )


def test_authenticate_verifies_a_dummy_argon2_hash_for_an_unknown_username(
    session: Session, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A missing account follows the password-verification path before failing."""
    service = auth_service(session, Clock(datetime(2026, 8, 18, tzinfo=UTC)))
    password_hasher = service._password_hash
    verified_passwords: list[str] = []
    real_verify = password_hasher.verify

    def record_verify(password: str, password_hash: str) -> bool:
        verified_passwords.append(password)
        return real_verify(password, password_hash)

    monkeypatch.setattr(password_hasher, "verify", record_verify)
    candidate_password = secrets.token_urlsafe(24)

    assert service.authenticate(username="unknown", password=candidate_password) is None
    assert verified_passwords == [candidate_password]


def test_create_session_stores_only_digest_with_absolute_expiry_and_csrf(
    session: Session,
) -> None:
    """A raw bearer value reaches the browser boundary but never database storage."""
    clock = Clock(datetime(2026, 8, 18, 10, tzinfo=UTC))
    service = auth_service(session, clock, ttl_seconds=900)
    seed = SecretStr(secrets.token_urlsafe(24))
    user = service.bootstrap_admin(username="admin", initial_password=seed, auth_enabled=True)

    assert user is not None
    issued = service.create_session(user)
    persisted = session.get(AuthSession, issued.session_id)

    assert persisted is not None
    assert issued.expires_at == clock.value + timedelta(seconds=900)
    assert persisted.token_hash == sha256(issued.token.encode()).hexdigest()
    assert issued.token != persisted.token_hash
    assert persisted.csrf_token == issued.csrf_token
    assert service.get_current_session(issued.token) == persisted
    assert service.is_csrf_valid(persisted, issued.csrf_token) is True
    assert service.is_csrf_valid(persisted, f"{issued.csrf_token}-incorrect") is False


def test_expired_and_revoked_sessions_do_not_resolve_as_current(
    session: Session,
) -> None:
    """Expiry is absolute and a server-side revocation takes effect immediately."""
    clock = Clock(datetime(2026, 8, 18, 10, tzinfo=UTC))
    service = auth_service(session, clock, ttl_seconds=900)
    seed = SecretStr(secrets.token_urlsafe(24))
    user = service.bootstrap_admin(username="admin", initial_password=seed, auth_enabled=True)

    assert user is not None
    expired = service.create_session(user)
    clock.value += timedelta(seconds=900)

    assert service.get_current_session(expired.token) is None
    assert session.get(AuthSession, expired.session_id) is None

    active = service.create_session(user)

    assert service.revoke_session(active.token) is True
    assert service.revoke_session(active.token) is False
    assert service.get_current_session(active.token) is None


def test_change_password_requires_current_password_and_replaces_all_sessions(
    session: Session,
) -> None:
    """Successful rotation revokes every old browser session and issues one new one."""
    clock = Clock(datetime(2026, 8, 18, 10, tzinfo=UTC))
    service = auth_service(session, clock)
    original_seed = SecretStr(secrets.token_urlsafe(24))
    replacement_seed = secrets.token_urlsafe(24)
    user = service.bootstrap_admin(
        username="admin", initial_password=original_seed, auth_enabled=True
    )

    assert user is not None
    first = service.create_session(user)
    second = service.create_session(user)
    original_hash = user.password_hash

    assert (
        service.change_password(
            user,
            current_password=f"{original_seed.get_secret_value()}-incorrect",
            new_password=replacement_seed,
        )
        is None
    )
    assert session.scalar(select(AuthSession).where(AuthSession.user_id == user.id)) is not None

    replacement = service.change_password(
        user,
        current_password=original_seed.get_secret_value(),
        new_password=replacement_seed,
    )

    assert replacement is not None
    assert user.password_hash != original_hash
    assert service.authenticate(username="admin", password=original_seed.get_secret_value()) is None
    assert service.authenticate(username="admin", password=replacement_seed) == user
    assert service.get_current_session(first.token) is None
    assert service.get_current_session(second.token) is None
    assert service.get_current_session(replacement.token) is not None
    assert session.scalars(select(AuthSession).where(AuthSession.user_id == user.id)).all() == [
        session.get(AuthSession, replacement.session_id)
    ]


def test_change_password_reloads_a_stale_user_before_rotation(tmp_path) -> None:
    """A caller with an old in-memory hash cannot issue a second replacement session."""
    engine = create_database_engine(f"sqlite+pysqlite:///{tmp_path / 'rotation-race.db'}")
    Base.metadata.create_all(engine)
    initial_secret = SecretStr(secrets.token_urlsafe(24))
    winning_secret = secrets.token_urlsafe(24)
    stale_secret = secrets.token_urlsafe(24)
    clock = Clock(datetime(2026, 8, 18, tzinfo=UTC))

    with Session(engine) as stale_session:
        stale_service = auth_service(stale_session, clock)
        user = stale_service.bootstrap_admin(
            username="admin", initial_password=initial_secret, auth_enabled=True
        )

        assert user is not None
        original_hash = user.password_hash

        with Session(engine) as winning_session:
            winning_service = auth_service(winning_session, clock)
            winning_user = winning_service.authenticate(
                username="admin", password=initial_secret.get_secret_value()
            )

            assert winning_user is not None
            winning_rotation = winning_service.change_password(
                winning_user,
                current_password=initial_secret.get_secret_value(),
                new_password=winning_secret,
            )

            assert winning_rotation is not None

        stale_rotation = stale_service.change_password(
            user,
            current_password=initial_secret.get_secret_value(),
            new_password=stale_secret,
        )

        assert stale_rotation is None
        assert user.password_hash != original_hash

    with Session(engine) as verification_session:
        sessions = verification_session.scalars(select(AuthSession)).all()

        assert len(sessions) == 1

    engine.dispose()


def test_change_password_allows_only_one_concurrent_old_password_rotation(
    tmp_path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A portable compare-and-set prevents two verified callers from both succeeding."""
    engine = create_database_engine(f"sqlite+pysqlite:///{tmp_path / 'cas-race.db'}")
    Base.metadata.create_all(engine)
    clock = Clock(datetime(2026, 8, 18, tzinfo=UTC))
    original_secret = SecretStr(secrets.token_urlsafe(24))
    first_replacement = secrets.token_urlsafe(24)
    second_replacement = secrets.token_urlsafe(24)

    with Session(engine) as bootstrap_session:
        bootstrap_service = auth_service(bootstrap_session, clock)
        user = bootstrap_service.bootstrap_admin(
            username="admin", initial_password=original_secret, auth_enabled=True
        )

        assert user is not None

    password_hasher = bootstrap_service._password_hash
    original_verify = password_hasher.verify
    original_hash = password_hasher.hash
    verification_barrier = threading.Barrier(2)
    first_rotation_finished = threading.Event()
    results: dict[str, object] = {}

    def controlled_verify(password: str, password_hash: str) -> bool:
        if password == original_secret.get_secret_value():
            verification_barrier.wait(timeout=10)
        return original_verify(password, password_hash)

    def controlled_hash(password: str) -> str:
        if password == second_replacement:
            assert first_rotation_finished.wait(timeout=10)
        return original_hash(password)

    monkeypatch.setattr(password_hasher, "verify", controlled_verify)
    monkeypatch.setattr(password_hasher, "hash", controlled_hash)

    def rotate(label: str, replacement_secret: str) -> None:
        try:
            with Session(engine) as rotation_session:
                rotation_service = auth_service(rotation_session, clock)
                rotating_user = rotation_session.scalar(
                    select(User).where(User.username == "admin")
                )

                assert rotating_user is not None
                results[label] = rotation_service.change_password(
                    rotating_user,
                    current_password=original_secret.get_secret_value(),
                    new_password=replacement_secret,
                )
        finally:
            if label == "first":
                first_rotation_finished.set()

    first_thread = threading.Thread(target=rotate, args=("first", first_replacement))
    second_thread = threading.Thread(target=rotate, args=("second", second_replacement))
    first_thread.start()
    second_thread.start()
    first_thread.join(timeout=20)
    second_thread.join(timeout=20)

    assert first_thread.is_alive() is False
    assert second_thread.is_alive() is False
    assert results["first"] is not None
    assert results["second"] is None

    with Session(engine) as verification_session:
        sessions = verification_session.scalars(select(AuthSession)).all()
        verification_service = auth_service(verification_session, clock)

        assert len(sessions) == 1
        assert (
            verification_service.authenticate(
                username="admin", password=first_replacement
            )
            is not None
        )
        assert (
            verification_service.authenticate(
                username="admin", password=second_replacement
            )
            is None
        )

    engine.dispose()
