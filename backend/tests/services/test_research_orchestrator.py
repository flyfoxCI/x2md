"""Research run state-machine and persistence contracts."""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass, field

import pytest
from sqlalchemy import select
from sqlalchemy.orm import Session, sessionmaker

from app.models import (
    Artifact,
    Base,
    ResearchCitation,
    ResearchEvidence,
    ResearchRun,
    Source,
    TagAssignment,
)
from app.services.ai import (
    GeneratedResearchNote,
    GeneratedResearchReport,
    ProviderError,
    SuggestedResearchTag,
)
from app.services.research.contracts import (
    CollectedEvidence,
    CollectionResult,
    EvidenceInput,
)
from app.services.research.orchestrator import ResearchOrchestrator


@dataclass
class FakeCollector:
    result: CollectionResult

    async def collect(self, source: object) -> CollectionResult:
        return self.result


@dataclass
class FakeAI:
    report: str
    tags: tuple[SuggestedResearchTag, ...] = ()
    note_error: ProviderError | None = None

    async def research_note(self, evidence: EvidenceInput) -> GeneratedResearchNote:
        if self.note_error is not None:
            raise self.note_error
        return GeneratedResearchNote(evidence_id=evidence.evidence_id, markdown=f"笔记 {evidence.evidence_id}")

    async def research_report(
        self, *, platform: str, coverage: Mapping[str, object], notes: tuple[GeneratedResearchNote, ...]
    ) -> GeneratedResearchReport:
        return GeneratedResearchReport(markdown=self.report, model_metadata={"model": "fake"})

    async def research_tags(
        self, *, notes: tuple[GeneratedResearchNote, ...]
    ) -> tuple[SuggestedResearchTag, ...]:
        return self.tags


@dataclass
class RepairingFakeAI(FakeAI):
    reports: tuple[str, ...] = ()
    report_calls: int = 0

    async def research_report(
        self, *, platform: str, coverage: Mapping[str, object], notes: tuple[GeneratedResearchNote, ...]
    ) -> GeneratedResearchReport:
        report = self.reports[self.report_calls]
        self.report_calls += 1
        return GeneratedResearchReport(markdown=report, model_metadata={"model": "fake"})


@dataclass
class CountingCollector(FakeCollector):
    calls: int = 0

    async def collect(self, source: object) -> CollectionResult:
        self.calls += 1
        return self.result


@dataclass
class CheckpointFakeAI(FakeAI):
    fail_report_once: bool = False
    fail_second_note_once: bool = False
    fail_tags_once: bool = False
    wrong_note_evidence_id: int | None = None
    note_calls: list[int] = field(default_factory=list)
    report_calls: int = 0
    tag_calls: int = 0

    async def research_note(self, evidence: EvidenceInput) -> GeneratedResearchNote:
        self.note_calls.append(evidence.evidence_id)
        if self.fail_second_note_once and len(self.note_calls) == 2:
            self.fail_second_note_once = False
            raise ProviderError("provider_error", "safe", 502)
        return GeneratedResearchNote(
            evidence_id=self.wrong_note_evidence_id or evidence.evidence_id,
            markdown=f"笔记 {evidence.evidence_id}",
        )

    async def research_report(
        self, *, platform: str, coverage: Mapping[str, object], notes: tuple[GeneratedResearchNote, ...]
    ) -> GeneratedResearchReport:
        self.report_calls += 1
        if self.fail_report_once:
            self.fail_report_once = False
            raise ProviderError("provider_error", "safe", 502)
        return GeneratedResearchReport(
            markdown=_report(f"E{notes[0].evidence_id}"),
            model_metadata={"model": "fake"},
        )

    async def research_tags(
        self, *, notes: tuple[GeneratedResearchNote, ...]
    ) -> tuple[SuggestedResearchTag, ...]:
        self.tag_calls += 1
        if self.fail_tags_once:
            self.fail_tags_once = False
            raise ProviderError("provider_error", "safe", 502)
        return self.tags


def _report(token: str = "E1") -> str:
    return f"""## 研究范围与覆盖率

本次材料范围有限。

## 背景与目标

背景来自公开证据。[{token}]

## 核心贡献

贡献来自公开证据。[{token}]

## 方法或架构

方法来自公开证据。[{token}]

## 实现、实验与配置

实现来自公开证据。[{token}]

## 关键结果

结果来自公开证据。[{token}]

## 局限与风险

局限来自公开证据。[{token}]

## 复现与应用建议

复现来自公开证据。[{token}]

## 标签

- 检索增强生成

## 证据索引

- [{token}] README
"""


@pytest.fixture
def db_factory(tmp_path) -> sessionmaker[Session]:
    from app.db import create_database_engine

    engine = create_database_engine(f"sqlite+pysqlite:///{tmp_path / 'research.db'}")
    Base.metadata.create_all(engine)
    factory = sessionmaker(bind=engine, autoflush=False, expire_on_commit=False)
    with factory() as session:
        session.add(
            Source(
                canonical_url="https://github.com/openai/researcher",
                platform="github",
                title="Researcher",
                raw_text="Original material",
                source_markdown="# Original",
                import_status="ready",
            )
        )
        session.commit()
    try:
        yield factory
    finally:
        engine.dispose()


@pytest.mark.asyncio
async def test_orchestrator_persists_evidence_citations_and_suggested_tags_without_mutating_source(
    db_factory: sessionmaker[Session],
) -> None:
    collector = FakeCollector(
        CollectionResult(
            platform="github",
            source_revision="abc123",
            evidence=(
                CollectedEvidence(
                    locator="github://openai/researcher@abc123/README.md",
                    kind="repository_file",
                    ordinal=0,
                    decision="included",
                    title="README.md",
                    content="Grounded project evidence.",
                    source_revision="abc123",
                ),
                CollectedEvidence(
                    locator="github://openai/researcher@abc123/model.bin",
                    kind="repository_file",
                    ordinal=1,
                    decision="excluded",
                    title="model.bin",
                    source_revision="abc123",
                    exclusion_reason="binary_or_unsupported",
                ),
            ),
            coverage={"complete": False, "reason": "material_excluded"},
        )
    )
    ai = FakeAI(
        _report(),
        tags=(SuggestedResearchTag("检索增强生成", 0.9, (1,)),),
    )
    service = ResearchOrchestrator(db_factory, collectors={"github": collector}, ai=ai)

    queued = service.enqueue(1, trigger="manual")
    completed = await service.execute(queued.id)

    assert completed.status == "partial", completed.failure_code
    with db_factory() as session:
        source = session.get(Source, 1)
        run = session.get(ResearchRun, queued.id)
        evidence = list(session.scalars(select(ResearchEvidence).where(ResearchEvidence.research_run_id == queued.id)))
        artifact = session.scalar(select(Artifact).where(Artifact.research_run_id == queued.id))
        citations = list(session.scalars(select(ResearchCitation)))
        tag = session.scalar(select(TagAssignment).where(TagAssignment.research_run_id == queued.id))

    assert source is not None and source.raw_text == "Original material"
    assert run is not None and run.coverage_json["complete"] is False
    assert len(evidence) == 2
    assert artifact is not None and artifact.kind == "research"
    assert [citation.token for citation in citations] == ["E1"]
    assert tag is not None and tag.status == "suggested"


@pytest.mark.asyncio
async def test_orchestrator_blocks_an_unconfigured_provider_without_creating_a_report(
    db_factory: sessionmaker[Session],
) -> None:
    collector = FakeCollector(
        CollectionResult(
            platform="github",
            source_revision="abc123",
            evidence=(
                CollectedEvidence(
                    locator="github://openai/researcher@abc123/README.md",
                    kind="repository_file",
                    ordinal=0,
                    decision="included",
                    content="Grounded project evidence.",
                ),
            ),
            coverage={"complete": True},
        )
    )
    ai = FakeAI(
        _report(),
        note_error=ProviderError("provider_not_configured", "safe", 422),
    )
    service = ResearchOrchestrator(db_factory, collectors={"github": collector}, ai=ai)

    queued = service.enqueue(1, trigger="manual")
    result = await service.execute(queued.id)

    assert result.status == "blocked", result.failure_code
    with db_factory() as session:
        assert session.scalar(select(Artifact).where(Artifact.research_run_id == queued.id)) is None


@pytest.mark.asyncio
async def test_orchestrator_replaces_collected_evidence_when_retrying_the_same_run(
    db_factory: sessionmaker[Session],
) -> None:
    collector = FakeCollector(
        CollectionResult(
            platform="github",
            source_revision="abc123",
            evidence=(
                CollectedEvidence(
                    locator="github://openai/researcher@abc123/README.md",
                    kind="repository_file",
                    ordinal=0,
                    decision="included",
                    content="Grounded project evidence.",
                ),
            ),
            coverage={"complete": True},
        )
    )
    ai = FakeAI(_report(), note_error=ProviderError("provider_error", "safe", 502))
    service = ResearchOrchestrator(db_factory, collectors={"github": collector}, ai=ai)
    queued = service.enqueue(1, trigger="manual")

    first = await service.execute(queued.id)
    ai.note_error = None
    second = await service.execute(queued.id)

    assert first.status == "failed"
    assert second.status == "completed", second.failure_code
    with db_factory() as session:
        evidence = list(
            session.scalars(
                select(ResearchEvidence).where(ResearchEvidence.research_run_id == queued.id)
            )
        )
    assert len(evidence) == 1


@pytest.mark.asyncio
async def test_orchestrator_regenerates_one_invalid_report_before_failing_the_run(
    db_factory: sessionmaker[Session],
) -> None:
    collector = FakeCollector(
        CollectionResult(
            platform="github",
            source_revision="abc123",
            evidence=(
                CollectedEvidence(
                    locator="github://openai/researcher@abc123/README.md",
                    kind="repository_file",
                    ordinal=0,
                    decision="included",
                    content="Grounded project evidence.",
                ),
            ),
            coverage={"complete": True},
        )
    )
    ai = RepairingFakeAI(report="", reports=(_report("E99"), _report("E1")))
    service = ResearchOrchestrator(db_factory, collectors={"github": collector}, ai=ai)

    result = await service.execute(service.enqueue(1, trigger="manual").id)

    assert result.status == "completed", result.failure_code
    assert ai.report_calls == 2


@pytest.mark.asyncio
async def test_orchestrator_resumes_at_report_without_recollecting_or_redigesting(
    db_factory: sessionmaker[Session],
) -> None:
    collector = CountingCollector(
        CollectionResult(
            platform="github",
            source_revision="abc123",
            evidence=(
                CollectedEvidence(
                    locator="github://openai/researcher@abc123/README.md",
                    kind="repository_file",
                    ordinal=0,
                    decision="included",
                    content="Grounded project evidence.",
                ),
            ),
            coverage={"complete": True},
        )
    )
    ai = CheckpointFakeAI(report="", fail_report_once=True)
    service = ResearchOrchestrator(db_factory, collectors={"github": collector}, ai=ai)
    queued = service.enqueue(1, trigger="manual")

    first = await service.execute(queued.id)
    second = await service.execute(queued.id)

    assert first.status == "failed" and first.failure_code == "provider_error"
    assert second.status == "completed", second.failure_code
    assert collector.calls == 1
    assert len(ai.note_calls) == 1
    assert ai.report_calls == 2


@pytest.mark.asyncio
async def test_orchestrator_persists_each_note_and_resumes_only_missing_notes(
    db_factory: sessionmaker[Session],
) -> None:
    collector = CountingCollector(
        CollectionResult(
            platform="github",
            source_revision="abc123",
            evidence=tuple(
                CollectedEvidence(
                    locator=f"github://openai/researcher@abc123/file-{ordinal}.md",
                    kind="repository_file",
                    ordinal=ordinal,
                    decision="included",
                    content=f"Grounded evidence {ordinal}.",
                )
                for ordinal in range(2)
            ),
            coverage={"complete": True},
        )
    )
    ai = CheckpointFakeAI(report="", fail_second_note_once=True)
    service = ResearchOrchestrator(db_factory, collectors={"github": collector}, ai=ai)
    queued = service.enqueue(1, trigger="manual")

    first = await service.execute(queued.id)
    with db_factory() as session:
        saved_after_failure = session.scalar(
            select(ResearchEvidence).where(ResearchEvidence.digest_markdown.is_not(None))
        )
    second = await service.execute(queued.id)

    assert first.status == "failed" and first.failure_code == "provider_error"
    assert saved_after_failure is not None
    assert second.status == "completed", second.failure_code
    assert collector.calls == 1
    assert len(ai.note_calls) == 3


@pytest.mark.asyncio
async def test_orchestrator_checkpoints_report_before_retrying_failed_tags(
    db_factory: sessionmaker[Session],
) -> None:
    collector = CountingCollector(
        CollectionResult(
            platform="github",
            source_revision="abc123",
            evidence=(
                CollectedEvidence(
                    locator="github://openai/researcher@abc123/README.md",
                    kind="repository_file",
                    ordinal=0,
                    decision="included",
                    content="Grounded project evidence.",
                ),
            ),
            coverage={"complete": True},
        )
    )
    ai = CheckpointFakeAI(report="", fail_tags_once=True)
    service = ResearchOrchestrator(db_factory, collectors={"github": collector}, ai=ai)
    queued = service.enqueue(1, trigger="manual")

    first = await service.execute(queued.id)
    with db_factory() as session:
        reports_after_failure = list(
            session.scalars(select(Artifact).where(Artifact.research_run_id == queued.id))
        )
    second = await service.execute(queued.id)
    with db_factory() as session:
        reports_after_retry = list(
            session.scalars(select(Artifact).where(Artifact.research_run_id == queued.id))
        )

    assert first.status == "failed" and first.failure_code == "provider_error"
    assert len(reports_after_failure) == 1
    assert second.status == "completed", second.failure_code
    assert collector.calls == 1
    assert len(ai.note_calls) == 1
    assert ai.report_calls == 1
    assert ai.tag_calls == 2
    assert len(reports_after_retry) == 1


@pytest.mark.asyncio
async def test_orchestrator_rejects_a_note_bound_to_different_evidence(
    db_factory: sessionmaker[Session],
) -> None:
    collector = FakeCollector(
        CollectionResult(
            platform="github",
            source_revision="abc123",
            evidence=tuple(
                CollectedEvidence(
                    locator=f"github://openai/researcher@abc123/file-{ordinal}.md",
                    kind="repository_file",
                    ordinal=ordinal,
                    decision="included",
                    content=f"Grounded project evidence {ordinal}.",
                )
                for ordinal in range(2)
            ),
            coverage={"complete": True},
        )
    )
    # SQLite assigns IDs 1 and 2 in this isolated database. The first model
    # response is deliberately bound to the other included row in the same run.
    ai = CheckpointFakeAI(report="", wrong_note_evidence_id=2)
    service = ResearchOrchestrator(db_factory, collectors={"github": collector}, ai=ai)

    queued = service.enqueue(1, trigger="manual")
    result = await service.execute(queued.id)

    assert result.status == "failed"
    assert result.failure_code == "research_processing_error"
    with db_factory() as session:
        evidence = list(session.scalars(
            select(ResearchEvidence).where(ResearchEvidence.research_run_id == queued.id)
        ))
    assert evidence and all(item.digest_markdown is None for item in evidence)


@pytest.mark.asyncio
async def test_orchestrator_rejects_invalid_citations_and_keeps_accepted_tags(
    db_factory: sessionmaker[Session],
) -> None:
    collector = FakeCollector(
        CollectionResult(
            platform="github",
            source_revision="abc123",
            evidence=(
                CollectedEvidence(
                    locator="github://openai/researcher@abc123/README.md",
                    kind="repository_file",
                    ordinal=0,
                    decision="included",
                    content="Grounded project evidence.",
                ),
            ),
            coverage={"complete": True},
        )
    )
    valid_ai = FakeAI(_report(), tags=(SuggestedResearchTag("智能体", 0.8, (1,)),))
    service = ResearchOrchestrator(db_factory, collectors={"github": collector}, ai=valid_ai)
    first = service.enqueue(1, trigger="manual")
    await service.execute(first.id)
    with db_factory() as session:
        assignment = session.scalar(select(TagAssignment).where(TagAssignment.research_run_id == first.id))
        assert assignment is not None
        assignment.status = "accepted"
        session.commit()

    invalid = ResearchOrchestrator(
        db_factory,
        collectors={"github": collector},
        ai=FakeAI(_report("E99")),
    )
    queued = invalid.enqueue(1, trigger="manual")
    result = await invalid.execute(queued.id)

    assert result.status == "failed"
    assert result.failure_code == "invalid_citation"
    with db_factory() as session:
        accepted = list(session.scalars(select(TagAssignment).where(TagAssignment.status == "accepted")))
        reports = list(session.scalars(select(Artifact).where(Artifact.research_run_id == queued.id)))
    assert len(accepted) == 1
    assert reports == []
