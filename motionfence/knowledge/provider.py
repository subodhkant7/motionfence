"""Knowledge provider interface and error definitions."""

from typing import List, Protocol, runtime_checkable
from motionfence.knowledge.models import KnowledgeEvidence


class KnowledgeProviderError(Exception):
    """Base exception for knowledge retrieval providers."""
    pass


class TavilyProviderError(KnowledgeProviderError):
    """Raised when an error occurs during Tavily API retrieval."""
    pass


@runtime_checkable
class KnowledgeProvider(Protocol):
    """Protocol for operational knowledge and engineering manual retrieval providers."""

    def retrieve(self, query: str) -> List[KnowledgeEvidence]:
        """Retrieve relevant knowledge evidence items for a given search query."""
        ...
