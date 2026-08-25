"""Research run state-machine and persistence contracts."""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass

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
