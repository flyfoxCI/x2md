"""Runtime composition for safe public-source connectors."""

from dataclasses import dataclass

from app.config import Settings
from app.services.connectors import (
    ArxivConnector,
    ConnectorRouter,
    GitHubConnector,
    HuggingFaceConnector,
    WebConnector,
    XConnector,
    YouTubeConnector,
)
from app.services.url_safety import SafeHttpClient


@dataclass(slots=True)
class ConnectorResources:
    """Connector router together with the outbound client it owns."""

    router: ConnectorRouter
    client: SafeHttpClient

    async def aclose(self) -> None:
        """Release the safe outbound client at application shutdown."""
        await self.client.aclose()


def compose_connector_resources(settings: Settings) -> ConnectorResources:
    """Build the one safe connector router using server-side configuration only."""
    client = SafeHttpClient()
    github_token = (
        settings.github_token.get_secret_value() if settings.github_token else None
    )
    router = ConnectorRouter(
        generic_connector=WebConnector(client),
        connectors=(
            GitHubConnector(client, token=github_token),
            ArxivConnector(client),
            HuggingFaceConnector(client),
            YouTubeConnector(client),
            XConnector(client, bearer_token=settings.x_bearer_token),
        ),
    )
    return ConnectorResources(router=router, client=client)
