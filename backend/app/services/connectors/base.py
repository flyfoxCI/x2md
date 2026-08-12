"""Shared normalized output contract for public-source connectors."""

from collections.abc import Mapping
from dataclasses import dataclass, field
from datetime import datetime
from math import isfinite
from types import MappingProxyType
from typing import Literal, Protocol

SourceStatus = Literal["ready", "partial", "blocked"]


@dataclass(frozen=True, slots=True)
class NormalizedSource:
    """Source content independent of any remote platform payload shape."""

    canonical_url: str
    platform: str
    title: str
    text: str
    markdown: str
    status: SourceStatus
    author: str | None = None
    published_at: datetime | None = None
    metadata: Mapping[str, object] = field(default_factory=dict)
    reason: str | None = None
    provenance: Mapping[str, object] = field(default_factory=dict)

    def __post_init__(self) -> None:
        if self.status not in {"ready", "partial", "blocked"}:
            raise ValueError("invalid source status")
        if self.status == "ready" and self.reason is not None:
            raise ValueError("ready sources cannot include a reason")
        if self.status == "ready" and (not self.text.strip() or not self.markdown.strip()):
            raise ValueError("ready sources require text and markdown")
        if self.status != "ready" and not self.reason:
            raise ValueError("partial and blocked sources require a reason")
        if self.status == "blocked" and (self.text or self.markdown):
            raise ValueError("blocked sources cannot include extracted content")
        object.__setattr__(self, "metadata", _freeze_mapping(self.metadata, "metadata"))
        object.__setattr__(self, "provenance", _freeze_mapping(self.provenance, "provenance"))


class Connector(Protocol):
    """A platform-aware connector selectable by ``ConnectorRouter``."""

    def can_handle(self, url: str) -> bool:
        """Return whether this connector owns the supplied URL."""

    async def fetch(self, url: str) -> NormalizedSource:
        """Retrieve the URL as a normalized source record."""


def _freeze_mapping(mapping: object, field_name: str) -> Mapping[str, object]:
    if not isinstance(mapping, Mapping):
        raise ValueError(  # noqa: TRY004 - this public contract specifies ValueError.
            f"{field_name} must be JSON-shaped: it must be a mapping"
        )
    frozen: dict[str, object] = {}
    for key, value in mapping.items():
        if not isinstance(key, str):
            raise ValueError(  # noqa: TRY004 - this public contract specifies ValueError.
                f"{field_name} must be JSON-shaped: mapping keys must be strings"
            )
        frozen[key] = _freeze_value(value, field_name)
    return MappingProxyType(frozen)


def _freeze_value(value: object, field_name: str) -> object:
    if value is None or type(value) in {bool, int, str}:
        return value
    if type(value) is float:
        if not isfinite(value):
            raise ValueError(f"{field_name} must be JSON-shaped: floats must be finite")
        return value
    if isinstance(value, Mapping):
        return _freeze_mapping(value, field_name)
    if isinstance(value, (list, tuple)):
        return tuple(_freeze_value(item, field_name) for item in value)
    raise ValueError(
        f"{field_name} must be JSON-shaped: values must be null, booleans, numbers, strings, mappings, or lists"
    )
