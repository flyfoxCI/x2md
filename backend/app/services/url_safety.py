"""URL validation guard used before fetching imported content."""

import asyncio
import ipaddress
import math
import socket
import time
from collections.abc import Callable, Iterable
from typing import Self
from urllib.parse import urljoin

import httpx
from pydantic_core import Url

Resolver = Callable[[str], Iterable[str]]
MonotonicClock = Callable[[], float]


class UnsafeUrlError(ValueError):
    """A URL cannot safely be fetched from the public internet."""

    detail = "unsafe_url"

    def __init__(self) -> None:
        super().__init__(self.detail)


class RateLimitExceededError(UnsafeUrlError):
    """A public host has exhausted this client's request budget."""

    detail = "rate_limited"


def validate_public_url(url: str | Url) -> Url:
    """Parse an HTTPS URL and reject unsafe literal hosts and credentials."""
    try:
        parsed = Url(str(url))
    except ValueError as error:
        raise UnsafeUrlError() from error

    host = parsed.host
    if (
        parsed.scheme != "https"
        or parsed.username is not None
        or parsed.password is not None
        or host is None
        or host.rstrip(".").lower() == "localhost"
    ):
        raise UnsafeUrlError()

    try:
        address = ipaddress.ip_address(host.strip("[]"))
    except ValueError:
        return parsed

    if not _is_public_address(address):
        raise UnsafeUrlError()
    return parsed


def validate_redirect(source_url: str | Url, location: str) -> Url:
    """Resolve a redirect location and apply the same URL policy."""
    return validate_public_url(urljoin(str(source_url), location))


def resolve_hostname(host: str) -> list[str]:
    """Return every address a hostname resolves to, without choosing one."""
    try:
        results = socket.getaddrinfo(host, None, type=socket.SOCK_STREAM)
    except socket.gaierror as error:
        raise UnsafeUrlError() from error
    return sorted({result[4][0] for result in results})


class SafeHttpClient:
    """An async HTTP wrapper that rejects unsafe targets before every request."""

    def __init__(
        self,
        *,
        timeout: float = 10.0,
        resolver: Resolver = resolve_hostname,
        transport: httpx.AsyncBaseTransport | None = None,
        max_requests_per_host: int = 20,
        rate_window_seconds: float = 60.0,
        monotonic_clock: MonotonicClock = time.monotonic,
    ) -> None:
        if not math.isfinite(timeout) or timeout <= 0:
            raise ValueError("timeout must be finite and positive")
        if (
            isinstance(max_requests_per_host, bool)
            or not isinstance(max_requests_per_host, int)
            or max_requests_per_host <= 0
        ):
            raise ValueError("max_requests_per_host must be a positive integer")
        if (
            isinstance(rate_window_seconds, bool)
            or not isinstance(rate_window_seconds, (int, float))
            or not math.isfinite(rate_window_seconds)
            or rate_window_seconds <= 0
        ):
            raise ValueError("rate_window_seconds must be finite and positive")
        self.timeout = timeout
        self.follow_redirects = False
        self._resolver = resolver
        self._max_requests_per_host = max_requests_per_host
        self._rate_window_seconds = float(rate_window_seconds)
        self._monotonic_clock = monotonic_clock
        self._host_request_times: dict[str, list[float]] = {}
        self._client = httpx.AsyncClient(
            follow_redirects=False,
            timeout=timeout,
            transport=transport,
        )

    async def __aenter__(self) -> Self:
        return self

    async def __aexit__(self, *args: object) -> None:
        await self.aclose()

    async def aclose(self) -> None:
        """Release network resources held by the underlying HTTP client."""
        await self._client.aclose()

    async def get(self, url: str | Url, **kwargs: object) -> httpx.Response:
        """Compatibility alias for :meth:`get_public`."""
        return await self.get_public(url, **kwargs)

    async def get_public(self, url: str | Url, **kwargs: object) -> httpx.Response:
        """Fetch a public URL without following redirects automatically."""
        return await self.request("GET", url, **kwargs)

    async def request(
        self, method: str, url: str | Url, **kwargs: object
    ) -> httpx.Response:
        """Fetch a URL only after its literal and DNS targets are public."""
        for argument in ("timeout", "extensions"):
            if argument in kwargs:
                raise ValueError(f"{argument} may not override SafeHttpClient policy")
        target = await self._validate_target(url)
        self._consume_host_request_budget(target)
        kwargs.pop("follow_redirects", None)
        response = await self._client.request(
            method, str(target), follow_redirects=False, **kwargs
        )
        location = response.headers.get("location")
        if response.is_redirect and location is not None:
            await self._validate_target(validate_redirect(target, location))
        return response

    async def _validate_target(self, url: str | Url) -> Url:
        target = validate_public_url(url)
        host = target.host
        assert host is not None
        host = host.strip("[]")
        try:
            answers = list(await asyncio.to_thread(self._resolver, host))
        except (OSError, ValueError, UnsafeUrlError) as error:
            raise UnsafeUrlError() from error
        if not answers:
            raise UnsafeUrlError()
        try:
            addresses = [ipaddress.ip_address(answer) for answer in answers]
        except ValueError as error:
            raise UnsafeUrlError() from error
        if any(not _is_public_address(address) for address in addresses):
            raise UnsafeUrlError()
        return target

    def _consume_host_request_budget(self, target: Url) -> None:
        now = self._monotonic_clock()
        cutoff = now - self._rate_window_seconds
        for host, request_times in list(self._host_request_times.items()):
            unexpired_times = [
                requested_at for requested_at in request_times if requested_at > cutoff
            ]
            if unexpired_times:
                self._host_request_times[host] = unexpired_times
            else:
                del self._host_request_times[host]

        host = target.host
        assert host is not None
        normalized_host = host.strip("[]").rstrip(".").lower()
        request_times = self._host_request_times.setdefault(normalized_host, [])
        if len(request_times) >= self._max_requests_per_host:
            raise RateLimitExceededError()
        request_times.append(now)


def _is_public_address(address: ipaddress.IPv4Address | ipaddress.IPv6Address) -> bool:
    return (
        address.is_global
        and not address.is_multicast
        and not getattr(address, "is_site_local", False)
    )
