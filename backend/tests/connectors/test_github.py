"""Fixture tests for the public GitHub repository connector."""

import json
from collections.abc import Mapping
from dataclasses import dataclass
from pathlib import Path

import pytest

from app.services.connectors.github import GitHubConnector
from app.services.connectors.router import ConnectorRouter
from app.services.connectors.web import WebConnector
from app.services.url_safety import RateLimitExceededError


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
async def test_github_connector_normalizes_public_repository_readme_without_leaking_token() -> (
    None
):
    repo_url = "https://github.com/openai/expert-reasoner"
    api_url = "https://api.github.com/repos/openai/expert-reasoner"
    readme_url = (
        "https://raw.githubusercontent.com/openai/expert-reasoner/main/README.md"
    )
    client = FakeSafeHttpClient(
        {
            api_url: FakeResponse(
                200,
                {"content-type": "application/json"},
                _fixture_bytes("github_repository.json"),
            ),
            readme_url: FakeResponse(
                200,
                {"content-type": "text/markdown"},
                _fixture_bytes("github_readme.md"),
            ),
        }
    )

    source = await GitHubConnector(client, token="only-on-server").fetch(
        f"{repo_url}?tab=readme"
    )

    assert source.status == "ready"
    assert source.platform == "github"
    assert source.canonical_url == repo_url
    assert source.title == "openai/expert-reasoner"
    assert source.text == _fixture_bytes("github_readme.md").decode()
    assert source.markdown == source.text
    assert source.author == "openai"
    assert source.metadata == {
        "default_branch": "main",
        "description": "Reference implementation for inspectable reasoning.",
        "forks": 7,
        "language": "Python",
        "license": "MIT",
        "repository": "openai/expert-reasoner",
        "stars": 42,
        "topics": ("reasoning", "agents"),
        "updated_at": "2026-08-10T12:00:00Z",
    }
    assert source.provenance == {"metadata": "github_rest", "readme": "github_raw"}
    assert "only-on-server" not in repr(source.metadata)
    assert "only-on-server" not in repr(source.provenance)
    assert client.requests == [
        (
            api_url,
            {
                "headers": {
                    "accept": "application/vnd.github+json",
                    "authorization": "Bearer only-on-server",
                }
            },
        ),
        (readme_url, {"headers": {"accept": "text/markdown, text/plain;q=0.9"}}),
    ]


@pytest.mark.asyncio
async def test_github_connector_marks_a_missing_readme_partial_with_public_metadata() -> (
    None
):
    repo_url = "https://github.com/openai/expert-reasoner"
    client = FakeSafeHttpClient(
        {
            "https://api.github.com/repos/openai/expert-reasoner": FakeResponse(
                200,
                {"content-type": "application/json"},
                _fixture_bytes("github_repository.json"),
            ),
            "https://raw.githubusercontent.com/openai/expert-reasoner/main/README.md": FakeResponse(
                404, {"content-type": "text/plain"}, b"Not Found"
            ),
        }
    )

    source = await GitHubConnector(client).fetch(repo_url)

    assert source.status == "partial"
    assert source.reason == "readme_unavailable"
    assert source.title == "openai/expert-reasoner"
    assert source.text == ""
    assert source.markdown == ""
    assert source.metadata["repository"] == "openai/expert-reasoner"


@pytest.mark.asyncio
async def test_github_connector_blocks_private_repositories_without_fetching_a_readme() -> (
    None
):
    repo_url = "https://github.com/openai/private-reasoner"
    api_url = "https://api.github.com/repos/openai/private-reasoner"
    client = FakeSafeHttpClient(
        {
            api_url: FakeResponse(
                200,
                {"content-type": "application/json"},
                _fixture_bytes("github_private_repository.json"),
            )
        }
    )

    source = await GitHubConnector(client).fetch(repo_url)

    assert source.status == "blocked"
    assert source.reason == "private_repository"
    assert source.text == ""
    assert client.requests == [
        (api_url, {"headers": {"accept": "application/vnd.github+json"}})
    ]


@pytest.mark.asyncio
async def test_github_connector_blocks_unsupported_paths_and_router_selects_it_for_github() -> (
    None
):
    client = FakeSafeHttpClient({})
    connector = GitHubConnector(client)
    router = ConnectorRouter(
        generic_connector=WebConnector(client), connectors=(connector,)
    )

    source = await router.fetch("https://github.com/openai/expert-reasoner/issues")

    assert (
        router.select("https://github.com/openai/expert-reasoner/issues") is connector
    )
    assert source.status == "blocked"
    assert source.reason == "unsupported_github_url"
    assert client.requests == []


@pytest.mark.asyncio
async def test_github_connector_normalizes_restricted_api_responses() -> None:
    repo_url = "https://github.com/openai/expert-reasoner"
    client = FakeSafeHttpClient(
        {
            "https://api.github.com/repos/openai/expert-reasoner": FakeResponse(
                403,
                {"content-type": "application/json"},
                json.dumps({"message": "Forbidden"}).encode(),
            )
        }
    )

    source = await GitHubConnector(client).fetch(repo_url)

    assert source.status == "blocked"
    assert source.reason == "restricted_repository"
    assert source.metadata == {"http_status": 403, "content_type": "application/json"}


@pytest.mark.asyncio
async def test_github_connector_maps_safe_client_rate_limit_without_reflecting_token() -> (
    None
):
    repo_url = "https://github.com/openai/expert-reasoner"
    api_url = "https://api.github.com/repos/openai/expert-reasoner"
    client = FakeSafeHttpClient({api_url: RateLimitExceededError()})

    source = await GitHubConnector(client, token="only-on-server").fetch(repo_url)

    assert source.status == "blocked"
    assert source.reason == "rate_limited"
    assert source.canonical_url == repo_url
    assert "only-on-server" not in repr(source)
    assert client.requests == [
        (
            api_url,
            {
                "headers": {
                    "accept": "application/vnd.github+json",
                    "authorization": "Bearer only-on-server",
                }
            },
        )
    ]


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("headers", "content", "reason"),
    [
        ({"content-type": "text/html"}, b"<html>error</html>", "unsupported_mime"),
        (
            {
                "content-type": "application/json",
                "content-length": str(5 * 1024 * 1024 + 1),
            },
            b'{"message": "error"}',
            "response_too_large",
        ),
    ],
)
async def test_github_connector_applies_response_policy_before_non_success_api_status(
    headers: Mapping[str, str], content: bytes, reason: str
) -> None:
    repo_url = "https://github.com/openai/expert-reasoner"
    client = FakeSafeHttpClient(
        {
            "https://api.github.com/repos/openai/expert-reasoner": FakeResponse(
                503, headers, content
            )
        }
    )

    source = await GitHubConnector(client).fetch(repo_url)

    assert source.status == "blocked"
    assert source.reason == reason
    assert source.metadata["http_status"] == 503
    assert source.metadata["content_type"] == headers["content-type"]


@pytest.mark.asyncio
async def test_github_connector_blocks_malformed_repository_json() -> None:
    repo_url = "https://github.com/openai/expert-reasoner"
    client = FakeSafeHttpClient(
        {
            "https://api.github.com/repos/openai/expert-reasoner": FakeResponse(
                200,
                {"content-type": "application/json"},
                _fixture_bytes("github_malformed.json"),
            )
        }
    )

    source = await GitHubConnector(client).fetch(repo_url)

    assert source.status == "blocked"
    assert source.reason == "invalid_repository_response"
    assert source.text == ""


@pytest.mark.asyncio
async def test_github_connector_blocks_html_readme_before_decoding() -> None:
    repo_url = "https://github.com/openai/expert-reasoner"
    client = FakeSafeHttpClient(
        {
            "https://api.github.com/repos/openai/expert-reasoner": FakeResponse(
                200,
                {"content-type": "application/json"},
                _fixture_bytes("github_repository.json"),
            ),
            "https://raw.githubusercontent.com/openai/expert-reasoner/main/README.md": FakeResponse(
                200,
                {"content-type": "text/html"},
                b"<html><body>not a README</body></html>",
            ),
        }
    )

    source = await GitHubConnector(client).fetch(repo_url)

    assert source.status == "blocked"
    assert source.reason == "unsupported_mime"
    assert source.metadata["http_status"] == 200
    assert source.metadata["content_type"] == "text/html"
    assert source.text == ""


@pytest.mark.asyncio
async def test_router_blocks_credentialed_github_url_before_connector_dispatch() -> (
    None
):
    client = FakeSafeHttpClient({})
    router = ConnectorRouter(
        generic_connector=WebConnector(client), connectors=(GitHubConnector(client),)
    )

    source = await router.fetch(
        "https://user:credential@github.com/openai/expert-reasoner"
    )

    assert source.status == "blocked"
    assert source.reason == "unsafe_url"
    assert "credential" not in repr(source)
    assert client.requests == []


@pytest.mark.asyncio
async def test_github_connector_blocks_credentialed_url_before_path_parsing_or_dispatch() -> (
    None
):
    client = FakeSafeHttpClient({})

    source = await GitHubConnector(client).fetch(
        "https://user:credential@github.com/openai/expert-reasoner"
    )

    assert source.status == "blocked"
    assert source.reason == "unsafe_url"
    assert "credential" not in repr(source)
    assert client.requests == []


@pytest.mark.asyncio
async def test_router_blocks_malformed_bracket_url_without_throwing_or_dispatching() -> (
    None
):
    client = FakeSafeHttpClient({})
    router = ConnectorRouter(
        generic_connector=WebConnector(client), connectors=(GitHubConnector(client),)
    )

    source = await router.fetch("https://[")

    assert source.status == "blocked"
    assert source.reason == "unsafe_url"
    assert client.requests == []


def test_router_selects_a_safe_blocked_connector_for_a_malformed_bracket_url() -> None:
    client = FakeSafeHttpClient({})
    router = ConnectorRouter(
        generic_connector=WebConnector(client), connectors=(GitHubConnector(client),)
    )

    selected = router.select("https://[")

    assert selected is not router.select("https://example.com/article")


def test_router_selects_github_connector_for_a_trailing_dot_hostname() -> None:
    client = FakeSafeHttpClient({})
    connector = GitHubConnector(client)
    router = ConnectorRouter(
        generic_connector=WebConnector(client), connectors=(connector,)
    )

    assert router.select("https://github.com./openai/expert-reasoner") is connector
