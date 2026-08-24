"""Merge authentication and deep-research migration branches.

Revision ID: 0003_merge_auth_research
Revises: 0002_add_authentication, 0002_deep_research
Create Date: 2026-08-24
"""

from collections.abc import Sequence

revision: str = "0003_merge_auth_research"
down_revision: tuple[str, str] = (
    "0002_add_authentication",
    "0002_deep_research",
)
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Join both already-applied schema branches without changing data."""


def downgrade() -> None:
    """Return to the two branch heads without changing data."""
