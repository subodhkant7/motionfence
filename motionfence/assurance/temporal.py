"""Bounded temporal property checking over short discrete execution horizons."""

from dataclasses import dataclass
from typing import Any, Dict, List, Optional
import time

from motionfence.assurance.models import (
    AssuranceFinding,
    FindingStatus,
    FindingSeverity,
    AssuranceScope,
    FormalState,
)
from motionfence.policy.engine import PolicyEngine
from motionfence.models.actions import ActionProposal, ActionType
from motionfence.policy.models import DecisionType
from motionfence.evidence.models import Evidence, EvidenceSource


@dataclass
class TransitionStep:
    """Discrete step in a bounded transition sequence."""
    step_index: int
    state: FormalState
    action: Optional[ActionType]
    target: str
    confidence: float = 0.95
    environment_perturbation: Optional[str] = None


class BoundedTemporalChecker:
    """Evaluates safety invariants across bounded multi-step action sequences (Horizon H = 1..5)."""

    def __init__(self) -> None:
        pass

    def check_cooling_preservation_sequence(
        self,
        initial_state: FormalState,
        action_sequence: List[ActionType],
        horizon: int = 3,
    ) -> AssuranceFinding:
        """Verify: G_bounded(authorized_action -> cooling == ACTIVE) over horizon H."""
        current_state = FormalState.model_validate(initial_state.model_dump())
        trace: List[Dict[str, Any]] = []

        effective_horizon = min(len(action_sequence), horizon)
        for i in range(effective_horizon):
            action = action_sequence[i]
            target = "valve_b"

            ev = Evidence(
                source=EvidenceSource.PRESSURE_SENSOR,
                target=target,
                observation={"status": "normal"},
                confidence=0.96,
                provenance="sensor_probe_temporal",
            )

            # Create proposal
            proposal = ActionProposal(
                action_type=action,
                target=target,
                parameters={},
                model_confidence=0.95,
                rationale=f"Sequential transition step {i}",
                supporting_evidence_ids=[ev.id],
            )

            # Evaluate policy against current state
            world_snapshot = current_state.to_world_state()
            decision = PolicyEngine.evaluate(proposal, world_snapshot, [ev])

            step_record = {
                "step": i,
                "action": action.value,
                "cooling": current_state.cooling,
                "human_zone": current_state.human_zone,
                "pump_p1": current_state.pumps.get("pump_p1", "INACTIVE"),
                "decision": decision.decision.value,
            }
            trace.append(step_record)

            # Invariant check: An action cannot be authorized if cooling is not ACTIVE
            if decision.decision == DecisionType.ALLOW and current_state.cooling != "ACTIVE":
                return AssuranceFinding(
                    property_id="PROP_007_TEMPORAL_COOLING_PRESERVATION",
                    property_name="Temporal Cooling Preservation Across Horizon",
                    status=FindingStatus.VIOLATED,
                    severity=FindingSeverity.CRITICAL,
                    scope=AssuranceScope.TEMPORAL_SAFETY.value,
                    counterexample={"failing_step": i, "trace": trace},
                    explanation=f"Cooling degraded at step {i} but action {action.value} was granted ALLOW.",
                )

            # Simulate state transition if action was allowed
            if decision.decision == DecisionType.ALLOW:
                if action == ActionType.CLOSE_VALVE:
                    current_state.valves[target] = "CLOSED"
                elif action == ActionType.OPEN_VALVE:
                    current_state.valves[target] = "OPEN"

        return AssuranceFinding(
            property_id="PROP_007_TEMPORAL_COOLING_PRESERVATION",
            property_name="Temporal Cooling Preservation Across Horizon",
            status=FindingStatus.SATISFIED,
            severity=FindingSeverity.CRITICAL,
            scope=AssuranceScope.TEMPORAL_SAFETY.value,
            explanation=f"BOUNDED PROPERTY SATISFIED: Cooling invariant held across all {effective_horizon} transition steps.",
        )

    def check_dynamic_human_incursion(
        self,
        horizon: int = 3,
        incursion_step: int = 1,
    ) -> AssuranceFinding:
        """Verify that dynamic environmental human entry during a sequence blocks subsequent action."""
        state = FormalState(
            valves={"valve_a": "OPEN", "valve_b": "OPEN"},
            cooling="ACTIVE",
            human_zone="CLEAR",
            pumps={"pump_p1": "INACTIVE"},
        )

        trace: List[Dict[str, Any]] = []
        for step in range(horizon):
            # Dynamic incursion event at specified step
            if step >= incursion_step:
                state.human_zone = "OCCUPIED"

            ev = Evidence(
                source=EvidenceSource.PRESSURE_SENSOR,
                target="valve_b",
                observation={"status": "normal"},
                confidence=0.96,
                provenance="sensor_probe_incursion",
            )

            proposal = ActionProposal(
                action_type=ActionType.CLOSE_VALVE,
                target="valve_b",
                parameters={},
                model_confidence=0.96,
                rationale=f"Step {step} attempt",
                supporting_evidence_ids=[ev.id],
            )

            world_snapshot = state.to_world_state()
            decision = PolicyEngine.evaluate(proposal, world_snapshot, [ev])

            trace.append({
                "step": step,
                "human_zone": state.human_zone,
                "decision": decision.decision.value,
            })

            # If human is in zone, decision MUST be DENY
            if state.human_zone == "OCCUPIED" and decision.decision == DecisionType.ALLOW:
                return AssuranceFinding(
                    property_id="PROP_001_HUMAN_ZONE_PROHIBITION",
                    property_name="Human-Zone Actuation Prohibition (Dynamic)",
                    status=FindingStatus.VIOLATED,
                    severity=FindingSeverity.CRITICAL,
                    scope=AssuranceScope.TEMPORAL_SAFETY.value,
                    counterexample={"step": step, "trace": trace},
                    explanation=f"Human incursion occurred at step {step} but action was ALLOWed.",
                )

        return AssuranceFinding(
            property_id="PROP_001_HUMAN_ZONE_PROHIBITION",
            property_name="Human-Zone Actuation Prohibition (Dynamic)",
            status=FindingStatus.SATISFIED,
            severity=FindingSeverity.CRITICAL,
            scope=AssuranceScope.TEMPORAL_SAFETY.value,
            explanation=f"BOUNDED PROPERTY SATISFIED: Dynamic incursion safely blocked actuation across horizon {horizon}.",
        )
