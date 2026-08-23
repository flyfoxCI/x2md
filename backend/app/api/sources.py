"""Knowledge-library read endpoints."""

from fastapi import APIRouter, HTTPException, Query
from pydantic import BaseModel, ConfigDict
from sqlalchemy import select

from app.api.dependencies import (
    AIKnowledgeServiceDependency,
    AIServiceDependency,
    DatabaseSession,
    KnowledgeServiceDependency,
)
from app.models import ResearchRun, TagAssignment
from app.schemas import (
    ApiErrorResponse,
    ArtifactRead,
    ChatRequest,
    ChatTurnRead,
    DerivationRequest,
    ResearchRunRead,
    SourceRead,
    TagAssignmentRead,
)
from app.services.ai import ProviderError
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
    research_runs: list[ResearchRunRead]
    tag_assignments: list[TagAssignmentRead]


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
    session: DatabaseSession,
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
        research_runs=[
            ResearchRunRead.model_validate(run)
            for run in session.scalars(
                select(ResearchRun)
                .where(ResearchRun.source_id == source.id)
                .order_by(ResearchRun.created_at.desc(), ResearchRun.id.desc())
            )
        ],
        tag_assignments=[
            TagAssignmentRead.model_validate(assignment)
            for assignment in session.scalars(
                select(TagAssignment)
                .where(TagAssignment.source_id == source.id)
                .order_by(TagAssignment.created_at.desc(), TagAssignment.id.desc())
            )
        ],
    )


@router.post(
    "/{source_id}/derive",
    response_model=ArtifactRead,
    responses={
        404: {"model": ApiErrorResponse, "description": "The source does not exist."},
        422: {"model": ApiErrorResponse, "description": "The action is unavailable."},
        502: {"model": ApiErrorResponse, "description": "The provider failed safely."},
    },
)
async def derive_source(
    source_id: int,
    payload: DerivationRequest,
    knowledge: AIKnowledgeServiceDependency,
    ai: AIServiceDependency,
) -> ArtifactRead:
    """Append one provider-backed, source-provenance AI derivation."""
    try:
        material = knowledge.load_source_material(source_id)
        generated = await ai.derive(material, payload.kind)
        artifact = knowledge.create_generated_artifact(
            source_id,
            kind=payload.kind,
            title=generated.title,
            markdown=generated.markdown,
            language=generated.language,
            model_metadata_json=generated.model_metadata,
        )
    except (KnowledgeError, ProviderError) as error:
        raise _http_error(error) from error
    return ArtifactRead.model_validate(artifact)


@router.post(
    "/{source_id}/chat",
    response_model=ChatTurnRead,
    responses={
        404: {"model": ApiErrorResponse, "description": "The source does not exist."},
        422: {"model": ApiErrorResponse, "description": "The action is unavailable."},
        502: {"model": ApiErrorResponse, "description": "The provider failed safely."},
    },
)
async def chat_with_source(
    source_id: int,
    payload: ChatRequest,
    knowledge: AIKnowledgeServiceDependency,
    ai: AIServiceDependency,
) -> ChatTurnRead:
    """Persist a response grounded in the selected source and its own artifacts only."""
    try:
        material = knowledge.load_source_material(source_id)
        generated = await ai.answer(material, payload.question)
        turn = knowledge.create_chat_turn(
            source_id,
            question=payload.question,
            answer_markdown=generated.markdown,
            citations_json=list(generated.citations),
        )
    except (KnowledgeError, ProviderError) as error:
        raise _http_error(error) from error
    return ChatTurnRead.model_validate(turn)


def _http_error(error: KnowledgeError | ProviderError) -> HTTPException:
    """Translate stable domain/provider errors into the public envelope."""
    return HTTPException(
        status_code=error.status_code,
        detail={"code": error.code, "message": error.message},
    )
