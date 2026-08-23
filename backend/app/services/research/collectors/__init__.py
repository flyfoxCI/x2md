"""Platform-specific collectors that return bounded research evidence."""

from app.services.research.collectors.arxiv import ArxivResearchCollector
from app.services.research.collectors.github import GitHubResearchCollector
from app.services.research.collectors.huggingface import HuggingFaceResearchCollector

__all__ = [
    "ArxivResearchCollector",
    "GitHubResearchCollector",
    "HuggingFaceResearchCollector",
]
