"""Database engine and request-session ownership."""

from collections.abc import Generator
from functools import lru_cache

from sqlalchemy import Engine, create_engine, event
from sqlalchemy.engine import URL, make_url
from sqlalchemy.orm import Session, sessionmaker

from app.config import Settings


def normalize_database_url(database_url: str | URL) -> URL:
    """Select psycopg v3 for bare PostgreSQL URLs while preserving explicit drivers."""
    url = make_url(database_url)
    if url.get_backend_name() == "postgresql" and url.drivername == "postgresql":
        return url.set(drivername="postgresql+psycopg")
    return url


def create_database_engine(database_url: str | URL) -> Engine:
    """Create an engine compatible with the configured SQLite or PostgreSQL URL."""
    url = normalize_database_url(database_url)
    connect_args = {"check_same_thread": False} if url.get_backend_name() == "sqlite" else {}
    engine = create_engine(url, connect_args=connect_args)
    if url.get_backend_name() == "sqlite":

        @event.listens_for(engine, "connect")
        def enable_sqlite_foreign_keys(dbapi_connection: object, _: object) -> None:
            cursor = dbapi_connection.cursor()  # type: ignore[attr-defined]
            cursor.execute("PRAGMA foreign_keys=ON")
            cursor.close()

    return engine


@lru_cache
def get_engine() -> Engine:
    """Return the process-wide database engine."""
    return create_database_engine(Settings().database_url)


@lru_cache
def get_session_factory() -> sessionmaker[Session]:
    """Return the process-wide factory for independent database sessions."""
    return sessionmaker(bind=get_engine(), autoflush=False, expire_on_commit=False)


def get_db() -> Generator[Session, None, None]:
    """Yield a request-scoped session for FastAPI dependencies."""
    with get_session_factory()() as session:
        yield session
