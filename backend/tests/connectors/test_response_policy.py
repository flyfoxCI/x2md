"""Tests for shared bounded body and MIME validation."""

from collections.abc import Mapping
from dataclasses import dataclass

import pytest

from app.services.connectors.response_policy import (
    MAX_RESPONSE_BYTES,
    validate_response_body,
)


@dataclass(frozen=True)
class FakeResponse:
    status_code: int
    headers: Mapping[str, str]
    content: bytes


@pytest.mark.parametrize(
    "content_length",
    [str(MAX_RESPONSE_BYTES + 1), str(MAX_RESPONSE_BYTES + 10)],
)
def test_response_policy_rejects_declared_oversize_before_body_parsing(
    content_length: str,
) -> None:
    result = validate_response_body(
        FakeResponse(
            200,
            {"Content-Type": "application/json", "Content-Length": content_length},
            b"not parsed",
        ),
        allowed_mime_types={"application/json"},
    )

    assert result.reason == "response_too_large"
    assert result.metadata == {
        "http_status": 200,
        "content_type": "application/json",
    }


def test_response_policy_rejects_actual_oversize_and_invalid_mime_case_insensitively() -> (
    None
):
    oversized = validate_response_body(
        FakeResponse(
            200,
            {"cOnTeNt-TyPe": "Application/JSON; charset=UTF-8"},
            b"x" * (MAX_RESPONSE_BYTES + 1),
        ),
        allowed_mime_types={"application/json"},
    )
    unsupported = validate_response_body(
        FakeResponse(
            200,
            {"CONTENT-TYPE": "text/html"},
            b"<html />",
        ),
        allowed_mime_types={"application/json"},
    )

    assert oversized.reason == "response_too_large"
    assert unsupported.reason == "unsupported_mime"
    assert unsupported.metadata == {"http_status": 200, "content_type": "text/html"}


def test_response_policy_accepts_an_explicit_larger_pdf_limit_without_changing_default() -> None:
    response = FakeResponse(
        200,
        {"content-type": "application/pdf", "content-length": str(6 * 1024 * 1024)},
        b"%PDF-small-fixture",
    )

    default = validate_response_body(response, allowed_mime_types={"application/pdf"})
    explicit = validate_response_body(
        response,
        allowed_mime_types={"application/pdf"},
        max_response_bytes=25 * 1024 * 1024,
    )

    assert default.reason == "response_too_large"
    assert explicit.reason is None


@pytest.mark.parametrize("content_length", ["not-a-number", "-1"])
def test_response_policy_ignores_malformed_or_negative_declared_size(
    content_length: str,
) -> None:
    result = validate_response_body(
        FakeResponse(
            200,
            {"content-type": "application/json", "content-length": content_length},
            b"{}",
        ),
        allowed_mime_types={"application/json"},
    )

    assert result.reason is None
