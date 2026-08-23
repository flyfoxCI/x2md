"""A durable single-worker loop for persisted deep-research runs."""

from __future__ import annotations

import asyncio
import uuid
from datetime import timedelta

from sqlalchemy import and_, or_, select, update
from sqlalchemy.exc import OperationalError
from sqlalchemy.orm import Session
from sqlalchemy.orm.session import sessionmaker

from app.models import AppSetting, ResearchRun, utc_now
from app.services.research.orchestrator import ResearchOrchestrator

type SessionFactory = sessionmaker[Session]

_TRANSIENT_FAILURE_CODES = frozenset({"collection_error", "network_error", "provider_error", "rate_limited"})


class ResearchWorker:
    """Claim at most one leased run at a time and retry only transient failures twice."""

    def __init__(
        self,
        session_factory: SessionFactory,
        orchestrator: ResearchOrchestrator,
        *,
        worker_id: str | None = None,
        lease_seconds: int = 30,
        poll_interval_seconds: float = 0.2,
        retry_delay_seconds: int = 5,
    ) -> None:
        if lease_seconds <= 0 or retry_delay_seconds <= 0 or poll_interval_seconds <= 0:
            raise ValueError("worker timing values must be positive")
        self._session_factory = session_factory
        self._orchestrator = orchestrator
        self._worker_id = worker_id or f"research-{uuid.uuid4().hex}"
        self._lease_seconds = lease_seconds
        self._poll_interval_seconds = poll_interval_seconds
        self._retry_delay_seconds = retry_delay_seconds
        self._stop_event = asyncio.Event()
        self._task: asyncio.Task[None] | None = None

    @property
    def task(self) -> asyncio.Task[None] | None:
        """Expose the one lifecycle-owned loop task for tests and shutdown handling."""
        return self._task

    async def start(self) -> None:
        """Start exactly one non-blocking polling loop."""
        if self._task is None or self._task.done():
            self._stop_event.clear()
            self._task = asyncio.create_task(self._run(), name="deep-research-worker")

    async def stop(self) -> None:
        """Stop polling and await the sole owned task without cancelling a database action."""
        task = self._task
        if task is None:
            return
        self._stop_event.set()
        await task
        self._task = None

    async def run_once(self, *, now=None) -> bool:
        """Claim, execute and release/retry at most one run; return whether work was found."""
        claimed_at = now or utc_now()
        run = self.claim_next(now=claimed_at)
        if run is None:
            return False
        try:
            await self._orchestrator.execute(run.id)
        except Exception:  # noqa: BLE001 - a worker must never strand a claimed run.
            self._mark_execution_exception(run.id)
        self._release_or_retry(run.id, now=claimed_at)
        return True

    def claim_next(self, *, now) -> ResearchRun | None:
        """Atomically claim a queued or expired run with a compare-and-set update."""
        eligible = or_(
            and_(
                ResearchRun.status == "queued",
                or_(ResearchRun.next_attempt_at.is_(None), ResearchRun.next_attempt_at <= now),
            ),
            and_(
                ResearchRun.status == "running",
                ResearchRun.lease_expires_at.is_not(None),
                ResearchRun.lease_expires_at <= now,
            ),
        )
        with self._session_factory() as session:
            candidate_id = session.scalar(
                select(ResearchRun.id)
                .where(eligible)
                .order_by(ResearchRun.created_at, ResearchRun.id)
                .limit(1)
            )
            if candidate_id is None:
                return None
            claimed = session.execute(
                update(ResearchRun)
                .where(ResearchRun.id == candidate_id, eligible)
                .values(
                    status="running",
                    lease_owner=self._worker_id,
                    lease_expires_at=now + timedelta(seconds=self._lease_seconds),
                    next_attempt_at=None,
                    attempt_count=ResearchRun.attempt_count + 1,
                )
            )
            if claimed.rowcount != 1:
                session.rollback()
                return None
            session.commit()
            run = session.get(ResearchRun, candidate_id)
            assert run is not None
            session.refresh(run)
            return run

    async def _run(self) -> None:
        """Poll until shutdown, waking early when the lifecycle asks the worker to stop."""
        while not self._stop_event.is_set():
            progressed = await self.run_once()
            if progressed:
                continue
            try:
                await asyncio.wait_for(
                    self._stop_event.wait(), timeout=self._poll_interval_seconds
                )
            except TimeoutError:
                continue

    def _mark_execution_exception(self, run_id: int) -> None:
        with self._session_factory() as session:
            run = session.get(ResearchRun, run_id)
            if run is None:
                return
            run.status = "failed"
            run.phase = None
            run.failure_code = "worker_execution_error"
            run.finished_at = utc_now()
            session.commit()

    def _release_or_retry(self, run_id: int, *, now) -> None:
        with self._session_factory() as session:
            run = session.get(ResearchRun, run_id)
            if run is None:
                return
            can_retry = (
                run.status == "failed"
                and run.failure_code in _TRANSIENT_FAILURE_CODES
                and run.attempt_count <= run.max_attempts
            )
            if can_retry:
                run.status = "queued"
                run.phase = None
                run.failure_code = None
                run.finished_at = None
                run.next_attempt_at = now + timedelta(seconds=self._retry_delay_seconds)
            run.lease_owner = None
            run.lease_expires_at = None
            session.commit()


def auto_start_enabled(session: Session) -> bool:
    """Read the opt-in automatic-research switch with a secure disabled default."""
    try:
        setting = session.get(AppSetting, "research.auto_start")
    except OperationalError:
        return False
    return bool(setting and setting.value_json.get("enabled") is True)
