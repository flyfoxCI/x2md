"""Fixture tests for constrained X source handling."""

import json
from collections.abc import Mapping
from dataclasses import dataclass
from pathlib import Path

import httpx
import pytest
from pydantic import SecretStr

from app.services.connectors.router import ConnectorRouter
from app.services.connectors.web import WebConnector
from app.services.connectors.x import XConnector
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


def _oembed_url(canonical_url: str) -> str:
    return (
        "https://publish.twitter.com/oembed?url="
        "https%3A%2F%2Fx.com%2Fada%2Fstatus%2F1881234567890123456&omit_script=true"
    )


def _v2_url(post_id: str) -> str:
    return (
        f"https://api.x.com/2/tweets/{post_id}?"
        "tweet.fields=author_id%2Ccreated_at%2Cpublic_metrics&"
        "expansions=author_id&user.fields=name%2Cusername"
    )


@pytest.mark.asyncio
async def test_x_connector_without_bearer_uses_public_oembed_only_and_never_invents_post_text() -> (
    None
):
    canonical_url = "https://x.com/ada/status/1881234567890123456"
    client = FakeSafeHttpClient(
        {
            _oembed_url(canonical_url): FakeResponse(
                200,
                {"content-type": "application/json"},
                _fixture_bytes("x_oembed.json"),
            )
        }
    )

    source = await XConnector(client).fetch(
        "https://twitter.com/ada/status/1881234567890123456?s=20"
    )

    assert source.status == "partial"
    assert source.reason == "provider_not_configured"
    assert source.platform == "x"
    assert source.canonical_url == canonical_url
    assert source.title == "X post"
    assert source.author == "Ada Lovelace"
    assert source.text == ""
    assert source.markdown == ""
    assert source.metadata == {
        "author_url": "https://x.com/ada",
        "post_id": "1881234567890123456",
        "provider": "X",
    }
    assert source.provenance == {"metadata": "x_oembed", "content": "x_v2"}
    assert client.requests == [
        (_oembed_url(canonical_url), {"headers": {"accept": "application/json"}})
    ]
    assert all("api.x.com/2/tweets" not in url for url, _ in client.requests)


@pytest.mark.asyncio
async def test_x_connector_blocks_unavailable_public_card_without_inventing_post_text() -> (
    None
):
    canonical_url = "https://x.com/ada/status/1881234567890123456"
    client = FakeSafeHttpClient(
        {_oembed_url(canonical_url): httpx.ConnectError("unavailable")}
    )

    source = await XConnector(client).fetch(canonical_url)

    assert source.status == "blocked"
    assert source.reason == "network_error"
    assert source.text == ""
    assert source.markdown == ""
    assert source.metadata == {"post_id": "1881234567890123456"}
    assert all("api.x.com/2/tweets" not in url for url, _ in client.requests)


@pytest.mark.asyncio
async def test_x_connector_with_bearer_uses_v2_and_returns_only_explicit_post_text() -> (
    None
):
    post_id = "1881234567890123456"
    client = FakeSafeHttpClient(
        {
            _v2_url(post_id): FakeResponse(
                200,
                {"content-type": "application/json"},
                _fixture_bytes("x_post.json"),
            )
        }
    )

    source = await XConnector(client, bearer_token=SecretStr("only-on-server")).fetch(
        f"https://x.com/ada/status/{post_id}"
    )

    assert source.status == "ready"
    assert source.title == "X post by @ada"
    assert source.author == "Ada Lovelace"
    assert source.text == "Public post text retrieved from the explicit X API response."
    assert source.markdown == (
        "# X post by @ada\n\n"
        "Public post text retrieved from the explicit X API response."
    )
    assert source.metadata == {
        "post_id": post_id,
        "public_metrics": {
            "like_count": 9,
            "quote_count": 1,
            "reply_count": 2,
            "repost_count": 3,
        },
        "username": "ada",
    }
    assert source.provenance == {"metadata": "x_v2", "content": "x_v2"}
    assert "only-on-server" not in repr(source)
    assert client.requests == [
        (
            _v2_url(post_id),
            {
                "headers": {
                    "accept": "application/json",
                    "authorization": "Bearer only-on-server",
                }
            },
        )
    ]


def test_x_connector_retains_secret_wrapper_without_retaining_raw_bearer_value() -> (
    None
):
    connector = XConnector(
        FakeSafeHttpClient({}), bearer_token=SecretStr("only-on-server")
    )

    assert connector._bearer_token == SecretStr("only-on-server")
    assert "only-on-server" not in repr(connector)
    assert all(value != "only-on-server" for value in connector.__dict__.values())


@pytest.mark.asyncio
async def test_x_connector_blocks_restricted_v2_and_does_not_reflect_credential() -> (
    None
):
    post_id = "1881234567890123456"
    client = FakeSafeHttpClient(
        {
            _v2_url(post_id): FakeResponse(
                403,
                {"content-type": "application/json"},
                json.dumps({"title": "Forbidden"}).encode(),
            )
        }
    )

    source = await XConnector(client, bearer_token=SecretStr("only-on-server")).fetch(
        f"https://x.com/ada/status/{post_id}"
    )

    assert source.status == "blocked"
    assert source.reason == "restricted_source"
    assert source.text == ""
    assert source.metadata == {"content_type": "application/json", "http_status": 403}
    assert "only-on-server" not in repr(source)


@pytest.mark.asyncio
@pytest.mark.parametrize("bearer_token", [None, SecretStr("only-on-server")])
async def test_x_connector_maps_http_429_to_rate_limited_after_response_policy(
    bearer_token: SecretStr | None,
) -> None:
    post_id = "1881234567890123456"
    canonical_url = f"https://x.com/ada/status/{post_id}"
    endpoint = (
        _v2_url(post_id) if bearer_token is not None else _oembed_url(canonical_url)
    )
    client = FakeSafeHttpClient(
        {
            endpoint: FakeResponse(
                429,
                {"content-type": "application/json"},
                json.dumps({"error": "limited"}).encode(),
            )
        }
    )

    source = await XConnector(client, bearer_token=bearer_token).fetch(canonical_url)

    assert source.status == "blocked"
    assert source.reason == "rate_limited"
    assert source.text == ""


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("headers", "reason"),
    [
        ({"content-type": "text/html"}, "unsupported_mime"),
        (
            {
                "content-type": "application/json",
                "content-length": str(5 * 1024 * 1024 + 1),
            },
            "response_too_large",
        ),
    ],
)
async def test_x_connector_applies_response_policy_before_v2_status_handling(
    headers: Mapping[str, str], reason: str
) -> None:
    post_id = "1881234567890123456"
    client = FakeSafeHttpClient({_v2_url(post_id): FakeResponse(503, headers, b"bad")})

    source = await XConnector(client, bearer_token=SecretStr("only-on-server")).fetch(
        f"https://x.com/ada/status/{post_id}"
    )

    assert source.status == "blocked"
    assert source.reason == reason
    assert source.text == ""
    assert source.metadata["http_status"] == 503


@pytest.mark.asyncio
async def test_x_connector_blocks_missing_explicit_v2_text_instead_of_completing_from_metadata() -> (
    None
):
    post_id = "1881234567890123456"
    client = FakeSafeHttpClient(
        {
            _v2_url(post_id): FakeResponse(
                200,
                {"content-type": "application/json"},
                json.dumps({"data": {"id": post_id}}).encode(),
            )
        }
    )

    source = await XConnector(client, bearer_token=SecretStr("only-on-server")).fetch(
        f"https://x.com/ada/status/{post_id}"
    )

    assert source.status == "blocked"
    assert source.reason == "post_text_unavailable"
    assert source.text == ""
    assert source.markdown == ""


@pytest.mark.asyncio
async def test_x_connector_maps_rate_limits_and_unsafe_urls_without_full_api_fallback() -> (
    None
):
    post_id = "1881234567890123456"
    client = FakeSafeHttpClient({_v2_url(post_id): RateLimitExceededError()})

    limited = await XConnector(client, bearer_token=SecretStr("only-on-server")).fetch(
        f"https://x.com/ada/status/{post_id}"
    )
    unsafe = await XConnector(FakeSafeHttpClient({})).fetch(
        f"https://user:secret@x.com/ada/status/{post_id}"
    )

    assert limited.status == "blocked"
    assert limited.reason == "rate_limited"
    assert unsafe.status == "blocked"
    assert unsafe.reason == "unsafe_url"
    assert "secret" not in repr(unsafe)


@pytest.mark.asyncio
async def test_x_connector_owns_supported_host_but_blocks_unsupported_status_paths_without_fetching() -> (
    None
):
    client = FakeSafeHttpClient({})
    connector = XConnector(client)
    router = ConnectorRouter(
        generic_connector=WebConnector(client), connectors=(connector,)
    )

    source = await router.fetch("https://x.com/ada/lists/123")

    assert router.select("https://x.com/ada/lists/123") is connector
    assert source.status == "blocked"
    assert source.reason == "unsupported_x_url"
    assert client.requests == []


@pytest.mark.asyncio
@pytest.mark.parametrize("bearer_token", [None, SecretStr("only-on-server")])
@pytest.mark.parametrize(
    "url",
    [
        "https://x.com/%61da/status/1881234567890123456",
        "https://x.com/a%2Fb/status/1881234567890123456",
        "https://x.com/a%252Fb/status/1881234567890123456",
        "https://x.com/ada//status/1881234567890123456",
        "https://x.com/ada./status/1881234567890123456",
        "https://x.com/ada/status/1881234567890123456/",
    ],
)
async def test_x_connector_rejects_ambiguous_or_noncanonical_paths_without_fetching(
    bearer_token: SecretStr | None, url: str
) -> None:
    client = FakeSafeHttpClient({})

    source = await XConnector(client, bearer_token=bearer_token).fetch(url)

    assert source.status == "blocked"
    assert source.reason == "unsupported_x_url"
    assert client.requests == []
