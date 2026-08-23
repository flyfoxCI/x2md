"""Add durable evidence-backed deep research records.

Revision ID: 0002_deep_research
Revises: 0001_initial_schema
Create Date: 2026-08-23
"""

from __future__ import annotations

import hashlib
import json
import re
from collections.abc import Sequence
from datetime import UTC, datetime

import sqlalchemy as sa

from alembic import op

revision: str = "0002_deep_research"
down_revision: str | None = "0001_initial_schema"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Create research records and preserve legacy note tags as user labels."""
    op.create_table(
        "tag_definitions",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("slug", sa.String(length=160), nullable=False),
        sa.Column("label", sa.String(length=160), nullable=False),
        sa.Column("facet", sa.String(length=32), nullable=True),
        sa.Column("parent_id", sa.Integer(), nullable=True),
        sa.Column("is_system", sa.Boolean(), nullable=False),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["parent_id"], ["tag_definitions.id"]),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("slug", name="uq_tag_definitions_slug"),
    )
    op.create_index("ix_tag_definitions_facet", "tag_definitions", ["facet"])
    op.create_index("ix_tag_definitions_parent_id", "tag_definitions", ["parent_id"])

    op.create_table(
        "research_runs",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("source_id", sa.Integer(), nullable=False),
        sa.Column("trigger", sa.String(length=16), nullable=False),
        sa.Column("status", sa.String(length=16), nullable=False),
        sa.Column("phase", sa.String(length=32), nullable=True),
        sa.Column("budget_json", sa.JSON(), nullable=False),
        sa.Column("coverage_json", sa.JSON(), nullable=False),
        sa.Column("attempt_count", sa.Integer(), nullable=False),
        sa.Column("max_attempts", sa.Integer(), nullable=False),
        sa.Column("next_attempt_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("lease_owner", sa.String(length=128), nullable=True),
        sa.Column("lease_expires_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("failure_code", sa.String(length=64), nullable=True),
        sa.Column("provider_metadata_json", sa.JSON(), nullable=False),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("finished_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["source_id"], ["sources.id"]),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("id", "source_id", name="uq_research_runs_id_source_id"),
    )
    op.create_index("ix_research_runs_source_id", "research_runs", ["source_id"])
    op.create_index("ix_research_runs_status", "research_runs", ["status"])
    op.create_index("ix_research_runs_next_attempt_at", "research_runs", ["next_attempt_at"])
    op.create_index("ix_research_runs_lease_expires_at", "research_runs", ["lease_expires_at"])
    active_status = sa.text("status IN ('queued', 'running')")
    op.create_index(
        "uq_research_runs_one_active_per_source",
        "research_runs",
        ["source_id"],
        unique=True,
        sqlite_where=active_status,
        postgresql_where=active_status,
    )

    with op.batch_alter_table("artifacts") as batch_op:
        batch_op.add_column(sa.Column("research_run_id", sa.Integer(), nullable=True))
        batch_op.create_foreign_key(
            "fk_artifacts_research_run_same_source",
            "research_runs",
            ["research_run_id", "source_id"],
            ["id", "source_id"],
        )
    op.create_index("ix_artifacts_research_run_id", "artifacts", ["research_run_id"])

    op.create_table(
        "research_evidence",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("research_run_id", sa.Integer(), nullable=False),
        sa.Column("source_id", sa.Integer(), nullable=False),
        sa.Column("locator", sa.String(length=4096), nullable=False),
        sa.Column("kind", sa.String(length=32), nullable=False),
        sa.Column("title", sa.String(length=512), nullable=True),
        sa.Column("ordinal", sa.Integer(), nullable=False),
        sa.Column("source_revision", sa.String(length=256), nullable=True),
        sa.Column("content", sa.Text(), nullable=True),
        sa.Column("content_sha256", sa.String(length=64), nullable=True),
        sa.Column("digest_markdown", sa.Text(), nullable=True),
        sa.Column("digest_model_metadata_json", sa.JSON(), nullable=False),
        sa.Column("status", sa.String(length=16), nullable=False),
        sa.Column("exclusion_reason", sa.String(length=64), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(
            ["research_run_id", "source_id"],
            ["research_runs.id", "research_runs.source_id"],
            name="fk_research_evidence_run_same_source",
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("id", "source_id", name="uq_research_evidence_id_source_id"),
        sa.UniqueConstraint(
            "research_run_id", "locator", name="uq_research_evidence_run_locator"
        ),
    )
    op.create_index("ix_research_evidence_research_run_id", "research_evidence", ["research_run_id"])
    op.create_index("ix_research_evidence_source_id", "research_evidence", ["source_id"])
    op.create_index("ix_research_evidence_status", "research_evidence", ["status"])

    op.create_table(
        "research_citations",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("artifact_id", sa.Integer(), nullable=False),
        sa.Column("evidence_id", sa.Integer(), nullable=False),
        sa.Column("source_id", sa.Integer(), nullable=False),
        sa.Column("token", sa.String(length=32), nullable=False),
        sa.Column("paragraph_anchor", sa.String(length=128), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(
            ["artifact_id", "source_id"],
            ["artifacts.id", "artifacts.source_id"],
            name="fk_research_citations_artifact_same_source",
        ),
        sa.ForeignKeyConstraint(
            ["evidence_id", "source_id"],
            ["research_evidence.id", "research_evidence.source_id"],
            name="fk_research_citations_evidence_same_source",
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("artifact_id", "token", name="uq_research_citations_artifact_token"),
    )
    op.create_index("ix_research_citations_artifact_id", "research_citations", ["artifact_id"])
    op.create_index("ix_research_citations_evidence_id", "research_citations", ["evidence_id"])
    op.create_index("ix_research_citations_source_id", "research_citations", ["source_id"])

    op.create_table(
        "tag_assignments",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("source_id", sa.Integer(), nullable=False),
        sa.Column("research_run_id", sa.Integer(), nullable=True),
        sa.Column("tag_id", sa.Integer(), nullable=False),
        sa.Column("origin", sa.String(length=16), nullable=False),
        sa.Column("status", sa.String(length=16), nullable=False),
        sa.Column("confidence", sa.Float(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["source_id"], ["sources.id"]),
        sa.ForeignKeyConstraint(
            ["research_run_id", "source_id"],
            ["research_runs.id", "research_runs.source_id"],
            name="fk_tag_assignments_run_same_source",
        ),
        sa.ForeignKeyConstraint(["tag_id"], ["tag_definitions.id"]),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("id", "source_id", name="uq_tag_assignments_id_source_id"),
    )
    op.create_index("ix_tag_assignments_source_id", "tag_assignments", ["source_id"])
    op.create_index("ix_tag_assignments_research_run_id", "tag_assignments", ["research_run_id"])
    op.create_index("ix_tag_assignments_tag_id", "tag_assignments", ["tag_id"])
    op.create_index("ix_tag_assignments_status", "tag_assignments", ["status"])

    op.create_table(
        "tag_assignment_evidence",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("tag_assignment_id", sa.Integer(), nullable=False),
        sa.Column("evidence_id", sa.Integer(), nullable=False),
        sa.Column("source_id", sa.Integer(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(
            ["tag_assignment_id", "source_id"],
            ["tag_assignments.id", "tag_assignments.source_id"],
            name="fk_tag_assignment_evidence_assignment_same_source",
        ),
        sa.ForeignKeyConstraint(
            ["evidence_id", "source_id"],
            ["research_evidence.id", "research_evidence.source_id"],
            name="fk_tag_assignment_evidence_evidence_same_source",
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "tag_assignment_id", "evidence_id", name="uq_tag_assignment_evidence_link"
        ),
    )
    op.create_index("ix_tag_assignment_evidence_tag_assignment_id", "tag_assignment_evidence", ["tag_assignment_id"])
    op.create_index("ix_tag_assignment_evidence_evidence_id", "tag_assignment_evidence", ["evidence_id"])
    op.create_index("ix_tag_assignment_evidence_source_id", "tag_assignment_evidence", ["source_id"])

    _migrate_legacy_tags()


def downgrade() -> None:
    """Remove research tables while retaining the original note JSON values."""
    op.drop_index("ix_tag_assignment_evidence_source_id", table_name="tag_assignment_evidence")
    op.drop_index("ix_tag_assignment_evidence_evidence_id", table_name="tag_assignment_evidence")
    op.drop_index("ix_tag_assignment_evidence_tag_assignment_id", table_name="tag_assignment_evidence")
    op.drop_table("tag_assignment_evidence")
    op.drop_index("ix_tag_assignments_status", table_name="tag_assignments")
    op.drop_index("ix_tag_assignments_tag_id", table_name="tag_assignments")
    op.drop_index("ix_tag_assignments_research_run_id", table_name="tag_assignments")
    op.drop_index("ix_tag_assignments_source_id", table_name="tag_assignments")
    op.drop_table("tag_assignments")
    op.drop_index("ix_research_citations_source_id", table_name="research_citations")
    op.drop_index("ix_research_citations_evidence_id", table_name="research_citations")
    op.drop_index("ix_research_citations_artifact_id", table_name="research_citations")
    op.drop_table("research_citations")
    op.drop_index("ix_research_evidence_status", table_name="research_evidence")
    op.drop_index("ix_research_evidence_source_id", table_name="research_evidence")
    op.drop_index("ix_research_evidence_research_run_id", table_name="research_evidence")
    op.drop_table("research_evidence")
    op.drop_index("ix_artifacts_research_run_id", table_name="artifacts")
    with op.batch_alter_table("artifacts") as batch_op:
        batch_op.drop_constraint("fk_artifacts_research_run_same_source", type_="foreignkey")
        batch_op.drop_column("research_run_id")
    op.drop_index("uq_research_runs_one_active_per_source", table_name="research_runs")
    op.drop_index("ix_research_runs_lease_expires_at", table_name="research_runs")
    op.drop_index("ix_research_runs_next_attempt_at", table_name="research_runs")
    op.drop_index("ix_research_runs_status", table_name="research_runs")
    op.drop_index("ix_research_runs_source_id", table_name="research_runs")
    op.drop_table("research_runs")
    op.drop_index("ix_tag_definitions_parent_id", table_name="tag_definitions")
    op.drop_index("ix_tag_definitions_facet", table_name="tag_definitions")
    op.drop_table("tag_definitions")


def _migrate_legacy_tags() -> None:
    """Copy legacy note tags into durable, confirmed custom labels once."""
    bind = op.get_bind()
    notes = sa.table(
        "knowledge_notes",
        sa.column("source_id", sa.Integer()),
        sa.column("tags_json", sa.JSON()),
    )
    tags = sa.table(
        "tag_definitions",
        sa.column("id", sa.Integer()),
        sa.column("slug", sa.String()),
        sa.column("label", sa.String()),
        sa.column("facet", sa.String()),
        sa.column("is_system", sa.Boolean()),
        sa.column("description", sa.Text()),
        sa.column("created_at", sa.DateTime(timezone=True)),
    )
    assignments = sa.table(
        "tag_assignments",
        sa.column("source_id", sa.Integer()),
        sa.column("research_run_id", sa.Integer()),
        sa.column("tag_id", sa.Integer()),
        sa.column("origin", sa.String()),
        sa.column("status", sa.String()),
        sa.column("confidence", sa.Float()),
        sa.column("created_at", sa.DateTime(timezone=True)),
        sa.column("updated_at", sa.DateTime(timezone=True)),
    )
    now = datetime.now(UTC)
    tag_ids: dict[str, int] = {}
    assigned: set[tuple[int, int]] = set()
    for source_id, raw_tags in bind.execute(sa.select(notes.c.source_id, notes.c.tags_json)):
        for label in _legacy_labels(raw_tags):
            slug = _legacy_slug(label)
            tag_id = tag_ids.get(slug)
            if tag_id is None:
                tag_id = bind.execute(
                    sa.select(tags.c.id).where(tags.c.slug == slug)
                ).scalar_one_or_none()
                if tag_id is None:
                    bind.execute(
                        sa.insert(tags).values(
                            slug=slug,
                            label=label,
                            facet=None,
                            is_system=False,
                            description=None,
                            created_at=now,
                        )
                    )
                    tag_id = bind.execute(
                        sa.select(tags.c.id).where(tags.c.slug == slug)
                    ).scalar_one()
                tag_ids[slug] = tag_id
            if (source_id, tag_id) in assigned:
                continue
            bind.execute(
                sa.insert(assignments).values(
                    source_id=source_id,
                    research_run_id=None,
                    tag_id=tag_id,
                    origin="user",
                    status="accepted",
                    confidence=None,
                    created_at=now,
                    updated_at=now,
                )
            )
            assigned.add((source_id, tag_id))


def _legacy_labels(raw_tags: object) -> tuple[str, ...]:
    if isinstance(raw_tags, str):
        try:
            raw_tags = json.loads(raw_tags)
        except json.JSONDecodeError:
            return ()
    if not isinstance(raw_tags, list):
        return ()
    unique: dict[str, str] = {}
    for value in raw_tags:
        if not isinstance(value, str) or not (label := value.strip()):
            continue
        unique.setdefault(label.casefold(), label)
    return tuple(unique.values())


def _legacy_slug(label: str) -> str:
    normalized = " ".join(label.split()).casefold()
    readable = re.sub(r"[^a-z0-9]+", "-", normalized).strip("-") or "tag"
    digest = hashlib.sha256(normalized.encode("utf-8")).hexdigest()[:12]
    return f"custom-{readable[:120]}-{digest}"
