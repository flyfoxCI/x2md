"""Bounded Hugging Face config/source research collection contracts."""

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
