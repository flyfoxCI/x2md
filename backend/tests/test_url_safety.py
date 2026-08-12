"""Tests for the safe prefetch URL boundary."""

from collections.abc import Callable

import httpx
import pytest
from pydantic_core import Url

from app.services.url_safety import (
    RateLimitExceededError,
    SafeHttpClient,
    UnsafeUrlError,
    validate_public_url,
)


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


@pytest.mark.asyncio
async def test_safe_client_limits_requests_to_a_normalized_host_without_dispatching() -> None:
    requests: list[httpx.Request] = []

    async def handler(request: httpx.Request) -> httpx.Response:
        requests.append(request)
        return httpx.Response(200, request=request)

    async with SafeHttpClient(
        resolver=lambda _: ["93.184.216.34"],
        transport=httpx.MockTransport(handler),
        max_requests_per_host=1,
        monotonic_clock=lambda: 100.0,
    ) as client:
        await client.get("https://EXAMPLE.com/first")
        with pytest.raises(RateLimitExceededError, match="rate_limited") as error:
            await client.get("https://example.com./second")

    assert error.value.detail == "rate_limited"
    assert [str(request.url) for request in requests] == ["https://example.com/first"]


@pytest.mark.asyncio
async def test_safe_client_gives_each_host_its_own_rate_limit_budget() -> None:
    requests: list[httpx.Request] = []

    async def handler(request: httpx.Request) -> httpx.Response:
        requests.append(request)
        return httpx.Response(200, request=request)

    async with SafeHttpClient(
        resolver=lambda _: ["93.184.216.34"],
        transport=httpx.MockTransport(handler),
        max_requests_per_host=1,
        monotonic_clock=lambda: 100.0,
    ) as client:
        await client.get("https://example.com/first")
        await client.get("https://www.example.com/first")

    assert [request.url.host for request in requests] == [
        "example.com",
        "www.example.com",
    ]


@pytest.mark.asyncio
async def test_safe_client_allows_a_host_after_its_rate_limit_window_expires() -> None:
    requests: list[httpx.Request] = []
    clock = [100.0]

    async def handler(request: httpx.Request) -> httpx.Response:
        requests.append(request)
        return httpx.Response(200, request=request)

    async with SafeHttpClient(
        resolver=lambda _: ["93.184.216.34"],
        transport=httpx.MockTransport(handler),
        max_requests_per_host=1,
        rate_window_seconds=60.0,
        monotonic_clock=lambda: clock[0],
    ) as client:
        await client.get("https://example.com/first")
        clock[0] += 60.0
        await client.get("https://example.com/second")

    assert [str(request.url) for request in requests] == [
        "https://example.com/first",
        "https://example.com/second",
    ]


@pytest.mark.asyncio
async def test_safe_client_does_not_charge_redirect_validation_to_host_budget() -> None:
    requests: list[httpx.Request] = []

    async def handler(request: httpx.Request) -> httpx.Response:
        requests.append(request)
        if request.url.path == "/start":
            return httpx.Response(
                302,
                headers={"location": "https://example.com/redirect-target"},
                request=request,
            )
        return httpx.Response(200, request=request)

    async with SafeHttpClient(
        resolver=lambda _: ["93.184.216.34"],
        transport=httpx.MockTransport(handler),
        max_requests_per_host=2,
        monotonic_clock=lambda: 100.0,
    ) as client:
        response = await client.get("https://example.com/start")
        follow_up = await client.get("https://example.com/follow-up")

    assert response.is_redirect
    assert follow_up.status_code == 200
    assert [str(request.url) for request in requests] == [
        "https://example.com/start",
        "https://example.com/follow-up",
    ]


@pytest.mark.parametrize(
    ("kwargs", "message"),
    [
        ({"max_requests_per_host": 0}, "max_requests_per_host"),
        ({"max_requests_per_host": -1}, "max_requests_per_host"),
        ({"max_requests_per_host": 1.5}, "max_requests_per_host"),
        ({"max_requests_per_host": False}, "max_requests_per_host"),
        ({"rate_window_seconds": 0}, "rate_window_seconds"),
        ({"rate_window_seconds": -1}, "rate_window_seconds"),
        ({"rate_window_seconds": float("inf")}, "rate_window_seconds"),
        ({"rate_window_seconds": float("nan")}, "rate_window_seconds"),
    ],
)
def test_safe_client_rejects_invalid_rate_limit_configuration(
    kwargs: dict[str, object], message: str
) -> None:
    with pytest.raises(ValueError, match=message):
        SafeHttpClient(**kwargs)
