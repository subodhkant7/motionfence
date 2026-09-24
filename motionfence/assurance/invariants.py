"""Specification and registry of machine-checkable safety invariant properties."""

from dataclasses import dataclass
from typing import Callable, Dict, List, Optional
from motionfence.assurance.models import FindingSeverity, AssuranceScope


@dataclass
class AssuranceProperty:
    """Definition of a machine-checkable safety property."""
    property_id: str
    name: str
    description: str
    severity: FindingSeverity
    scope: AssuranceScope
    check_fn: Optional[Callable] = None


class AssurancePropertyRegistry:
    """Extensible registry of bounded assurance and safety properties."""

    def __init__(self) -> None:
        self._properties: Dict[str, AssuranceProperty] = {}
        self._register_default_properties()

    def register(self, prop: AssuranceProperty) -> None:
        """Register a new property into the assurance suite."""
        self._properties[prop.property_id] = prop

    def get(self, property_id: str) -> Optional[AssuranceProperty]:
        """Retrieve a registered property by ID."""
        return self._properties.get(property_id)

    def list_all(self) -> List[AssuranceProperty]:
        """List all currently registered properties in deterministic order."""
        return sorted(self._properties.values(), key=lambda p: p.property_id)

    def _register_default_properties(self) -> None:
        """Register the core MotionFence Phase 2E bounded safety properties."""
        # Property 1: Human-zone prohibition
        self.register(
            AssuranceProperty(
                property_id="PROP_001_HUMAN_ZONE_PROHIBITION",
                name="Human-Zone Actuation Prohibition",
                description="If human_zone == OCCUPIED, valve actuation commands cannot be authorized (ALLOW is prohibited).",
                severity=FindingSeverity.CRITICAL,
                scope=AssuranceScope.STATIC_INVARIANT,
            )
        )

        # Property 2: Cooling preservation
        self.register(
            AssuranceProperty(
                property_id="PROP_002_COOLING_PRESERVATION",
                name="Cooling System Preservation",
                description="An ALLOW authorization decision cannot occur if the cooling system is INACTIVE or DEGRADED.",
                severity=FindingSeverity.CRITICAL,
                scope=AssuranceScope.STATIC_INVARIANT,
            )
        )

        # Property 3: Unauthorized mutation impossible
        self.register(
            AssuranceProperty(
                property_id="PROP_003_UNAUTHORIZED_MUTATION_IMPOSSIBLE",
                name="Actuator Authority Isolation",
                description="PhysicalWorld state cannot mutate unless executed with a valid, matching, unconsumed AuthorizationTicket.",
                severity=FindingSeverity.CRITICAL,
                scope=AssuranceScope.STATIC_INVARIANT,
            )
        )

        # Property 4: Conflicted policy blocks authorization
        self.register(
            AssuranceProperty(
                property_id="PROP_004_CONFLICTED_POLICY_BLOCKS_AUTHORIZATION",
                name="Conflicted Knowledge Policy Gating",
                description="If active knowledge constraints contain an unresolved mutual conflict, Policy cannot return ALLOW.",
                severity=FindingSeverity.HIGH,
                scope=AssuranceScope.STATIC_INVARIANT,
            )
        )

        # Property 5: Stale safety constraint blocks unsafe authorization
        self.register(
            AssuranceProperty(
                property_id="PROP_005_STALE_SAFETY_CONSTRAINT_BLOCKS_AUTHORIZATION",
                name="Stale Safety Knowledge Gating",
                description="Stale safety-relevant knowledge constraints cannot silently authorize physical action without recertification.",
                severity=FindingSeverity.HIGH,
                scope=AssuranceScope.STATIC_INVARIANT,
            )
        )

        # Property 6: Contradictory evidence gating
        self.register(
            AssuranceProperty(
                property_id="PROP_006_CONTRADICTORY_EVIDENCE_GATING",
                name="Sensor Contradiction Gating",
                description="High-severity sensor contradictions across physical modalities must block ALLOW verdicts.",
                severity=FindingSeverity.HIGH,
                scope=AssuranceScope.STATIC_INVARIANT,
            )
        )

        # Property 7: Bounded temporal cooling preservation
        self.register(
            AssuranceProperty(
                property_id="PROP_007_TEMPORAL_COOLING_PRESERVATION",
                name="Temporal Cooling Preservation Across Horizon",
                description="Cooling system must remain ACTIVE throughout all sequential valve transitions across bounded horizon H.",
                severity=FindingSeverity.CRITICAL,
                scope=AssuranceScope.TEMPORAL_SAFETY,
            )
        )
