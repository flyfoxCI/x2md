"""API contracts for persisted AI-derived artifacts and safe settings."""

import asyncio
import json
from threading import Barrier, Lock

import httpx
import pytest
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.config import Settings
from app.models import AppSetting, Artifact, Source
from app.services.ai import AIService
from tests.api.conftest import ApiHarness


async def request(
    harness: ApiHarness, method: str, path: str, **kwargs: object
) -> httpx.Response:
    """Issue one request through the in-process API application."""
    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=harness.app), base_url="http://testserver"
    ) as client:
        return await client.request(method, path, **kwargs)


async def import_source(harness: ApiHarness, url: str) -> dict[str, object]:
    """Create a ready canonical source using the existing fake connector."""
    response = await request(harness, "POST", "/api/imports", json={"url": url})
    assert response.status_code == 200
    return response.json()


def configured_service(observed: dict[str, object]) -> AIService:
    """Construct a mock OpenAI provider which records the safe request contract."""
    async def handler(request: httpx.Request) -> httpx.Response:
        observed["headers"] = dict(request.headers)
        observed["payload"] = json.loads(request.content)
        return httpx.Response(
            200,
            json={"choices": [{"message": {"content": "# 生成内容\n\n来自来源。"}}]},
        )

    return AIService(
        Settings(
            ai_base_url="https://provider.example/v1",
            ai_api_key="test-provider-key",
            ai_model="fixture-model",
        ),
        client=httpx.AsyncClient(transport=httpx.MockTransport(handler)),
    )


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("kind", "expected_language"),
    [("translation", "zh"), ("skill", "zh")],
)
async def test_derivation_appends_translation_and_skill_artifacts_with_source_provenance(
    api_harness: ApiHarness, kind: str, expected_language: str
) -> None:
    source = await import_source(api_harness, "https://example.com/reasoning")
    observed: dict[str, object] = {}
    service = configured_service(observed)
    api_harness.app.state.ai_service = service

    response = await request(
        api_harness,
        "POST",
        f"/api/sources/{source['id']}/derive",
        json={"kind": kind},
    )

    assert response.status_code == 200
    artifact = response.json()
    assert artifact["kind"] == kind
    assert artifact["source_id"] == source["id"]
    assert artifact["language"] == expected_language
    assert artifact["parent_artifact_id"] is None
    assert artifact["model_metadata_json"] == {
        "model": "fixture-model",
        "provider": "openai_compatible",
    }
    payload = observed["payload"]
    assert isinstance(payload, dict)
    assert "https://example.com/reasoning" in payload["messages"][1]["content"]
    assert "test-provider-key" not in response.text
    with api_harness.session_factory() as session:
        persisted = session.scalar(select(Artifact).where(Artifact.id == artifact["id"]))
        assert persisted is not None
        assert persisted.markdown == "# 生成内容\n\n来自来源。"
    await service.aclose()


@pytest.mark.asyncio
async def test_derivation_reports_unconfigured_provider_without_creating_an_artifact(
    api_harness: ApiHarness,
) -> None:
    source = await import_source(api_harness, "https://example.com/no-provider")

    response = await request(
        api_harness,
        "POST",
        f"/api/sources/{source['id']}/derive",
        json={"kind": "translation"},
    )

    assert response.status_code == 422
    assert response.json()["detail"]["code"] == "provider_not_configured"
    with api_harness.session_factory() as session:
        assert session.scalars(select(Artifact).where(Artifact.source_id == source["id"])).all() == []


@pytest.mark.asyncio
async def test_derivation_refuses_empty_imported_material_before_provider_dispatch(
    api_harness: ApiHarness,
) -> None:
    """Metadata-only imports must not turn into fabricated AI artifacts."""
    with api_harness.session_factory() as session:
        source = Source(
            canonical_url="https://example.com/metadata-only",
            platform="youtube",
            title="Metadata-only video",
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

    service = AIService(
        Settings(
            ai_base_url="https://provider.example/v1",
            ai_api_key="configured-secret",
            ai_model="fixture-model",
        ),
        client=httpx.AsyncClient(transport=httpx.MockTransport(handler)),
    )
    api_harness.app.state.ai_service = service

    response = await request(
        api_harness,
        "POST",
        f"/api/sources/{source.id}/derive",
        json={"kind": "skill"},
    )

    assert response.status_code == 422
    assert response.json()["detail"]["code"] == "source_unavailable"
    assert called is False
    with api_harness.session_factory() as session:
        artifacts = session.scalars(
            select(Artifact).where(Artifact.source_id == source.id)
        ).all()
        assert artifacts == []
    await service.aclose()


@pytest.mark.asyncio
async def test_settings_exposes_and_accepts_only_non_secret_presentation_values(
    api_harness: ApiHarness,
) -> None:
    first = await request(api_harness, "GET", "/api/settings")
    rejected = await request(
        api_harness,
        "PATCH",
        "/api/settings",
        json={"presentation": {"theme": "dark", "ai_api_key": "not-allowed"}},
    )
    saved = await request(
        api_harness,
        "PATCH",
        "/api/settings",
        json={"presentation": {"theme": "dark", "preview_device": "mobile"}},
    )

    assert first.status_code == 200
    assert first.json() == {
        "aiConfigured": False,
        "presentation": {"theme": "system", "preview_device": "desktop"},
    }
    assert rejected.status_code == 422
    assert rejected.json()["detail"]["code"] == "invalid_request"
    assert saved.status_code == 200
    assert saved.json() == {
        "aiConfigured": False,
        "presentation": {"theme": "dark", "preview_device": "mobile"},
    }
    serialized = json.dumps(saved.json())
    assert "api_key" not in serialized.lower()
    assert "bearer" not in serialized.lower()


@pytest.mark.asyncio
async def test_settings_concurrent_first_writes_both_succeed_and_leave_valid_preferences(
    api_harness: ApiHarness, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Two request sessions must safely initialize the initially absent setting."""
    original_get = Session.get
    first_reads = Barrier(2)
    counter_lock = Lock()
    setting_reads = 0

    def synchronize_first_setting_reads(
        session: Session, entity: type[object], ident: object, *args: object, **kwargs: object
    ) -> object:
        nonlocal setting_reads
        setting = original_get(session, entity, ident, *args, **kwargs)
        if entity is AppSetting and ident == "presentation":
            with counter_lock:
                setting_reads += 1
                should_wait = setting_reads <= 2
            if should_wait:
                first_reads.wait(timeout=2)
        return setting

    monkeypatch.setattr(Session, "get", synchronize_first_setting_reads)
    presentations = [
        {"theme": "dark", "preview_device": "mobile"},
        {"theme": "light", "preview_device": "desktop"},
    ]

    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=api_harness.app), base_url="http://testserver"
    ) as client:
        responses = await asyncio.gather(
            *[
                client.patch("/api/settings", json={"presentation": presentation})
                for presentation in presentations
            ]
        )
        saved = await client.get("/api/settings")

    assert [response.status_code for response in responses] == [200, 200]
    assert saved.status_code == 200
    assert saved.json()["presentation"] in presentations
    with api_harness.session_factory() as session:
        assert session.get(AppSetting, "presentation") is not None
