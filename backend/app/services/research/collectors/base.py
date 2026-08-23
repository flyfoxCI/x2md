"""Shared narrow protocols for bounded evidence collectors."""

from __future__ import annotations

from collections.abc import Mapping
from typing import Protocol

from app.services.research.contracts import CollectionResult


class ResearchableSource(Protocol):
    """The immutable source fields a collector is allowed to inspect."""

    canonical_url: str
    platform: str
    metadata_json: Mapping[str, object]


class ResearchCollector(Protocol):
    """Return a bounded result rather than mutating a source or database row."""

    async def collect(self, source: ResearchableSource) -> CollectionResult:
        """Collect version-pinned included/excluded evidence for one source."""
