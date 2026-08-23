"""Bounded, version-aware arXiv PDF collection."""

from __future__ import annotations

import re

import httpx

from app.services.connectors.arxiv import SafeHttpClientProtocol
from app.services.connectors.response_policy import validate_response_body
from app.services.research.collectors.base import ResearchableSource
from app.services.research.collectors.pdf import extract_pdf_pages
from app.services.research.contracts import CollectionResult, collection_budget
from app.services.url_safety import RateLimitExceededError, UnsafeUrlError

_ARXIV_IDENTIFIER = re.compile(
    r"^(?:\d{4}\.\d{4,5}|[A-Za-z]+(?:[.-][A-Za-z]+)*/\d{7})(?:v\d+)?$"
)


class ArxivResearchCollector:
    """Use the imported paper version's PDF as page-level research evidence."""

    def __init__(self, client: SafeHttpClientProtocol) -> None:
        self._client = client

    async def collect(self, source: ResearchableSource) -> CollectionResult:
        """Fetch one bounded PDF and report extraction coverage rather than OCRing it."""
        identifier = _identifier_from_source(source)
        if identifier is None:
            return _failure_result("invalid_arxiv_identifier")
        budget = collection_budget("arxiv")
        pdf_url = f"https://arxiv.org/pdf/{identifier}"
        try:
            response = await self._client.get_public(
                pdf_url, headers={"accept": "application/pdf"}
            )
        except RateLimitExceededError:
            return _failure_result("rate_limited", source_revision=identifier)
        except UnsafeUrlError:
            return _failure_result("unsafe_url", source_revision=identifier)
        except httpx.RequestError:
            return _failure_result("network_error", source_revision=identifier)
        policy = validate_response_body(
            response,
            allowed_mime_types={"application/pdf"},
            max_response_bytes=budget.max_pdf_bytes,
        )
        if policy.reason is not None:
            return _failure_result(policy.reason, source_revision=identifier)
        if not 200 <= response.status_code < 300:
            return _failure_result("arxiv_http_status", source_revision=identifier)
        extraction = extract_pdf_pages(
            response.content,
            locator_prefix=f"arxiv://{identifier}/pdf",
            source_revision=identifier,
            max_pages=budget.max_pages or 0,
            max_chars=budget.max_extracted_chars or 0,
        )
        coverage = {**extraction.coverage, "pdf_bytes": len(response.content), "requests_used": 1}
        return CollectionResult(
            platform="arxiv",
            source_revision=identifier,
            evidence=extraction.evidence,
            coverage=coverage,
        )


def _identifier_from_source(source: ResearchableSource) -> str | None:
    candidate = source.metadata_json.get("arxiv_id")
    if not isinstance(candidate, str):
        marker = "/abs/"
        candidate = source.canonical_url.partition(marker)[2] if marker in source.canonical_url else ""
    candidate = candidate.strip()
    return candidate if _ARXIV_IDENTIFIER.fullmatch(candidate) else None


def _failure_result(reason: str, *, source_revision: str | None = None) -> CollectionResult:
    return CollectionResult(
        platform="arxiv",
        source_revision=source_revision,
        evidence=(),
        coverage={"complete": False, "reason": reason, "requests_used": 0},
    )
