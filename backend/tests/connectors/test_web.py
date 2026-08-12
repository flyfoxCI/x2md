"""Tests for generic public-web source normalization."""

from collections.abc import Mapping
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path

import httpx
import pytest

from app.services.connectors.base import NormalizedSource
from app.services.connectors.router import ConnectorRouter
from app.services.connectors.web import MAX_RESPONSE_BYTES, WebConnector
from app.services.url_safety import UnsafeUrlError


@dataclass(frozen=True)
class FakeResponse:
    """Small response shape supplied by the SafeHttpClient boundary."""

    status_code: int
    headers: Mapping[str, str]
    content: bytes


class FakeSafeHttpClient:
    """Records requests so the connector cannot bypass the safe fetch boundary."""

    def __init__(self, response: FakeResponse | BaseException) -> None:
        self.response = response
        self.public_requested_urls: list[str] = []

    async def get_public(self, url: str) -> FakeResponse:
        self.public_requested_urls.append(url)
        if isinstance(self.response, BaseException):
            raise self.response
        return self.response


@pytest.fixture
def article_html() -> bytes:
    fixture_path = Path(__file__).parents[1] / "fixtures" / "article.html"
    return fixture_path.read_bytes()


@pytest.fixture
def div_only_article_html() -> bytes:
    fixture_path = Path(__file__).parents[1] / "fixtures" / "div_only_article.html"
    return fixture_path.read_bytes()


@pytest.mark.asyncio
@pytest.mark.parametrize("content_type_header", ["Content-Type", "cOnTeNt-TyPe"])
async def test_web_connector_accepts_case_insensitive_html_content_type(
    article_html: bytes, content_type_header: str
) -> None:
    client = FakeSafeHttpClient(
        FakeResponse(
            status_code=200,
            headers={content_type_header: "text/html; charset=utf-8"},
            content=article_html,
        )
    )

    source = await WebConnector(client).fetch("https://example.com/reasoning")

    assert client.public_requested_urls == ["https://example.com/reasoning"]
    assert source.status == "ready"
    assert source.canonical_url == "https://example.com/reasoning"
    assert source.platform == "web"
    assert source.title == "Reasoning at Scale"
    assert source.author == "Ada Lovelace"
    assert source.published_at == datetime(2026, 8, 11, 9, 30, tzinfo=UTC)
    assert "clear intermediate representations" in source.text
    assert "measure both final answers" in source.text
    assert "Pricing" not in source.text
    assert "navigation-noise" not in source.text
    assert source.markdown.startswith("# Reasoning at Scale")
    assert source.provenance["extractor"] == "beautifulsoup4"


@pytest.mark.asyncio
async def test_web_connector_blocks_unsupported_mime_type() -> None:
    client = FakeSafeHttpClient(
        FakeResponse(
            status_code=200,
            headers={"content-type": "application/pdf"},
            content=b"%PDF-1.7",
        )
    )

    source = await WebConnector(client).fetch("https://example.com/report")

    assert source.status == "blocked"
    assert source.reason == "unsupported_mime"
    assert source.text == ""
    assert source.markdown == ""


@pytest.mark.asyncio
async def test_web_connector_blocks_declared_oversize_response() -> None:
    client = FakeSafeHttpClient(
        FakeResponse(
            status_code=200,
            headers={
                "content-type": "text/html",
                "content-length": str(MAX_RESPONSE_BYTES + 1),
            },
            content=b"<html><body>not read</body></html>",
        )
    )

    source = await WebConnector(client).fetch("https://example.com/large")

    assert source.status == "blocked"
    assert source.reason == "response_too_large"


@pytest.mark.asyncio
async def test_web_connector_blocks_case_insensitive_declared_oversize_before_parsing(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    def fail_if_parsed(*_: object) -> NormalizedSource:
        raise AssertionError("oversize response must not be parsed")

    monkeypatch.setattr("app.services.connectors.web._extract_article", fail_if_parsed)
    client = FakeSafeHttpClient(
        FakeResponse(
            status_code=200,
            headers={
                "Content-Type": "text/html",
                "Content-Length": str(MAX_RESPONSE_BYTES + 1),
            },
            content=b"not parsed",
        )
    )

    source = await WebConnector(client).fetch("https://example.com/large-header")

    assert source.status == "blocked"
    assert source.reason == "response_too_large"


@pytest.mark.asyncio
async def test_web_connector_ignores_malformed_content_length(article_html: bytes) -> None:
    client = FakeSafeHttpClient(
        FakeResponse(
            status_code=200,
            headers={"Content-Type": "text/html", "CoNtEnT-LeNgTh": "not-a-number"},
            content=article_html,
        )
    )

    source = await WebConnector(client).fetch("https://example.com/malformed-length")

    assert source.status == "ready"


@pytest.mark.asyncio
async def test_web_connector_blocks_non_success_http_status_before_parsing(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    def fail_if_parsed(*_: object) -> NormalizedSource:
        raise AssertionError("failed HTTP response must not be parsed")

    monkeypatch.setattr("app.services.connectors.web._extract_article", fail_if_parsed)
    client = FakeSafeHttpClient(
        FakeResponse(
            status_code=404,
            headers={"Content-Type": "text/html"},
            content=b"not parsed",
        )
    )

    source = await WebConnector(client).fetch("https://example.com/missing")

    assert source.status == "blocked"
    assert source.reason == "http_status"


@pytest.mark.asyncio
async def test_web_connector_blocks_unsafe_url_error_from_safe_client() -> None:
    client = FakeSafeHttpClient(UnsafeUrlError())

    source = await WebConnector(client).fetch("https://example.com/unsafe")

    assert client.public_requested_urls == ["https://example.com/unsafe"]
    assert source.status == "blocked"
    assert source.reason == "unsafe_url"
    assert source.text == ""
    assert source.markdown == ""


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "error",
    [httpx.RequestError("network unavailable"), httpx.ReadTimeout("timed out")],
)
async def test_web_connector_blocks_network_errors_from_safe_client(
    error: httpx.RequestError,
) -> None:
    client = FakeSafeHttpClient(error)

    source = await WebConnector(client).fetch("https://example.com/unavailable")

    assert source.status == "blocked"
    assert source.reason == "network_error"
    assert source.text == ""
    assert source.markdown == ""


@pytest.mark.asyncio
async def test_web_connector_blocks_actual_oversize_response() -> None:
    client = FakeSafeHttpClient(
        FakeResponse(
            status_code=200,
            headers={"content-type": "application/xhtml+xml"},
            content=b"x" * (MAX_RESPONSE_BYTES + 1),
        )
    )

    source = await WebConnector(client).fetch("https://example.com/large-body")

    assert source.status == "blocked"
    assert source.reason == "response_too_large"


@pytest.mark.asyncio
async def test_web_connector_marks_missing_readable_body_partial() -> None:
    client = FakeSafeHttpClient(
        FakeResponse(
            status_code=200,
            headers={"content-type": "text/html"},
            content=b"<html><head><title>Empty article</title></head><body><nav>Menu</nav></body></html>",
        )
    )

    source = await WebConnector(client).fetch("https://example.com/empty")

    assert source.status == "partial"
    assert source.reason == "no_readable_content"
    assert source.title == "Empty article"
    assert source.text == ""


@pytest.mark.asyncio
async def test_router_uses_generic_connector_as_fallback(article_html: bytes) -> None:
    client = FakeSafeHttpClient(
        FakeResponse(
            status_code=200,
            headers={"content-type": "text/html"},
            content=article_html,
        )
    )
    web_connector = WebConnector(client)
    router = ConnectorRouter(generic_connector=web_connector, connectors=())

    source = await router.fetch("https://example.com/reasoning")

    assert source.platform == "web"
    assert client.public_requested_urls == ["https://example.com/reasoning"]


@pytest.mark.asyncio
async def test_web_connector_decodes_declared_gbk_charset() -> None:
    content = (
        "<html><head><title>推理规模化</title></head>"
        "<body><article><p>这是正确解码的中文内容。</p></article></body></html>"
    ).encode("gbk")
    client = FakeSafeHttpClient(
        FakeResponse(
            status_code=200,
            headers={"Content-Type": "text/html; Charset=GBK"},
            content=content,
        )
    )

    source = await WebConnector(client).fetch("https://example.com/gbk")

    assert source.status == "ready"
    assert source.title == "推理规模化"
    assert source.text == "这是正确解码的中文内容。"


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("content_type", "content"),
    [
        ("text/html; charset=unknown-charset", b"<html><body>ignored</body></html>"),
        (
            "text/html; charset=ascii",
            "<html><body><article><p>中文</p></article></body></html>".encode("gbk"),
        ),
    ],
)
async def test_web_connector_blocks_invalid_or_undecodable_declared_charset(
    content_type: str, content: bytes
) -> None:
    client = FakeSafeHttpClient(
        FakeResponse(status_code=200, headers={"Content-Type": content_type}, content=content)
    )

    source = await WebConnector(client).fetch("https://example.com/charset")

    assert source.status == "blocked"
    assert source.reason == "invalid_charset"
    assert source.text == ""
    assert source.markdown == ""


@pytest.mark.asyncio
async def test_web_connector_extracts_semantic_and_div_only_article_blocks(
    div_only_article_html: bytes,
) -> None:
    client = FakeSafeHttpClient(
        FakeResponse(
            status_code=200,
            headers={"Content-Type": "text/html"},
            content=div_only_article_html,
        )
    )

    source = await WebConnector(client).fetch("https://example.com/div-only")

    assert source.status == "ready"
    assert source.text.split("\n\n") == [
        "Why the fallback matters",
        "First useful div-only section.",
        "Second useful div-only section.",
    ]
    assert "Navigation that must not be extracted" not in source.text


@pytest.mark.asyncio
async def test_web_connector_extracts_only_leaf_readable_elements() -> None:
    client = FakeSafeHttpClient(
        FakeResponse(
            status_code=200,
            headers={"Content-Type": "text/html"},
            content=(
                b"<html><body><article>"
                b"<blockquote><p>Quoted source</p></blockquote>"
                b"<ul><li><p>Nested list item</p></li></ul>"
                b"</article></body></html>"
            ),
        )
    )

    source = await WebConnector(client).fetch("https://example.com/nested-readable")

    paragraphs = source.text.split("\n\n")
    assert paragraphs.count("Quoted source") == 1
    assert paragraphs.count("Nested list item") == 1


def test_normalized_source_defensively_freezes_metadata_and_provenance() -> None:
    metadata = {"nested": {"values": ["original"]}}
    provenance = {"steps": ["fetched"]}

    source = NormalizedSource(
        canonical_url="https://example.com/article",
        platform="web",
        title="Article",
        text="content",
        markdown="# Article\n\ncontent",
        status="ready",
        metadata=metadata,
        provenance=provenance,
    )
    metadata["nested"]["values"].append("changed")
    provenance["steps"].append("changed")

    assert source.metadata["nested"] == {"values": ("original",)}
    assert source.provenance["steps"] == ("fetched",)
    with pytest.raises(TypeError):
        source.metadata["new"] = "value"  # type: ignore[index]


def test_normalized_source_rejects_bytearray_metadata() -> None:
    with pytest.raises(ValueError, match="JSON-shaped"):
        NormalizedSource(
            canonical_url="https://example.com/article",
            platform="web",
            title="Article",
            text="content",
            markdown="# Article\n\ncontent",
            status="ready",
            metadata={"response_body": bytearray(b"mutable")},
        )


@pytest.mark.parametrize(
    ("status", "text", "markdown", "reason", "message"),
    [
        ("ready", "", "# Article", None, "ready sources require text and markdown"),
        ("ready", "content", "", None, "ready sources require text and markdown"),
        ("blocked", "content", "", "restricted_source", "blocked sources cannot include extracted content"),
        ("blocked", "", "# Article", "restricted_source", "blocked sources cannot include extracted content"),
    ],
)
def test_normalized_source_enforces_status_content_invariants(
    status: str, text: str, markdown: str, reason: str | None, message: str
) -> None:
    with pytest.raises(ValueError, match=message):
        NormalizedSource(
            canonical_url="https://example.com/article",
            platform="web",
            title="Article",
            text=text,
            markdown=markdown,
            status=status,  # type: ignore[arg-type]
            reason=reason,
        )


def test_normalized_source_rejects_an_unknown_status() -> None:
    with pytest.raises(ValueError, match="invalid source status"):
        NormalizedSource(
            canonical_url="https://example.com/article",
            platform="web",
            title="Article",
            text="content",
            markdown="content",
            status="unknown",  # type: ignore[arg-type]
        )
