"""Public additive API contracts for persistent research runs and evidence."""

import httpx
import pytest

from app.models import ResearchEvidence, Source
from app.services.research.orchestrator import ResearchOrchestrator
from tests.api.conftest import ApiHarness
from tests.api.test_sources import add_source


class UnusedAI:
    """Enqueue tests never execute provider work."""


async def request(harness: ApiHarness, method: str, path: str, **kwargs: object) -> httpx.Response:
    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=harness.app), base_url="http://testserver"
    ) as client:
        return await client.request(method, path, **kwargs)


@pytest.mark.asyncio
async def test_research_api_enqueues_idempotently_and_pages_persisted_evidence(
    api_harness: ApiHarness,
) -> None:
    with api_harness.session_factory() as session:
        source = add_source(
            session,
            Source(
                canonical_url="https://github.com/openai/api-research",
                platform="github",
                title="API research",
                raw_text="raw",
                source_markdown="raw",
                import_status="ready",
            ),
        )
    api_harness.app.state.research_orchestrator = ResearchOrchestrator(
        api_harness.session_factory, collectors={}, ai=UnusedAI()
    )

    first = await request(api_harness, "POST", f"/api/sources/{source.id}/research")
    second = await request(api_harness, "POST", f"/api/sources/{source.id}/research")
    run_id = first.json()["id"]
    with api_harness.session_factory() as session:
        session.add_all(
            [
                ResearchEvidence(
                    research_run_id=run_id,
                    source_id=source.id,
                    locator="github://openai/api-research@abc/README.md",
                    kind="repository_file",
                    ordinal=0,
                    content="evidence",
                    status="included",
                ),
                ResearchEvidence(
                    research_run_id=run_id,
                    source_id=source.id,
                    locator="github://openai/api-research@abc/blob.bin",
                    kind="repository_file",
                    ordinal=1,
                    status="excluded",
                    exclusion_reason="binary_or_unsupported",
                ),
            ]
        )
        session.commit()

    detail = await request(api_harness, "GET", f"/api/research-runs/{run_id}")
    evidence = await request(
        api_harness, "GET", f"/api/research-runs/{run_id}/evidence?page=1&page_size=1"
    )

    assert first.status_code == second.status_code == 202
    assert second.json()["id"] == run_id
    assert detail.status_code == 200
    assert detail.json()["status"] == "queued"
    assert evidence.json()["total"] == 2
    assert len(evidence.json()["items"]) == 1
    assert evidence.json()["items"][0]["locator"].endswith("README.md")


@pytest.mark.asyncio
async def test_research_api_returns_safe_not_found_errors(api_harness: ApiHarness) -> None:
    missing_run = await request(api_harness, "GET", "/api/research-runs/999")
    missing_source = await request(api_harness, "POST", "/api/sources/999/research")

    assert missing_run.status_code == missing_source.status_code == 404
    assert missing_run.json()["detail"]["code"] == "research_run_not_found"
    assert missing_source.json()["detail"]["code"] == "source_not_found"
