"""Bounded text-layer extraction for public research PDFs."""

from __future__ import annotations

from dataclasses import dataclass
from io import BytesIO

from pypdf import PdfReader
from pypdf.errors import PdfReadError

from app.services.research.contracts import CollectedEvidence


@dataclass(frozen=True, slots=True)
class PdfExtraction:
    """Page-level evidence and honest extraction coverage for one PDF document."""

    evidence: tuple[CollectedEvidence, ...]
    coverage: dict[str, object]


def extract_pdf_pages(
    content: bytes,
    *,
    locator_prefix: str,
    source_revision: str,
    max_pages: int,
    max_chars: int,
) -> PdfExtraction:
    """Extract only a bounded text layer; OCR and encrypted documents stay partial."""
    try:
        reader = PdfReader(BytesIO(content))
    except (PdfReadError, ValueError, TypeError):
        return _document_exclusion(locator_prefix, source_revision, "invalid_pdf")
    if reader.is_encrypted:
        return _document_exclusion(locator_prefix, source_revision, "encrypted_pdf")

    try:
        page_count = len(reader.pages)
    except (PdfReadError, ValueError, TypeError):
        return _document_exclusion(locator_prefix, source_revision, "invalid_pdf")
    evidence: list[CollectedEvidence] = []
    text_characters = 0
    partial_reason: str | None = "page_limit" if page_count > max_pages else None
    pages_examined = min(page_count, max_pages)
    for page_index in range(pages_examined):
        locator = f"{locator_prefix}#page={page_index + 1}"
        try:
            extracted = reader.pages[page_index].extract_text()
        except (PdfReadError, ValueError, TypeError, KeyError):
            evidence.append(
                _excluded_page(locator, source_revision, page_index, "text_extraction_failed")
            )
            partial_reason = partial_reason or "text_extraction_failed"
            continue
        text = " ".join((extracted or "").replace("\x00", "\ufffd").split())
        if not text:
            evidence.append(_excluded_page(locator, source_revision, page_index, "non_text_pdf_page"))
            partial_reason = partial_reason or "no_extractable_text"
            continue
        remaining = max_chars - text_characters
        if remaining <= 0:
            evidence.append(
                _excluded_page(locator, source_revision, page_index, "character_limit")
            )
            partial_reason = "character_limit"
            break
        included_text = text[:remaining]
        evidence.append(
            CollectedEvidence(
                locator=locator,
                kind="paper_page",
                ordinal=len(evidence),
                decision="included",
                title=f"PDF page {page_index + 1}",
                content=included_text,
                source_revision=source_revision,
            )
        )
        text_characters += len(included_text)
        if len(included_text) != len(text):
            partial_reason = "character_limit"
            break
    if not any(item.decision == "included" for item in evidence):
        partial_reason = partial_reason or "no_extractable_text"
    coverage: dict[str, object] = {
        "complete": partial_reason is None,
        "page_count": page_count,
        "pages_examined": pages_examined,
        "text_characters": text_characters,
    }
    if partial_reason is not None:
        coverage["reason"] = partial_reason
    return PdfExtraction(evidence=tuple(evidence), coverage=coverage)


def _document_exclusion(
    locator_prefix: str, source_revision: str, reason: str
) -> PdfExtraction:
    evidence = CollectedEvidence(
        locator=f"{locator_prefix}#document",
        kind="paper_pdf",
        ordinal=0,
        decision="excluded",
        title="PDF document",
        source_revision=source_revision,
        exclusion_reason=reason,
    )
    return PdfExtraction(
        evidence=(evidence,),
        coverage={
            "complete": False,
            "page_count": 0,
            "pages_examined": 0,
            "reason": reason,
            "text_characters": 0,
        },
    )


def _excluded_page(
    locator: str, source_revision: str, page_index: int, reason: str
) -> CollectedEvidence:
    return CollectedEvidence(
        locator=locator,
        kind="paper_page",
        ordinal=page_index,
        decision="excluded",
        title=f"PDF page {page_index + 1}",
        source_revision=source_revision,
        exclusion_reason=reason,
    )
