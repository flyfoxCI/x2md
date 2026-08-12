"""Create the canonical persistence schema.

Revision ID: 0001_initial_schema
Revises:
Create Date: 2026-08-12
"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "0001_initial_schema"
down_revision: str | None = None
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Create canonical sources and append-only artifact lineage tables."""
    op.create_table(
        "sources",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("canonical_url", sa.String(length=2048), nullable=False),
        sa.Column("platform", sa.String(length=64), nullable=False),
        sa.Column("title", sa.String(length=512), nullable=False),
        sa.Column("author", sa.String(length=512), nullable=True),
        sa.Column("published_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("raw_text", sa.Text(), nullable=False),
        sa.Column("source_markdown", sa.Text(), nullable=False),
        sa.Column("metadata_json", sa.JSON(), nullable=False),
        sa.Column("import_status", sa.String(length=32), nullable=False),
        sa.Column("failure_reason", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("canonical_url"),
    )
    op.create_index("ix_sources_import_status", "sources", ["import_status"])
    op.create_index("ix_sources_platform", "sources", ["platform"])

    op.create_table(
        "artifacts",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("source_id", sa.Integer(), nullable=False),
        sa.Column("kind", sa.String(length=32), nullable=False),
        sa.Column("title", sa.String(length=512), nullable=False),
        sa.Column("markdown", sa.Text(), nullable=False),
        sa.Column("language", sa.String(length=32), nullable=True),
        sa.Column("parent_artifact_id", sa.Integer(), nullable=True),
        sa.Column("model_metadata_json", sa.JSON(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(
            ["parent_artifact_id", "source_id"],
            ["artifacts.id", "artifacts.source_id"],
            name="fk_artifacts_parent_same_source",
        ),
        sa.ForeignKeyConstraint(["source_id"], ["sources.id"]),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("id", "source_id", name="uq_artifacts_id_source_id"),
    )
    op.create_index("ix_artifacts_kind", "artifacts", ["kind"])
    op.create_index("ix_artifacts_parent_artifact_id", "artifacts", ["parent_artifact_id"])
    op.create_index("ix_artifacts_source_id", "artifacts", ["source_id"])

    op.create_table(
        "knowledge_notes",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("source_id", sa.Integer(), nullable=False),
        sa.Column("artifact_id", sa.Integer(), nullable=True),
        sa.Column("tags_json", sa.JSON(), nullable=False),
        sa.Column("pinned", sa.Boolean(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(
            ["artifact_id", "source_id"],
            ["artifacts.id", "artifacts.source_id"],
            name="fk_knowledge_notes_artifact_same_source",
        ),
        sa.ForeignKeyConstraint(["source_id"], ["sources.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_knowledge_notes_artifact_id", "knowledge_notes", ["artifact_id"])
    op.create_index("ix_knowledge_notes_source_id", "knowledge_notes", ["source_id"])

    op.create_table(
        "chat_turns",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("source_id", sa.Integer(), nullable=False),
        sa.Column("question", sa.Text(), nullable=False),
        sa.Column("answer_markdown", sa.Text(), nullable=False),
        sa.Column("citations_json", sa.JSON(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["source_id"], ["sources.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_chat_turns_source_id", "chat_turns", ["source_id"])

    op.create_table(
        "app_settings",
        sa.Column("key", sa.String(length=128), nullable=False),
        sa.Column("value_json", sa.JSON(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint("key"),
    )


def downgrade() -> None:
    """Drop the initial persistence schema in dependency order."""
    op.drop_table("app_settings")
    op.drop_index("ix_chat_turns_source_id", table_name="chat_turns")
    op.drop_table("chat_turns")
    op.drop_index("ix_knowledge_notes_source_id", table_name="knowledge_notes")
    op.drop_index("ix_knowledge_notes_artifact_id", table_name="knowledge_notes")
    op.drop_table("knowledge_notes")
    op.drop_index("ix_artifacts_source_id", table_name="artifacts")
    op.drop_index("ix_artifacts_parent_artifact_id", table_name="artifacts")
    op.drop_index("ix_artifacts_kind", table_name="artifacts")
    op.drop_table("artifacts")
    op.drop_index("ix_sources_platform", table_name="sources")
    op.drop_index("ix_sources_import_status", table_name="sources")
    op.drop_table("sources")
