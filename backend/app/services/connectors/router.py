"""URL-to-connector selection without platform branching in route handlers."""

from collections.abc import Sequence

from app.services.connectors.base import Connector, NormalizedSource


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
        """Choose the first specialized connector that owns the URL."""
        return next(
            (connector for connector in self._connectors if connector.can_handle(url)),
            self._generic_connector,
        )

    async def fetch(self, url: str) -> NormalizedSource:
        """Retrieve a normalized source using the selected connector."""
        return await self.select(url).fetch(url)
