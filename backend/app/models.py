"""SQLAlchemy persistence shape for sources and their derived knowledge."""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any

from sqlalchemy import (
    JSON,
    Boolean,
    CheckConstraint,
    DateTime,
    ForeignKey,
    ForeignKeyConstraint,
    Index,
    String,
    Text,
    UniqueConstraint,
    text,
)
from sqlalchemy.orm import (
    DeclarativeBase,
    Mapped,
    mapped_column,
    relationship,
    validates,
)


def utc_now() -> datetime:
    """Return a timezone-aware timestamp suitable for persistence defaults."""
    return datetime.now(UTC)


class Base(DeclarativeBase):
    """Declarative metadata owner for database migrations."""


ADMIN_SINGLETON_MARKER = "administrator"


class User(Base):
    """The single administrator account used to protect the knowledge library."""

    __tablename__ = "users"
    __table_args__ = (
        CheckConstraint(
            f"singleton_marker = '{ADMIN_SINGLETON_MARKER}'",
            name="ck_users_singleton_marker",
        ),
        UniqueConstraint("singleton_marker", name="uq_users_singleton_marker"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    username: Mapped[str] = mapped_column(String(128), unique=True, index=True)
    singleton_marker: Mapped[str] = mapped_column(
        String(32),
        nullable=False,
        default=ADMIN_SINGLETON_MARKER,
        server_default=text(f"'{ADMIN_SINGLETON_MARKER}'"),
    )
    password_hash: Mapped[str] = mapped_column(String(1024))
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utc_now, onupdate=utc_now
    )

    auth_sessions: Mapped[list[AuthSession]] = relationship(
        back_populates="user", cascade="all, delete-orphan"
    )

    @validates("singleton_marker")
    def validate_singleton_marker(self, _: str, value: str) -> str:
        """Prevent model callers from selecting another administrator slot."""
        if value != ADMIN_SINGLETON_MARKER:
            raise ValueError("singleton_marker must use the administrator marker")
        return value


class AuthSession(Base):
    """A revocable opaque browser session whose raw token is never persisted."""

    __tablename__ = "auth_sessions"

    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), index=True
    )
    token_hash: Mapped[str] = mapped_column(String(64), unique=True, index=True)
    csrf_token: Mapped[str] = mapped_column(String(128))
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), index=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utc_now, onupdate=utc_now
    )

    user: Mapped[User] = relationship(back_populates="auth_sessions")


class Source(Base):
    """Canonical, imported source material and provenance."""

    __tablename__ = "sources"

    id: Mapped[int] = mapped_column(primary_key=True)
    canonical_url: Mapped[str] = mapped_column(String(2048), unique=True)
    platform: Mapped[str] = mapped_column(String(64), index=True)
    title: Mapped[str] = mapped_column(String(512))
    author: Mapped[str | None] = mapped_column(String(512), nullable=True)
    published_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    raw_text: Mapped[str] = mapped_column(Text)
    source_markdown: Mapped[str] = mapped_column(Text)
    metadata_json: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict)
    import_status: Mapped[str] = mapped_column(String(32), index=True)
    failure_reason: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utc_now, onupdate=utc_now
    )

    artifacts: Mapped[list[Artifact]] = relationship(
        back_populates="source", cascade="all, delete-orphan"
    )
    knowledge_notes: Mapped[list[KnowledgeNote]] = relationship(back_populates="source")
    chat_turns: Mapped[list[ChatTurn]] = relationship(back_populates="source")
    research_runs: Mapped[list[ResearchRun]] = relationship(
        back_populates="source", cascade="all, delete-orphan"
    )
    tag_assignments: Mapped[list[TagAssignment]] = relationship(
        back_populates="source", cascade="all, delete-orphan"
    )


class Artifact(Base):
    """An append-only, source-scoped generated or user-edited document version."""

    __tablename__ = "artifacts"
    __table_args__ = (
        UniqueConstraint("id", "source_id", name="uq_artifacts_id_source_id"),
        ForeignKeyConstraint(
            ["parent_artifact_id", "source_id"],
            ["artifacts.id", "artifacts.source_id"],
            name="fk_artifacts_parent_same_source",
        ),
        ForeignKeyConstraint(
            ["research_run_id", "source_id"],
            ["research_runs.id", "research_runs.source_id"],
            name="fk_artifacts_research_run_same_source",
        ),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    source_id: Mapped[int] = mapped_column(ForeignKey("sources.id"), index=True)
    kind: Mapped[str] = mapped_column(String(32), index=True)
    title: Mapped[str] = mapped_column(String(512))
    markdown: Mapped[str] = mapped_column(Text)
    language: Mapped[str | None] = mapped_column(String(32), nullable=True)
    parent_artifact_id: Mapped[int | None] = mapped_column(nullable=True, index=True)
    research_run_id: Mapped[int | None] = mapped_column(nullable=True, index=True)
    model_metadata_json: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utc_now, onupdate=utc_now
    )

    source: Mapped[Source] = relationship(back_populates="artifacts")


class KnowledgeNote(Base):
    """Library-level metadata that references, rather than duplicates, content."""

    __tablename__ = "knowledge_notes"
    __table_args__ = (
        ForeignKeyConstraint(
            ["artifact_id", "source_id"],
            ["artifacts.id", "artifacts.source_id"],
            name="fk_knowledge_notes_artifact_same_source",
        ),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    source_id: Mapped[int] = mapped_column(ForeignKey("sources.id"), index=True)
    artifact_id: Mapped[int | None] = mapped_column(nullable=True, index=True)
    tags_json: Mapped[list[str]] = mapped_column(JSON, default=list)
    pinned: Mapped[bool] = mapped_column(Boolean, default=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utc_now, onupdate=utc_now
    )

    source: Mapped[Source] = relationship(back_populates="knowledge_notes")


class ChatTurn(Base):
    """A source-scoped answer and its traceable citations."""

    __tablename__ = "chat_turns"

    id: Mapped[int] = mapped_column(primary_key=True)
    source_id: Mapped[int] = mapped_column(ForeignKey("sources.id"), index=True)
    question: Mapped[str] = mapped_column(Text)
    answer_markdown: Mapped[str] = mapped_column(Text)
    citations_json: Mapped[list[dict[str, Any]]] = mapped_column(JSON, default=list)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now)

    source: Mapped[Source] = relationship(back_populates="chat_turns")


class AppSetting(Base):
    """Non-secret application setting stored by key."""

    __tablename__ = "app_settings"

    key: Mapped[str] = mapped_column(String(128), primary_key=True)
    value_json: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utc_now, onupdate=utc_now
    )


class ResearchRun(Base):
    """One bounded, durable attempt to study a canonical source."""

    __tablename__ = "research_runs"
    __table_args__ = (
        UniqueConstraint("id", "source_id", name="uq_research_runs_id_source_id"),
        Index(
            "uq_research_runs_one_active_per_source",
            "source_id",
            unique=True,
            sqlite_where=text("status IN ('queued', 'running')"),
            postgresql_where=text("status IN ('queued', 'running')"),
        ),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    source_id: Mapped[int] = mapped_column(ForeignKey("sources.id"), index=True)
    trigger: Mapped[str] = mapped_column(String(16))
    status: Mapped[str] = mapped_column(String(16), index=True)
    phase: Mapped[str | None] = mapped_column(String(32), nullable=True)
    budget_json: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict)
    coverage_json: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict)
    attempt_count: Mapped[int] = mapped_column(default=0)
    max_attempts: Mapped[int] = mapped_column(default=2)
    next_attempt_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True, index=True
    )
    lease_owner: Mapped[str | None] = mapped_column(String(128), nullable=True)
    lease_expires_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True, index=True
    )
    failure_code: Mapped[str | None] = mapped_column(String(64), nullable=True)
    provider_metadata_json: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict)
    started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    finished_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utc_now, onupdate=utc_now
    )

    source: Mapped[Source] = relationship(back_populates="research_runs")


class ResearchEvidence(Base):
    """Included or excluded material discovered during one research run."""

    __tablename__ = "research_evidence"
    __table_args__ = (
        ForeignKeyConstraint(
            ["research_run_id", "source_id"],
            ["research_runs.id", "research_runs.source_id"],
            name="fk_research_evidence_run_same_source",
        ),
        UniqueConstraint("id", "source_id", name="uq_research_evidence_id_source_id"),
        UniqueConstraint("research_run_id", "locator", name="uq_research_evidence_run_locator"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    research_run_id: Mapped[int] = mapped_column(index=True)
    source_id: Mapped[int] = mapped_column(index=True)
    locator: Mapped[str] = mapped_column(String(4096))
    kind: Mapped[str] = mapped_column(String(32))
    title: Mapped[str | None] = mapped_column(String(512), nullable=True)
    ordinal: Mapped[int] = mapped_column()
    source_revision: Mapped[str | None] = mapped_column(String(256), nullable=True)
    content: Mapped[str | None] = mapped_column(Text, nullable=True)
    content_sha256: Mapped[str | None] = mapped_column(String(64), nullable=True)
    digest_markdown: Mapped[str | None] = mapped_column(Text, nullable=True)
    digest_model_metadata_json: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict)
    status: Mapped[str] = mapped_column(String(16), index=True)
    exclusion_reason: Mapped[str | None] = mapped_column(String(64), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now)


class ResearchCitation(Base):
    """A report citation that cannot cross a source boundary."""

    __tablename__ = "research_citations"
    __table_args__ = (
        ForeignKeyConstraint(
            ["artifact_id", "source_id"],
            ["artifacts.id", "artifacts.source_id"],
            name="fk_research_citations_artifact_same_source",
        ),
        ForeignKeyConstraint(
            ["evidence_id", "source_id"],
            ["research_evidence.id", "research_evidence.source_id"],
            name="fk_research_citations_evidence_same_source",
        ),
        UniqueConstraint("artifact_id", "token", name="uq_research_citations_artifact_token"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    artifact_id: Mapped[int] = mapped_column(index=True)
    evidence_id: Mapped[int] = mapped_column(index=True)
    source_id: Mapped[int] = mapped_column(index=True)
    token: Mapped[str] = mapped_column(String(32))
    paragraph_anchor: Mapped[str | None] = mapped_column(String(128), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now)


class TagDefinition(Base):
    """One controlled or user-defined label in the research taxonomy."""

    __tablename__ = "tag_definitions"
    __table_args__ = (UniqueConstraint("slug", name="uq_tag_definitions_slug"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    slug: Mapped[str] = mapped_column(String(160))
    label: Mapped[str] = mapped_column(String(160))
    facet: Mapped[str | None] = mapped_column(String(32), nullable=True, index=True)
    parent_id: Mapped[int | None] = mapped_column(
        ForeignKey("tag_definitions.id"), nullable=True, index=True
    )
    is_system: Mapped[bool] = mapped_column(Boolean, default=True)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now)


class TagAssignment(Base):
    """A source-level tag suggestion or an explicit user decision."""

    __tablename__ = "tag_assignments"
    __table_args__ = (
        ForeignKeyConstraint(
            ["research_run_id", "source_id"],
            ["research_runs.id", "research_runs.source_id"],
            name="fk_tag_assignments_run_same_source",
        ),
        UniqueConstraint("id", "source_id", name="uq_tag_assignments_id_source_id"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    source_id: Mapped[int] = mapped_column(ForeignKey("sources.id"), index=True)
    research_run_id: Mapped[int | None] = mapped_column(nullable=True, index=True)
    tag_id: Mapped[int] = mapped_column(ForeignKey("tag_definitions.id"), index=True)
    origin: Mapped[str] = mapped_column(String(16))
    status: Mapped[str] = mapped_column(String(16), index=True)
    confidence: Mapped[float | None] = mapped_column(nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utc_now, onupdate=utc_now
    )

    source: Mapped[Source] = relationship(back_populates="tag_assignments")


class TagAssignmentEvidence(Base):
    """Evidence supporting one suggested or confirmed tag assignment."""

    __tablename__ = "tag_assignment_evidence"
    __table_args__ = (
        ForeignKeyConstraint(
            ["tag_assignment_id", "source_id"],
            ["tag_assignments.id", "tag_assignments.source_id"],
            name="fk_tag_assignment_evidence_assignment_same_source",
        ),
        ForeignKeyConstraint(
            ["evidence_id", "source_id"],
            ["research_evidence.id", "research_evidence.source_id"],
            name="fk_tag_assignment_evidence_evidence_same_source",
        ),
        UniqueConstraint(
            "tag_assignment_id", "evidence_id", name="uq_tag_assignment_evidence_link"
        ),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    tag_assignment_id: Mapped[int] = mapped_column(index=True)
    evidence_id: Mapped[int] = mapped_column(index=True)
    source_id: Mapped[int] = mapped_column(index=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now)
