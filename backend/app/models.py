"""SQLAlchemy persistence shape for sources and their derived knowledge."""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any

from sqlalchemy import (
    JSON,
    Boolean,
    DateTime,
    ForeignKey,
    ForeignKeyConstraint,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship


def utc_now() -> datetime:
    """Return a timezone-aware timestamp suitable for persistence defaults."""
    return datetime.now(UTC)


class Base(DeclarativeBase):
    """Declarative metadata owner for database migrations."""


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
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    source_id: Mapped[int] = mapped_column(ForeignKey("sources.id"), index=True)
    kind: Mapped[str] = mapped_column(String(32), index=True)
    title: Mapped[str] = mapped_column(String(512))
    markdown: Mapped[str] = mapped_column(Text)
    language: Mapped[str | None] = mapped_column(String(32), nullable=True)
    parent_artifact_id: Mapped[int | None] = mapped_column(nullable=True, index=True)
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
