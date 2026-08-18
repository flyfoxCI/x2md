"""Source-scoped chat contracts: material, citation provenance, and persistence."""

import json

import httpx
import pytest
from sqlalchemy import select

from app.config import Settings
from app.models import Artifact, ChatTurn, Source
from app.services.ai import AIService
from tests.api.conftest import ApiHarness


async def request(
    harness: ApiHarness, method: str, path: str, **kwargs: object
) -> httpx.Response:
    """Issue a request through the ASGI application."""
    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=harness.app), base_url="http://testserver"
    ) as client:
        return await client.request(method, path, **kwargs)


def chat_service(observed: dict[str, object]) -> AIService:
    """Make a configured response-only fake compatible provider."""
    async def handler(request: httpx.Request) -> httpx.Response:
        observed["payload"] = json.loads(request.content)
        return httpx.Response(
            200,
            json={"choices": [{"message": {"content": "答案只来自给定材料。"}}]},
        )

    return AIService(
        Settings(
            ai_base_url="https://provider.example/v1",
            ai_api_key="chat-provider-secret",
            ai_model="chat-fixture",
            auth_enabled=False,
        ),
        client=httpx.AsyncClient(transport=httpx.MockTransport(handler)),
    )


def add_source_with_artifact(harness: ApiHarness) -> tuple[Source, Artifact]:
    """Persist the only source and artifact eligible for a chat response."""
    with harness.session_factory() as session:
        source = Source(
            canonical_url="https://example.com/grounded",
            platform="web",
            title="Grounded material",
            raw_text="The source says: cite only supplied materials.",
            source_markdown="# Grounded material\n\nCite only supplied materials.",
            metadata_json={},
            import_status="ready",
        )
        session.add(source)
        session.commit()
        artifact = Artifact(
            source_id=source.id,
            kind="summary",
            title="Grounded summary",
            markdown="# Summary\n\nThe artifact is also grounded.",
            language="zh",
            model_metadata_json={},
        )
        session.add(artifact)
        session.commit()
        session.refresh(source)
        session.refresh(artifact)
        return source, artifact


@pytest.mark.asyncio
async def test_chat_persists_answer_with_citations_limited_to_supplied_source_sections(
    api_harness: ApiHarness,
) -> None:
    source, artifact = add_source_with_artifact(api_harness)
    observed: dict[str, object] = {}
    service = chat_service(observed)
    api_harness.app.state.ai_service = service

    response = await request(
        api_harness,
        "POST",
        f"/api/sources/{source.id}/chat",
        json={"question": "这份材料的核心约束是什么？"},
    )

    assert response.status_code == 200
    turn = response.json()
    assert turn["source_id"] == source.id
    assert turn["answer_markdown"] == "答案只来自给定材料。"
    assert turn["citations_json"] == [
        {
            "source_id": source.id,
            "artifact_id": None,
            "url": source.canonical_url,
            "section": "Original source",
        },
        {
            "source_id": source.id,
            "artifact_id": artifact.id,
            "url": source.canonical_url,
            "section": "Artifact: Grounded summary",
        },
    ]
    prompt = observed["payload"]["messages"][1]["content"]
    assert "https://example.com/grounded" in prompt
    assert "Grounded summary" in prompt
    with api_harness.session_factory() as session:
        persisted = session.scalar(select(ChatTurn).where(ChatTurn.id == turn["id"]))
        assert persisted is not None
        assert persisted.citations_json == turn["citations_json"]
    await service.aclose()


@pytest.mark.asyncio
async def test_chat_refuses_empty_imported_material_before_provider_dispatch(
    api_harness: ApiHarness,
) -> None:
    with api_harness.session_factory() as session:
        source = Source(
            canonical_url="https://example.com/empty",
            platform="youtube",
            title="Metadata-only source",
            raw_text="",
            source_markdown="",
            metadata_json={},
            import_status="partial",
            failure_reason="transcript_unavailable",
        )
        session.add(source)
        session.commit()
        session.refresh(source)
    called = False

    async def handler(_: httpx.Request) -> httpx.Response:
        nonlocal called
        called = True
        return httpx.Response(200)

    api_harness.app.state.ai_service = AIService(
        Settings(
            ai_base_url="https://provider.example/v1",
            ai_api_key="configured-secret",
            ai_model="fixture-model",
            auth_enabled=False,
        ),
        client=httpx.AsyncClient(transport=httpx.MockTransport(handler)),
    )

    response = await request(
        api_harness,
        "POST",
        f"/api/sources/{source.id}/chat",
        json={"question": "能否回答？"},
    )

    assert response.status_code == 422
    assert response.json()["detail"]["code"] == "source_unavailable"
    assert called is False
    with api_harness.session_factory() as session:
        assert session.scalars(select(ChatTurn).where(ChatTurn.source_id == source.id)).all() == []


@pytest.mark.asyncio
async def test_chat_rejects_an_overlong_question_before_provider_dispatch(
    api_harness: ApiHarness,
) -> None:
    """Question input has a deliberate bounded contract for the model request."""
    source, _ = add_source_with_artifact(api_harness)
    called = False

    async def handler(_: httpx.Request) -> httpx.Response:
        nonlocal called
        called = True
        return httpx.Response(200)

    service = AIService(
        Settings(
            ai_base_url="https://provider.example/v1",
            ai_api_key="configured-secret",
            ai_model="fixture-model",
            auth_enabled=False,
        ),
        client=httpx.AsyncClient(transport=httpx.MockTransport(handler)),
    )
    api_harness.app.state.ai_service = service

    response = await request(
        api_harness,
        "POST",
        f"/api/sources/{source.id}/chat",
        json={"question": "x" * 1_001},
    )

    assert response.status_code == 422
    assert response.json()["detail"]["code"] == "invalid_request"
    assert called is False
    await service.aclose()
