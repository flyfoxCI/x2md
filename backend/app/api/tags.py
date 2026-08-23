"""Taxonomy inspection and explicit user governance endpoints."""

from fastapi import APIRouter, HTTPException, Response
from pydantic import BaseModel, Field
from sqlalchemy import select

from app.api.dependencies import DatabaseSession
from app.models import Source, TagAssignment, TagAssignmentEvidence
from app.schemas import ApiErrorResponse, TagAssignmentRead, TagDefinitionRead
from app.services.research.tags import TagError, TagService

router = APIRouter(prefix="/api", tags=["tags"])


class TagTreeRead(BaseModel):
    """The full controlled taxonomy for source filtering and tag review."""

    items: list[TagDefinitionRead]


class CustomTagRequest(BaseModel):
    """A user-created source label."""

    label: str = Field(min_length=1, max_length=160)


class TagDecisionRequest(BaseModel):
    """A user confirmation or rejection of one persisted assignment."""

    status: str = Field(pattern="^(accepted|rejected)$")


@router.get("/tags", response_model=TagTreeRead)
def get_tag_tree(session: DatabaseSession) -> TagTreeRead:
    """Read and, on a fresh database, seed the controlled hierarchy."""
    service = TagService(session)
    items = service.tree()
    session.commit()
    return TagTreeRead(items=[TagDefinitionRead.model_validate(item) for item in items])


@router.post(
    "/sources/{source_id}/tags",
    response_model=TagAssignmentRead,
    status_code=201,
    responses={404: {"model": ApiErrorResponse, "description": "The source does not exist."}},
)
def create_custom_tag(
    source_id: int, payload: CustomTagRequest, session: DatabaseSession
) -> TagAssignmentRead:
    """Attach a user label immediately as an accepted assignment."""
    if session.get(Source, source_id) is None:
        raise HTTPException(
            status_code=404,
            detail={"code": "source_not_found", "message": "The requested source does not exist."},
        )
    try:
        assignment = TagService(session).create_custom(source_id=source_id, label=payload.label)
        session.commit()
    except TagError as error:
        raise _http_error(error) from error
    return TagAssignmentRead.model_validate(assignment)


@router.patch(
    "/tag-assignments/{assignment_id}",
    response_model=TagAssignmentRead,
    responses={404: {"model": ApiErrorResponse, "description": "The assignment does not exist."}},
)
def decide_tag_assignment(
    assignment_id: int, payload: TagDecisionRequest, session: DatabaseSession
) -> TagAssignmentRead:
    """Persist an explicit acceptance or rejection while retaining evidence provenance."""
    service = TagService(session)
    try:
        assignment = (
            service.accept(assignment_id)
            if payload.status == "accepted"
            else service.reject(assignment_id)
        )
        session.commit()
    except TagError as error:
        raise _http_error(error) from error
    return TagAssignmentRead.model_validate(assignment)


@router.delete(
    "/tag-assignments/{assignment_id}",
    status_code=204,
    response_class=Response,
    responses={404: {"model": ApiErrorResponse, "description": "The assignment does not exist."}},
)
def delete_tag_assignment(assignment_id: int, session: DatabaseSession) -> Response:
    """Remove an assignment and its join rows; definitions remain reusable taxonomy nodes."""
    assignment = session.get(TagAssignment, assignment_id)
    if assignment is None:
        raise HTTPException(
            status_code=404,
            detail={"code": "tag_assignment_not_found", "message": "The tag assignment does not exist."},
        )
    for link in session.scalars(
        select(TagAssignmentEvidence).where(TagAssignmentEvidence.tag_assignment_id == assignment_id)
    ):
        session.delete(link)
    session.delete(assignment)
    session.commit()
    return Response(status_code=204)


def _http_error(error: TagError) -> HTTPException:
    return HTTPException(
        status_code=error.status_code,
        detail={"code": error.code, "message": error.message},
    )
