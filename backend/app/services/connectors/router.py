"""URL-to-connector selection without platform branching in route handlers."""

from collections.abc import Sequence

from app.services.connectors.base import Connector, NormalizedSource
from app.services.url_safety import UnsafeUrlError, validate_public_url


class ConnectorRouter:
    """Select a specific connector or the generic web fallback."""

    def __init__(
        self,
        *,
        generic_connector: Connector,
        connectors: Sequence[Connector] = (),
    ) -> None:
        self._generic_connector = generic_connector
        self._connectors = tuple(connectors)

    def select(self, url: str) -> Connector:
        """Choose the first specialized connector for a validated canonical URL."""
        try:
            canonical_url = str(validate_public_url(url))
        except UnsafeUrlError:
            return _UnsafeUrlConnector()
        return next(
            (
                connector
                for connector in self._connectors
                if connector.can_handle(canonical_url)
            ),
            self._generic_connector,
        )

    async def fetch(self, url: str) -> NormalizedSource:
        """Retrieve a normalized source or a safe blocked result for invalid URLs."""
        try:
            canonical_url = str(validate_public_url(url))
        except UnsafeUrlError:
            return _unsafe_source()
        return await self.select(canonical_url).fetch(canonical_url)


def _unsafe_source() -> NormalizedSource:
    """Avoid reflecting malformed URLs or credential text in an import result."""
    return NormalizedSource(
        canonical_url="https://invalid.invalid/",
        platform="web",
        title="Invalid source URL",
        text="",
        markdown="",
        status="blocked",
        metadata={},
        reason="unsafe_url",
        provenance={"router": "url_safety"},
    )


class _UnsafeUrlConnector:
    """Return a structured safe result when ``select`` receives an invalid URL."""

    def can_handle(self, url: str) -> bool:
        """This connector is selected only internally for an invalid URL."""
        return False

    async def fetch(self, url: str) -> NormalizedSource:
        """Never reflect or fetch an unsafe original URL."""
        return _unsafe_source()
