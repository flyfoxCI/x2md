"""Contract tests for source library search and detail endpoints."""

import httpx
import pytest
from sqlalchemy.orm import Session

from app.models import Artifact, KnowledgeNote, Source
from tests.api.conftest import ApiHarness


async def request(
    harness: ApiHarness, method: str, path: str, **kwargs: object
) -> httpx.Response:
    """Issue one ASGI request without opening an external connection."""
    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=harness.app), base_url="http://testserver"
    ) as client:
        return await client.request(method, path, **kwargs)


def add_source(session: Session, source: Source) -> Source:
    """Persist a source for a library read-contract setup."""
    session.add(source)
    session.commit()
    session.refresh(source)
    return source


@pytest.mark.asyncio
async def test_sources_searches_title_and_url_and_paginates(
    api_harness: ApiHarness,
) -> None:
    with api_harness.session_factory() as session:
        first = add_source(
            session,
            Source(
                canonical_url="https://example.com/reasoning",
                platform="web",
                title="Reasoning at Scale",
                raw_text="Raw one",
                source_markdown="# One",
                metadata_json={},
                import_status="ready",
            ),
        )
        add_source(
            session,
            Source(
                canonical_url="https://example.com/other",
                platform="github",
                title="Other library entry",
                raw_text="Raw two",
                source_markdown="# Two",
                metadata_json={},
                import_status="ready",
            ),
        )

    by_title = await request(api_harness, "GET", "/api/sources?q=reasoning")
    by_url = await request(api_harness, "GET", "/api/sources?q=other&page_size=1")

    assert by_title.status_code == 200
    assert by_title.json()["total"] == 1
    assert by_title.json()["items"][0]["id"] == first.id
    assert by_url.status_code == 200
    assert by_url.json()["page"] == 1
    assert by_url.json()["page_size"] == 1
    assert by_url.json()["items"][0]["canonical_url"] == "https://example.com/other"


@pytest.mark.asyncio
async def test_source_detail_returns_canonical_source_artifacts_and_status(
    api_harness: ApiHarness,
) -> None:
    with api_harness.session_factory() as session:
        source = add_source(
            session,
            Source(
                canonical_url="https://example.com/reasoning",
                platform="web",
                title="Reasoning at Scale",
                raw_text="Immutable raw material.",
                source_markdown="# Original",
                metadata_json={"fixture": True},
                import_status="partial",
                failure_reason="transcript_unavailable",
            ),
        )
        session.add(
            Artifact(
                source_id=source.id,
                kind="summary",
                title="Summary",
                markdown="# Summary",
                model_metadata_json={},
            )
        )
        session.commit()

    response = await request(api_harness, "GET", f"/api/sources/{source.id}")

    assert response.status_code == 200
    assert response.json()["source"]["raw_text"] == "Immutable raw material."
    assert response.json()["source"]["import_status"] == "partial"
    assert response.json()["artifacts"][0]["title"] == "Summary"


@pytest.mark.asyncio
async def test_source_detail_uses_a_structured_not_found_error(
    api_harness: ApiHarness,
) -> None:
    response = await request(api_harness, "GET", "/api/sources/999")

    assert response.status_code == 404
    assert response.json()["detail"]["code"] == "source_not_found"


@pytest.mark.asyncio
async def test_sources_filters_by_a_knowledge_note_tag_without_duplicates(
    api_harness: ApiHarness,
) -> None:
    with api_harness.session_factory() as session:
        tagged = add_source(
            session,
            Source(
                canonical_url="https://example.com/tagged",
                platform="web",
                title="Tagged source",
                raw_text="Tagged raw",
                source_markdown="# Tagged",
                metadata_json={},
                import_status="ready",
            ),
        )
        untagged = add_source(
            session,
            Source(
                canonical_url="https://example.com/untagged",
                platform="web",
                title="Untagged source",
                raw_text="Untagged raw",
                source_markdown="# Untagged",
                metadata_json={},
                import_status="ready",
            ),
        )
        session.add_all(
            [
                KnowledgeNote(source_id=tagged.id, tags_json=["machine-learning", "ai"]),
                KnowledgeNote(source_id=tagged.id, tags_json=["machine-learning"]),
                KnowledgeNote(source_id=untagged.id, tags_json=["reference"]),
            ]
        )
        session.commit()

    matching = await request(api_harness, "GET", "/api/sources?tag=machine-learning")
    missing = await request(api_harness, "GET", "/api/sources?tag=missing")

    assert matching.status_code == 200
    assert matching.json()["total"] == 1
    assert [item["id"] for item in matching.json()["items"]] == [tagged.id]
    assert missing.status_code == 200
    assert missing.json()["items"] == []
