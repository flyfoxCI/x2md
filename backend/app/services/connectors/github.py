"""Public GitHub repository metadata and README normalization."""

import json
from collections.abc import Mapping
from typing import Protocol
from urllib.parse import urlsplit

import httpx

from app.services.connectors.base import NormalizedSource
from app.services.connectors.response_policy import validate_response_body
from app.services.url_safety import (
    RateLimitExceededError,
    UnsafeUrlError,
    validate_public_url,
)

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


class GitHubConnector:
    """Fetch a public repository's REST metadata and raw default-branch README."""

    def __init__(
        self, client: SafeHttpClientProtocol, *, token: str | None = None
    ) -> None:
        self._client = client
        self._token = token

    def can_handle(self, url: str) -> bool:
        """Own GitHub browser URLs, including unsupported paths for an honest response."""
        return _normalized_host(url) in {"github.com", "www.github.com"}

    async def fetch(self, url: str) -> NormalizedSource:
        """Return public repository material, never private repository content."""
        try:
            safe_url = str(validate_public_url(url))
        except UnsafeUrlError:
            return _blocked(_INVALID_URL, "unsafe_url")
        repository = _repository_from_url(safe_url)
        if repository is None:
            return _blocked(safe_url, "unsupported_github_url")

        canonical_url = f"https://github.com/{repository}"
        api_url = f"https://api.github.com/repos/{repository}"
        headers = {"accept": "application/vnd.github+json"}
        if self._token:
            headers["authorization"] = f"Bearer {self._token}"
        try:
            response = await self._client.get_public(api_url, headers=headers)
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
                "github_http_status",
                response_policy.metadata,
            )
        try:
            payload = _json_object(response.content)
        except (UnicodeDecodeError, json.JSONDecodeError):
            return _blocked(canonical_url, "invalid_repository_response")
        if payload.get("private") is True:
            return _blocked(canonical_url, "private_repository")

        title = _string(payload.get("full_name")) or repository
        owner = _owner_login(payload)
        metadata = _metadata(payload, repository)
        branch = _string(payload.get("default_branch"))
        if branch is None:
            return _partial(canonical_url, title, owner, metadata, "readme_unavailable")

        readme_url = (
            f"https://raw.githubusercontent.com/{repository}/{branch}/README.md"
        )
        try:
            readme_response = await self._client.get_public(
                readme_url, headers={"accept": "text/markdown, text/plain;q=0.9"}
            )
        except RateLimitExceededError:
            return _blocked(canonical_url, "rate_limited", metadata)
        except UnsafeUrlError:
            return _blocked(canonical_url, "unsafe_url", metadata)
        except httpx.RequestError:
            return _partial(canonical_url, title, owner, metadata, "readme_unavailable")
        readme_policy = validate_response_body(
            readme_response, allowed_mime_types=_TEXT_MIME_TYPES
        )
        if readme_policy.reason is not None:
            return _blocked(canonical_url, readme_policy.reason, readme_policy.metadata)
        if readme_response.status_code in {401, 403}:
            return _blocked(
                canonical_url, "restricted_repository", readme_policy.metadata
            )
        if not 200 <= readme_response.status_code < 300:
            return _partial(canonical_url, title, owner, metadata, "readme_unavailable")
        try:
            readme = readme_response.content.decode("utf-8")
        except UnicodeDecodeError:
            return _partial(
                canonical_url, title, owner, metadata, "invalid_readme_encoding"
            )
        if not readme.strip():
            return _partial(canonical_url, title, owner, metadata, "readme_unavailable")
        return NormalizedSource(
            canonical_url=canonical_url,
            platform="github",
            title=title,
            text=readme,
            markdown=readme,
            status="ready",
            author=owner,
            metadata=metadata,
            provenance={"metadata": "github_rest", "readme": "github_raw"},
        )


def _repository_from_url(url: str) -> str | None:
    try:
        parsed = urlsplit(url)
    except ValueError:
        return None
    if _normalized_host(url) not in {"github.com", "www.github.com"}:
        return None
    parts = [part for part in parsed.path.split("/") if part]
    if len(parts) != 2 or any(part in {"-", "."} for part in parts):
        return None
    return "/".join(parts)


def _normalized_host(url: str) -> str | None:
    try:
        host = urlsplit(url).hostname
    except ValueError:
        return None
    return host.rstrip(".").lower() if host else None


def _json_object(content: bytes) -> Mapping[str, object]:
    payload = json.loads(content.decode("utf-8"))
    if not isinstance(payload, Mapping):
        raise json.JSONDecodeError("expected object", "", 0)
    return payload


def _string(value: object) -> str | None:
    return value.strip() if isinstance(value, str) and value.strip() else None


def _owner_login(payload: Mapping[str, object]) -> str | None:
    owner = payload.get("owner")
    return _string(owner.get("login")) if isinstance(owner, Mapping) else None


def _metadata(payload: Mapping[str, object], repository: str) -> dict[str, object]:
    license_value = payload.get("license")
    license_id = (
        _string(license_value.get("spdx_id"))
        if isinstance(license_value, Mapping)
        else None
    )
    topics = payload.get("topics")
    return {
        "repository": repository,
        "description": _string(payload.get("description")),
        "default_branch": _string(payload.get("default_branch")),
        "stars": payload.get("stargazers_count")
        if isinstance(payload.get("stargazers_count"), int)
        else 0,
        "forks": payload.get("forks_count")
        if isinstance(payload.get("forks_count"), int)
        else 0,
        "language": _string(payload.get("language")),
        "topics": tuple(item for item in topics if isinstance(item, str))
        if isinstance(topics, list)
        else (),
        "license": license_id,
        "updated_at": _string(payload.get("updated_at")),
    }


def _blocked(
    url: str, reason: str, metadata: Mapping[str, object] | None = None
) -> NormalizedSource:
    return NormalizedSource(
        canonical_url=url,
        platform="github",
        title="GitHub repository",
        text="",
        markdown="",
        status="blocked",
        metadata=metadata or {},
        reason=reason,
        provenance={"metadata": "github_rest"},
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
        platform="github",
        title=title,
        text="",
        markdown="",
        status="partial",
        author=author,
        metadata=metadata,
        reason=reason,
        provenance={"metadata": "github_rest", "readme": "github_raw"},
    )
