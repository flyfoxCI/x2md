"""Platform-specific collectors that return bounded research evidence."""

from app.services.research.collectors.github import GitHubResearchCollector

__all__ = ["GitHubResearchCollector"]

