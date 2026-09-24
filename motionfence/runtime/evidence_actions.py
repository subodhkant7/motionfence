"""EvidenceActionGateway: Deterministic execution of bounded information-gathering actions.

Phase 2G introduces active evidence acquisition when MotionFence encounters
uncertainty (NEED_MORE_EVIDENCE). The gateway executes ONLY bounded informational
actions that mutate perception/sensor telemetry without altering consequential
physical plant state.

SECURITY INVARIANTS:
1. InformationActionGateway can close valve = NO
2. InformationActionGateway can start/stop pump = NO
3. InformationActionGateway can alter cooling = NO
4. InformationActionGateway can mint AuthorizationTicket = NO
5. InformationActionGateway can bypass SafetyEnclave = NO
6. Consequential action invocation strictly raises CapabilityEscalationError.
"""

from enum import Enum
from typing import Any, Dict, List, Optional
import time
import uuid
from pydantic import BaseModel, Field

from motionfence.models.actions import (
    ActionType,
    ActionClass,
    get_action_class,
    is_information_action,
    is_consequential_action,
)
from motionfence.evidence.models import Evidence, EvidenceSource
from motionfence.simulation.world import PhysicalWorld
from motionfence.runtime.events import EventBus
from motionfence.models.events import EventType
from motionfence.runtime.capabilities import (
    CapabilityPolicy,
    CapabilityType,
    CapabilityEscalationError,
    create_planner_capability_policy,
)
from motionfence.simulation.exceptions import UnauthorizedActionError


class InformationActionRisk(str, Enum):
    """Risk tier of information-gathering actions."""
    LOW = "LOW"        # Passive optical zoom, sensor read, telemetry query
    MEDIUM = "MEDIUM"  # Gimbal PTU pan/tilt reorientation
    HIGH = "HIGH"      # Proximity probe repositioning (still non-consequential)


class InformationGainLevel(str, Enum):
    """Categorical assessment of information gain."""
    HIGH = "HIGH"          # Significant ambiguity or contradiction resolution
    MEDIUM = "MEDIUM"      # Moderate confidence improvement or new sensor modality
    LOW = "LOW"            # Ineffective observation, minimal reduction in uncertainty
    ZERO = "ZERO"          # Completely uninformative or redundant reading
    NEGATIVE = "NEGATIVE"  # Contradiction amplified, uncertainty increased


class InformationAction(BaseModel):
    """Typed request for a bounded information-gathering operation."""
    action_id: str = Field(default_factory=lambda: f"info_{uuid.uuid4().hex[:8]}")
    action_type: ActionType
    target: str
    parameters: Dict[str, Any] = Field(default_factory=dict)
    reason: str = Field(default="Acquire missing evidence to resolve policy uncertainty.")
    expected_gain: str = Field(default="MEDIUM", description="Predicted information gain (LOW, MEDIUM, HIGH).")
    risk: InformationActionRisk = Field(default=InformationActionRisk.LOW)
    timestamp: float = Field(default_factory=time.time)


class InformationActionExecutionResult(BaseModel):
    """Outcome report from an executed information-gathering action."""
    success: bool
    action_id: str
    action_type: ActionType
    target: str
    new_evidence: List[Evidence] = Field(default_factory=list)
    predicted_gain: str
    observed_gain: str
    message: str
    timestamp: float = Field(default_factory=time.time)


class EvidenceActionGateway:
    """Bounded, safe gateway executing only passive information-gathering actions.

    SECURITY INVARIANTS:
    1. Possesses ZERO consequential actuator authority.
    2. Possesses ZERO ticket-minting authority.
    3. Any consequential action attempt (e.g. CLOSE_VALVE) strictly raises CapabilityEscalationError.
    4. Mutates only sensor telemetry and perception fixtures, never valves/pumps/cooling.
    """

    def __init__(
        self,
        world: PhysicalWorld,
        event_bus: Optional[EventBus] = None,
        capability_policy: Optional[CapabilityPolicy] = None,
    ) -> None:
        self.world = world
        self.event_bus = event_bus
        self.capability_policy = capability_policy or create_planner_capability_policy()

    def execute_action(self, action: InformationAction) -> InformationActionExecutionResult:
        """Execute a typed information action and produce empirical new evidence."""
        # Hard Security Gate 1: Reject consequential actions immediately
        if is_consequential_action(action.action_type):
            if self.event_bus:
                self.event_bus.emit(
                    EventType.EVIDENCE_ACTION_REJECTED,
                    f"SECURITY VIOLATION: InformationActionGateway rejected consequential action '{action.action_type.value}'.",
                    payload={"action_type": action.action_type.value, "target": action.target},
                )
            raise CapabilityEscalationError(
                f"SECURITY VIOLATION: InformationActionGateway cannot execute consequential action "
                f"'{action.action_type.value}'. Consequential actions strictly require SafetyEnclave and "
                f"consequential AuthorizationTicket."
            )

        # Hard Security Gate 2: Capability policy check
        self.capability_policy.validate_action(action.action_type, action.target)

        # Notify start of action
        if self.event_bus:
            self.event_bus.emit(
                EventType.EVIDENCE_ACTION_PROPOSED,
                f"Information action proposed: {action.action_type.value} on {action.target} (predicted_gain={action.expected_gain}).",
                payload=action.model_dump(),
            )
            self.event_bus.emit(
                EventType.EVIDENCE_ACTION_AUTHORIZED,
                f"Information action authorized under capability policy '{self.capability_policy.policy_id}'.",
                payload={"action_id": action.action_id, "action_type": action.action_type.value},
            )

        # Capture plant state before action to verify invariant: NO consequential mutation
        valves_before = dict(self.world.valves)
        cooling_before = self.world.cooling
        pumps_before = dict(self.world.pumps)

        new_evidence: List[Evidence] = []
        observed_gain = InformationGainLevel.MEDIUM.value

        try:
            # Dispatch to simulator observation model based on action type
            if action.action_type in (ActionType.INSPECT_TARGET, ActionType.INSPECT, ActionType.GATHER_EVIDENCE):
                viewpoint = action.parameters.get("viewpoint", "optimal")
                zoom = action.parameters.get("zoom", "4x")
                new_evidence = self.world.inspect_target(
                    target=action.target,
                    viewpoint=viewpoint,
                    zoom=zoom,
                )
                if viewpoint in ("suboptimal", "obstructed"):
                    observed_gain = InformationGainLevel.LOW.value
                elif any(e.confidence >= 0.95 for e in new_evidence):
                    observed_gain = InformationGainLevel.HIGH.value

            elif action.action_type == ActionType.RESAMPLE_SENSOR:
                sensor_id = action.parameters.get("sensor_id", "sensor_piezo_pressure_01")
                resolve = action.parameters.get("resolve_contradiction", False)
                increase = action.parameters.get("increase_contradiction", False)
                new_evidence = self.world.resample_sensor(
                    sensor_id=sensor_id,
                    target=action.target,
                    resolve_contradiction=resolve,
                    increase_contradiction=increase,
                )
                if increase:
                    observed_gain = InformationGainLevel.NEGATIVE.value
                elif resolve or any(e.confidence >= 0.94 for e in new_evidence):
                    observed_gain = InformationGainLevel.HIGH.value
                else:
                    observed_gain = InformationGainLevel.MEDIUM.value

            elif action.action_type == ActionType.CHANGE_VIEWPOINT:
                viewpoint = action.parameters.get("viewpoint", "viewpoint_2")
                new_evidence = self.world.change_viewpoint(
                    target=action.target,
                    viewpoint=viewpoint,
                )
                observed_gain = InformationGainLevel.MEDIUM.value

            elif action.action_type == ActionType.WAIT_FOR_STABLE_STATE:
                settling = action.parameters.get("settling_seconds", 1.0)
                new_evidence = self.world.wait_for_stable_state(
                    subsystem=action.target,
                    settling_seconds=settling,
                )
                observed_gain = InformationGainLevel.HIGH.value

            elif action.action_type == ActionType.READ_SENSOR:
                sensor_id = action.parameters.get("sensor_id", "press_sensor_01")
                new_evidence = self.world.read_sensor(
                    sensor_id=sensor_id,
                    target=action.target,
                )
                observed_gain = InformationGainLevel.MEDIUM.value

            elif action.action_type == ActionType.QUERY_KNOWLEDGE:
                # Query knowledge evidence
                new_evidence = [
                    Evidence(
                        source=EvidenceSource.SYSTEM_TELEMETRY,
                        target=action.target,
                        observation={"knowledge_query": action.parameters.get("query", ""), "result": "guidance_retrieved"},
                        confidence=0.90,
                        timestamp=time.time(),
                        provenance="manual:query_knowledge",
                    )
                ]
                observed_gain = InformationGainLevel.MEDIUM.value

            else:
                raise UnauthorizedActionError(f"Unsupported information action '{action.action_type.value}'.")

            # HARD SECURITY INVARIANT CHECK: Consequential state must remain 100% UNCHANGED
            assert dict(self.world.valves) == valves_before, "CRITICAL: Information action mutated valves!"
            assert self.world.cooling == cooling_before, "CRITICAL: Information action mutated cooling!"
            assert dict(self.world.pumps) == pumps_before, "CRITICAL: Information action mutated pumps!"

            res = InformationActionExecutionResult(
                success=True,
                action_id=action.action_id,
                action_type=action.action_type,
                target=action.target,
                new_evidence=new_evidence,
                predicted_gain=action.expected_gain,
                observed_gain=observed_gain,
                message=f"Successfully executed {action.action_type.value} on {action.target}; collected {len(new_evidence)} new observation(s).",
            )

            if self.event_bus:
                self.event_bus.emit(
                    EventType.EVIDENCE_ACTION_EXECUTED,
                    res.message,
                    payload={"action_id": action.action_id, "evidence_count": len(new_evidence), "observed_gain": observed_gain},
                )
                self.event_bus.emit(
                    EventType.INFORMATION_GAIN_MEASURED,
                    f"Information gain measured for {action.action_type.value}: predicted={action.expected_gain}, observed={observed_gain}.",
                    payload={"predicted_gain": action.expected_gain, "observed_gain": observed_gain, "action_id": action.action_id},
                )

            return res

        except Exception as e:
            if isinstance(e, CapabilityEscalationError):
                raise
            err_msg = f"Failed to execute information action {action.action_type.value}: {e}"
            if self.event_bus:
                self.event_bus.emit(
                    EventType.EVIDENCE_ACTION_FAILED,
                    err_msg,
                    payload={"action_id": action.action_id, "error": str(e)},
                )
            return InformationActionExecutionResult(
                success=False,
                action_id=action.action_id,
                action_type=action.action_type,
                target=action.target,
                new_evidence=[],
                predicted_gain=action.expected_gain,
                observed_gain=InformationGainLevel.ZERO.value,
                message=err_msg,
            )
