"""Bounded MIME and body-size checks shared by structured connectors."""

from collections.abc import Mapping
from collections.abc import Set as AbstractSet
from dataclasses import dataclass
from typing import Protocol

MAX_RESPONSE_BYTES = 5 * 1024 * 1024


class ResponseLike(Protocol):
    """The buffered response attributes needed for connector-side validation."""

    status_code: int
    headers: Mapping[str, str]
    content: bytes


@dataclass(frozen=True)
class ResponseBodyValidation:
    """A parsed-body admission decision with safe diagnostic metadata."""

    reason: str | None
    metadata: Mapping[str, object]


def validate_response_body(
    response: ResponseLike, *, allowed_mime_types: AbstractSet[str]
) -> ResponseBodyValidation:
    """Reject unsupported or oversized bodies before a connector decodes them."""
    content_type = _content_type(response.headers)
    metadata = {"http_status": response.status_code, "content_type": content_type}
    content_length = _declared_content_length(response.headers)
    if content_length is not None and content_length > MAX_RESPONSE_BYTES:
        return ResponseBodyValidation("response_too_large", metadata)
    if content_type not in {mime_type.lower() for mime_type in allowed_mime_types}:
        return ResponseBodyValidation("unsupported_mime", metadata)
    if len(response.content) > MAX_RESPONSE_BYTES:
        return ResponseBodyValidation("response_too_large", metadata)
    return ResponseBodyValidation(None, metadata)


def _content_type(headers: Mapping[str, str]) -> str:
    return _header_value(headers, "content-type").split(";", 1)[0].strip().lower()


def _declared_content_length(headers: Mapping[str, str]) -> int | None:
    value = _header_value(headers, "content-length")
    try:
        content_length = int(value)
    except ValueError:
        return None
    return content_length if content_length >= 0 else None


def _header_value(headers: Mapping[str, str], name: str) -> str:
    normalized_name = name.casefold()
    return next(
        (value for key, value in headers.items() if key.casefold() == normalized_name),
        "",
    )
