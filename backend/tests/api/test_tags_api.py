"""Public API contracts for taxonomy reads and explicit user tag decisions."""

import httpx
import pytest

from app.models import Source, TagAssignment, TagDefinition
from tests.api.conftest import ApiHarness
from tests.api.test_sources import add_source


async def request(harness: ApiHarness, method: str, path: str, **kwargs: object) -> httpx.Response:
    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=harness.app), base_url="http://testserver"
    ) as client:
        return await client.request(method, path, **kwargs)


@pytest.mark.asyncio
async def test_tags_api_reads_taxonomy_and_governs_custom_and_suggested_assignments(
    api_harness: ApiHarness,
) -> None:
    with api_harness.session_factory() as session:
        source = add_source(
            session,
            Source(
                canonical_url="https://example.com/tags-api",
                platform="github",
                title="Tags API",
                raw_text="raw",
                source_markdown="raw",
                import_status="ready",
            ),
        )
        definition = TagDefinition(slug="suggested", label="Suggested", is_system=False)
        session.add(definition)
        session.flush()
        suggested = TagAssignment(
            source_id=source.id,
            tag_id=definition.id,
            origin="ai",
            status="suggested",
            confidence=0.7,
        )
        session.add(suggested)
        session.commit()

    tree = await request(api_harness, "GET", "/api/tags")
    custom = await request(
        api_harness, "POST", f"/api/sources/{source.id}/tags", json={"label": "内部评审"}
    )
    accepted = await request(
        api_harness,
        "PATCH",
        f"/api/tag-assignments/{suggested.id}",
        json={"status": "accepted"},
    )
    removed = await request(api_harness, "DELETE", f"/api/tag-assignments/{custom.json()['id']}")

    assert tree.status_code == 200
    assert any(item["slug"] == "method" for item in tree.json()["items"])
    assert custom.status_code == 201 and custom.json()["status"] == "accepted"
    assert accepted.status_code == 200 and accepted.json()["status"] == "accepted"
    assert removed.status_code == 204
