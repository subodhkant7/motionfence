"""Knowledge retrieval service and registry maintaining full evidence provenance."""

from typing import Dict, List, Optional
import time

from motionfence.knowledge.models import KnowledgeEvidence, TrustStatus
from motionfence.knowledge.provider import KnowledgeProvider, KnowledgeProviderError
from motionfence.models.events import EventType
from motionfence.runtime.events import EventBus


class KnowledgeRetrievalService:
    """Orchestrates operational knowledge queries, provenance recording, and evidence registration."""

    def __init__(
        self,
        provider: KnowledgeProvider,
        fallback_provider: Optional[KnowledgeProvider] = None,
        event_bus: Optional[EventBus] = None,
    ) -> None:
        self.provider = provider
        self.fallback_provider = fallback_provider
        self.event_bus = event_bus
        self._evidence_registry: Dict[str, KnowledgeEvidence] = {}

    def query(self, search_query: str) -> List[KnowledgeEvidence]:
        """Execute search query, store results in registry, and record structured audit events."""
        if self.event_bus:
            self.event_bus.emit(
                EventType.KNOWLEDGE_QUERY_REQUESTED,
                f"Knowledge retrieval requested: '{search_query}'",
                payload={"query": search_query, "provider": getattr(self.provider, "provider_name", "unknown")},
            )

        results: List[KnowledgeEvidence] = []
        try:
            results = self.provider.retrieve(search_query)
        except KnowledgeProviderError as e:
            if self.fallback_provider is not None:
                if self.event_bus:
                    self.event_bus.emit(
                        EventType.KNOWLEDGE_RESULT_REJECTED,
                        f"Primary provider failed ({e}); falling back to secondary provider.",
                        payload={"query": search_query, "error": str(e)},
                    )
                results = self.fallback_provider.retrieve(search_query)
            else:
                if self.event_bus:
                    self.event_bus.emit(
                        EventType.KNOWLEDGE_RESULT_REJECTED,
                        f"Knowledge retrieval failed: {e}",
                        payload={"query": search_query, "error": str(e)},
                    )
                raise

        # Register evidence items to maintain continuous provenance chain
        for item in results:
            self._evidence_registry[item.id] = item

        if self.event_bus:
            self.event_bus.emit(
                EventType.KNOWLEDGE_RESULT_RECEIVED,
                f"Retrieved {len(results)} knowledge evidence items for '{search_query}'.",
                payload={
                    "query": search_query,
                    "count": len(results),
                    "evidence_ids": [item.id for item in results],
                },
            )

        return results

    def get_evidence(self, evidence_id: str) -> Optional[KnowledgeEvidence]:
        """Lookup previously retrieved knowledge evidence by ID."""
        return self._evidence_registry.get(evidence_id)

    def register_evidence(self, evidence: KnowledgeEvidence) -> None:
        """Manually register knowledge evidence (e.g. for testing or preloaded SOPs)."""
        self._evidence_registry[evidence.id] = evidence

    def get_all_registered_evidence(self) -> List[KnowledgeEvidence]:
        """Return all registered knowledge items."""
        return list(self._evidence_registry.values())
