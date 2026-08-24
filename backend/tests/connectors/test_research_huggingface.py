"""Bounded Hugging Face config/source research collection contracts."""

import hashlib
import json
from collections.abc import Mapping
from dataclasses import dataclass
from types import SimpleNamespace

import pytest

from app.services.research.collectors.huggingface import HuggingFaceResearchCollector


@dataclass(frozen=True)
class FakeResponse:
    status_code: int
    headers: Mapping[str, str]
    content: bytes


class FakeSafeHttpClient:
    def __init__(self, responses: Mapping[str, FakeResponse]) -> None:
        self._responses = responses
        self.requests: list[str] = []

    async def get_public(self, url: str, **_: object) -> FakeResponse:
        self.requests.append(url)
        return self._responses[url]


def _json_response(payload: object) -> FakeResponse:
    return FakeResponse(200, {"content-type": "application/json"}, json.dumps(payload).encode())


def _text_response(content: str) -> FakeResponse:
    return FakeResponse(200, {"content-type": "text/plain"}, content.encode())


@pytest.fixture
def blog_article_source() -> SimpleNamespace:
    return SimpleNamespace(
        canonical_url="https://huggingface.co/blog/openenv-agentic-rl",
        platform="huggingface",
        metadata_json={
            "resource_type": "blog_article",
            "blog_slug": "openenv-agentic-rl",
        },
    )


@pytest.fixture
def ready_blog_response() -> FakeResponse:
    return FakeResponse(
        200,
        {"content-type": "text/html"},
        b"""
        <html>
          <head><title>OpenEnv Agentic RL</title></head>
          <body><article><p>Train agents in reproducible environments.</p></article></body>
        </html>
        """,
    )


@pytest.fixture
def oversized_blog_response() -> FakeResponse:
    article = "x" * 1_048_577
    return FakeResponse(
        200,
        {"content-type": "text/html"},
        f"<html><head><title>Large article</title></head><body><article><p>{article}</p></article></body></html>".encode(),
    )


@pytest.mark.asyncio
async def test_hub_collector_refetches_blog_article_as_single_hash_versioned_evidence(
    blog_article_source: SimpleNamespace,
    ready_blog_response: FakeResponse,
) -> None:
    article_url = blog_article_source.canonical_url
    incorrect_api_url = "https://huggingface.co/api/models/blog/openenv-agentic-rl"
    client = FakeSafeHttpClient(
        {
            article_url: ready_blog_response,
            incorrect_api_url: FakeResponse(404, {"content-type": "application/json"}, b"{}"),
        }
    )

    result = await HuggingFaceResearchCollector(client).collect(blog_article_source)

    content = "Train agents in reproducible environments."
    source_revision = hashlib.sha256(content.encode("utf-8")).hexdigest()
    assert result.source_revision == source_revision
    assert len(result.evidence) == 1
    evidence = result.evidence[0]
    assert evidence.kind == "blog_article"
    assert evidence.locator == "huggingface://blog/openenv-agentic-rl#article"
    assert evidence.ordinal == 0
    assert evidence.decision == "included"
    assert evidence.title == "OpenEnv Agentic RL"
    assert evidence.content == content
    assert evidence.source_revision == source_revision
    assert result.coverage == {
        "complete": True,
        "included_count": 1,
        "excluded_count": 0,
        "requests_used": 1,
        "source_type": "blog_article",
    }
    assert client.requests == [article_url]


@pytest.mark.asyncio
async def test_hub_collector_rejects_blog_article_content_over_the_evidence_budget(
    blog_article_source: SimpleNamespace,
    oversized_blog_response: FakeResponse,
) -> None:
    article_url = blog_article_source.canonical_url
    incorrect_api_url = "https://huggingface.co/api/models/blog/openenv-agentic-rl"
    client = FakeSafeHttpClient(
        {
            article_url: oversized_blog_response,
            incorrect_api_url: FakeResponse(404, {"content-type": "application/json"}, b"{}"),
        }
    )

    result = await HuggingFaceResearchCollector(client).collect(blog_article_source)

    assert result.source_revision is None
    assert result.evidence == ()
    assert result.coverage == {
        "complete": False,
        "included_count": 0,
        "excluded_count": 0,
        "reason": "response_too_large",
        "requests_used": 1,
        "source_type": "blog_article",
    }
    assert client.requests == [article_url]


@pytest.mark.asyncio
async def test_hub_collector_preserves_non_ready_blog_article_failure_reason(
    blog_article_source: SimpleNamespace,
) -> None:
    article_url = blog_article_source.canonical_url
    incorrect_api_url = "https://huggingface.co/api/models/blog/openenv-agentic-rl"
    client = FakeSafeHttpClient(
        {
            article_url: FakeResponse(
                503,
                {"content-type": "text/html"},
                b"<html><body>Unavailable</body></html>",
            ),
            incorrect_api_url: FakeResponse(404, {"content-type": "application/json"}, b"{}"),
        }
    )

    result = await HuggingFaceResearchCollector(client).collect(blog_article_source)

    assert result.source_revision is None
    assert result.evidence == ()
    assert result.coverage == {
        "complete": False,
        "included_count": 0,
        "excluded_count": 0,
        "reason": "http_status",
        "requests_used": 1,
        "source_type": "blog_article",
    }
    assert client.requests == [article_url]


@pytest.mark.asyncio
async def test_hub_collector_studies_card_config_and_source_without_downloading_weights() -> None:
    repository = "openai/expert-encoder"
    revision = "c" * 40
    api_url = f"https://huggingface.co/api/models/{repository}"
    payload = {
        "id": repository,
        "sha": revision,
        "siblings": [
            {"rfilename": "README.md", "size": 10},
            {"rfilename": "config.json", "size": 10},
            {"rfilename": "modeling_expert.py", "size": 10},
            {"rfilename": "model.safetensors", "size": 1_000_000},
            {"rfilename": "train.parquet", "size": 1_000_000},
        ],
    }
    selected = ("README.md", "config.json", "modeling_expert.py")
    responses: dict[str, FakeResponse] = {api_url: _json_response(payload)}
    for filename in selected:
        responses[f"https://huggingface.co/{repository}/raw/{revision}/{filename}"] = _text_response(
            f"contents of {filename}"
        )
    client = FakeSafeHttpClient(responses)

    result = await HuggingFaceResearchCollector(client).collect(
        SimpleNamespace(
            canonical_url=f"https://huggingface.co/{repository}",
            platform="huggingface",
            metadata_json={"id": repository, "repository_type": "model"},
        )
    )

    included = tuple(item for item in result.evidence if item.decision == "included")
    excluded = {item.title: item for item in result.evidence if item.decision == "excluded"}
    assert tuple(item.title for item in included) == selected
    assert all(f"@{revision}/" in item.locator for item in included)
    assert excluded["model.safetensors"].exclusion_reason == "weight_or_payload"
    assert excluded["train.parquet"].exclusion_reason == "weight_or_payload"
    assert not any("model.safetensors" in request for request in client.requests)
    assert result.coverage["complete"] is False
    assert result.coverage["reason"] == "material_excluded"
