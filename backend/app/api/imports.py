"""URL import endpoint for persisted canonical sources."""

from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel, Field

from app.api.dependencies import ImportKnowledgeServiceDependency, require_csrf
from app.schemas import ApiErrorResponse, SourceRead
from app.services.knowledge import KnowledgeError
from app.services.research.worker import auto_start_enabled

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
    request: Request,
) -> SourceRead:
    """Synchronously import a supported public URL into the canonical library."""
    try:
        source = await service.import_url(payload.url)
        if _eligible_for_auto_research(source, request):
            orchestrator = getattr(request.app.state, "research_orchestrator", None)
            if orchestrator is not None:
                orchestrator.enqueue(source.id, trigger="auto")
        return SourceRead.model_validate(source)
    except KnowledgeError as error:
        raise HTTPException(
            status_code=error.status_code,
            detail={"code": error.code, "message": error.message},
        ) from error


def _eligible_for_auto_research(source: object, request: Request) -> bool:
    """Enqueue only persisted, content-bearing sources after a user enabled the switch."""
    if not getattr(source, "platform", None) in {"github", "arxiv", "huggingface"}:
        return False
    if not (getattr(source, "raw_text", "").strip() or getattr(source, "source_markdown", "").strip()):
        return False
    with request.app.state.session_factory() as session:
        return auto_start_enabled(session)
