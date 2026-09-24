"""Deterministic capability policy and action-boundary management.

Phase 2G restricts what actions an entity (such as EvidenceAcquisitionPlanner or
agent proposal generator) can request based on explicitly granted capabilities.

SECURITY INVARIANTS:
1. An EvidenceAcquisitionPlanner CANNOT possess ACTUATE capability.
2. No arbitrary tool name or unregistered actuator command can be introduced.
3. Information actions cannot be escalated into consequential actions.
"""

from enum import Enum
from typing import Dict, List, Optional, Set
from pydantic import BaseModel, Field

from motionfence.models.actions import ActionType, ActionClass, get_action_class, is_consequential_action
from motionfence.simulation.exceptions import UnauthorizedActionError


class CapabilityEscalationError(UnauthorizedActionError):
    """Raised when an informational entity attempts to invoke an actuation capability."""
    pass


class CapabilityType(str, Enum):
    """Deterministic capability classes in the physical and perception environments."""
    OBSERVE = "OBSERVE"                  # Passive overview observation
    INSPECT = "INSPECT"                  # Targeted optical/thermal inspection of a component
    READ_SENSOR = "READ_SENSOR"          # Direct polling or resampling of telemetry
    QUERY_KNOWLEDGE = "QUERY_KNOWLEDGE"  # Retrieval from manuals or engineering databases
    REORIENT_SENSOR = "REORIENT_SENSOR"  # Pan/tilt/zoom gimbal repositioning (passive PTU)
    ACTUATE = "ACTUATE"                  # Physical state mutation (strictly gated by Safety Enclave)


class Capability(BaseModel):
    """Specification of an operational capability and its permitted actions."""
    capability_type: CapabilityType
    allowed_actions: List[ActionType]
    is_consequential: bool = False
    description: str = ""


# Default mapping from capability to allowed actions
CAPABILITY_ACTION_MAPPING: Dict[CapabilityType, List[ActionType]] = {
    CapabilityType.OBSERVE: [
        ActionType.INSPECT,
        ActionType.GATHER_EVIDENCE,
    ],
    CapabilityType.INSPECT: [
        ActionType.INSPECT_TARGET,
    ],
    CapabilityType.READ_SENSOR: [
        ActionType.RESAMPLE_SENSOR,
        ActionType.READ_SENSOR,
        ActionType.WAIT_FOR_STABLE_STATE,
    ],
    CapabilityType.QUERY_KNOWLEDGE: [
        ActionType.QUERY_KNOWLEDGE,
    ],
    CapabilityType.REORIENT_SENSOR: [
        ActionType.CHANGE_VIEWPOINT,
    ],
    CapabilityType.ACTUATE: [
        ActionType.CLOSE_VALVE,
        ActionType.OPEN_VALVE,
        ActionType.START_PUMP,
        ActionType.STOP_PUMP,
        ActionType.ADJUST_COOLING,
        ActionType.EMERGENCY_STOP,
    ],
}


class CapabilityPolicy(BaseModel):
    """Deterministic capability policy governing what actions an entity may request."""
    policy_id: str = "default_capability_policy"
    granted_capabilities: List[CapabilityType] = Field(default_factory=list)
    allowed_targets: Optional[List[str]] = None

    def is_action_permitted(self, action_type: ActionType, target: Optional[str] = None) -> bool:
        """Check whether the given action type and target are permitted by this policy."""
        # Target check if restricted
        if self.allowed_targets is not None and target is not None:
            if target not in self.allowed_targets:
                return False

        # Capability check
        for cap in self.granted_capabilities:
            if action_type in CAPABILITY_ACTION_MAPPING.get(cap, []):
                return True
        return False

    def validate_action(self, action_type: ActionType, target: Optional[str] = None) -> None:
        """Validate that an action is permitted, raising a descriptive error on violation."""
        # Detect escalation: requesting consequential action without ACTUATE capability
        if is_consequential_action(action_type) and CapabilityType.ACTUATE not in self.granted_capabilities:
            raise CapabilityEscalationError(
                f"SECURITY VIOLATION: Entity with capabilities {[c.value for c in self.granted_capabilities]} "
                f"attempted to invoke consequential action '{action_type.value}'. Consequential actions strictly "
                f"require ACTUATE capability and Safety Enclave authorization."
            )

        if not self.is_action_permitted(action_type, target):
            raise UnauthorizedActionError(
                f"Action '{action_type.value}' on target '{target}' is not permitted by capability policy "
                f"'{self.policy_id}'. Granted capabilities: {[c.value for c in self.granted_capabilities]}."
            )

    @property
    def allows_actuation(self) -> bool:
        """Return True if this policy grants consequential actuation capability."""
        return CapabilityType.ACTUATE in self.granted_capabilities


def create_planner_capability_policy(
    allowed_targets: Optional[List[str]] = None,
) -> CapabilityPolicy:
    """Create a strictly non-consequential capability policy for the EvidenceAcquisitionPlanner.

    Planner receives observation, inspection, and sensor polling capabilities,
    but NEVER consequential ACTUATE authority.
    """
    return CapabilityPolicy(
        policy_id="evidence_planner_capability_policy",
        granted_capabilities=[
            CapabilityType.OBSERVE,
            CapabilityType.INSPECT,
            CapabilityType.READ_SENSOR,
            CapabilityType.QUERY_KNOWLEDGE,
            CapabilityType.REORIENT_SENSOR,
        ],
        allowed_targets=allowed_targets,
    )


def create_actuator_capability_policy(
    allowed_targets: Optional[List[str]] = None,
) -> CapabilityPolicy:
    """Create a consequential capability policy for the PhysicalActuator."""
    return CapabilityPolicy(
        policy_id="physical_actuator_capability_policy",
        granted_capabilities=[CapabilityType.ACTUATE],
        allowed_targets=allowed_targets,
    )
