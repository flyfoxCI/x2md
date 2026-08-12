"""Database engine and request-session ownership."""

from collections.abc import Generator
from dataclasses import dataclass

from fastapi import Request
from sqlalchemy import Engine, create_engine, event
from sqlalchemy.engine import URL, make_url
from sqlalchemy.orm import Session, sessionmaker


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


@dataclass(slots=True)
class DatabaseResources:
    """One application's database engine and independent request sessions."""

    engine: Engine
    session_factory: sessionmaker[Session]

    def dispose(self) -> None:
        """Release connections owned by this application instance."""
        self.engine.dispose()


def create_database_resources(database_url: str | URL) -> DatabaseResources:
    """Create app-owned database resources from explicit runtime configuration."""
    engine = create_database_engine(database_url)
    return DatabaseResources(
        engine=engine,
        session_factory=sessionmaker(bind=engine, autoflush=False, expire_on_commit=False),
    )


def get_db(request: Request) -> Generator[Session, None, None]:
    """Yield a request session bound to the receiving application's configuration."""
    with request.app.state.session_factory() as session:
        yield session
