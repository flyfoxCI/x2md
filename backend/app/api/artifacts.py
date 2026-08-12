"""Append-only artifact editing and Markdown export endpoints."""

import re

from fastapi import APIRouter, HTTPException
from fastapi.responses import Response
from pydantic import BaseModel, Field

from app.api.dependencies import KnowledgeServiceDependency
from app.schemas import ApiErrorResponse, ArtifactRead
from app.services.knowledge import KnowledgeError

router = APIRouter(
    prefix="/api/artifacts",
    tags=["artifacts"],
    responses={
        422: {
            "model": ApiErrorResponse,
            "description": "The request is invalid.",
        }
    },
)
_FILENAME_CHARS = re.compile(r"[^A-Za-z0-9._-]+")


class ArtifactEditRequest(BaseModel):
    """User-provided content for a new artifact version."""

    title: str | None = Field(default=None, min_length=1, max_length=512)
    markdown: str = Field(min_length=1, max_length=100_000)
    language: str | None = Field(default=None, max_length=32)


@router.patch(
    "/{artifact_id}",
    response_model=ArtifactRead,
    responses={
        404: {"model": ApiErrorResponse, "description": "The artifact does not exist."}
    },
)
def edit_artifact(
    artifact_id: int,
    payload: ArtifactEditRequest,
    service: KnowledgeServiceDependency,
) -> ArtifactRead:
    """Create a new user-edit artifact linked to the selected parent version."""
    try:
        artifact = service.create_user_edit(
            artifact_id,
            title=payload.title,
            markdown=payload.markdown,
            language=payload.language,
        )
    except KnowledgeError as error:
        raise HTTPException(
            status_code=error.status_code,
            detail={"code": error.code, "message": error.message},
        ) from error
    return ArtifactRead.model_validate(artifact)


@router.get(
    "/{artifact_id}/download",
    responses={
        404: {"model": ApiErrorResponse, "description": "The artifact does not exist."}
    },
)
def download_artifact(
    artifact_id: int,
    service: KnowledgeServiceDependency,
) -> Response:
    """Download exactly the persisted Markdown content with a safe `.md` name."""
    try:
        artifact = service.get_artifact(artifact_id)
    except KnowledgeError as error:
        raise HTTPException(
            status_code=error.status_code,
            detail={"code": error.code, "message": error.message},
        ) from error
    filename = _markdown_filename(artifact.title)
    return Response(
        content=artifact.markdown,
        media_type="text/markdown; charset=utf-8",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )


def _markdown_filename(title: str) -> str:
    """Make an ASCII attachment filename that cannot alter response headers."""
    stem = _FILENAME_CHARS.sub("-", title).strip(".-") or "artifact"
    stem = stem.removesuffix(".md")
    return f"{stem}.md"
