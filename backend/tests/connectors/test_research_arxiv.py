"""PDF-backed arXiv research collection contracts."""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from io import BytesIO
from types import SimpleNamespace

import pytest
from pypdf import PdfWriter
from pypdf.generic import DecodedStreamObject, DictionaryObject, NameObject

from app.services.research.collectors.arxiv import ArxivResearchCollector
from app.services.research.collectors.pdf import extract_pdf_pages


@dataclass(frozen=True)
class FakeResponse:
    status_code: int
    headers: Mapping[str, str]
    content: bytes


class FakeSafeHttpClient:
    def __init__(self, responses: Mapping[str, FakeResponse]) -> None:
        self._responses = responses
        self.requests: list[str] = []

    async def get_public(self, url: str, **_: object) -> FakeResponse:
        self.requests.append(url)
        return self._responses[url]


def _text_pdf_bytes(*page_texts: str) -> bytes:
    writer = PdfWriter()
    font = writer._add_object(
        DictionaryObject(
            {
                NameObject("/Type"): NameObject("/Font"),
                NameObject("/Subtype"): NameObject("/Type1"),
                NameObject("/BaseFont"): NameObject("/Helvetica"),
            }
        )
    )
    for page_text in page_texts:
        page = writer.add_blank_page(width=612, height=792)
        stream = DecodedStreamObject()
        escaped = page_text.replace("\\", "\\\\").replace("(", "\\(").replace(")", "\\)")
        stream.set_data(f"BT /F1 12 Tf 72 720 Td ({escaped}) Tj ET".encode())
        page[NameObject("/Resources")] = DictionaryObject(
            {NameObject("/Font"): DictionaryObject({NameObject("/F1"): font})}
        )
        page[NameObject("/Contents")] = writer._add_object(stream)
    output = BytesIO()
    writer.write(output)
    return output.getvalue()


def test_pdf_extraction_returns_page_locators_and_honest_partial_coverage() -> None:
    result = extract_pdf_pages(
        _text_pdf_bytes("First page evidence", "Second page evidence"),
        locator_prefix="arxiv://2401.01234v2/pdf",
        source_revision="2401.01234v2",
        max_pages=1,
        max_chars=500_000,
    )

    assert result.evidence[0].locator == "arxiv://2401.01234v2/pdf#page=1"
    assert result.evidence[0].content == "First page evidence"
    assert result.coverage == {
        "complete": False,
        "page_count": 2,
        "pages_examined": 1,
        "reason": "page_limit",
        "text_characters": len("First page evidence"),
    }


def test_pdf_extraction_marks_encrypted_and_non_text_documents_partial() -> None:
    encrypted_writer = PdfWriter()
    encrypted_writer.add_blank_page(width=612, height=792)
    encrypted_writer.encrypt("secret")
    encrypted_stream = BytesIO()
    encrypted_writer.write(encrypted_stream)

    encrypted = extract_pdf_pages(
        encrypted_stream.getvalue(),
        locator_prefix="arxiv://2401.01234/pdf",
        source_revision="2401.01234",
        max_pages=60,
        max_chars=500_000,
    )
    non_text = extract_pdf_pages(
        _text_pdf_bytes(" "),
        locator_prefix="arxiv://2401.01234/pdf",
        source_revision="2401.01234",
        max_pages=60,
        max_chars=500_000,
    )

    assert encrypted.evidence[0].exclusion_reason == "encrypted_pdf"
    assert encrypted.coverage["complete"] is False
    assert non_text.evidence[0].exclusion_reason == "non_text_pdf_page"
    assert non_text.coverage["reason"] == "no_extractable_text"


@pytest.mark.asyncio
async def test_arxiv_research_collector_uses_versioned_pdf_and_page_evidence() -> None:
    identifier = "2401.01234v2"
    pdf_url = f"https://arxiv.org/pdf/{identifier}"
    client = FakeSafeHttpClient(
        {
            pdf_url: FakeResponse(
                200,
                {"content-type": "application/pdf"},
                _text_pdf_bytes("Method section", "Results section"),
            )
        }
    )

    result = await ArxivResearchCollector(client).collect(
        SimpleNamespace(
            canonical_url=f"https://arxiv.org/abs/{identifier}",
            platform="arxiv",
            metadata_json={"arxiv_id": identifier},
        )
    )

    assert result.source_revision == identifier
    assert tuple(item.locator for item in result.evidence) == (
        f"arxiv://{identifier}/pdf#page=1",
        f"arxiv://{identifier}/pdf#page=2",
    )
    assert result.coverage["complete"] is True
    assert result.coverage["requests_used"] == 1
    assert client.requests == [pdf_url]
