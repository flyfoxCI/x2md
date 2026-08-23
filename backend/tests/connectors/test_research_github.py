"""Bounded, revision-pinned GitHub research collection contracts."""

import json
from collections.abc import Mapping
from dataclasses import dataclass
from types import SimpleNamespace

import pytest

from app.services.research.collectors.github import GitHubResearchCollector


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
    return FakeResponse(
        status_code=200,
        headers={"content-type": "application/json"},
        content=json.dumps(payload).encode(),
    )


def _text_response(content: str) -> FakeResponse:
    return FakeResponse(
        status_code=200,
        headers={"content-type": "text/plain; charset=utf-8"},
        content=content.encode(),
    )


@pytest.mark.asyncio
async def test_github_research_collector_selects_revision_pinned_text_evidence() -> None:
    repository = "openai/expert-reasoner"
    sha = "a" * 40
    tree = [
        {"path": "README.md", "type": "blob", "size": 12},
        {"path": "pyproject.toml", "type": "blob", "size": 12},
        {"path": "app/main.py", "type": "blob", "size": 12},
        {"path": "docs/architecture.md", "type": "blob", "size": 12},
        {"path": "src/engine.py", "type": "blob", "size": 12},
        {"path": "web.min.js", "type": "blob", "size": 12},
        {"path": "assets/logo.png", "type": "blob", "size": 12},
        {"path": "node_modules/example/index.js", "type": "blob", "size": 12},
    ]
    tree.extend(
        {"path": f"src/module_{index:02}.py", "type": "blob", "size": 12}
        for index in range(25)
    )
    api = f"https://api.github.com/repos/{repository}"
    ref = f"{api}/git/ref/heads/main"
    tree_url = f"{api}/git/trees/{sha}?recursive=1"
    responses: dict[str, FakeResponse] = {
        api: _json_response({"default_branch": "main"}),
        ref: _json_response({"object": {"sha": sha, "type": "commit"}}),
        tree_url: _json_response({"truncated": True, "tree": tree}),
    }
    selected_paths = (
        "README.md",
        "pyproject.toml",
        "app/main.py",
        "docs/architecture.md",
        "src/engine.py",
        *(f"src/module_{index:02}.py" for index in range(15)),
    )
    for path in selected_paths:
        responses[f"https://raw.githubusercontent.com/{repository}/{sha}/{path}"] = (
            _text_response(f"contents of {path}")
        )
    client = FakeSafeHttpClient(responses)

    result = await GitHubResearchCollector(client).collect(
        SimpleNamespace(
            canonical_url=f"https://github.com/{repository}",
            platform="github",
            metadata_json={"repository": repository, "default_branch": "main"},
        )
    )

    included = tuple(item for item in result.evidence if item.decision == "included")
    excluded = {item.locator.rsplit("/", 1)[-1]: item for item in result.evidence if item.decision == "excluded"}
    assert result.source_revision == sha
    assert tuple(item.title for item in included) == selected_paths
    assert len(included) == 20
    assert all(f"@{sha}/" in item.locator for item in included)
    assert excluded["web.min.js"].exclusion_reason == "minified_or_generated"
    assert excluded["logo.png"].exclusion_reason == "binary_or_unsupported"
    assert excluded["index.js"].exclusion_reason == "vendor_or_dependency"
    assert result.coverage["complete"] is False
    assert result.coverage["reason"] == "tree_truncated"
    assert len(client.requests) == 23


@pytest.mark.asyncio
async def test_github_research_collector_stops_before_the_per_run_request_budget() -> None:
    repository = "openai/request-bounded"
    sha = "b" * 40
    tree = [
        {"path": f"src/module_{index:02}.py", "type": "blob", "size": 10}
        for index in range(35)
    ]
    api = f"https://api.github.com/repos/{repository}"
    ref = f"{api}/git/ref/heads/main"
    tree_url = f"{api}/git/trees/{sha}?recursive=1"
    responses: dict[str, FakeResponse] = {
        api: _json_response({"default_branch": "main"}),
        ref: _json_response({"object": {"sha": sha, "type": "commit"}}),
        tree_url: _json_response({"truncated": False, "tree": tree}),
    }
    for item in tree[:20]:
        path = item["path"]
        assert isinstance(path, str)
        responses[f"https://raw.githubusercontent.com/{repository}/{sha}/{path}"] = (
            _text_response("module")
        )
    client = FakeSafeHttpClient(responses)

    result = await GitHubResearchCollector(client).collect(
        SimpleNamespace(
            canonical_url=f"https://github.com/{repository}",
            platform="github",
            metadata_json={},
        )
    )

    assert len(client.requests) == 23
    assert result.coverage["requests_used"] == 23
    assert result.coverage["complete"] is False
    assert result.coverage["excluded_count"] == 15
