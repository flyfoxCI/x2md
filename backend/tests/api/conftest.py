"""Shared API fixtures with a fake connector and isolated SQLite database."""

from collections.abc import Generator
from dataclasses import dataclass, field
from pathlib import Path

import pytest
from sqlalchemy.orm import Session, sessionmaker

from app.config import Settings
from app.main import create_app
from app.models import Base
from app.services.connectors.base import NormalizedSource


@dataclass
class FakeConnectorRouter:
    """Test double that records imports without performing network requests."""

    sources: dict[str, NormalizedSource] = field(default_factory=dict)
    requested_urls: list[str] = field(default_factory=list)

    async def fetch(self, url: str) -> NormalizedSource:
        self.requested_urls.append(url)
        return self.sources.get(url, ready_source(url))


@dataclass
class ApiHarness:
    """The ASGI app, connector double, and test-only session factory."""

    app: object
    router: FakeConnectorRouter
    session_factory: sessionmaker[Session]


def ready_source(url: str, *, title: str = "Reasoning at Scale") -> NormalizedSource:
    """Create a normal ready connector result for a public test URL."""
    return NormalizedSource(
        canonical_url=url,
        platform="web",
        title=title,
        text="Canonical source material.",
        markdown=f"# {title}\n\nCanonical source material.",
        status="ready",
        author="Ada Lovelace",
        metadata={"fixture": True},
        provenance={"connector": "fake"},
    )


@pytest.fixture
def api_harness(tmp_path: Path) -> Generator[ApiHarness, None, None]:
    """Supply an app whose request sessions use its own configured SQLite database."""
    app = create_app(
        Settings(database_url=f"sqlite+pysqlite:///{tmp_path / 'api.db'}")
    )
    engine = app.state.database_resources.engine
    Base.metadata.create_all(engine)
    router = FakeConnectorRouter()
    app.state.connector_router = router
    yield ApiHarness(app=app, router=router, session_factory=app.state.session_factory)
    app.state.database_resources.dispose()
