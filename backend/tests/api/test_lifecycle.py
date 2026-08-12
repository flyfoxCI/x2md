"""Application-lifecycle tests for deterministic connector composition."""

import asyncio
from dataclasses import dataclass

import httpx
import pytest

from app.config import Settings
from app.db import DatabaseResources
from app.main import create_app
from app.models import Base
from tests.api.conftest import FakeConnectorRouter


@dataclass
class TrackingConnectorResources:
    """A composition result that records one lifecycle close operation."""

    router: FakeConnectorRouter
    closed: bool = False

    async def aclose(self) -> None:
        self.closed = True


@dataclass
class FailingConnectorResources(TrackingConnectorResources):
    """A resource whose close error must not prevent database teardown."""

    async def aclose(self) -> None:
        self.closed = True
        raise RuntimeError("connector close failed")


@dataclass
class FailingAIService:
    """A server-owned AI adapter whose close failure must not skip cleanup."""

    closed: bool = False

    async def aclose(self) -> None:
        self.closed = True
        raise RuntimeError("AI close failed")


@pytest.mark.asyncio
async def test_lifespan_composes_once_for_concurrent_requests_and_closes_resource(
    monkeypatch: pytest.MonkeyPatch, tmp_path
) -> None:
    app = create_app(Settings(database_url=f"sqlite+pysqlite:///{tmp_path / 'api.db'}"))
    Base.metadata.create_all(app.state.database_resources.engine)
    composed: list[TrackingConnectorResources] = []

    def compose(_: Settings) -> TrackingConnectorResources:
        resources = TrackingConnectorResources(router=FakeConnectorRouter())
        composed.append(resources)
        return resources

    monkeypatch.setattr("app.main.compose_connector_resources", compose)
    async with app.router.lifespan_context(app):
        async with httpx.AsyncClient(
            transport=httpx.ASGITransport(app=app), base_url="http://testserver"
        ) as client:
            responses = await asyncio.gather(
                client.get("/api/sources"), client.get("/api/sources")
            )

        assert [response.status_code for response in responses] == [200, 200]
        assert len(composed) == 1
        assert composed[0].closed is False

    assert composed[0].closed is True


@pytest.mark.asyncio
async def test_lifespan_preserves_a_test_injected_router_without_composition(
    monkeypatch: pytest.MonkeyPatch, tmp_path
) -> None:
    app = create_app(Settings(database_url=f"sqlite+pysqlite:///{tmp_path / 'api.db'}"))
    app.state.connector_router = FakeConnectorRouter()

    def fail_if_composed(_: Settings) -> TrackingConnectorResources:
        raise AssertionError("the injected test router must be used")

    monkeypatch.setattr("app.main.compose_connector_resources", fail_if_composed)
    async with app.router.lifespan_context(app):
        assert isinstance(app.state.connector_router, FakeConnectorRouter)



@pytest.mark.asyncio
async def test_lifespan_disposes_and_clears_database_state_when_connector_close_fails(
    monkeypatch: pytest.MonkeyPatch, tmp_path
) -> None:
    app = create_app(Settings(database_url=f"sqlite+pysqlite:///{tmp_path / 'api.db'}"))
    resources = FailingConnectorResources(router=FakeConnectorRouter())
    disposed: list[DatabaseResources] = []

    monkeypatch.setattr("app.main.compose_connector_resources", lambda _: resources)
    monkeypatch.setattr(
        DatabaseResources,
        "dispose",
        lambda database_resources: disposed.append(database_resources),
    )

    database_resources = app.state.database_resources
    with pytest.raises(RuntimeError, match="connector close failed"):
        async with app.router.lifespan_context(app):
            pass

    assert resources.closed is True
    assert disposed == [database_resources]
    assert not hasattr(app.state, "connector_resources")
    assert not hasattr(app.state, "connector_router")
    assert not hasattr(app.state, "database_resources")
    assert not hasattr(app.state, "session_factory")


@pytest.mark.asyncio
async def test_lifespan_closes_all_resources_and_cleans_state_when_ai_close_fails(
    monkeypatch: pytest.MonkeyPatch, tmp_path
) -> None:
    app = create_app(Settings(database_url=f"sqlite+pysqlite:///{tmp_path / 'api.db'}"))
    connector_resources = FailingConnectorResources(router=FakeConnectorRouter())
    failing_ai = FailingAIService()
    disposed: list[DatabaseResources] = []
    app.state.ai_service = failing_ai

    monkeypatch.setattr(
        "app.main.compose_connector_resources", lambda _: connector_resources
    )
    monkeypatch.setattr(
        DatabaseResources,
        "dispose",
        lambda database_resources: disposed.append(database_resources),
    )
    database_resources = app.state.database_resources

    with pytest.raises(RuntimeError, match="AI close failed"):
        async with app.router.lifespan_context(app):
            pass

    assert failing_ai.closed is True
    assert connector_resources.closed is True
    assert disposed == [database_resources]
    assert not hasattr(app.state, "ai_service")
    assert not hasattr(app.state, "connector_resources")
    assert not hasattr(app.state, "connector_router")
    assert not hasattr(app.state, "database_resources")
    assert not hasattr(app.state, "session_factory")


@pytest.mark.asyncio
async def test_lifespan_preserves_body_error_when_resource_close_also_fails(
    monkeypatch: pytest.MonkeyPatch, tmp_path
) -> None:
    """A shutdown failure must not mask the actual application execution failure."""
    app = create_app(Settings(database_url=f"sqlite+pysqlite:///{tmp_path / 'api.db'}"))
    connector_resources = FailingConnectorResources(router=FakeConnectorRouter())
    app.state.ai_service = FailingAIService()
    disposed: list[DatabaseResources] = []
    database_resources = app.state.database_resources

    monkeypatch.setattr(
        "app.main.compose_connector_resources", lambda _: connector_resources
    )
    monkeypatch.setattr(
        DatabaseResources,
        "dispose",
        lambda resources: disposed.append(resources),
    )

    with pytest.raises(RuntimeError, match="body failed"):
        async with app.router.lifespan_context(app):
            raise RuntimeError("body failed")

    assert connector_resources.closed is True
    assert disposed == [database_resources]
    assert not hasattr(app.state, "ai_service")
    assert not hasattr(app.state, "connector_resources")
    assert not hasattr(app.state, "connector_router")
    assert not hasattr(app.state, "database_resources")
    assert not hasattr(app.state, "session_factory")


@pytest.mark.asyncio
async def test_lifespan_disposes_and_clears_database_state_when_composition_fails(
    monkeypatch: pytest.MonkeyPatch, tmp_path
) -> None:
    app = create_app(Settings(database_url=f"sqlite+pysqlite:///{tmp_path / 'api.db'}"))
    database_resources = app.state.database_resources
    disposed: list[DatabaseResources] = []

    def fail_to_compose(_: Settings) -> TrackingConnectorResources:
        raise RuntimeError("connector composition failed")

    monkeypatch.setattr("app.main.compose_connector_resources", fail_to_compose)
    monkeypatch.setattr(
        DatabaseResources,
        "dispose",
        lambda resources: disposed.append(resources),
    )

    with pytest.raises(RuntimeError, match="connector composition failed"):
        async with app.router.lifespan_context(app):
            pass

    assert disposed == [database_resources]
    assert not hasattr(app.state, "connector_resources")
    assert not hasattr(app.state, "connector_router")
    assert not hasattr(app.state, "database_resources")
    assert not hasattr(app.state, "session_factory")
