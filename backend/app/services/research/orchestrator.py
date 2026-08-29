"""The sole state-machine owner for evidence-first deep research runs."""

from __future__ import annotations

import hashlib
from collections.abc import Mapping
from dataclasses import dataclass
from typing import Protocol

from sqlalchemy import select
from sqlalchemy.orm import Session
from sqlalchemy.orm.session import sessionmaker

from app.models import (
    Artifact,
    ResearchCitation,
    ResearchEvidence,
    ResearchRun,
    Source,
    utc_now,
)
from app.services.ai import (
    GeneratedResearchNote,
    GeneratedResearchReport,
    ProviderError,
    SuggestedResearchTag,
)
from app.services.research.citations import (
    ResearchReportValidationError,
    validate_research_report,
)
from app.services.research.collectors.base import ResearchCollector
from app.services.research.contracts import (
    CollectionResult,
    EvidenceInput,
    collection_budget,
)
from app.services.research.tags import TagService

type SessionFactory = sessionmaker[Session]


@dataclass(frozen=True, slots=True)
class ResearchError(Exception):
    """A stable research-domain failure for worker and API callers."""

    code: str
    message: str
    status_code: int = 422


@dataclass(frozen=True, slots=True)
class _SourceSnapshot:
    canonical_url: str
    platform: str
    metadata_json: Mapping[str, object]


class ResearchAI(Protocol):
    """The typed subset of the server-only AI boundary used by the orchestrator."""

    async def research_note(self, evidence: EvidenceInput) -> GeneratedResearchNote:
        """Produce a note for one evidence record."""

    async def research_report(
        self,
        *,
        platform: str,
        coverage: Mapping[str, object],
        notes: tuple[GeneratedResearchNote, ...],
    ) -> GeneratedResearchReport:
        """Produce a fixed-template research report."""

    async def research_tags(
        self, *, notes: tuple[GeneratedResearchNote, ...]
    ) -> tuple[SuggestedResearchTag, ...]:
        """Produce evidence-scoped tag candidates."""


class ResearchOrchestrator:
    """Persist collection, notes, validated reports and tag suggestions in one workflow."""

    def __init__(
        self,
        session_factory: SessionFactory,
        *,
        collectors: Mapping[str, ResearchCollector],
        ai: ResearchAI,
    ) -> None:
        self._session_factory = session_factory
        self._collectors = dict(collectors)
        self._ai = ai

    def enqueue(self, source_id: int, *, trigger: str) -> ResearchRun:
        """Create one durable run or return the already active run for this source."""
        with self._session_factory() as session:
            source = session.get(Source, source_id)
            if source is None:
                raise ResearchError("source_not_found", "The requested source does not exist.", 404)
            try:
                budget = collection_budget(source.platform)  # type: ignore[arg-type]
            except ValueError as error:
                raise ResearchError(
                    "unsupported_research_source",
                    "Deep research is available for GitHub, arXiv, and Hugging Face sources.",
                ) from error
            active = session.scalar(
                select(ResearchRun)
                .where(
                    ResearchRun.source_id == source_id,
                    ResearchRun.status.in_(("queued", "running")),
                )
                .order_by(ResearchRun.id.desc())
            )
            if active is not None:
                return active
            run = ResearchRun(
                source_id=source_id,
                trigger=trigger,
                status="queued",
                budget_json=budget.as_dict(),
                coverage_json={},
            )
            session.add(run)
            session.commit()
            session.refresh(run)
            return run

    async def execute(self, run_id: int) -> ResearchRun:
        """Execute one durable run without keeping a database session during I/O."""
        source = self._start_run(run_id)
        checkpoint = self._load_collection_checkpoint(run_id)
        if checkpoint is None:
            collector = self._collectors.get(source.platform)
            if collector is None:
                return self._finish(
                    run_id, status="blocked", failure_code="unsupported_research_source"
                )
            try:
                collection = await collector.collect(source)
            except Exception:  # noqa: BLE001 - collectors are untrusted I/O boundaries.
                return self._finish(run_id, status="failed", failure_code="collection_error")
            inputs = self._persist_collection(run_id, collection)
            coverage = dict(collection.coverage)
        else:
            inputs, coverage = checkpoint
        if not inputs:
            reason = coverage.get("reason")
            if reason in {"network_error", "rate_limited"}:
                return self._finish(run_id, status="failed", failure_code=str(reason))
            return self._finish(run_id, status="blocked", failure_code="no_included_evidence")

        try:
            notes = await self._research_notes(run_id, inputs)
            if not self._has_report_checkpoint(run_id):
                report = await self._generate_valid_report(
                    platform=source.platform,
                    coverage=coverage,
                    notes=notes,
                    known_tokens={evidence.evidence_id for evidence in inputs},
                )
                self._persist_report_checkpoint(run_id, report)
            self._set_phase(run_id, "tagging")
            tags = await self._generate_valid_tags(notes)
        except ProviderError as error:
            if error.code == "invalid_research_tags" and self._has_report_checkpoint(run_id):
                status = "partial"
            else:
                status = "blocked" if error.code == "provider_not_configured" else "failed"
            return self._finish(run_id, status=status, failure_code=error.code)
        except ResearchReportValidationError:
            return self._finish(run_id, status="failed", failure_code="invalid_citation")
        except Exception:  # noqa: BLE001 - malformed AI adapters cannot leave a running run.
            return self._finish(run_id, status="failed", failure_code="research_processing_error")
        return self._persist_completion(run_id, coverage, tags)

    async def _generate_valid_report(
        self,
        *,
        platform: str,
        coverage: Mapping[str, object],
        notes: tuple[GeneratedResearchNote, ...],
        known_tokens: set[int],
    ) -> GeneratedResearchReport:
        """Retry one model-format failure without weakening citation validation."""
        for attempt in range(2):
            report = await self._ai.research_report(
                platform=platform, coverage=coverage, notes=notes
            )
            try:
                validate_research_report(report.markdown, known_tokens=known_tokens)
                return report
            except ResearchReportValidationError:
                if attempt == 1:
                    raise
        raise AssertionError("unreachable")

    async def _generate_valid_tags(
        self, notes: tuple[GeneratedResearchNote, ...]
    ) -> tuple[SuggestedResearchTag, ...]:
        """Retry one malformed structured-tag response before honest degradation."""
        for attempt in range(2):
            try:
                return await self._ai.research_tags(notes=notes)
            except ProviderError as error:
                if error.code != "invalid_research_tags" or attempt == 1:
                    raise
        raise AssertionError("unreachable")

    def _start_run(self, run_id: int) -> _SourceSnapshot:
        with self._session_factory() as session:
            run = session.get(ResearchRun, run_id)
            if run is None:
                raise ResearchError("research_run_not_found", "The research run does not exist.", 404)
            source = session.get(Source, run.source_id)
            if source is None:
                raise ResearchError("source_not_found", "The requested source does not exist.", 404)
            if run.status not in {"queued", "running"}:
                return _SourceSnapshot(
                    canonical_url=source.canonical_url,
                    platform=source.platform,
                    metadata_json=dict(source.metadata_json),
                )
            run.status = "running"
            run.phase = "collecting"
            run.started_at = run.started_at or utc_now()
            session.commit()
            return _SourceSnapshot(
                canonical_url=source.canonical_url,
                platform=source.platform,
                metadata_json=dict(source.metadata_json),
            )

    def _persist_collection(
        self, run_id: int, collection: CollectionResult
    ) -> tuple[EvidenceInput, ...]:
        with self._session_factory() as session:
            run = _require_run(session, run_id)
            for item in collection.evidence:
                session.add(
                    ResearchEvidence(
                        research_run_id=run.id,
                        source_id=run.source_id,
                        locator=item.locator,
                        kind=item.kind,
                        title=item.title,
                        ordinal=item.ordinal,
                        source_revision=item.source_revision or collection.source_revision,
                        content=item.content,
                        content_sha256=(
                            hashlib.sha256(item.content.encode()).hexdigest()
                            if item.content is not None
                            else None
                        ),
                        status=item.decision,
                        exclusion_reason=item.exclusion_reason,
                    )
                )
            run.coverage_json = dict(collection.coverage)
            run.phase = "summarizing"
            session.commit()
            included = list(
                session.scalars(
                    select(ResearchEvidence)
                    .where(
                        ResearchEvidence.research_run_id == run.id,
                        ResearchEvidence.status == "included",
                    )
                    .order_by(ResearchEvidence.ordinal, ResearchEvidence.id)
                )
            )
            return tuple(
                EvidenceInput(
                    evidence_id=evidence.id,
                    locator=evidence.locator,
                    kind=evidence.kind,
                    title=evidence.title,
                    content=evidence.content or "",
                    source_revision=evidence.source_revision,
                )
                for evidence in included
            )

    def _load_collection_checkpoint(
        self, run_id: int
    ) -> tuple[tuple[EvidenceInput, ...], dict[str, object]] | None:
        with self._session_factory() as session:
            run = _require_run(session, run_id)
            evidence = list(
                session.scalars(
                    select(ResearchEvidence)
                    .where(ResearchEvidence.research_run_id == run.id)
                    .order_by(ResearchEvidence.ordinal, ResearchEvidence.id)
                )
            )
            if not evidence:
                return None
            inputs = tuple(
                EvidenceInput(
                    evidence_id=item.id,
                    locator=item.locator,
                    kind=item.kind,
                    title=item.title,
                    content=item.content or "",
                    source_revision=item.source_revision,
                )
                for item in evidence
                if item.status == "included"
            )
            return inputs, dict(run.coverage_json)

    async def _research_notes(
        self, run_id: int, inputs: tuple[EvidenceInput, ...]
    ) -> tuple[GeneratedResearchNote, ...]:
        self._set_phase(run_id, "summarizing")
        with self._session_factory() as session:
            persisted = {
                evidence.id: GeneratedResearchNote(
                    evidence_id=evidence.id,
                    markdown=evidence.digest_markdown,
                    model_metadata=dict(evidence.digest_model_metadata_json),
                )
                for evidence in session.scalars(
                    select(ResearchEvidence).where(
                        ResearchEvidence.research_run_id == run_id,
                        ResearchEvidence.status == "included",
                        ResearchEvidence.digest_markdown.is_not(None),
                    )
                )
                if evidence.digest_markdown is not None
            }
        notes: list[GeneratedResearchNote] = []
        for evidence in inputs:
            note = persisted.get(evidence.evidence_id)
            if note is None:
                note = await self._ai.research_note(evidence)
                self._persist_note(run_id, evidence.evidence_id, note)
            notes.append(note)
        self._set_phase(run_id, "reporting")
        return tuple(notes)

    def _persist_note(
        self, run_id: int, expected_evidence_id: int, note: GeneratedResearchNote
    ) -> None:
        with self._session_factory() as session:
            evidence = session.get(ResearchEvidence, note.evidence_id)
            if (
                note.evidence_id != expected_evidence_id
                or evidence is None
                or evidence.research_run_id != run_id
                or evidence.status != "included"
            ):
                raise ResearchError(
                    "invalid_note_evidence", "Research note did not match persisted evidence."
                )
            evidence.digest_markdown = note.markdown
            evidence.digest_model_metadata_json = dict(note.model_metadata or {})
            session.commit()

    def _set_phase(self, run_id: int, phase: str) -> None:
        with self._session_factory() as session:
            run = _require_run(session, run_id)
            run.phase = phase
            session.commit()

    def _has_report_checkpoint(self, run_id: int) -> bool:
        with self._session_factory() as session:
            return (
                session.scalar(
                    select(Artifact.id).where(
                        Artifact.research_run_id == run_id,
                        Artifact.kind == "research",
                    )
                )
                is not None
            )

    def _persist_report_checkpoint(
        self, run_id: int, report: GeneratedResearchReport
    ) -> None:
        """Commit a validated report before the independent tag provider request."""
        with self._session_factory() as session:
            run = _require_run(session, run_id)
            existing = session.scalar(
                select(Artifact.id).where(
                    Artifact.research_run_id == run.id,
                    Artifact.kind == "research",
                )
            )
            if existing is not None:
                return
            source = session.get(Source, run.source_id)
            assert source is not None
            evidence = {
                item.id: item
                for item in session.scalars(
                    select(ResearchEvidence).where(
                        ResearchEvidence.research_run_id == run.id,
                        ResearchEvidence.status == "included",
                    )
                )
            }
            tokens = validate_research_report(report.markdown, known_tokens=evidence)
            artifact = Artifact(
                source_id=run.source_id,
                research_run_id=run.id,
                kind="research",
                title=f"{source.title} — 深度研究",
                markdown=report.markdown,
                language="zh",
                model_metadata_json=dict(report.model_metadata),
            )
            session.add(artifact)
            session.flush()
            session.add_all(
                ResearchCitation(
                    artifact_id=artifact.id,
                    evidence_id=evidence[int(token[1:])].id,
                    source_id=run.source_id,
                    token=token,
                )
                for token in tokens
            )
            run.provider_metadata_json = dict(report.model_metadata)
            run.phase = "tagging"
            session.commit()

    def _persist_completion(
        self,
        run_id: int,
        coverage: Mapping[str, object],
        tags: tuple[SuggestedResearchTag, ...],
    ) -> ResearchRun:
        with self._session_factory() as session:
            run = _require_run(session, run_id)
            tag_service = TagService(session)
            for candidate in tags:
                tag_service.suggest(
                    source_id=run.source_id,
                    run_id=run.id,
                    label=candidate.label,
                    confidence=candidate.confidence,
                    evidence_ids=candidate.evidence_ids,
                )
            run.phase = None
            run.status = "completed" if coverage.get("complete") is True else "partial"
            run.finished_at = utc_now()
            session.commit()
            session.refresh(run)
            return run

    def _finish(self, run_id: int, *, status: str, failure_code: str) -> ResearchRun:
        with self._session_factory() as session:
            run = _require_run(session, run_id)
            run.status = status
            run.phase = None
            run.failure_code = failure_code
            run.finished_at = utc_now()
            session.commit()
            session.refresh(run)
            return run


def _require_run(session: Session, run_id: int) -> ResearchRun:
    run = session.get(ResearchRun, run_id)
    if run is None:
        raise ResearchError("research_run_not_found", "The research run does not exist.", 404)
    return run
