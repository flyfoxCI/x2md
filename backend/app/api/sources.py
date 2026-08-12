"""Knowledge-library read endpoints."""

from fastapi import APIRouter, HTTPException, Query
from pydantic import BaseModel, ConfigDict

from app.api.dependencies import KnowledgeServiceDependency
from app.schemas import ApiErrorResponse, ArtifactRead, SourceRead
from app.services.knowledge import KnowledgeError

router = APIRouter(
    prefix="/api/sources",
    tags=["sources"],
    responses={
        422: {
            "model": ApiErrorResponse,
            "description": "The request is invalid.",
        }
    },
)


class SourcePageRead(BaseModel):
    """Paginated source-library response."""

    items: list[SourceRead]
    total: int
    page: int
    page_size: int


class SourceDetailRead(BaseModel):
    """Canonical source with all persisted artifact versions."""

    model_config = ConfigDict(from_attributes=True)

    source: SourceRead
    artifacts: list[ArtifactRead]


@router.get("", response_model=SourcePageRead)
def list_sources(
    service: KnowledgeServiceDependency,
    q: str | None = Query(default=None, max_length=512),
    platform: str | None = Query(default=None, max_length=64),
    tag: str | None = Query(default=None, max_length=128),
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=20, ge=1, le=100),
) -> SourcePageRead:
    """Search library titles/URLs and return one requested page."""
    result = service.list_sources(
        query=q, platform=platform, tag=tag, page=page, page_size=page_size
    )
    return SourcePageRead(
        items=[SourceRead.model_validate(source) for source in result.items],
        total=result.total,
        page=page,
        page_size=page_size,
    )


@router.get(
    "/{source_id}",
    response_model=SourceDetailRead,
    responses={
        404: {"model": ApiErrorResponse, "description": "The source does not exist."}
    },
)
def get_source(
    source_id: int,
    service: KnowledgeServiceDependency,
) -> SourceDetailRead:
    """Read one canonical source, its status, and append-only artifact history."""
    try:
        source = service.get_source(source_id)
    except KnowledgeError as error:
        raise HTTPException(
            status_code=error.status_code,
            detail={"code": error.code, "message": error.message},
        ) from error
    return SourceDetailRead(
        source=SourceRead.model_validate(source),
        artifacts=[
            ArtifactRead.model_validate(artifact)
            for artifact in sorted(source.artifacts, key=lambda item: (item.created_at, item.id))
        ],
    )
