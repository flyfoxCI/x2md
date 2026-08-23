"""Contract tests for the persisted URL import endpoint."""

import httpx
import pytest
from sqlalchemy import func, select

from app.models import Source
from app.services.connectors.base import NormalizedSource
from tests.api.conftest import ApiHarness


async def post_import(harness: ApiHarness, url: str) -> httpx.Response:
    """Post one import request through the ASGI application."""
    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=harness.app), base_url="http://testserver"
    ) as client:
        return await client.post("/api/imports", json={"url": url})


@pytest.mark.asyncio
async def test_import_persists_connector_output_and_is_idempotent(
    api_harness: ApiHarness,
) -> None:
    url = "https://example.com/reasoning"

    first = await post_import(api_harness, url)
    second = await post_import(api_harness, url)

    assert first.status_code == 200
    assert first.json()["canonical_url"] == url
    assert first.json()["import_status"] == "ready"
    assert first.json()["metadata_json"] == {
        "fixture": True,
        "provenance": {"connector": "fake"},
    }
    assert second.status_code == 200
    assert second.json()["id"] == first.json()["id"]
    assert api_harness.router.requested_urls == [url]
    with api_harness.session_factory() as session:
        assert session.scalar(select(func.count()).select_from(Source)) == 1


@pytest.mark.asyncio
async def test_enabled_auto_research_enqueues_only_supported_content_bearing_imports(
    api_harness: ApiHarness,
) -> None:
    class RecordingOrchestrator:
        def __init__(self) -> None:
            self.calls: list[tuple[int, str]] = []

        def enqueue(self, source_id: int, *, trigger: str) -> None:
            self.calls.append((source_id, trigger))

    orchestrator = RecordingOrchestrator()
    api_harness.app.state.research_orchestrator = orchestrator
    url = "https://github.com/openai/auto-research"
    api_harness.router.sources[url] = NormalizedSource(
        canonical_url=url,
        platform="github",
        title="Auto research",
        text="Repository README",
        markdown="# Repository README",
        status="ready",
    )
    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=api_harness.app), base_url="http://testserver"
    ) as client:
        settings = await client.patch(
            "/api/settings", json={"research": {"autoStart": True}}
        )
        response = await client.post("/api/imports", json={"url": url})

    assert settings.status_code == 200
    assert settings.json()["research"] == {"autoStart": True}
    assert response.status_code == 200
    assert orchestrator.calls == [(response.json()["id"], "auto")]


@pytest.mark.asyncio
async def test_import_rejects_invalid_urls_before_connector_dispatch(
    api_harness: ApiHarness,
) -> None:
    response = await post_import(api_harness, "http://127.0.0.1/private")

    assert response.status_code == 422
    assert response.json()["detail"]["code"] == "unsupported_url"
    assert api_harness.router.requested_urls == []


@pytest.mark.asyncio
async def test_import_maps_blocked_connector_status_to_a_structured_error(
    api_harness: ApiHarness,
) -> None:
    url = "https://example.com/restricted"
    api_harness.router.sources[url] = NormalizedSource(
        canonical_url=url,
        platform="web",
        title="Restricted source",
        text="",
        markdown="",
        status="blocked",
        reason="restricted_source",
    )

    response = await post_import(api_harness, url)

    assert response.status_code == 422
    assert response.json()["detail"] == {
        "code": "restricted_source",
        "message": "The source is restricted or unavailable.",
    }
    with api_harness.session_factory() as session:
        assert session.scalar(select(func.count()).select_from(Source)) == 0


@pytest.mark.asyncio
async def test_import_keeps_partial_connector_results_with_their_status(
    api_harness: ApiHarness,
) -> None:
    url = "https://example.com/partial"
    api_harness.router.sources[url] = NormalizedSource(
        canonical_url=url,
        platform="youtube",
        title="Metadata-only video",
        text="",
        markdown="",
        status="partial",
        reason="transcript_unavailable",
        metadata={"video_id": "abc123def45"},
    )

    response = await post_import(api_harness, url)

    assert response.status_code == 200
    assert response.json()["import_status"] == "partial"
    assert response.json()["failure_reason"] == "transcript_unavailable"


@pytest.mark.asyncio
async def test_import_normalizes_every_blocked_connector_reason(
    api_harness: ApiHarness,
) -> None:
    expectations = {
        "unsafe_url": "unsupported_url",
        "unsupported_github_url": "unsupported_url",
        "private_repository": "restricted_source",
        "restricted_repository": "restricted_source",
        "restricted_source": "restricted_source",
        "network_error": "source_unavailable",
        "rate_limited": "source_unavailable",
        "response_too_large": "source_unavailable",
        "unsupported_mime": "source_unavailable",
        "invalid_post_response": "source_unavailable",
        "readme_unavailable": "source_unavailable",
        "post_text_unavailable": "source_unavailable",
    }
    for index, (reason, code) in enumerate(expectations.items()):
        url = f"https://example.com/blocked-{index}"
        api_harness.router.sources[url] = NormalizedSource(
            canonical_url=url,
            platform="web",
            title="Blocked source",
            text="",
            markdown="",
            status="blocked",
            reason=reason,
        )

        response = await post_import(api_harness, url)

        assert response.status_code == 422
        assert response.json()["detail"]["code"] == code


@pytest.mark.asyncio
async def test_import_returns_the_standard_error_envelope_for_malformed_payload(
    api_harness: ApiHarness,
) -> None:
    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=api_harness.app), base_url="http://testserver"
    ) as client:
        response = await client.post("/api/imports", json={})

    assert response.status_code == 422
    assert response.json() == {
        "detail": {
            "code": "invalid_request",
            "message": "The request payload is invalid.",
        }
    }


@pytest.mark.asyncio
async def test_openapi_documents_the_standard_validation_error_envelope(
    api_harness: ApiHarness,
) -> None:
    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=api_harness.app), base_url="http://testserver"
    ) as client:
        schema = (await client.get("/openapi.json")).json()

    assert (
        schema["paths"]["/api/imports"]["post"]["responses"]["422"]["content"]
        ["application/json"]["schema"]["$ref"]
        == "#/components/schemas/ApiErrorResponse"
    )
    assert (
        schema["paths"]["/api/sources"]["get"]["responses"]["422"]["content"]
        ["application/json"]["schema"]["$ref"]
        == "#/components/schemas/ApiErrorResponse"
    )
