"""Platform-neutral immutable inputs and hard limits for deep research."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Literal

ResearchPlatform = Literal["github", "arxiv", "huggingface"]
EvidenceDecision = Literal["included", "excluded"]
ResearchRunStatus = Literal[
    "queued", "running", "completed", "partial", "blocked", "failed"
]
ResearchPhase = Literal["collecting", "summarizing", "reporting", "tagging"]


@dataclass(frozen=True, slots=True)
class CollectionBudget:
    """Explicit platform ceiling persisted with every research run."""

    platform: ResearchPlatform
    max_items: int
    max_content_bytes: int
    max_requests: int = 32
    max_pdf_bytes: int | None = None
    max_pages: int | None = None
    max_extracted_chars: int | None = None

    def as_dict(self) -> dict[str, int | str | None]:
        """Return the stable JSON-safe shape stored on a research run."""
        return {
            "platform": self.platform,
            "max_items": self.max_items,
            "max_content_bytes": self.max_content_bytes,
            "max_requests": self.max_requests,
            "max_pdf_bytes": self.max_pdf_bytes,
            "max_pages": self.max_pages,
            "max_extracted_chars": self.max_extracted_chars,
        }


COLLECTION_BUDGETS: dict[ResearchPlatform, CollectionBudget] = {
    "github": CollectionBudget(
        platform="github", max_items=20, max_content_bytes=1_572_864
    ),
    "arxiv": CollectionBudget(
        platform="arxiv",
        max_items=60,
        max_content_bytes=500_000,
        max_pdf_bytes=26_214_400,
        max_pages=60,
        max_extracted_chars=500_000,
    ),
    "huggingface": CollectionBudget(
        platform="huggingface", max_items=12, max_content_bytes=1_048_576
    ),
}


def collection_budget(platform: ResearchPlatform) -> CollectionBudget:
    """Resolve a non-configurable first-release budget for a supported platform."""
    try:
        return COLLECTION_BUDGETS[platform]
    except KeyError as error:
        raise ValueError(f"unsupported research platform: {platform}") from error


@dataclass(frozen=True, slots=True)
class EvidenceInput:
    """One persisted included-evidence record made safe for an AI request."""

    evidence_id: int
    locator: str
    kind: str
    content: str
    title: str | None = None
    source_revision: str | None = None

    def __post_init__(self) -> None:
        if self.evidence_id <= 0:
            raise ValueError("evidence_id must be positive")
        if not self.locator.strip():
            raise ValueError("locator must be non-empty")
        if len(self.locator) > 4096:
            raise ValueError("locator exceeds the persistence limit")
        if not self.kind.strip():
            raise ValueError("evidence kind must be non-empty")
        if not self.content.strip():
            raise ValueError("included evidence content must be non-empty")


@dataclass(frozen=True, slots=True)
class CollectedEvidence:
    """A collector decision, including exclusions needed to report true coverage."""

    locator: str
    kind: str
    ordinal: int
    decision: EvidenceDecision
    title: str | None = None
    content: str | None = None
    source_revision: str | None = None
    exclusion_reason: str | None = None

    def __post_init__(self) -> None:
        if not self.locator.strip():
            raise ValueError("locator must be non-empty")
        if self.ordinal < 0:
            raise ValueError("ordinal must not be negative")
        if self.decision == "included" and not (self.content or "").strip():
            raise ValueError("included evidence requires content")
        if self.decision == "excluded" and not (self.exclusion_reason or "").strip():
            raise ValueError("excluded evidence requires an exclusion reason")


@dataclass(frozen=True, slots=True)
class CollectionResult:
    """Immutable bounded collection outcome returned by one platform collector."""

    platform: ResearchPlatform
    source_revision: str | None
    evidence: tuple[CollectedEvidence, ...]
    coverage: dict[str, object] = field(default_factory=dict)

    def __post_init__(self) -> None:
        budget = collection_budget(self.platform)
        included = tuple(item for item in self.evidence if item.decision == "included")
        if len(included) > budget.max_items:
            raise ValueError("collection exceeds the platform item budget")
        content_bytes = sum(len((item.content or "").encode()) for item in included)
        if content_bytes > budget.max_content_bytes:
            raise ValueError("collection exceeds the platform content budget")
