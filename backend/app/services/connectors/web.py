"""Generic article extraction through the safe outbound HTTP boundary."""

from collections.abc import Mapping
from datetime import UTC, datetime
from typing import Protocol

import httpx
from bs4 import BeautifulSoup, Tag

from app.services.connectors.base import NormalizedSource
from app.services.url_safety import UnsafeUrlError

MAX_RESPONSE_BYTES = 5 * 1024 * 1024
ALLOWED_HTML_MIME_TYPES = frozenset({"text/html", "application/xhtml+xml"})
_REMOVABLE_TAGS = frozenset({"aside", "footer", "form", "nav", "noscript", "script", "style"})
_READABLE_TAGS = ("h1", "h2", "h3", "h4", "h5", "h6", "p", "li", "blockquote", "div")


class SafeResponse(Protocol):
    """Read-only response data exposed by the safe HTTP boundary."""

    status_code: int
    headers: Mapping[str, str]
    content: bytes


class SafeHttpClientProtocol(Protocol):
    """The only fetch capability a generic connector may depend on."""

    async def get_public(self, url: str) -> SafeResponse:
        """Retrieve a URL that the client has already protected."""


class WebConnector:
    """Normalize a public HTML/XHTML article fetched by ``SafeHttpClient``."""

    def __init__(self, client: SafeHttpClientProtocol) -> None:
        self._client = client

    def can_handle(self, url: str) -> bool:
        """The generic connector is a fallback, so it handles any safe URL."""
        return True

    async def fetch(self, url: str) -> NormalizedSource:
        """Fetch and extract a bounded HTML document without direct HTTP access."""
        try:
            response = await self._client.get_public(url)
        except UnsafeUrlError:
            return _blocked_source(url, "unsafe_url", {})
        except httpx.RequestError:
            return _blocked_source(url, "network_error", {})
        metadata = _response_metadata(response.status_code, response.headers)

        if not 200 <= response.status_code < 300:
            return _blocked_source(url, "http_status", metadata)

        content_type = _content_type(response.headers)
        if content_type not in ALLOWED_HTML_MIME_TYPES:
            return _blocked_source(url, "unsupported_mime", metadata)

        content_length = _declared_content_length(response.headers)
        if content_length is not None and content_length > MAX_RESPONSE_BYTES:
            return _blocked_source(url, "response_too_large", metadata)
        if len(response.content) > MAX_RESPONSE_BYTES:
            return _blocked_source(url, "response_too_large", metadata)

        try:
            content = _decode_declared_charset(response.content, response.headers)
        except (LookupError, UnicodeDecodeError):
            return _blocked_source(url, "invalid_charset", metadata)
        return _extract_article(url, content, metadata)


def _response_metadata(status_code: int, headers: Mapping[str, str]) -> dict[str, object]:
    return {
        "http_status": status_code,
        "content_type": _content_type(headers),
    }


def _content_type(headers: Mapping[str, str]) -> str:
    return _content_type_header(headers).split(";", 1)[0].strip().lower()


def _content_type_header(headers: Mapping[str, str]) -> str:
    return _header_value(headers, "content-type")


def _declared_content_length(headers: Mapping[str, str]) -> int | None:
    value = _header_value(headers, "content-length")
    if not value:
        return None
    try:
        content_length = int(value)
    except ValueError:
        return None
    return content_length if content_length >= 0 else None


def _header_value(headers: Mapping[str, str], name: str) -> str:
    """Retrieve an HTTP header from a generic mapping without casing assumptions."""
    normalized_name = name.casefold()
    return next(
        (value for key, value in headers.items() if key.casefold() == normalized_name),
        "",
    )


def _decode_declared_charset(content: bytes, headers: Mapping[str, str]) -> bytes | str:
    charset = _declared_charset(_content_type_header(headers))
    return content if charset is None else content.decode(charset)


def _declared_charset(content_type: str) -> str | None:
    for parameter in content_type.split(";")[1:]:
        name, separator, value = parameter.partition("=")
        if separator and name.strip().casefold() == "charset":
            return value.strip().strip('"')
    return None


def _extract_article(
    url: str, content: bytes | str, response_metadata: Mapping[str, object]
) -> NormalizedSource:
    soup = BeautifulSoup(content, "html.parser")
    title = _extract_title(soup)
    author = _meta_content(soup, "name", "author") or _meta_content(
        soup, "property", "article:author"
    )
    published_at = _parse_published_at(
        _meta_content(soup, "property", "article:published_time")
        or _meta_content(soup, "name", "date")
    )
    article = soup.find("article") or soup.find("main") or soup.body
    paragraphs = _readable_paragraphs(article)
    provenance = {"extractor": "beautifulsoup4", "source": "generic_web"}

    if not paragraphs:
        return NormalizedSource(
            canonical_url=url,
            platform="web",
            title=title,
            text="",
            markdown="",
            status="partial",
            author=author,
            published_at=published_at,
            metadata=response_metadata,
            reason="no_readable_content",
            provenance=provenance,
        )

    text = "\n\n".join(paragraphs)
    markdown = f"# {title}\n\n{text}"
    return NormalizedSource(
        canonical_url=url,
        platform="web",
        title=title,
        text=text,
        markdown=markdown,
        status="ready",
        author=author,
        published_at=published_at,
        metadata=response_metadata,
        provenance=provenance,
    )


def _blocked_source(
    url: str, reason: str, metadata: Mapping[str, object]
) -> NormalizedSource:
    return NormalizedSource(
        canonical_url=url,
        platform="web",
        title="Untitled web source",
        text="",
        markdown="",
        status="blocked",
        metadata=metadata,
        reason=reason,
        provenance={"extractor": "generic_web"},
    )


def _extract_title(soup: BeautifulSoup) -> str:
    if soup.title is not None:
        title = soup.title.get_text(" ", strip=True)
        if title:
            return title
    heading = soup.find("h1")
    if isinstance(heading, Tag):
        title = heading.get_text(" ", strip=True)
        if title:
            return title
    return "Untitled web source"


def _meta_content(soup: BeautifulSoup, attribute: str, value: str) -> str | None:
    element = soup.find("meta", attrs={attribute: value})
    if not isinstance(element, Tag):
        return None
    content = element.get("content")
    return content.strip() if isinstance(content, str) and content.strip() else None


def _parse_published_at(value: str | None) -> datetime | None:
    if value is None:
        return None
    try:
        parsed = datetime.fromisoformat(value)
    except ValueError:
        return None
    return parsed.replace(tzinfo=UTC) if parsed.tzinfo is None else parsed


def _readable_paragraphs(article: Tag | None) -> list[str]:
    if article is None:
        return []
    for element in article.find_all(_REMOVABLE_TAGS):
        element.decompose()
    return [
        text
        for element in article.find_all(_READABLE_TAGS)
        if not element.find(_READABLE_TAGS)
        if (text := element.get_text(" ", strip=True))
    ]
