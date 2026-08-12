"""Contract tests for append-only artifact editing and markdown download."""

import httpx
import pytest
from sqlalchemy.orm import Session

from app.models import Artifact, Source
from tests.api.conftest import ApiHarness


async def request(
    harness: ApiHarness, method: str, path: str, **kwargs: object
) -> httpx.Response:
    """Issue one ASGI request against the application under test."""
    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=harness.app), base_url="http://testserver"
    ) as client:
        return await client.request(method, path, **kwargs)


def add_source_and_artifact(session: Session) -> tuple[Source, Artifact]:
    """Persist a canonical source and one generated artifact for editing."""
    source = Source(
        canonical_url="https://example.com/reasoning",
        platform="web",
        title="Reasoning at Scale",
        raw_text="Original immutable raw material.",
        source_markdown="# Original",
        metadata_json={},
        import_status="ready",
    )
    artifact = Artifact(
        source=source,
        kind="summary",
        title="Original summary",
        markdown="# Original summary",
        language="en",
        model_metadata_json={"provider": "fixture"},
    )
    session.add_all([source, artifact])
    session.commit()
    session.refresh(source)
    session.refresh(artifact)
    return source, artifact


@pytest.mark.asyncio
async def test_artifact_edit_creates_a_new_user_edit_version(
    api_harness: ApiHarness,
) -> None:
    with api_harness.session_factory() as session:
        source, artifact = add_source_and_artifact(session)

    response = await request(
        api_harness,
        "PATCH",
        f"/api/artifacts/{artifact.id}",
        json={"title": "Edited summary", "markdown": "# Edited", "language": "zh"},
    )

    assert response.status_code == 200
    edit = response.json()
    assert edit["id"] != artifact.id
    assert edit["kind"] == "user_edit"
    assert edit["source_id"] == source.id
    assert edit["parent_artifact_id"] == artifact.id
    with api_harness.session_factory() as session:
        persisted_source = session.get(Source, source.id)
        persisted_original = session.get(Artifact, artifact.id)
        assert persisted_source is not None
        assert persisted_source.raw_text == "Original immutable raw material."
        assert persisted_original is not None
        assert persisted_original.markdown == "# Original summary"


@pytest.mark.asyncio
async def test_artifact_download_returns_markdown_attachment(
    api_harness: ApiHarness,
) -> None:
    with api_harness.session_factory() as session:
        _, artifact = add_source_and_artifact(session)

    response = await request(
        api_harness, "GET", f"/api/artifacts/{artifact.id}/download"
    )

    assert response.status_code == 200
    assert response.headers["content-type"].startswith("text/markdown")
    assert response.headers["content-disposition"].endswith('.md"')
    assert response.text == "# Original summary"


@pytest.mark.asyncio
async def test_artifact_edit_uses_a_structured_not_found_error(
    api_harness: ApiHarness,
) -> None:
    response = await request(
        api_harness, "PATCH", "/api/artifacts/999", json={"markdown": "# Missing"}
    )

    assert response.status_code == 404
    assert response.json()["detail"]["code"] == "artifact_not_found"


@pytest.mark.asyncio
async def test_artifact_edit_rejects_markdown_beyond_the_persistence_budget(
    api_harness: ApiHarness,
) -> None:
    """User edits stay within the bounded document contract before database work."""
    with api_harness.session_factory() as session:
        _, artifact = add_source_and_artifact(session)

    response = await request(
        api_harness,
        "PATCH",
        f"/api/artifacts/{artifact.id}",
        json={"markdown": "x" * 100_001},
    )

    assert response.status_code == 422
    assert response.json()["detail"]["code"] == "invalid_request"
