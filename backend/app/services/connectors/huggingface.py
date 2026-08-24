"""Public Hugging Face repository and blog article normalization."""

import json
from collections.abc import Mapping
from dataclasses import replace
from typing import Literal, Protocol
from urllib.parse import urlsplit

import httpx

from app.services.connectors.base import NormalizedSource
from app.services.connectors.response_policy import validate_response_body
from app.services.connectors.web import WebConnector
from app.services.url_safety import (
    RateLimitExceededError,
    UnsafeUrlError,
    validate_public_url,
)

RepositoryType = Literal["model", "dataset"]
_JSON_MIME_TYPES = {"application/json"}
_TEXT_MIME_TYPES = {
    "text/markdown",
    "text/plain",
    "text/x-markdown",
    "application/markdown",
}
_INVALID_URL = "https://invalid.invalid/"


class SafeResponse(Protocol):
    """The bounded response shape supplied by the safe HTTP capability."""

    status_code: int
    headers: Mapping[str, str]
    content: bytes


class SafeHttpClientProtocol(Protocol):
    """Public-fetch capability; connectors never create HTTP clients directly."""

    async def get_public(self, url: str, **kwargs: object) -> SafeResponse:
        """Fetch an already protected public target."""


class HuggingFaceConnector:
    """Fetch public Hub repository cards and blog articles."""

    def __init__(self, client: SafeHttpClientProtocol) -> None:
        self._client = client
        self._web_connector = WebConnector(client)

    def can_handle(self, url: str) -> bool:
        """Own Hub URLs, including unsupported areas such as Spaces."""
        return _normalized_host(url) in {"huggingface.co", "www.huggingface.co"}

    async def fetch(self, url: str) -> NormalizedSource:
        """Normalize an accessible model/dataset card without bypassing access controls."""
        try:
            safe_url = str(validate_public_url(url))
        except UnsafeUrlError:
            return _blocked(_INVALID_URL, "unsafe_url")
        if _is_blog_path(safe_url):
            blog_slug = _blog_slug_from_url(safe_url)
            if blog_slug is None:
                return _blocked(safe_url, "unsupported_huggingface_url")
            return await self._fetch_blog_article(blog_slug)
        target = _target_from_url(safe_url)
        if target is None:
            return _blocked(safe_url, "unsupported_huggingface_url")
        repository_type, repository = target
        canonical_url = _canonical_url(repository_type, repository)
        api_url = f"https://huggingface.co/api/{repository_type}s/{repository}"
        try:
            response = await self._client.get_public(
                api_url, headers={"accept": "application/json"}
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
        if response.status_code in {401, 403, 404}:
            return _blocked(
                canonical_url,
                "restricted_repository",
                response_policy.metadata,
            )
        if not 200 <= response.status_code < 300:
            return _blocked(
                canonical_url,
                "huggingface_http_status",
                response_policy.metadata,
            )
        try:
            payload = _json_object(response.content)
        except (UnicodeDecodeError, json.JSONDecodeError):
            return _blocked(canonical_url, "invalid_repository_response")
        if _is_restricted(payload):
            return _blocked(canonical_url, "restricted_repository")

        title = _string(payload.get("id")) or repository
        author = _string(payload.get("author")) or repository.partition("/")[0]
        metadata = _metadata(payload, repository_type, title)
        card_url = f"{canonical_url}/raw/main/README.md"
        try:
            card_response = await self._client.get_public(
                card_url, headers={"accept": "text/markdown, text/plain;q=0.9"}
            )
        except RateLimitExceededError:
            return _blocked(canonical_url, "rate_limited", metadata)
        except UnsafeUrlError:
            return _blocked(canonical_url, "unsafe_url", metadata)
        except httpx.RequestError:
            return _partial(canonical_url, title, author, metadata, "card_unavailable")
        card_policy = validate_response_body(
            card_response, allowed_mime_types=_TEXT_MIME_TYPES
        )
        if card_policy.reason is not None:
            return _blocked(canonical_url, card_policy.reason, card_policy.metadata)
        if card_response.status_code in {401, 403}:
            return _blocked(
                canonical_url, "restricted_repository", card_policy.metadata
            )
        if not 200 <= card_response.status_code < 300:
            return _partial(canonical_url, title, author, metadata, "card_unavailable")
        try:
            card = card_response.content.decode("utf-8")
        except UnicodeDecodeError:
            return _partial(
                canonical_url, title, author, metadata, "invalid_card_encoding"
            )
        if not card.strip():
            return _partial(canonical_url, title, author, metadata, "card_unavailable")
        return NormalizedSource(
            canonical_url=canonical_url,
            platform="huggingface",
            title=title,
            text=card,
            markdown=card,
            status="ready",
            author=author,
            metadata=metadata,
            provenance={"metadata": "huggingface_hub", "card": "huggingface_raw"},
        )

    async def _fetch_blog_article(self, blog_slug: str) -> NormalizedSource:
        canonical_url = f"https://huggingface.co/blog/{blog_slug}"
        source = await self._web_connector.fetch(canonical_url)
        return replace(
            source,
            canonical_url=canonical_url,
            platform="huggingface",
            metadata={
                **source.metadata,
                "resource_type": "blog_article",
                "blog_slug": blog_slug,
            },
        )


def _target_from_url(url: str) -> tuple[RepositoryType, str] | None:
    try:
        parsed = urlsplit(url)
    except ValueError:
        return None
    if _normalized_host(url) not in {"huggingface.co", "www.huggingface.co"}:
        return None
    parts = [part for part in parsed.path.split("/") if part]
    if len(parts) == 2:
        return "model", "/".join(parts)
    if len(parts) == 3 and parts[0] == "datasets":
        return "dataset", "/".join(parts[1:])
    return None


def _blog_slug_from_url(url: str) -> str | None:
    try:
        parsed = urlsplit(url)
    except ValueError:
        return None
    if _normalized_host(url) not in {"huggingface.co", "www.huggingface.co"}:
        return None
    parts = parsed.path.split("/")
    if len(parts) == 3 and parts[:2] == ["", "blog"] and parts[2]:
        return parts[2]
    return None


def _is_blog_path(url: str) -> bool:
    if _normalized_host(url) not in {"huggingface.co", "www.huggingface.co"}:
        return False
    try:
        path = urlsplit(url).path
    except ValueError:
        return False
    return path.lstrip("/").split("/", 1)[0] == "blog"


def _normalized_host(url: str) -> str | None:
    try:
        host = urlsplit(url).hostname
    except ValueError:
        return None
    return host.rstrip(".").lower() if host else None


def _canonical_url(repository_type: RepositoryType, repository: str) -> str:
    prefix = "datasets/" if repository_type == "dataset" else ""
    return f"https://huggingface.co/{prefix}{repository}"


def _json_object(content: bytes) -> Mapping[str, object]:
    payload = json.loads(content.decode("utf-8"))
    if not isinstance(payload, Mapping):
        raise json.JSONDecodeError("expected object", "", 0)
    return payload


def _is_restricted(payload: Mapping[str, object]) -> bool:
    gated = payload.get("gated")
    return payload.get("private") is True or not (
        gated is None or gated is False or gated in {"", "false", "False"}
    )


def _string(value: object) -> str | None:
    return value.strip() if isinstance(value, str) and value.strip() else None


def _metadata(
    payload: Mapping[str, object], repository_type: RepositoryType, identifier: str
) -> dict[str, object]:
    tags = payload.get("tags")
    metadata: dict[str, object] = {
        "id": identifier,
        "repository_type": repository_type,
        "gated": payload.get("gated")
        if isinstance(payload.get("gated"), (str, bool))
        else False,
        "downloads": payload.get("downloads")
        if isinstance(payload.get("downloads"), int)
        else 0,
        "likes": payload.get("likes") if isinstance(payload.get("likes"), int) else 0,
        "last_modified": _string(payload.get("lastModified")),
        "tags": tuple(item for item in tags if isinstance(item, str))
        if isinstance(tags, list)
        else (),
    }
    if repository_type == "model":
        metadata["pipeline_tag"] = _string(payload.get("pipeline_tag"))
        metadata["library_name"] = _string(payload.get("library_name"))
    return metadata


def _blocked(
    url: str, reason: str, metadata: Mapping[str, object] | None = None
) -> NormalizedSource:
    return NormalizedSource(
        canonical_url=url,
        platform="huggingface",
        title="Hugging Face repository",
        text="",
        markdown="",
        status="blocked",
        metadata=metadata or {},
        reason=reason,
        provenance={"metadata": "huggingface_hub"},
    )


def _partial(
    url: str,
    title: str,
    author: str | None,
    metadata: Mapping[str, object],
    reason: str,
) -> NormalizedSource:
    return NormalizedSource(
        canonical_url=url,
        platform="huggingface",
        title=title,
        text="",
        markdown="",
        status="partial",
        author=author,
        metadata=metadata,
        reason=reason,
        provenance={"metadata": "huggingface_hub", "card": "huggingface_raw"},
    )
