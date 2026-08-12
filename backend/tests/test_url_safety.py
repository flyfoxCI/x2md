"""Tests for the safe prefetch URL boundary."""

from collections.abc import Callable

import httpx
import pytest
from pydantic_core import Url

from app.services.url_safety import SafeHttpClient, UnsafeUrlError, validate_public_url


@pytest.mark.parametrize(
    "url",
    [
        "http://example.com",
        "https://localhost",
        "https://127.0.0.1",
        "https://10.0.0.2",
        "https://172.16.0.1",
        "https://[::1]",
        "https://[::]",
        "https://[fc00::1]",
        "https://[fe80::1]",
        "https://[ff00::1]",
        "https://user:password@example.com",
        "https://0.0.0.0",
        "https://169.254.169.254/latest/meta-data",
        "https://224.0.0.1",
    ],
)
def test_validate_public_url_rejects_unsafe_values(url: str) -> None:
    with pytest.raises(UnsafeUrlError, match="unsafe_url") as error:
        validate_public_url(url)

    assert error.value.detail == "unsafe_url"


def test_validate_public_url_accepts_public_https_url() -> None:
    url = validate_public_url("https://example.com/a")

    assert isinstance(url, Url)
    assert str(url) == "https://example.com/a"


@pytest.mark.asyncio
async def test_safe_client_rejects_private_dns_answer_without_http_request() -> None:
    requests: list[httpx.Request] = []

    async def handler(request: httpx.Request) -> httpx.Response:
        requests.append(request)
        return httpx.Response(200, request=request)

    resolver: Callable[[str], list[str]] = lambda _: ["192.168.1.1"]
    async with SafeHttpClient(
        resolver=resolver,
        transport=httpx.MockTransport(handler),
    ) as client:
        with pytest.raises(UnsafeUrlError, match="unsafe_url"):
            await client.get("https://example.com")

    assert requests == []


@pytest.mark.asyncio
async def test_safe_client_uses_injected_resolver_and_validates_redirect_target(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    requests: list[httpx.Request] = []

    def reject_system_dns(*_: object, **__: object) -> None:
        raise AssertionError("system DNS must not be used")

    async def handler(request: httpx.Request) -> httpx.Response:
        requests.append(request)
        return httpx.Response(
            302,
            headers={"location": "https://192.168.1.1/private"},
            request=request,
        )

    monkeypatch.setattr("socket.getaddrinfo", reject_system_dns)
    resolver: Callable[[str], list[str]] = lambda _: ["93.184.216.34"]
    async with SafeHttpClient(
        resolver=resolver,
        timeout=2.5,
        transport=httpx.MockTransport(handler),
    ) as client:
        assert client.follow_redirects is False
        assert client.timeout == 2.5
        with pytest.raises(UnsafeUrlError, match="unsafe_url"):
            await client.get("https://example.com/start", follow_redirects=True)

    assert [str(request.url) for request in requests] == [
        "https://example.com/start"
    ]


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("kwargs", "argument"),
    [
        ({"timeout": None}, "timeout"),
        (
            {
                "extensions": {
                    "timeout": {"connect": None, "read": None, "write": None}
                }
            },
            "extensions",
        ),
    ],
)
async def test_safe_client_rejects_per_request_safety_overrides(
    kwargs: dict[str, object], argument: str
) -> None:
    requests: list[httpx.Request] = []

    async def handler(request: httpx.Request) -> httpx.Response:
        requests.append(request)
        return httpx.Response(200, request=request)

    async with SafeHttpClient(
        resolver=lambda _: ["93.184.216.34"],
        transport=httpx.MockTransport(handler),
    ) as client:
        with pytest.raises(ValueError, match=argument):
            await client.get("https://example.com", **kwargs)

    assert requests == []


@pytest.mark.asyncio
async def test_safe_client_normalizes_public_ipv6_literal_for_injected_resolver() -> None:
    resolved_hosts: list[str] = []

    def resolver(host: str) -> list[str]:
        resolved_hosts.append(host)
        return [host]

    async def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, request=request)

    async with SafeHttpClient(
        resolver=resolver,
        transport=httpx.MockTransport(handler),
    ) as client:
        response = await client.get("https://[2606:4700:4700::1111]/")

    assert response.status_code == 200
    assert resolved_hosts == ["2606:4700:4700::1111"]
