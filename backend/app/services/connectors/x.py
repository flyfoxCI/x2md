"""Constrained X post retrieval with an explicit server-side credential gate."""

import json
import re
from collections.abc import Mapping
from datetime import UTC, datetime
from typing import Protocol
from urllib.parse import unquote, urlencode, urlsplit

import httpx
from pydantic import SecretStr

from app.services.connectors.base import NormalizedSource
from app.services.connectors.response_policy import validate_response_body
from app.services.url_safety import (
    RateLimitExceededError,
    UnsafeUrlError,
    validate_public_url,
)

_JSON_MIME_TYPES = {"application/json"}
_X_HOSTS = {"x.com", "www.x.com", "twitter.com", "www.twitter.com"}
_POST_ID = re.compile(r"^\d{1,20}$")
_HANDLE = re.compile(r"^[A-Za-z0-9_]{1,15}$")
_INVALID_URL = "https://invalid.invalid/"
_V2_PROVENANCE = {"metadata": "x_v2", "content": "x_v2"}
_OEMBED_PROVENANCE = {"metadata": "x_oembed", "content": "x_v2"}


class SafeResponse(Protocol):
    """The bounded response shape supplied by the safe HTTP capability."""

    status_code: int
    headers: Mapping[str, str]
    content: bytes


class SafeHttpClientProtocol(Protocol):
    """Public-fetch capability; connectors never create HTTP clients directly."""

    async def get_public(self, url: str, **kwargs: object) -> SafeResponse:
        """Fetch an already protected public target."""


class XConnector:
    """Retrieve explicit X API post text only when a server secret is configured."""

    def __init__(
        self, client: SafeHttpClientProtocol, *, bearer_token: SecretStr | None = None
    ) -> None:
        self._client = client
        self._bearer_token = bearer_token

    def can_handle(self, url: str) -> bool:
        """Own X and legacy Twitter browser URLs, including unsupported forms."""
        return _normalized_host(url) in _X_HOSTS

    async def fetch(self, url: str) -> NormalizedSource:
        """Return only source material received explicitly from an allowed endpoint."""
        try:
            safe_url = str(validate_public_url(url))
        except UnsafeUrlError:
            return _blocked(_INVALID_URL, "unsafe_url")
        target = _target_from_url(safe_url)
        if target is None:
            return _blocked(safe_url, "unsupported_x_url")
        username, post_id = target
        canonical_url = f"https://x.com/{username}/status/{post_id}"
        if self._bearer_token is None or not self._bearer_token.get_secret_value():
            return await self._fetch_oembed(canonical_url, post_id)
        return await self._fetch_v2(canonical_url, post_id)

    async def _fetch_oembed(self, canonical_url: str, post_id: str) -> NormalizedSource:
        metadata: dict[str, object] = {"post_id": post_id}
        try:
            response = await self._client.get_public(
                _oembed_url(canonical_url), headers={"accept": "application/json"}
            )
        except RateLimitExceededError:
            return _blocked(canonical_url, "rate_limited", metadata, _OEMBED_PROVENANCE)
        except UnsafeUrlError:
            return _blocked(canonical_url, "unsafe_url", metadata, _OEMBED_PROVENANCE)
        except httpx.RequestError:
            return _blocked(
                canonical_url, "network_error", metadata, _OEMBED_PROVENANCE
            )
        response_policy = validate_response_body(
            response, allowed_mime_types=_JSON_MIME_TYPES
        )
        if response_policy.reason is not None:
            return _blocked(
                canonical_url,
                response_policy.reason,
                response_policy.metadata,
                _OEMBED_PROVENANCE,
            )
        if response.status_code == 429:
            return _blocked(
                canonical_url,
                "rate_limited",
                response_policy.metadata,
                _OEMBED_PROVENANCE,
            )
        if response.status_code in {401, 403, 404}:
            return _blocked(
                canonical_url,
                "restricted_source",
                response_policy.metadata,
                _OEMBED_PROVENANCE,
            )
        if not 200 <= response.status_code < 300:
            return _blocked(
                canonical_url,
                "x_oembed_http_status",
                response_policy.metadata,
                _OEMBED_PROVENANCE,
            )
        try:
            payload = _json_object(response.content)
        except (UnicodeDecodeError, json.JSONDecodeError):
            return _blocked(
                canonical_url,
                "invalid_oembed_response",
                metadata,
                _OEMBED_PROVENANCE,
            )
        metadata.update(_oembed_metadata(payload))
        return _partial(
            canonical_url,
            "X post",
            _string(payload.get("author_name")),
            metadata,
            "provider_not_configured",
            _OEMBED_PROVENANCE,
        )

    async def _fetch_v2(self, canonical_url: str, post_id: str) -> NormalizedSource:
        assert self._bearer_token is not None
        bearer_token = self._bearer_token.get_secret_value()
        try:
            response = await self._client.get_public(
                _v2_url(post_id),
                headers={
                    "accept": "application/json",
                    "authorization": f"Bearer {bearer_token}",
                },
            )
        except RateLimitExceededError:
            return _blocked(canonical_url, "rate_limited")
        except UnsafeUrlError:
            return _blocked(canonical_url, "unsafe_url")
        except httpx.RequestError:
            return _blocked(canonical_url, "network_error")
        response_policy = validate_response_body(
            response, allowed_mime_types=_JSON_MIME_TYPES
        )
        if response_policy.reason is not None:
            return _blocked(
                canonical_url, response_policy.reason, response_policy.metadata
            )
        if response.status_code == 429:
            return _blocked(canonical_url, "rate_limited", response_policy.metadata)
        if response.status_code in {401, 403, 404}:
            return _blocked(
                canonical_url, "restricted_source", response_policy.metadata
            )
        if not 200 <= response.status_code < 300:
            return _blocked(canonical_url, "x_http_status", response_policy.metadata)
        try:
            payload = _json_object(response.content)
        except (UnicodeDecodeError, json.JSONDecodeError):
            return _blocked(canonical_url, "invalid_post_response")
        post = payload.get("data")
        if not isinstance(post, Mapping):
            return _blocked(canonical_url, "invalid_post_response")
        text = _string(post.get("text"))
        if text is None:
            return _blocked(canonical_url, "post_text_unavailable")
        author, username = _author(payload, post)
        title = f"X post by @{username}" if username else "X post"
        return NormalizedSource(
            canonical_url=canonical_url,
            platform="x",
            title=title,
            text=text,
            markdown=f"# {title}\n\n{text}",
            status="ready",
            author=author,
            published_at=_parse_datetime(_string(post.get("created_at"))),
            metadata=_v2_metadata(post_id, post, username),
            provenance=_V2_PROVENANCE,
        )


def _target_from_url(url: str) -> tuple[str, str] | None:
    try:
        parsed = urlsplit(url)
    except ValueError:
        return None
    if _normalized_host(url) not in _X_HOSTS:
        return None
    raw_segments = parsed.path.split("/")
    if (
        len(raw_segments) != 4
        or raw_segments[0]
        or any(not part for part in raw_segments[1:])
    ):
        return None
    parts = [unquote(segment) for segment in raw_segments[1:]]
    if any(
        decoded != raw or _unsafe_decoded_segment(decoded)
        for raw, decoded in zip(raw_segments[1:], parts, strict=True)
    ):
        return None
    if (
        not _HANDLE.fullmatch(parts[0])
        or parts[1] != "status"
        or not _POST_ID.fullmatch(parts[2])
    ):
        return None
    return parts[0], parts[2]


def _unsafe_decoded_segment(segment: str) -> bool:
    return (
        not segment
        or any(character.isspace() for character in segment)
        or any(character in "/\\." for character in segment)
    )


def _normalized_host(url: str) -> str | None:
    try:
        host = urlsplit(url).hostname
    except ValueError:
        return None
    return host.rstrip(".").lower() if host else None


def _oembed_url(canonical_url: str) -> str:
    return "https://publish.twitter.com/oembed?" + urlencode(
        {"url": canonical_url, "omit_script": "true"}
    )


def _v2_url(post_id: str) -> str:
    return (
        "https://api.x.com/2/tweets/"
        + post_id
        + "?"
        + urlencode(
            {
                "tweet.fields": "author_id,created_at,public_metrics",
                "expansions": "author_id",
                "user.fields": "name,username",
            }
        )
    )


def _json_object(content: bytes) -> Mapping[str, object]:
    payload = json.loads(content.decode("utf-8"))
    if not isinstance(payload, Mapping):
        raise json.JSONDecodeError("expected object", "", 0)
    return payload


def _string(value: object) -> str | None:
    return value.strip() if isinstance(value, str) and value.strip() else None


def _oembed_metadata(payload: Mapping[str, object]) -> dict[str, object]:
    return {
        "author_url": _string(payload.get("author_url")),
        "provider": _string(payload.get("provider_name")) or "X",
    }


def _author(
    payload: Mapping[str, object], post: Mapping[str, object]
) -> tuple[str | None, str | None]:
    includes = payload.get("includes")
    users = includes.get("users") if isinstance(includes, Mapping) else None
    author_id = _string(post.get("author_id"))
    if not isinstance(users, list) or author_id is None:
        return None, None
    for user in users:
        if isinstance(user, Mapping) and _string(user.get("id")) == author_id:
            return _string(user.get("name")), _string(user.get("username"))
    return None, None


def _v2_metadata(
    post_id: str, post: Mapping[str, object], username: str | None
) -> dict[str, object]:
    metrics = post.get("public_metrics")
    safe_metrics = (
        {
            key: value
            for key, value in metrics.items()
            if isinstance(key, str)
            and isinstance(value, int)
            and not isinstance(value, bool)
        }
        if isinstance(metrics, Mapping)
        else {}
    )
    return {
        "post_id": post_id,
        "username": username,
        "public_metrics": safe_metrics,
    }


def _parse_datetime(value: str | None) -> datetime | None:
    if value is None:
        return None
    try:
        parsed = datetime.fromisoformat(value)
    except ValueError:
        return None
    return parsed.replace(tzinfo=UTC) if parsed.tzinfo is None else parsed


def _blocked(
    url: str,
    reason: str,
    metadata: Mapping[str, object] | None = None,
    provenance: Mapping[str, object] = _V2_PROVENANCE,
) -> NormalizedSource:
    return NormalizedSource(
        canonical_url=url,
        platform="x",
        title="X post",
        text="",
        markdown="",
        status="blocked",
        metadata=metadata or {},
        reason=reason,
        provenance=provenance,
    )


def _partial(
    url: str,
    title: str,
    author: str | None,
    metadata: Mapping[str, object],
    reason: str,
    provenance: Mapping[str, object],
) -> NormalizedSource:
    return NormalizedSource(
        canonical_url=url,
        platform="x",
        title=title,
        text="",
        markdown="",
        status="partial",
        author=author,
        metadata=metadata,
        reason=reason,
        provenance=provenance,
    )
