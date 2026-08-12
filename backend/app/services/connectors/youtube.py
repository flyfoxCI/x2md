"""Constrained public YouTube metadata and transcript normalization."""

import json
import re
from collections.abc import Mapping
from typing import Protocol
from urllib.parse import parse_qsl, urlencode, urlsplit

import httpx
from defusedxml import ElementTree
from defusedxml.common import DefusedXmlException

from app.services.connectors.base import NormalizedSource
from app.services.connectors.response_policy import validate_response_body
from app.services.url_safety import (
    RateLimitExceededError,
    UnsafeUrlError,
    validate_public_url,
)

_JSON_MIME_TYPES = {"application/json"}
_XML_MIME_TYPES = {"application/xml", "text/xml"}
_VIDEO_ID = re.compile(r"^[A-Za-z0-9_-]{11}$")
_YOUTUBE_HOSTS = {"youtube.com", "www.youtube.com", "m.youtube.com", "youtu.be"}
_INVALID_URL = "https://invalid.invalid/"
_PROVENANCE = {"metadata": "youtube_oembed", "transcript": "public_provider"}


class SafeResponse(Protocol):
    """The bounded response shape supplied by the safe HTTP capability."""

    status_code: int
    headers: Mapping[str, str]
    content: bytes


class SafeHttpClientProtocol(Protocol):
    """Public-fetch capability; connectors never create HTTP clients directly."""

    async def get_public(self, url: str, **kwargs: object) -> SafeResponse:
        """Fetch an already protected public target."""


class PublicTranscriptProvider(Protocol):
    """Optional provider for captions already known to be publicly available."""

    async def get_public_transcript(self, video_id: str) -> str | None:
        """Return public captions, or ``None`` when captions cannot be retrieved."""


class YouTubeTimedTextTranscriptProvider:
    """Fetch public timed-text captions without bypassing YouTube access controls."""

    def __init__(self, client: SafeHttpClientProtocol, *, language: str = "en") -> None:
        self._client = client
        self._language = language

    async def get_public_transcript(self, video_id: str) -> str | None:
        """Return XML caption text only when the public endpoint returns it."""
        try:
            response = await self._client.get_public(
                _timedtext_url(video_id, self._language),
                headers={"accept": "application/xml, text/xml;q=0.9"},
            )
        except RateLimitExceededError:
            raise
        except httpx.RequestError:
            return None
        response_policy = validate_response_body(
            response, allowed_mime_types=_XML_MIME_TYPES
        )
        if response_policy.reason is not None:
            return None
        if response.status_code == 429:
            raise RateLimitExceededError()
        if not 200 <= response.status_code < 300:
            return None
        try:
            root = ElementTree.fromstring(response.content)
        except (DefusedXmlException, ElementTree.ParseError, LookupError):
            return None
        if _local_name(root.tag) != "transcript":
            return None
        captions = [
            " ".join("".join(element.itertext()).split())
            for element in root.iter()
            if _local_name(element.tag) == "text"
            if "".join(element.itertext()).strip()
        ]
        transcript = " ".join(captions)
        return transcript if transcript else None


class YouTubeConnector:
    """Fetch oEmbed metadata and only injected, public transcript content."""

    def __init__(
        self,
        client: SafeHttpClientProtocol,
        *,
        transcript_provider: PublicTranscriptProvider | None = None,
    ) -> None:
        self._client = client
        self._transcript_provider = (
            transcript_provider or YouTubeTimedTextTranscriptProvider(client)
        )

    def can_handle(self, url: str) -> bool:
        """Own YouTube browser URLs, including unsupported forms for honesty."""
        return _normalized_host(url) in _YOUTUBE_HOSTS

    async def fetch(self, url: str) -> NormalizedSource:
        """Normalize public metadata without scraping or inventing captions."""
        try:
            safe_url = str(validate_public_url(url))
        except UnsafeUrlError:
            return _blocked(_INVALID_URL, "unsafe_url")
        video_id = _video_id_from_url(safe_url)
        if video_id is None:
            return _blocked(safe_url, "unsupported_youtube_url")

        canonical_url = f"https://www.youtube.com/watch?v={video_id}"
        try:
            response = await self._client.get_public(
                _oembed_url(canonical_url), headers={"accept": "application/json"}
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
            return _blocked(
                canonical_url, "youtube_http_status", response_policy.metadata
            )
        try:
            payload = _json_object(response.content)
        except (UnicodeDecodeError, json.JSONDecodeError):
            return _blocked(canonical_url, "invalid_oembed_response")

        title = _string(payload.get("title"))
        if title is None:
            return _partial(
                canonical_url,
                "YouTube video",
                None,
                {"video_id": video_id},
                "metadata_unavailable",
            )
        author = _string(payload.get("author_name"))
        metadata = _metadata(payload, video_id)
        try:
            transcript = await self._public_transcript(video_id)
        except RateLimitExceededError:
            return _blocked(canonical_url, "rate_limited", metadata)
        except UnsafeUrlError:
            return _blocked(canonical_url, "unsafe_url", metadata)
        if transcript is None:
            return _partial(
                canonical_url, title, author, metadata, "transcript_unavailable"
            )
        return NormalizedSource(
            canonical_url=canonical_url,
            platform="youtube",
            title=title,
            text=transcript,
            markdown=f"# {title}\n\n## Transcript\n\n{transcript}",
            status="ready",
            author=author,
            metadata=metadata,
            provenance=_PROVENANCE,
        )

    async def _public_transcript(self, video_id: str) -> str | None:
        try:
            transcript = await self._transcript_provider.get_public_transcript(video_id)
        except RateLimitExceededError:
            raise
        except httpx.RequestError:
            return None
        return transcript if transcript and transcript.strip() else None


def _video_id_from_url(url: str) -> str | None:
    try:
        parsed = urlsplit(url)
    except ValueError:
        return None
    host = _normalized_host(url)
    if host not in _YOUTUBE_HOSTS:
        return None
    if parsed.path == "/watch":
        candidate = _single_query_value(parsed.query, "v")
    else:
        candidate = None
    return candidate if candidate and _VIDEO_ID.fullmatch(candidate) else None


def _normalized_host(url: str) -> str | None:
    try:
        host = urlsplit(url).hostname
    except ValueError:
        return None
    return host.rstrip(".").lower() if host else None


def _single_query_value(query: str, name: str) -> str | None:
    try:
        values = [
            value
            for key, value in parse_qsl(query, keep_blank_values=True)
            if key == name
        ]
    except ValueError:
        return None
    return values[0] if len(values) == 1 else None


def _oembed_url(canonical_url: str) -> str:
    return "https://www.youtube.com/oembed?" + urlencode(
        {"url": canonical_url, "format": "json"}
    )


def _timedtext_url(video_id: str, language: str) -> str:
    return "https://www.youtube.com/api/timedtext?" + urlencode(
        {"v": video_id, "lang": language}
    )


def _local_name(tag: str) -> str:
    return tag.rsplit("}", 1)[-1]


def _json_object(content: bytes) -> Mapping[str, object]:
    payload = json.loads(content.decode("utf-8"))
    if not isinstance(payload, Mapping):
        raise json.JSONDecodeError("expected object", "", 0)
    return payload


def _string(value: object) -> str | None:
    return value.strip() if isinstance(value, str) and value.strip() else None


def _metadata(payload: Mapping[str, object], video_id: str) -> dict[str, object]:
    return {
        "video_id": video_id,
        "author_url": _string(payload.get("author_url")),
        "provider": _string(payload.get("provider_name")) or "YouTube",
    }


def _blocked(
    url: str, reason: str, metadata: Mapping[str, object] | None = None
) -> NormalizedSource:
    return NormalizedSource(
        canonical_url=url,
        platform="youtube",
        title="YouTube video",
        text="",
        markdown="",
        status="blocked",
        metadata=metadata or {},
        reason=reason,
        provenance=_PROVENANCE,
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
        platform="youtube",
        title=title,
        text="",
        markdown="",
        status="partial",
        author=author,
        metadata=metadata,
        reason=reason,
        provenance=_PROVENANCE,
    )
