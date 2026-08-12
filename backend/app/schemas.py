"""Pydantic data-transfer objects for persistence-backed API contracts."""

from datetime import datetime
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field

ArtifactKind = Literal["translation", "summary", "skill", "user_edit"]
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


class AppSettingWrite(BaseModel):
    """Value to store for a non-secret application setting."""

    value_json: dict[str, Any] = Field(default_factory=dict)


class AppSettingRead(AppSettingWrite):
    """Persisted application setting representation."""

    model_config = ConfigDict(from_attributes=True)

    key: str
    updated_at: datetime
