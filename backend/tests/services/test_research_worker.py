"""Durable single-worker lease, retry, and shutdown contracts."""

from __future__ import annotations

import asyncio
from datetime import UTC, datetime, timedelta

import pytest
from sqlalchemy import select
from sqlalchemy.orm import Session, sessionmaker

from app.db import create_database_engine
from app.models import Artifact, Base, ResearchRun, Source, utc_now
from app.services.research.worker import ResearchWorker


class TransientFailureOrchestrator:
    """Marks claimed runs failed so the worker's retry policy is observable."""

    def __init__(self, factory: sessionmaker[Session]) -> None:
        self._factory = factory
        self.calls: list[int] = []

    async def execute(self, run_id: int) -> ResearchRun:
        self.calls.append(run_id)
        with self._factory() as session:
            run = session.get(ResearchRun, run_id)
            assert run is not None
            run.status = "failed"
            run.failure_code = "provider_error"
            session.commit()
            session.refresh(run)
            return run


class BlockingOrchestrator:
    """Hold one run open long enough to observe lease heartbeats."""

    def __init__(self, factory: sessionmaker[Session]) -> None:
        self._factory = factory
        self.started = asyncio.Event()
        self.release = asyncio.Event()

    async def execute(self, run_id: int) -> ResearchRun:
        self.started.set()
        await self.release.wait()
        with self._factory() as session:
            run = session.get(ResearchRun, run_id)
            assert run is not None
            run.status = "completed"
            session.commit()
            session.refresh(run)
            return run


class CheckpointedTagFailureOrchestrator:
    """Persist a valid report, then emulate an exhausted tag-provider failure."""

    def __init__(self, factory: sessionmaker[Session]) -> None:
        self._factory = factory

    async def execute(self, run_id: int) -> ResearchRun:
        with self._factory() as session:
            run = session.get(ResearchRun, run_id)
            assert run is not None
            if session.scalar(
                select(Artifact.id).where(Artifact.research_run_id == run_id)
            ) is None:
                session.add(
                    Artifact(
                        source_id=run.source_id,
                        research_run_id=run.id,
                        kind="research",
                        title="Checkpointed report",
                        markdown="# Correct report",
                        language="zh",
                    )
                )
            run.status = "failed"
            run.failure_code = "provider_error"
            session.commit()
            session.refresh(run)
            return run


@pytest.fixture
def worker_factory(tmp_path) -> sessionmaker[Session]:
    engine = create_database_engine(f"sqlite+pysqlite:///{tmp_path / 'worker.db'}")
    Base.metadata.create_all(engine)
    factory = sessionmaker(bind=engine, autoflush=False, expire_on_commit=False)
    with factory() as session:
        source = Source(
            canonical_url="https://github.com/openai/worker",
            platform="github",
            title="Worker",
            raw_text="raw",
            source_markdown="raw",
            import_status="ready",
        )
        session.add(source)
        session.flush()
        session.add(
            ResearchRun(
                source_id=source.id,
                trigger="manual",
                status="queued",
                next_attempt_at=datetime(2026, 8, 23, tzinfo=UTC),
            )
        )
        session.commit()
    try:
        yield factory
    finally:
        engine.dispose()


def test_worker_claim_is_atomic_and_reclaims_an_expired_lease(
    worker_factory: sessionmaker[Session],
) -> None:
    now = datetime(2026, 8, 23, 12, tzinfo=UTC)
    first = ResearchWorker(worker_factory, TransientFailureOrchestrator(worker_factory), worker_id="one")
    second = ResearchWorker(worker_factory, TransientFailureOrchestrator(worker_factory), worker_id="two")

    claimed = first.claim_next(now=now)
    assert claimed is not None and claimed.lease_owner == "one"
    assert second.claim_next(now=now) is None
    reclaimed = second.claim_next(now=now + timedelta(seconds=31))

    assert reclaimed is not None and reclaimed.id == claimed.id
    assert reclaimed.lease_owner == "two"
    assert reclaimed.attempt_count == 2


@pytest.mark.asyncio
async def test_worker_retries_transient_failures_at_most_twice(
    worker_factory: sessionmaker[Session],
) -> None:
    now = datetime(2026, 8, 23, 12, tzinfo=UTC)
    orchestrator = TransientFailureOrchestrator(worker_factory)
    worker = ResearchWorker(
        worker_factory,
        orchestrator,
        worker_id="retry",
        retry_delay_seconds=1,
    )

    assert await worker.run_once(now=now) is True
    assert await worker.run_once(now=now + timedelta(seconds=2)) is True
    assert await worker.run_once(now=now + timedelta(seconds=4)) is True
    assert await worker.run_once(now=now + timedelta(seconds=6)) is False
    with worker_factory() as session:
        run = session.get(ResearchRun, 1)
        assert run is not None
        assert run.status == "failed"
        assert run.attempt_count == 3
    assert orchestrator.calls == [1, 1, 1]


@pytest.mark.asyncio
async def test_worker_renews_the_lease_while_a_provider_call_is_running(
    worker_factory: sessionmaker[Session],
) -> None:
    orchestrator = BlockingOrchestrator(worker_factory)
    first = ResearchWorker(
        worker_factory,
        orchestrator,  # type: ignore[arg-type]
        worker_id="heartbeat-owner",
        lease_seconds=1,
    )
    second = ResearchWorker(
        worker_factory,
        TransientFailureOrchestrator(worker_factory),
        worker_id="competing-worker",
        lease_seconds=1,
    )

    execution = asyncio.create_task(first.run_once())
    await asyncio.wait_for(orchestrator.started.wait(), timeout=1)
    await asyncio.sleep(1.2)

    assert second.claim_next(now=utc_now()) is None

    orchestrator.release.set()
    assert await asyncio.wait_for(execution, timeout=1) is True


@pytest.mark.asyncio
async def test_worker_keeps_a_checkpointed_report_as_partial_after_tag_retries_exhaust(
    worker_factory: sessionmaker[Session],
) -> None:
    now = datetime(2026, 8, 23, 12, tzinfo=UTC)
    worker = ResearchWorker(
        worker_factory,
        CheckpointedTagFailureOrchestrator(worker_factory),  # type: ignore[arg-type]
        worker_id="tag-retry",
        retry_delay_seconds=1,
    )

    assert await worker.run_once(now=now) is True
    assert await worker.run_once(now=now + timedelta(seconds=2)) is True
    assert await worker.run_once(now=now + timedelta(seconds=4)) is True

    with worker_factory() as session:
        run = session.get(ResearchRun, 1)
        report = session.scalar(select(Artifact).where(Artifact.research_run_id == 1))
    assert report is not None and report.markdown == "# Correct report"
    assert run is not None and run.status == "partial"
    assert run.failure_code == "tag_provider_error"


@pytest.mark.asyncio
async def test_worker_starts_once_and_stops_cleanly(worker_factory: sessionmaker[Session]) -> None:
    worker = ResearchWorker(
        worker_factory,
        TransientFailureOrchestrator(worker_factory),
        poll_interval_seconds=0.001,
    )

    await worker.start()
    task = worker.task
    await worker.start()
    await worker.stop()

    assert task is not None
    assert worker.task is None
