"""URL import endpoint for persisted canonical sources."""

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field

from app.api.dependencies import ImportKnowledgeServiceDependency, require_csrf
from app.schemas import ApiErrorResponse, SourceRead
from app.services.knowledge import KnowledgeError

router = APIRouter(prefix="/api/imports", tags=["imports"])


class ImportRequest(BaseModel):
    """The URL supplied by a knowledge-library user."""

    url: str = Field(max_length=2048)


@router.post(
    "",
    response_model=SourceRead,
    dependencies=[Depends(require_csrf)],
    responses={
        422: {
            "model": ApiErrorResponse,
            "description": "A public URL or its source could not be imported safely.",
        }
    },
)
async def import_source(
    payload: ImportRequest,
    service: ImportKnowledgeServiceDependency,
) -> SourceRead:
    """Synchronously import a supported public URL into the canonical library."""
    try:
        return SourceRead.model_validate(await service.import_url(payload.url))
    except KnowledgeError as error:
        raise HTTPException(
            status_code=error.status_code,
            detail={"code": error.code, "message": error.message},
        ) from error
