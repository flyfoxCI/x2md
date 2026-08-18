"""Concurrency guarantees for persisted knowledge operations."""

import asyncio
from typing import Self

import httpx
import pytest
from sqlalchemy import create_engine, func, select
from sqlalchemy.orm import Session, sessionmaker

from app.config import Settings
from app.db import DatabaseResources, create_database_engine
from app.main import create_app
from app.models import Base, Source
from app.services.knowledge import KnowledgeService
from tests.api.conftest import FakeConnectorRouter, ready_source


class CoordinatedKnowledgeService(KnowledgeService):
    """Pauses both import attempts at the last point before persistence."""

    def __init__(self, *args: object, barrier: asyncio.Barrier, **kwargs: object) -> None:
        super().__init__(*args, **kwargs)
        self._barrier = barrier

    async def _before_persist_source(self, source: Source) -> None:
        await self._barrier.wait()


class SlowConnectorRouter(FakeConnectorRouter):
    """Waits until both import attempts reached the connector boundary."""

    def __init__(self, started: asyncio.Event, release: asyncio.Event) -> None:
        super().__init__()
        self._started = started
        self._release = release

    async def fetch(self, url: str):
        self.requested_urls.append(url)
        if len(self.requested_urls) == 2:
            self._started.set()
        assert CountingSession.active_sessions == 0
        await self._release.wait()
        return self.sources.get(url, ready_source(url))


class CountingSession(Session):
    """Records request-local session scopes entered by the import workflow."""

    active_sessions = 0

    def __enter__(self) -> Self:
        type(self).active_sessions += 1
        return super().__enter__()

    def __exit__(self, *args: object) -> None:
        try:
            super().__exit__(*args)
        finally:
            type(self).active_sessions -= 1


@pytest.mark.asyncio
async def test_concurrent_imports_recover_the_unique_url_race(tmp_path) -> None:
    database_url = f"sqlite+pysqlite:///{tmp_path / 'concurrent-imports.db'}"
    engine = create_database_engine(database_url)
    Base.metadata.create_all(engine)
    router = FakeConnectorRouter()
    barrier = asyncio.Barrier(2)
    first = CoordinatedKnowledgeService(
        None,
        router,
        import_session_factory=sessionmaker(
            bind=engine, autoflush=False, expire_on_commit=False
        ),
        barrier=barrier,
    )
    second = CoordinatedKnowledgeService(
        None,
        router,
        import_session_factory=sessionmaker(
            bind=engine, autoflush=False, expire_on_commit=False
        ),
        barrier=barrier,
    )

    try:
        imported = await asyncio.gather(
            first.import_url("https://example.com/concurrent"),
            second.import_url("https://example.com/concurrent"),
        )

        assert {source.id for source in imported} == {1}
        with Session(engine) as session:
            assert session.scalar(select(func.count()).select_from(Source)) == 1
    finally:
        engine.dispose()


@pytest.mark.asyncio
async def test_slow_concurrent_imports_do_not_hold_pool_connections_during_fetch(
    tmp_path,
) -> None:
    engine = create_engine(
        f"sqlite+pysqlite:///{tmp_path / 'pool.db'}",
        connect_args={"check_same_thread": False},
        pool_size=1,
        max_overflow=0,
        pool_timeout=0.05,
    )
    Base.metadata.create_all(engine)
    CountingSession.active_sessions = 0
    factory = sessionmaker(
        bind=engine,
        class_=CountingSession,
        autoflush=False,
        expire_on_commit=False,
    )
    started = asyncio.Event()
    release = asyncio.Event()
    router = SlowConnectorRouter(started, release)
    services = [
        KnowledgeService(None, router, import_session_factory=factory)
        for _ in range(2)
    ]

    try:
        imports = [
            asyncio.create_task(
                service.import_url(f"https://example.com/slow-{index}")
            )
            for index, service in enumerate(services)
        ]
        await asyncio.wait_for(started.wait(), timeout=0.2)
        release.set()
        imported = await asyncio.wait_for(asyncio.gather(*imports), timeout=0.2)

        assert {source.canonical_url for source in imported} == {
            "https://example.com/slow-0",
            "https://example.com/slow-1",
        }
    finally:
        engine.dispose()


@pytest.mark.asyncio
async def test_import_endpoint_holds_no_request_session_during_slow_fetch(tmp_path) -> None:
    app = create_app(
        Settings(
            database_url=f"sqlite+pysqlite:///{tmp_path / 'unused.db'}",
            auth_enabled=False,
        )
    )
    app.state.database_resources.dispose()
    engine = create_engine(
        f"sqlite+pysqlite:///{tmp_path / 'endpoint-pool.db'}",
        connect_args={"check_same_thread": False},
        pool_size=1,
        max_overflow=0,
        pool_timeout=0.05,
    )
    Base.metadata.create_all(engine)
    CountingSession.active_sessions = 0
    factory = sessionmaker(
        bind=engine,
        class_=CountingSession,
        autoflush=False,
        expire_on_commit=False,
    )
    app.state.database_resources = DatabaseResources(engine, factory)
    app.state.session_factory = factory
    started = asyncio.Event()
    release = asyncio.Event()
    app.state.connector_router = SlowConnectorRouter(started, release)

    async with app.router.lifespan_context(app), httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app), base_url="http://testserver"
    ) as client:
        requests = [
            asyncio.create_task(client.post("/api/imports", json={"url": url}))
            for url in (
                "https://example.com/endpoint-slow-0",
                "https://example.com/endpoint-slow-1",
            )
        ]
        await asyncio.wait_for(started.wait(), timeout=0.2)
        release.set()
        responses = await asyncio.wait_for(asyncio.gather(*requests), timeout=0.2)

    assert [response.status_code for response in responses] == [200, 200]
