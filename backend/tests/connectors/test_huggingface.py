"""Fixture tests for the public Hugging Face Hub connector."""

from collections.abc import Mapping
from dataclasses import dataclass
from pathlib import Path

import pytest

from app.services.connectors.huggingface import HuggingFaceConnector
from app.services.connectors.router import ConnectorRouter
from app.services.connectors.web import WebConnector


@dataclass(frozen=True)
class FakeResponse:
    status_code: int
    headers: Mapping[str, str]
    content: bytes


class FakeSafeHttpClient:
    def __init__(self, responses: Mapping[str, FakeResponse | BaseException]) -> None:
        self._responses = responses
        self.requests: list[tuple[str, Mapping[str, object]]] = []

    async def get_public(self, url: str, **kwargs: object) -> FakeResponse:
        self.requests.append((url, kwargs))
        response = self._responses[url]
        if isinstance(response, BaseException):
            raise response
        return response


def _fixture_bytes(name: str) -> bytes:
    return (Path(__file__).parents[1] / "fixtures" / name).read_bytes()


@pytest.mark.asyncio
async def test_huggingface_connector_normalizes_a_public_model_card() -> None:
    url = "https://huggingface.co/openai/expert-encoder?library=transformers"
    api_url = "https://huggingface.co/api/models/openai/expert-encoder"
    card_url = "https://huggingface.co/openai/expert-encoder/raw/main/README.md"
    client = FakeSafeHttpClient(
        {
            api_url: FakeResponse(
                200,
                {"content-type": "application/json"},
                _fixture_bytes("huggingface_model.json"),
            ),
            card_url: FakeResponse(
                200,
                {"content-type": "text/markdown"},
                _fixture_bytes("huggingface_model_card.md"),
            ),
        }
    )

    source = await HuggingFaceConnector(client).fetch(url)

    assert source.status == "ready"
    assert source.platform == "huggingface"
    assert source.canonical_url == "https://huggingface.co/openai/expert-encoder"
    assert source.title == "openai/expert-encoder"
    assert source.author == "openai"
    assert source.text == _fixture_bytes("huggingface_model_card.md").decode()
    assert source.markdown == source.text
    assert source.metadata == {
        "downloads": 1250,
        "gated": False,
        "id": "openai/expert-encoder",
        "last_modified": "2026-08-10T12:00:00.000Z",
        "library_name": "transformers",
        "likes": 42,
        "pipeline_tag": "text-generation",
        "repository_type": "model",
        "tags": ("transformers", "text-generation"),
    }
    assert source.provenance == {
        "metadata": "huggingface_hub",
        "card": "huggingface_raw",
    }
    assert client.requests == [
        (api_url, {"headers": {"accept": "application/json"}}),
        (card_url, {"headers": {"accept": "text/markdown, text/plain;q=0.9"}}),
    ]


@pytest.mark.asyncio
async def test_huggingface_connector_normalizes_a_public_dataset_card() -> None:
    url = "https://huggingface.co/datasets/openai/expert-traces"
    api_url = "https://huggingface.co/api/datasets/openai/expert-traces"
    card_url = "https://huggingface.co/datasets/openai/expert-traces/raw/main/README.md"
    client = FakeSafeHttpClient(
        {
            api_url: FakeResponse(
                200,
                {"content-type": "application/json"},
                _fixture_bytes("huggingface_dataset.json"),
            ),
            card_url: FakeResponse(
                200,
                {"content-type": "text/plain"},
                _fixture_bytes("huggingface_dataset_card.md"),
            ),
        }
    )

    source = await HuggingFaceConnector(client).fetch(url)

    assert source.status == "ready"
    assert source.canonical_url == url
    assert source.title == "openai/expert-traces"
    assert source.metadata["repository_type"] == "dataset"
    assert source.metadata["tags"] == ("reasoning", "dataset")
    assert source.text.startswith("# Expert Traces")


@pytest.mark.asyncio
async def test_huggingface_connector_marks_an_unavailable_card_partial() -> None:
    url = "https://huggingface.co/openai/expert-encoder"
    client = FakeSafeHttpClient(
        {
            "https://huggingface.co/api/models/openai/expert-encoder": FakeResponse(
                200,
                {"content-type": "application/json"},
                _fixture_bytes("huggingface_model.json"),
            ),
            "https://huggingface.co/openai/expert-encoder/raw/main/README.md": FakeResponse(
                404, {"content-type": "text/plain"}, b"not found"
            ),
        }
    )

    source = await HuggingFaceConnector(client).fetch(url)

    assert source.status == "partial"
    assert source.reason == "card_unavailable"
    assert source.text == ""
    assert source.metadata["id"] == "openai/expert-encoder"


@pytest.mark.asyncio
async def test_huggingface_connector_blocks_gated_repositories_without_fetching_cards() -> (
    None
):
    url = "https://huggingface.co/openai/gated-expert-model"
    api_url = "https://huggingface.co/api/models/openai/gated-expert-model"
    client = FakeSafeHttpClient(
        {
            api_url: FakeResponse(
                200,
                {"content-type": "application/json"},
                _fixture_bytes("huggingface_gated_model.json"),
            )
        }
    )

    source = await HuggingFaceConnector(client).fetch(url)

    assert source.status == "blocked"
    assert source.reason == "restricted_repository"
    assert source.text == ""
    assert client.requests == [(api_url, {"headers": {"accept": "application/json"}})]


@pytest.mark.asyncio
async def test_huggingface_connector_blocks_unsupported_paths_and_router_selects_it_for_hub() -> (
    None
):
    client = FakeSafeHttpClient({})
    connector = HuggingFaceConnector(client)
    router = ConnectorRouter(
        generic_connector=WebConnector(client), connectors=(connector,)
    )

    source = await router.fetch("https://huggingface.co/spaces/openai/demo")

    assert router.select("https://huggingface.co/spaces/openai/demo") is connector
    assert source.status == "blocked"
    assert source.reason == "unsupported_huggingface_url"
    assert client.requests == []


@pytest.mark.asyncio
async def test_huggingface_connector_blocks_malformed_repository_json() -> None:
    url = "https://huggingface.co/openai/expert-encoder"
    client = FakeSafeHttpClient(
        {
            "https://huggingface.co/api/models/openai/expert-encoder": FakeResponse(
                200,
                {"content-type": "application/json"},
                _fixture_bytes("huggingface_malformed.json"),
            )
        }
    )

    source = await HuggingFaceConnector(client).fetch(url)

    assert source.status == "blocked"
    assert source.reason == "invalid_repository_response"
    assert source.text == ""


@pytest.mark.asyncio
async def test_huggingface_connector_blocks_octet_stream_card_before_decoding() -> None:
    url = "https://huggingface.co/openai/expert-encoder"
    client = FakeSafeHttpClient(
        {
            "https://huggingface.co/api/models/openai/expert-encoder": FakeResponse(
                200,
                {"content-type": "application/json"},
                _fixture_bytes("huggingface_model.json"),
            ),
            "https://huggingface.co/openai/expert-encoder/raw/main/README.md": FakeResponse(
                200,
                {"content-type": "application/octet-stream"},
                b"binary-card-content",
            ),
        }
    )

    source = await HuggingFaceConnector(client).fetch(url)

    assert source.status == "blocked"
    assert source.reason == "unsupported_mime"
    assert source.metadata["http_status"] == 200
    assert source.metadata["content_type"] == "application/octet-stream"
    assert source.text == ""


@pytest.mark.asyncio
async def test_huggingface_connector_applies_response_policy_before_non_success_card_status() -> (
    None
):
    url = "https://huggingface.co/openai/expert-encoder"
    client = FakeSafeHttpClient(
        {
            "https://huggingface.co/api/models/openai/expert-encoder": FakeResponse(
                200,
                {"content-type": "application/json"},
                _fixture_bytes("huggingface_model.json"),
            ),
            "https://huggingface.co/openai/expert-encoder/raw/main/README.md": FakeResponse(
                404,
                {"content-type": "application/octet-stream"},
                b"untrusted error body",
            ),
        }
    )

    source = await HuggingFaceConnector(client).fetch(url)

    assert source.status == "blocked"
    assert source.reason == "unsupported_mime"
    assert source.metadata == {
        "http_status": 404,
        "content_type": "application/octet-stream",
    }


@pytest.mark.asyncio
async def test_huggingface_connector_blocks_credentialed_url_before_path_parsing_or_dispatch() -> (
    None
):
    client = FakeSafeHttpClient({})

    source = await HuggingFaceConnector(client).fetch(
        "https://user:credential@huggingface.co/openai/expert-encoder"
    )

    assert source.status == "blocked"
    assert source.reason == "unsafe_url"
    assert "credential" not in repr(source)
    assert client.requests == []
