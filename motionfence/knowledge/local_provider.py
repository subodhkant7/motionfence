"""Deterministic local knowledge provider and synthetic plant documentation fixtures."""

import time
from typing import Dict, List, Optional
from motionfence.knowledge.models import KnowledgeEvidence, TrustStatus


class LocalKnowledgeProvider:
    """Offline deterministic provider serving synthetic industrial plant documentation fixtures."""

    def __init__(self, custom_fixtures: Optional[List[KnowledgeEvidence]] = None) -> None:
        self.fixtures: List[KnowledgeEvidence] = custom_fixtures if custom_fixtures is not None else self._build_default_fixtures()

    def retrieve(self, query: str) -> List[KnowledgeEvidence]:
        """Perform deterministic retrieval against local plant operating documentation."""
        query_normalized = query.lower()
        results: List[KnowledgeEvidence] = []

        for item in self.fixtures:
            # Match on query keywords in title, content, or query field
            text_to_search = f"{item.title} {item.content} {item.query}".lower()
            tokens = [t for t in query_normalized.split() if len(t) > 2]
            if any(t in text_to_search for t in tokens) or not tokens:
                results.append(item)

        # If no specific keyword match, return all relevant plant rules as baseline knowledge
        return results if results else list(self.fixtures)

    @classmethod
    def _build_default_fixtures(cls) -> List[KnowledgeEvidence]:
        """Construct the 5 mandatory deterministic synthetic plant documentation fixtures."""
        now = time.time()
        ninety_days_ago = now - (86400.0 * 90.0)

        return [
            # Fixture 1: Valid operational prohibition
            KnowledgeEvidence(
                id="kb_fixture_001",
                query="Valve B operational restrictions with pumps",
                title="Industrial Plant Safety Manual - Section 4.2: Pump Isolation Rules",
                source_url="local://plant_manual_v1/pumps_and_valves#sec4.2",
                content="MANDATORY SAFETY PROHIBITION: Valve B must not be closed while Pump P1 is active. Closing Valve B under pump pressure creates hazardous hydraulic hammer.",
                retrieved_at=now,
                source_metadata={"section": "4.2", "mandatory": True, "category": "prohibition"},
                provenance="local_fixture:plant_safety_manual_v1",
                confidence=0.98,
                trust_status=TrustStatus.LOCAL_FIXTURE,
            ),
            # Fixture 2: Ordinary procedure (harmless guidance; must NOT become a prohibition)
            KnowledgeEvidence(
                id="kb_fixture_002",
                query="Valve B routine maintenance and inspection",
                title="Industrial Plant Maintenance SOP - Section 2.1: Pre-Service Checklist",
                source_url="local://plant_manual_v1/routine_maintenance#sec2.1",
                content="ROUTINE PROCEDURE: Visual inspection should be performed before servicing Valve B. Check seal integrity and record ambient temperature.",
                retrieved_at=now,
                source_metadata={"section": "2.1", "mandatory": False, "category": "procedure"},
                provenance="local_fixture:maintenance_sop_v1",
                confidence=0.92,
                trust_status=TrustStatus.LOCAL_FIXTURE,
            ),
            # Fixture 3: Contradictory source (incompatible with Fixture 1)
            KnowledgeEvidence(
                id="kb_fixture_003",
                query="Emergency valve B servicing and pump P1 operation",
                title="Plant Emergency Guideline - Revision 3: Fast Isolation",
                source_url="local://plant_manual_v1/emergency_guidelines#rev3",
                content="CONTRADICTORY GUIDANCE: Valve B may be closed while Pump P1 is active during critical emergency isolation when secondary bypass valve is partially open.",
                retrieved_at=now,
                source_metadata={"revision": "3", "category": "contradictory_guidance"},
                provenance="local_fixture:emergency_handbook_v3",
                confidence=0.91,
                trust_status=TrustStatus.LOCAL_FIXTURE,
            ),
            # Fixture 4: Stale source (operational guidance old enough to trigger freshness handling)
            KnowledgeEvidence(
                id="kb_fixture_004",
                query="Cooling loop secondary isolation specification",
                title="Legacy Plant Specification 2021 (Archived)",
                source_url="local://plant_manual_archived/cooling_spec_2021",
                content="ARCHIVED SAFETY INVARIANT: Valve B closure requires secondary thermal purge verification across cooling circuit prior to mechanical seating.",
                retrieved_at=ninety_days_ago,  # 90 days old -> Stale
                source_metadata={"archived": True, "year": 2021},
                provenance="local_fixture:legacy_spec_2021",
                confidence=0.85,
                trust_status=TrustStatus.STALE,
            ),
            # Fixture 5: Missing provenance / malformed fixture (cannot be trusted)
            KnowledgeEvidence(
                id="kb_fixture_005",
                query="Unattributed note on valve operation",
                title="Unattributed Scratchpad Note",
                source_url="",  # Missing source URL
                content="Anonymous note: Close Valve B whenever pressure drops.",
                retrieved_at=now,
                source_metadata={},
                provenance="",  # Missing provenance!
                confidence=0.30,
                trust_status=TrustStatus.REJECTED,
            ),
        ]
