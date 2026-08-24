"""arXiv Atom metadata normalization with abstract-only content."""

import re
from collections.abc import Mapping
from datetime import UTC, datetime
from typing import Protocol
from urllib.parse import urlencode, urlsplit
from xml.etree import ElementTree

import httpx

from app.services.connectors.base import NormalizedSource
from app.services.connectors.response_policy import validate_response_body
from app.services.url_safety import (
    RateLimitExceededError,
    UnsafeUrlError,
    validate_public_url,
)

_ATOM = "{http://www.w3.org/2005/Atom}"
_CURRENT_IDENTIFIER = re.compile(r"^\d{4}\.\d{4,5}(?:v\d+)?$")
_LEGACY_IDENTIFIER = re.compile(r"^[A-Za-z]+(?:[.-][A-Za-z]+)*/\d{7}(?:v\d+)?$")
_ATOM_MIME_TYPES = {"application/atom+xml", "application/xml", "text/xml"}
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


class ArxivConnector:
    """Use arXiv's Atom endpoint for metadata and an abstract, never the PDF."""

    def __init__(self, client: SafeHttpClientProtocol) -> None:
        self._client = client

    def can_handle(self, url: str) -> bool:
        """Own arXiv browser URLs, including paper PDF links."""
        return _normalized_host(url) in {"arxiv.org", "www.arxiv.org"}

    async def fetch(self, url: str) -> NormalizedSource:
        """Fetch the public Atom record and normalize only its abstract."""
        try:
            safe_url = str(validate_public_url(url))
        except UnsafeUrlError:
            return _blocked(_INVALID_URL, "unsafe_url")
        identifier = _identifier_from_url(safe_url)
        if identifier is None:
            return _blocked(safe_url, "unsupported_arxiv_url")
        canonical_url = f"https://arxiv.org/abs/{identifier}"
        api_url = (
            f"https://export.arxiv.org/api/query?{urlencode({'id_list': identifier})}"
        )
        try:
            response = await self._client.get_public(
                api_url,
                headers={"accept": "application/atom+xml, application/xml;q=0.9"},
            )
        except RateLimitExceededError:
            return _blocked(canonical_url, "rate_limited")
        except UnsafeUrlError:
            return _blocked(canonical_url, "unsafe_url")
        except httpx.RequestError:
            return _blocked(canonical_url, "network_error")
        response_policy = validate_response_body(
            response, allowed_mime_types=_ATOM_MIME_TYPES
        )
        if response_policy.reason is not None:
            return _blocked(
                canonical_url, response_policy.reason, response_policy.metadata
            )
        if not 200 <= response.status_code < 300:
            return _blocked(
                canonical_url,
                "arxiv_http_status",
                response_policy.metadata,
            )
        try:
            entry = ElementTree.fromstring(response.content).find(f"{_ATOM}entry")
        except ElementTree.ParseError:
            return _blocked(canonical_url, "invalid_arxiv_response")
        if entry is None:
            return _partial(canonical_url, identifier, "arxiv_record_not_found")

        title = _element_text(entry, "title")
        abstract = _element_text(entry, "summary")
        if not title or not abstract:
            return _partial(canonical_url, identifier, "arxiv_record_incomplete")
        authors = tuple(
            name
            for author in entry.findall(f"{_ATOM}author")
            if (name := _element_text(author, "name"))
        )
        categories = tuple(
            term
            for category in entry.findall(f"{_ATOM}category")
            if (term := category.attrib.get("term"))
        )
        updated_at = _element_text(entry, "updated")
        metadata = {
            "arxiv_id": identifier,
            "authors": authors,
            "categories": categories,
            "updated_at": updated_at,
        }
        return NormalizedSource(
            canonical_url=canonical_url,
            platform="arxiv",
            title=title,
            text=abstract,
            markdown=f"# {title}\n\n## Abstract\n\n{abstract}",
            status="ready",
            author=", ".join(authors) or None,
            published_at=_parse_datetime(_element_text(entry, "published")),
            metadata=metadata,
            provenance={"metadata": "arxiv_atom", "content": "abstract_only"},
        )


def _identifier_from_url(url: str) -> str | None:
    try:
        parsed = urlsplit(url)
    except ValueError:
        return None
    if _normalized_host(url) not in {"arxiv.org", "www.arxiv.org"}:
        return None
    parts = [part for part in parsed.path.split("/") if part]
    if not parts or parts[0] not in {"abs", "pdf"}:
        return None
    identifier = "/".join(parts[1:])
    if parts[0] == "pdf" and identifier.endswith(".pdf"):
        identifier = identifier[:-4]
    if _CURRENT_IDENTIFIER.fullmatch(identifier) or _LEGACY_IDENTIFIER.fullmatch(
        identifier
    ):
        return identifier
    return None


def _normalized_host(url: str) -> str | None:
    try:
        host = urlsplit(url).hostname
    except ValueError:
        return None
    return host.rstrip(".").lower() if host else None


def _element_text(element: ElementTree.Element, name: str) -> str | None:
    text = element.findtext(f"{_ATOM}{name}")
    return " ".join(text.split()) if text and text.strip() else None


def _parse_datetime(value: str | None) -> datetime | None:
    if value is None:
        return None
    try:
        parsed = datetime.fromisoformat(value)
    except ValueError:
        return None
    return parsed.replace(tzinfo=UTC) if parsed.tzinfo is None else parsed


def _blocked(
    url: str, reason: str, metadata: Mapping[str, object] | None = None
) -> NormalizedSource:
    return NormalizedSource(
        canonical_url=url,
        platform="arxiv",
        title="arXiv paper",
        text="",
        markdown="",
        status="blocked",
        metadata=metadata or {},
        reason=reason,
        provenance={"metadata": "arxiv_atom", "content": "abstract_only"},
    )


def _partial(url: str, identifier: str, reason: str) -> NormalizedSource:
    return NormalizedSource(
        canonical_url=url,
        platform="arxiv",
        title=f"arXiv {identifier}",
        text="",
        markdown="",
        status="partial",
        metadata={"arxiv_id": identifier},
        reason=reason,
        provenance={"metadata": "arxiv_atom", "content": "abstract_only"},
    )
