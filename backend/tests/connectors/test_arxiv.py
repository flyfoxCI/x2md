"""Fixture tests for the arXiv Atom metadata connector."""

from collections.abc import Mapping
from dataclasses import dataclass
from pathlib import Path

import pytest

from app.services.connectors.arxiv import ArxivConnector
from app.services.connectors.router import ConnectorRouter
from app.services.connectors.web import WebConnector


@dataclass(frozen=True)
class FakeResponse:
    status_code: int
    headers: Mapping[str, str]
    content: bytes


class FakeSafeHttpClient:
    def __init__(self, responses: Mapping[str, FakeResponse | BaseException]) -> None:
        self._responses = responses
        self.requests: list[tuple[str, Mapping[str, object]]] = []

    async def get_public(self, url: str, **kwargs: object) -> FakeResponse:
        self.requests.append((url, kwargs))
        response = self._responses[url]
        if isinstance(response, BaseException):
            raise response
        return response


def _fixture_bytes(name: str) -> bytes:
    return (Path(__file__).parents[1] / "fixtures" / name).read_bytes()


@pytest.mark.asyncio
async def test_arxiv_connector_normalizes_atom_metadata_and_abstract_only() -> None:
    url = "https://arxiv.org/abs/2401.01234v2?ref=library"
    api_url = "https://export.arxiv.org/api/query?id_list=2401.01234v2"
    client = FakeSafeHttpClient(
        {
            api_url: FakeResponse(
                200,
                {"content-type": "application/atom+xml"},
                _fixture_bytes("arxiv_record.xml"),
            )
        }
    )

    source = await ArxivConnector(client).fetch(url)

    assert source.status == "ready"
    assert source.platform == "arxiv"
    assert source.canonical_url == "https://arxiv.org/abs/2401.01234v2"
    assert source.title == "Reasoning with Expert Traces"
    assert source.author == "Ada Lovelace, Grace Hopper"
    assert (
        source.text
        == "We study how inspectable intermediate representations improve expert model evaluation."
    )
    assert source.markdown == (
        "# Reasoning with Expert Traces\n\n## Abstract\n\n"
        "We study how inspectable intermediate representations improve expert model evaluation."
    )
    assert source.metadata == {
        "arxiv_id": "2401.01234v2",
        "authors": ("Ada Lovelace", "Grace Hopper"),
        "categories": ("cs.AI", "cs.LG"),
        "updated_at": "2026-08-10T12:00:00Z",
    }
    assert source.provenance == {"metadata": "arxiv_atom", "content": "abstract_only"}
    assert client.requests == [
        (
            api_url,
            {"headers": {"accept": "application/atom+xml, application/xml;q=0.9"}},
        )
    ]


@pytest.mark.asyncio
async def test_arxiv_connector_returns_partial_when_the_record_has_no_entry() -> None:
    url = "https://arxiv.org/abs/2401.01234"
    client = FakeSafeHttpClient(
        {
            "https://export.arxiv.org/api/query?id_list=2401.01234": FakeResponse(
                200,
                {"content-type": "application/atom+xml"},
                _fixture_bytes("arxiv_empty_feed.xml"),
            )
        }
    )

    source = await ArxivConnector(client).fetch(url)

    assert source.status == "partial"
    assert source.reason == "arxiv_record_not_found"
    assert source.canonical_url == "https://arxiv.org/abs/2401.01234"
    assert source.text == ""


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "url",
    [
        "https://arxiv.org/pdf/2608.20320",
        "https://arxiv.org/pdf/2608.20320.pdf",
    ],
)
async def test_arxiv_connector_normalizes_pdf_urls_to_the_paper_record(url: str) -> None:
    api_url = "https://export.arxiv.org/api/query?id_list=2608.20320"
    client = FakeSafeHttpClient(
        {
            api_url: FakeResponse(
                200,
                {"content-type": "application/atom+xml"},
                _fixture_bytes("arxiv_record.xml"),
            )
        }
    )
    connector = ArxivConnector(client)
    router = ConnectorRouter(
        generic_connector=WebConnector(client), connectors=(connector,)
    )

    source = await router.fetch(url)

    assert router.select(url) is connector
    assert source.status == "ready"
    assert source.canonical_url == "https://arxiv.org/abs/2608.20320"
    assert source.metadata["arxiv_id"] == "2608.20320"
    assert client.requests[0][0] == api_url


@pytest.mark.asyncio
async def test_arxiv_connector_blocks_unsupported_paths_and_router_selects_it_for_arxiv() -> (
    None
):
    client = FakeSafeHttpClient({})
    connector = ArxivConnector(client)
    router = ConnectorRouter(
        generic_connector=WebConnector(client), connectors=(connector,)
    )

    source = await router.fetch("https://arxiv.org/html/2401.01234")

    assert router.select("https://arxiv.org/html/2401.01234") is connector
    assert source.status == "blocked"
    assert source.reason == "unsupported_arxiv_url"
    assert client.requests == []


@pytest.mark.asyncio
async def test_arxiv_connector_normalizes_unavailable_api_responses() -> None:
    url = "https://arxiv.org/abs/2401.01234"
    client = FakeSafeHttpClient(
        {
            "https://export.arxiv.org/api/query?id_list=2401.01234": FakeResponse(
                503, {"content-type": "application/atom+xml"}, b"try later"
            )
        }
    )

    source = await ArxivConnector(client).fetch(url)

    assert source.status == "blocked"
    assert source.reason == "arxiv_http_status"
    assert source.metadata == {
        "http_status": 503,
        "content_type": "application/atom+xml",
    }


@pytest.mark.asyncio
async def test_arxiv_connector_applies_response_policy_before_non_success_status() -> (
    None
):
    url = "https://arxiv.org/abs/2401.01234"
    client = FakeSafeHttpClient(
        {
            "https://export.arxiv.org/api/query?id_list=2401.01234": FakeResponse(
                503,
                {"content-type": "text/html"},
                b"<html>untrusted error body</html>",
            )
        }
    )

    source = await ArxivConnector(client).fetch(url)

    assert source.status == "blocked"
    assert source.reason == "unsupported_mime"
    assert source.metadata == {"http_status": 503, "content_type": "text/html"}


@pytest.mark.asyncio
async def test_arxiv_connector_normalizes_legacy_category_identifier_with_encoded_query() -> (
    None
):
    url = "https://arxiv.org/abs/hep-th/9901001v2"
    api_url = "https://export.arxiv.org/api/query?id_list=hep-th%2F9901001v2"
    client = FakeSafeHttpClient(
        {
            api_url: FakeResponse(
                200,
                {"content-type": "application/atom+xml"},
                _fixture_bytes("arxiv_record.xml"),
            )
        }
    )

    source = await ArxivConnector(client).fetch(url)

    assert source.status == "ready"
    assert source.canonical_url == url
    assert source.metadata["arxiv_id"] == "hep-th/9901001v2"
    assert client.requests[0][0] == api_url


@pytest.mark.asyncio
async def test_arxiv_connector_normalizes_current_identifier_without_a_version() -> (
    None
):
    url = "https://arxiv.org/abs/2401.01234"
    api_url = "https://export.arxiv.org/api/query?id_list=2401.01234"
    client = FakeSafeHttpClient(
        {
            api_url: FakeResponse(
                200,
                {"content-type": "application/atom+xml"},
                _fixture_bytes("arxiv_record.xml"),
            )
        }
    )

    source = await ArxivConnector(client).fetch(url)

    assert source.status == "ready"
    assert source.canonical_url == url
    assert source.metadata["arxiv_id"] == "2401.01234"


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "url",
    [
        "https://arxiv.org/abs/2401.01234&foo=bar",
        "https://arxiv.org/abs/2401.01234/extra",
        "https://arxiv.org/abs/../2401.01234",
    ],
)
async def test_arxiv_connector_rejects_non_identifier_paths_without_dispatching(
    url: str,
) -> None:
    client = FakeSafeHttpClient({})

    source = await ArxivConnector(client).fetch(url)

    assert source.status == "blocked"
    assert source.reason == "unsupported_arxiv_url"
    assert client.requests == []


@pytest.mark.asyncio
async def test_arxiv_connector_blocks_malformed_atom_xml() -> None:
    url = "https://arxiv.org/abs/2401.01234"
    client = FakeSafeHttpClient(
        {
            "https://export.arxiv.org/api/query?id_list=2401.01234": FakeResponse(
                200,
                {"content-type": "application/atom+xml"},
                _fixture_bytes("arxiv_malformed.xml"),
            )
        }
    )

    source = await ArxivConnector(client).fetch(url)

    assert source.status == "blocked"
    assert source.reason == "invalid_arxiv_response"
    assert source.text == ""


@pytest.mark.asyncio
async def test_arxiv_connector_blocks_html_before_parsing_atom() -> None:
    url = "https://arxiv.org/abs/2401.01234"
    client = FakeSafeHttpClient(
        {
            "https://export.arxiv.org/api/query?id_list=2401.01234": FakeResponse(
                200,
                {"content-type": "text/html"},
                b"<html><body>not Atom</body></html>",
            )
        }
    )

    source = await ArxivConnector(client).fetch(url)

    assert source.status == "blocked"
    assert source.reason == "unsupported_mime"
    assert source.metadata == {"http_status": 200, "content_type": "text/html"}
    assert source.text == ""


@pytest.mark.asyncio
async def test_arxiv_connector_blocks_credentialed_url_before_path_parsing_or_dispatch() -> (
    None
):
    client = FakeSafeHttpClient({})

    source = await ArxivConnector(client).fetch(
        "https://user:credential@arxiv.org/abs/2401.01234"
    )

    assert source.status == "blocked"
    assert source.reason == "unsafe_url"
    assert "credential" not in repr(source)
    assert client.requests == []
