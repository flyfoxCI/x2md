"""Persistence invariants for canonical sources and derived artifacts."""

from collections.abc import Generator
from pathlib import Path

import pytest
from alembic.autogenerate import compare_metadata
from alembic.config import Config
from alembic.migration import MigrationContext
from sqlalchemy import exc
from sqlalchemy.dialects import postgresql
from sqlalchemy.engine import make_url
from sqlalchemy.orm import Session
from sqlalchemy.schema import CreateTable

from alembic import command
from app.config import Settings
from app.db import create_database_engine
from app.models import (
    Artifact,
    Base,
    KnowledgeNote,
    ResearchCitation,
    ResearchEvidence,
    ResearchRun,
    Source,
    TagAssignment,
    TagAssignmentEvidence,
    TagDefinition,
)


@pytest.fixture
def session() -> Generator[Session, None, None]:
    """Provide an isolated temporary SQLite database for each test."""
    engine = create_database_engine("sqlite+pysqlite:///:memory:")
    Base.metadata.create_all(engine)
    with Session(engine) as database_session:
        yield database_session
    engine.dispose()


def test_persists_canonical_source(session: Session) -> None:
    source = Source(
        canonical_url="https://example.com/reasoning",
        platform="web",
        title="Reasoning at Scale",
        author="Ada Lovelace",
        raw_text="Canonical source material.",
        source_markdown="# Reasoning at Scale",
        metadata_json={"canonical_url": "https://example.com/reasoning"},
        import_status="ready",
    )

    session.add(source)
    session.commit()
    session.expire_all()

    persisted = session.get(Source, source.id)
    assert persisted is not None
    assert persisted.canonical_url == "https://example.com/reasoning"
    assert persisted.raw_text == "Canonical source material."
    assert persisted.metadata_json == {
        "canonical_url": "https://example.com/reasoning"
    }


def test_user_edit_artifact_preserves_source_and_parent_lineage(
    session: Session,
) -> None:
    source = Source(
        canonical_url="https://example.com/reasoning",
        platform="web",
        title="Reasoning at Scale",
        raw_text="Original, immutable source material.",
        source_markdown="# Original",
        metadata_json={},
        import_status="ready",
    )
    generated = Artifact(
        source=source,
        kind="summary",
        title="Knowledge summary",
        markdown="# Summary\n\nGenerated from the source.",
        language="en",
        model_metadata_json={"provider": "test"},
    )
    session.add_all([source, generated])
    session.flush()

    user_edit = Artifact(
        source_id=source.id,
        kind="user_edit",
        title="Knowledge summary (edited)",
        markdown="# Summary\n\nAn intentional user edit.",
        language="en",
        parent_artifact_id=generated.id,
        model_metadata_json={},
    )
    session.add(user_edit)
    session.commit()
    session.expire_all()

    persisted_source = session.get(Source, source.id)
    persisted_generated = session.get(Artifact, generated.id)
    persisted_user_edit = session.get(Artifact, user_edit.id)

    assert persisted_source is not None
    assert persisted_source.raw_text == "Original, immutable source material."
    assert persisted_generated is not None
    assert persisted_user_edit is not None
    assert persisted_generated.source_id == persisted_source.id
    assert persisted_user_edit.source_id == persisted_source.id
    assert persisted_user_edit.parent_artifact_id == persisted_generated.id


def test_database_engine_uses_psycopg_for_bare_postgresql_urls() -> None:
    engine = create_database_engine("postgresql://user:password@db.example.test/content")

    assert engine.url.drivername == "postgresql+psycopg"


def test_database_engine_preserves_explicit_postgresql_driver() -> None:
    engine = create_database_engine(
        "postgresql+psycopg://user:password@db.example.test/content"
    )

    assert engine.url.drivername == "postgresql+psycopg"


def test_models_compile_json_for_postgresql() -> None:
    ddl = str(CreateTable(Source.__table__).compile(dialect=postgresql.dialect()))

    assert "metadata_json JSON" in ddl


def test_artifact_requires_an_existing_source(session: Session) -> None:
    orphan = Artifact(
        source_id=999,
        kind="summary",
        title="Orphaned artifact",
        markdown="# Orphaned",
        model_metadata_json={},
    )
    session.add(orphan)

    with pytest.raises(exc.IntegrityError):
        session.commit()


def test_artifact_parent_must_belong_to_the_same_source(session: Session) -> None:
    parent_source = Source(
        canonical_url="https://example.com/parent",
        platform="web",
        title="Parent source",
        raw_text="Parent source text.",
        source_markdown="# Parent",
        metadata_json={},
        import_status="ready",
    )
    child_source = Source(
        canonical_url="https://example.com/child",
        platform="web",
        title="Child source",
        raw_text="Child source text.",
        source_markdown="# Child",
        metadata_json={},
        import_status="ready",
    )
    parent = Artifact(
        source=parent_source,
        kind="summary",
        title="Parent summary",
        markdown="# Parent summary",
        model_metadata_json={},
    )
    session.add_all([parent_source, child_source, parent])
    session.flush()

    cross_source_child = Artifact(
        source_id=child_source.id,
        kind="user_edit",
        title="Invalid child",
        markdown="# Invalid child",
        parent_artifact_id=parent.id,
        model_metadata_json={},
    )
    session.add(cross_source_child)

    with pytest.raises(exc.IntegrityError):
        session.commit()


def test_knowledge_note_artifact_must_belong_to_the_same_source(session: Session) -> None:
    artifact_source = Source(
        canonical_url="https://example.com/artifact-source",
        platform="web",
        title="Artifact source",
        raw_text="Artifact source text.",
        source_markdown="# Artifact source",
        metadata_json={},
        import_status="ready",
    )
    note_source = Source(
        canonical_url="https://example.com/note-source",
        platform="web",
        title="Note source",
        raw_text="Note source text.",
        source_markdown="# Note source",
        metadata_json={},
        import_status="ready",
    )
    artifact = Artifact(
        source=artifact_source,
        kind="summary",
        title="Artifact summary",
        markdown="# Artifact summary",
        model_metadata_json={},
    )
    session.add_all([artifact_source, note_source, artifact])
    session.flush()

    cross_source_note = KnowledgeNote(
        source_id=note_source.id,
        artifact_id=artifact.id,
        tags_json=[],
    )
    session.add(cross_source_note)

    with pytest.raises(exc.IntegrityError):
        session.commit()


def test_knowledge_note_can_reference_source_without_an_artifact(session: Session) -> None:
    source = Source(
        canonical_url="https://example.com/note-only",
        platform="web",
        title="Note-only source",
        raw_text="Note-only source text.",
        source_markdown="# Note-only source",
        metadata_json={},
        import_status="ready",
    )
    note = KnowledgeNote(source=source, tags_json=["inbox"])
    session.add_all([source, note])

    session.commit()

    assert note.id is not None
    assert note.artifact_id is None


def test_settings_repr_hides_database_url_password(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("DATABASE_URL", "postgresql://user:not-a-real-secret@db.example.test/content")

    assert "not-a-real-secret" not in repr(Settings())


def test_initial_migration_matches_model_metadata(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    database_path = tmp_path / "migration-parity.db"
    database_url = f"sqlite:///{database_path}"
    monkeypatch.setenv("DATABASE_URL", database_url)
    alembic_config = Config(str(Path(__file__).parents[1] / "alembic.ini"))

    command.upgrade(alembic_config, "head")

    engine = create_database_engine(database_url)
    with engine.connect() as connection:
        context = MigrationContext.configure(connection)
        assert compare_metadata(context, Base.metadata) == []
    engine.dispose()


class ConnectionIntercepted(Exception):
    """Stops the Alembic test before it can open a PostgreSQL connection."""


class _ConnectionInterceptingEngine:
    def connect(self) -> None:
        raise ConnectionIntercepted


def test_alembic_normalizes_bare_postgresql_url_before_connecting(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    captured: dict[str, str] = {}

    def capture_engine(url: str, **_: object) -> _ConnectionInterceptingEngine:
        captured["url"] = url
        return _ConnectionInterceptingEngine()

    monkeypatch.setenv(
        "DATABASE_URL", "postgresql://user:password@db.example.test/content"
    )
    monkeypatch.setattr("sqlalchemy.engine.create.create_engine", capture_engine)
    alembic_config = Config(str(Path(__file__).parents[1] / "alembic.ini"))

    with pytest.raises(ConnectionIntercepted):
        command.upgrade(alembic_config, "head")

    normalized_url = make_url(captured["url"])
    assert normalized_url.drivername == "postgresql+psycopg"
    assert normalized_url.password == "password"


def test_alembic_preserves_percent_encoded_postgresql_password_before_connecting(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    captured: dict[str, str] = {}

    def capture_engine(url: str, **_: object) -> _ConnectionInterceptingEngine:
        captured["url"] = url
        return _ConnectionInterceptingEngine()

    monkeypatch.setenv(
        "DATABASE_URL", "postgresql://user:password%40with-symbol@db.example.test/content"
    )
    monkeypatch.setattr("sqlalchemy.engine.create.create_engine", capture_engine)
    alembic_config = Config(str(Path(__file__).parents[1] / "alembic.ini"))

    with pytest.raises(ConnectionIntercepted):
        command.upgrade(alembic_config, "head")

    normalized_url = make_url(captured["url"])
    assert normalized_url.drivername == "postgresql+psycopg"
    assert normalized_url.password == "password@with-symbol"


def test_research_records_preserve_source_lineage_and_evidence_links(
    session: Session,
) -> None:
    source = Source(
        canonical_url="https://github.com/example/researchable",
        platform="github",
        title="Researchable repository",
        raw_text="# README",
        source_markdown="# README",
        metadata_json={},
        import_status="ready",
    )
    run = ResearchRun(
        source=source,
        trigger="manual",
        status="completed",
        budget_json={"max_files": 20},
        coverage_json={"included": 1, "excluded": 0},
        attempt_count=1,
        max_attempts=2,
    )
    session.add_all([source, run])
    session.flush()

    evidence = ResearchEvidence(
        research_run_id=run.id,
        source_id=source.id,
        locator="github://example/researchable@abc123/README.md#L1-L1",
        kind="markdown",
        title="README.md",
        ordinal=1,
        source_revision="abc123",
        content="# README",
        content_sha256="a" * 64,
        status="included",
    )
    report = Artifact(
        source_id=source.id,
        research_run_id=run.id,
        kind="research",
        title="研究档案",
        markdown="# 研究档案\n\n结论 [E1]",
        language="zh",
        model_metadata_json={},
    )
    tag = TagDefinition(
        slug="method-transformer",
        label="Transformer",
        facet="method",
        is_system=True,
    )
    session.add_all([evidence, report, tag])
    session.flush()

    citation = ResearchCitation(
        artifact_id=report.id,
        evidence_id=evidence.id,
        source_id=source.id,
        token="E1",
    )
    assignment = TagAssignment(
        source_id=source.id,
        research_run_id=run.id,
        tag_id=tag.id,
        origin="ai",
        status="suggested",
        confidence=0.91,
    )
    session.add_all([citation, assignment])
    session.flush()
    assignment_evidence = TagAssignmentEvidence(
        tag_assignment_id=assignment.id,
        evidence_id=evidence.id,
        source_id=source.id,
    )
    session.add(assignment_evidence)
    session.commit()

    assert report.research_run_id == run.id
    assert citation.evidence_id == evidence.id
    assert assignment_evidence.tag_assignment_id == assignment.id
    assert source.raw_text == "# README"


def test_research_citation_rejects_artifact_and_evidence_from_different_sources(
    session: Session,
) -> None:
    first_source = Source(
        canonical_url="https://example.com/first-research",
        platform="web",
        title="First source",
        raw_text="First",
        source_markdown="# First",
        metadata_json={},
        import_status="ready",
    )
    second_source = Source(
        canonical_url="https://example.com/second-research",
        platform="web",
        title="Second source",
        raw_text="Second",
        source_markdown="# Second",
        metadata_json={},
        import_status="ready",
    )
    first_run = ResearchRun(
        source=first_source,
        trigger="manual",
        status="completed",
        budget_json={},
        coverage_json={},
    )
    second_run = ResearchRun(
        source=second_source,
        trigger="manual",
        status="completed",
        budget_json={},
        coverage_json={},
    )
    session.add_all([first_source, second_source, first_run, second_run])
    session.flush()
    report = Artifact(
        source_id=first_source.id,
        research_run_id=first_run.id,
        kind="research",
        title="First report",
        markdown="# First report",
        model_metadata_json={},
    )
    evidence = ResearchEvidence(
        research_run_id=second_run.id,
        source_id=second_source.id,
        locator="web://second#1",
        kind="text",
        ordinal=1,
        status="included",
    )
    session.add_all([report, evidence])
    session.flush()
    session.add(
        ResearchCitation(
            artifact_id=report.id,
            evidence_id=evidence.id,
            source_id=first_source.id,
            token="E1",
        )
    )

    with pytest.raises(exc.IntegrityError):
        session.commit()


def test_research_run_allows_only_one_active_run_for_a_source(session: Session) -> None:
    source = Source(
        canonical_url="https://example.com/one-active-run",
        platform="web",
        title="One active run",
        raw_text="Source",
        source_markdown="# Source",
        metadata_json={},
        import_status="ready",
    )
    session.add(source)
    session.flush()
    session.add_all(
        [
            ResearchRun(
                source_id=source.id,
                trigger="manual",
                status="queued",
                budget_json={},
                coverage_json={},
            ),
            ResearchRun(
                source_id=source.id,
                trigger="automatic",
                status="running",
                budget_json={},
                coverage_json={},
            ),
        ]
    )

    with pytest.raises(exc.IntegrityError):
        session.commit()


def test_deep_research_migration_converts_legacy_note_tags(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    database_path = tmp_path / "legacy-tags.db"
    database_url = f"sqlite:///{database_path}"
    monkeypatch.setenv("DATABASE_URL", database_url)
    alembic_config = Config(str(Path(__file__).parents[1] / "alembic.ini"))
    command.upgrade(alembic_config, "0001_initial_schema")

    engine = create_database_engine(database_url)
    with engine.begin() as connection:
        connection.exec_driver_sql(
            """
            INSERT INTO sources (
                canonical_url, platform, title, raw_text, source_markdown,
                metadata_json, import_status, created_at, updated_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, CURRENT_TIMESTAMP, CURRENT_TIMESTAMP)
            """,
            (
                "https://example.com/legacy-tags",
                "web",
                "Legacy tags",
                "Source",
                "# Source",
                "{}",
                "ready",
            ),
        )
        connection.exec_driver_sql(
            """
            INSERT INTO knowledge_notes (
                source_id, artifact_id, tags_json, pinned, created_at, updated_at
            ) VALUES (?, NULL, ?, ?, CURRENT_TIMESTAMP, CURRENT_TIMESTAMP)
            """,
            (1, '["RAG", "rag", "agents"]', 0),
        )
    engine.dispose()

    command.upgrade(alembic_config, "head")
    engine = create_database_engine(database_url)
    with Session(engine) as migrated:
        definitions = list(migrated.query(TagDefinition).order_by(TagDefinition.slug))
        assignments = list(migrated.query(TagAssignment).order_by(TagAssignment.id))

    engine.dispose()

    assert [(tag.label, tag.facet, tag.is_system) for tag in definitions] == [
        ("agents", None, False),
        ("RAG", None, False),
    ]
    assert [(assignment.origin, assignment.status) for assignment in assignments] == [
        ("user", "accepted"),
        ("user", "accepted"),
    ]
