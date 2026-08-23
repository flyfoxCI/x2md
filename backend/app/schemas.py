"""Pydantic data-transfer objects for persistence-backed API contracts."""

from datetime import datetime
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field

ArtifactKind = Literal["translation", "summary", "skill", "research", "user_edit"]
ImportStatus = Literal["ready", "partial", "blocked"]


class ApiErrorDetail(BaseModel):
    """Stable machine-readable code and safe message for a public failure."""

    code: str
    message: str


class ApiErrorResponse(BaseModel):
    """Documented envelope used by knowledge-library route failures."""

    detail: ApiErrorDetail


class SourceCreate(BaseModel):
    """Fields accepted when recording canonical connector output."""

    canonical_url: str
    platform: str
    title: str
    author: str | None = None
    published_at: datetime | None = None
    raw_text: str = ""
    source_markdown: str = ""
    metadata_json: dict[str, Any] = Field(default_factory=dict)
    import_status: ImportStatus
    failure_reason: str | None = None


class SourceRead(SourceCreate):
    """Canonical source representation returned to API clients."""

    model_config = ConfigDict(from_attributes=True)

    id: int
    created_at: datetime
    updated_at: datetime


class ArtifactCreate(BaseModel):
    """Fields for a new derived artifact; source raw material is excluded."""

    source_id: int
    kind: ArtifactKind
    title: str
    markdown: str
    language: str | None = None
    parent_artifact_id: int | None = None
    research_run_id: int | None = None
    model_metadata_json: dict[str, Any] = Field(default_factory=dict)


class ArtifactRead(ArtifactCreate):
    """Versioned artifact representation returned to API clients."""

    model_config = ConfigDict(from_attributes=True)

    id: int
    created_at: datetime
    updated_at: datetime


class KnowledgeNoteCreate(BaseModel):
    """Library metadata that points to a source and optional artifact."""

    source_id: int
    artifact_id: int | None = None
    tags_json: list[str] = Field(default_factory=list)
    pinned: bool = False


class KnowledgeNoteRead(KnowledgeNoteCreate):
    """Persisted library metadata representation."""

    model_config = ConfigDict(from_attributes=True)

    id: int
    created_at: datetime
    updated_at: datetime


class ChatTurnCreate(BaseModel):
    """Source-scoped question and grounded answer to persist."""

    source_id: int
    question: str
    answer_markdown: str
    citations_json: list[dict[str, Any]] = Field(default_factory=list)


class ChatTurnRead(ChatTurnCreate):
    """Persisted source-scoped chat turn representation."""

    model_config = ConfigDict(from_attributes=True)

    id: int
    created_at: datetime


class ResearchRunRead(BaseModel):
    """Safe persistent research-run state exposed to a browser client."""

    model_config = ConfigDict(from_attributes=True)

    id: int
    source_id: int
    trigger: str
    status: str
    phase: str | None
    budget_json: dict[str, Any]
    coverage_json: dict[str, Any]
    attempt_count: int
    max_attempts: int
    next_attempt_at: datetime | None
    failure_code: str | None
    provider_metadata_json: dict[str, Any]
    started_at: datetime | None
    finished_at: datetime | None
    created_at: datetime
    updated_at: datetime


class ResearchEvidenceRead(BaseModel):
    """One stored included/excluded evidence record without internal file paths."""

    model_config = ConfigDict(from_attributes=True)

    id: int
    research_run_id: int
    source_id: int
    locator: str
    kind: str
    title: str | None
    ordinal: int
    source_revision: str | None
    content: str | None
    digest_markdown: str | None
    status: str
    exclusion_reason: str | None
    created_at: datetime


class TagDefinitionRead(BaseModel):
    """One controlled or user-defined taxonomy node."""

    model_config = ConfigDict(from_attributes=True)

    id: int
    slug: str
    label: str
    facet: str | None
    parent_id: int | None
    is_system: bool
    description: str | None
    created_at: datetime


class TagAssignmentRead(BaseModel):
    """One explicit user or AI assignment; evidence links are queried separately."""

    model_config = ConfigDict(from_attributes=True)

    id: int
    source_id: int
    research_run_id: int | None
    tag_id: int
    origin: str
    status: str
    confidence: float | None
    created_at: datetime
    updated_at: datetime


class AppSettingWrite(BaseModel):
    """Value to store for a non-secret application setting."""

    value_json: dict[str, Any] = Field(default_factory=dict)


class AppSettingRead(AppSettingWrite):
    """Persisted application setting representation."""

    model_config = ConfigDict(from_attributes=True)

    key: str
    updated_at: datetime


class DerivationRequest(BaseModel):
    """One supported immutable artifact transformation."""

    kind: Literal["translation", "summary", "skill"]


class ChatRequest(BaseModel):
    """A non-empty question scoped to one imported source."""

    question: str = Field(min_length=1, max_length=1_000)
