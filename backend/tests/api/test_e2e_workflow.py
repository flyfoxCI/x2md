"""One public API workflow from import through a persisted Skill download."""

from __future__ import annotations

import json

import httpx
import pytest

from app.config import Settings
from app.services.ai import AIService
from tests.api.conftest import ApiHarness, ready_source


@pytest.mark.asyncio
async def test_api_workflow_imports_derives_edits_searches_and_downloads(
    api_harness: ApiHarness,
) -> None:
    """Exercise the user-visible knowledge path without network or real credentials."""
    source_url = "https://example.com/e2e-reasoning"
    api_harness.router.sources[source_url] = ready_source(
        source_url,
        title="Evidence-Grounded Reasoning",
    )

    async def provider(request: httpx.Request) -> httpx.Response:
        assert request.url == "https://provider.invalid/v1/chat/completions"
        assert request.headers["authorization"] == "Bearer fixture-provider-key"
        prompt = json.loads(request.content)["messages"][1]["content"]
        assert source_url in prompt
        return httpx.Response(
            200,
            json={
                "choices": [
                    {"message": {"content": "# 可复用知识\n\n仅基于导入材料。"}}
                ]
            },
        )

    provider_service = AIService(
        Settings(
            ai_base_url="https://provider.invalid/v1",
            ai_api_key="fixture-provider-key",
            ai_model="fixture-model",
        ),
        client=httpx.AsyncClient(transport=httpx.MockTransport(provider)),
    )
    api_harness.app.state.ai_service = provider_service

    try:
        async with httpx.AsyncClient(
            transport=httpx.ASGITransport(app=api_harness.app),
            base_url="http://testserver",
        ) as client:
            imported = await client.post("/api/imports", json={"url": source_url})
            assert imported.status_code == 200
            source = imported.json()
            assert source["canonical_url"] == source_url
            assert source["raw_text"] == "Canonical source material."

            translated = await client.post(
                f"/api/sources/{source['id']}/derive", json={"kind": "translation"}
            )
            skill = await client.post(
                f"/api/sources/{source['id']}/derive", json={"kind": "skill"}
            )
            assert translated.status_code == 200
            assert translated.json()["kind"] == "translation"
            assert skill.status_code == 200
            assert skill.json()["kind"] == "skill"

            edited = await client.patch(
                f"/api/artifacts/{skill.json()['id']}",
                json={"markdown": "# 我的 Skill\n\n可审计的个人版本。", "language": "zh"},
            )
            assert edited.status_code == 200
            assert edited.json()["kind"] == "user_edit"
            assert edited.json()["parent_artifact_id"] == skill.json()["id"]

            library = await client.get("/api/sources", params={"q": "grounded"})
            assert library.status_code == 200
            assert library.json()["total"] == 1
            assert library.json()["items"][0]["id"] == source["id"]

            download = await client.get(f"/api/artifacts/{edited.json()['id']}/download")
            assert download.status_code == 200
            assert download.headers["content-type"].startswith("text/markdown")
            assert download.headers["content-disposition"].endswith('.md"')
            assert download.text == "# 我的 Skill\n\n可审计的个人版本。"
    finally:
        await provider_service.aclose()
