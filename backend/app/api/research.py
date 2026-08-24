"""Additive APIs for durable research runs and paginated evidence inspection."""

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel
from sqlalchemy import func, select

from app.api.dependencies import (
    DatabaseSession,
    ResearchOrchestratorDependency,
    require_csrf,
)
from app.models import ResearchEvidence, ResearchRun
from app.schemas import ApiErrorResponse, ResearchEvidenceRead, ResearchRunRead
from app.services.research.orchestrator import ResearchError

sources_router = APIRouter(prefix="/api/sources", tags=["research"])
router = APIRouter(prefix="/api/research-runs", tags=["research"])


class EvidencePageRead(BaseModel):
    """A stable page of evidence rows belonging to one research run."""

    items: list[ResearchEvidenceRead]
    total: int
    page: int
    page_size: int


@sources_router.post(
    "/{source_id}/research",
    dependencies=[Depends(require_csrf)],
    response_model=ResearchRunRead,
    status_code=202,
    responses={
        404: {"model": ApiErrorResponse, "description": "The source does not exist."},
        422: {"model": ApiErrorResponse, "description": "The source is unsupported."},
    },
)
def start_research(
    source_id: int, orchestrator: ResearchOrchestratorDependency
) -> ResearchRunRead:
    """Queue a manual run or return the existing queued/running run for this source."""
    try:
        return ResearchRunRead.model_validate(orchestrator.enqueue(source_id, trigger="manual"))
    except ResearchError as error:
        raise _http_error(error) from error


@router.get(
    "/{run_id}",
    response_model=ResearchRunRead,
    responses={404: {"model": ApiErrorResponse, "description": "The run does not exist."}},
)
def get_research_run(run_id: int, session: DatabaseSession) -> ResearchRunRead:
    """Read persisted state without exposing a worker lease or provider secret."""
    run = session.get(ResearchRun, run_id)
    if run is None:
        raise HTTPException(
            status_code=404,
            detail={"code": "research_run_not_found", "message": "The research run does not exist."},
        )
    return ResearchRunRead.model_validate(run)


@router.get(
    "/{run_id}/evidence",
    response_model=EvidencePageRead,
    responses={404: {"model": ApiErrorResponse, "description": "The run does not exist."}},
)
def list_research_evidence(
    run_id: int,
    session: DatabaseSession,
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=20, ge=1, le=100),
) -> EvidencePageRead:
    """Page stored evidence in deterministic collector order."""
    if session.get(ResearchRun, run_id) is None:
        raise HTTPException(
            status_code=404,
            detail={"code": "research_run_not_found", "message": "The research run does not exist."},
        )
    statement = select(ResearchEvidence).where(ResearchEvidence.research_run_id == run_id)
    total = session.scalar(select(func.count()).select_from(statement.subquery())) or 0
    evidence = list(
        session.scalars(
            statement.order_by(ResearchEvidence.ordinal, ResearchEvidence.id)
            .offset((page - 1) * page_size)
            .limit(page_size)
        )
    )
    return EvidencePageRead(
        items=[ResearchEvidenceRead.model_validate(item) for item in evidence],
        total=total,
        page=page,
        page_size=page_size,
    )


def _http_error(error: ResearchError) -> HTTPException:
    return HTTPException(
        status_code=error.status_code,
        detail={"code": error.code, "message": error.message},
    )
