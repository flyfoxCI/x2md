"""Persistence invariants for canonical sources and derived artifacts."""

from collections.abc import Generator
from datetime import UTC, datetime
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
from app.models import Artifact, Base, KnowledgeNote, Source


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


def test_auth_models_persist_a_user_and_its_session(session: Session) -> None:
    """Administrator sessions retain only their relation and opaque digest fields."""
    from app import models

    user_model = getattr(models, "User", None)
    auth_session_model = getattr(models, "AuthSession", None)

    assert user_model is not None
    assert auth_session_model is not None

    administrator = user_model(
        username="admin",
        password_hash="argon2id-hash",
        is_active=True,
    )
    session.add(administrator)
    session.flush()
    auth_session = auth_session_model(
        user_id=administrator.id,
        token_hash="a" * 64,
        csrf_token="csrf-token",
        expires_at=datetime(2026, 8, 18, 12, tzinfo=UTC),
    )
    session.add(auth_session)
    session.commit()
    session.expire_all()

    persisted = session.get(auth_session_model, auth_session.id)

    assert persisted is not None
    assert persisted.user.username == "admin"
    assert persisted.user.auth_sessions[0].token_hash == "a" * 64


def test_auth_models_enforce_unique_usernames(session: Session) -> None:
    """The one administrator identity cannot be duplicated."""
    from app import models

    user_model = getattr(models, "User", None)

    assert user_model is not None
    session.add_all(
        [
            user_model(username="admin", password_hash="first", is_active=True),
            user_model(username="admin", password_hash="second", is_active=True),
        ]
    )

    with pytest.raises(exc.IntegrityError):
        session.commit()


def test_auth_session_requires_a_user_and_unique_token_digest(session: Session) -> None:
    """Session bearer digests are unique and always belong to an administrator."""
    from app import models

    user_model = getattr(models, "User", None)
    auth_session_model = getattr(models, "AuthSession", None)

    assert user_model is not None
    assert auth_session_model is not None
    administrator = user_model(username="admin", password_hash="hash", is_active=True)
    session.add(administrator)
    session.flush()
    session.add_all(
        [
            auth_session_model(
                user_id=administrator.id,
                token_hash="a" * 64,
                csrf_token="first-csrf-token",
                expires_at=datetime(2026, 8, 18, 12, tzinfo=UTC),
            ),
            auth_session_model(
                user_id=administrator.id,
                token_hash="a" * 64,
                csrf_token="second-csrf-token",
                expires_at=datetime(2026, 8, 18, 12, tzinfo=UTC),
            ),
        ]
    )

    with pytest.raises(exc.IntegrityError):
        session.commit()

    session.rollback()
    session.add(
        auth_session_model(
            user_id=999,
            token_hash="b" * 64,
            csrf_token="csrf-token",
            expires_at=datetime(2026, 8, 18, 12, tzinfo=UTC),
        )
    )

    with pytest.raises(exc.IntegrityError):
        session.commit()


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
