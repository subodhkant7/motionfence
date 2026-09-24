"""Autonomous recovery planner proposing bounded, non-consequential diagnostic procedures."""

from typing import List, Optional
import time

from motionfence.models.actions import ActionProposal, ActionType
from motionfence.models.world import WorldState
from motionfence.evidence.models import Evidence
from motionfence.recovery.models import (
    FailureClass,
    FailureRecord,
    QuarantineStatus,
    RecoveryPlan,
    RecoveryStep,
    RecoveryStrategy,
    RiskLevel,
)
from motionfence.recovery.policies import RecoveryBudget
from motionfence.recovery.quarantine import QuarantineManager


class RecoveryPlanner:
    """Proposes diagnostic and alternate-path recovery procedures without consequential actuation authority.
    
    SECURITY INVARIANTS:
    1. The planner CANNOT directly execute consequential actions (PROP_030).
    2. Proposing an alternate action path requires a completely fresh authorization cycle (PROP_026, PROP_027).
    3. If recovery budget is exhausted or component is quarantined, recovery must abort safely (PROP_029).
    """

    def __init__(self, budget: Optional[RecoveryBudget] = None) -> None:
        self.budget = budget or RecoveryBudget()

    def plan_recovery(
        self,
        failure: FailureRecord,
        world_state: WorldState,
        evidence_pool: List[Evidence],
        quarantine_manager: Optional[QuarantineManager] = None,
        attempt_number: int = 1,
        available_alternate_targets: Optional[List[str]] = None,
    ) -> RecoveryPlan:
        """Formulate a deterministic RecoveryPlan matching the observed failure signature."""
        qm = quarantine_manager or QuarantineManager()
        target = failure.target_component
        comp_status = qm.get_record(target).status if qm.get_record(target) else QuarantineStatus.HEALTHY

        # 1. Budget or Quarantine Exhaustion -> Abort and Quarantine (unless alternate targets provided)
        if attempt_number > self.budget.max_recovery_attempts or (comp_status == QuarantineStatus.QUARANTINED and not available_alternate_targets):
            return RecoveryPlan(
                failure_id=failure.failure_id,
                strategy=RecoveryStrategy.ABORT_AND_QUARANTINE,
                steps=[],
                required_evidence=[],
                expected_information_gain=0.0,
                risk_level=RiskLevel.LOW,
                rationale=(
                    f"Component '{target}' is QUARANTINED or recovery attempts ({attempt_number}) "
                    f"exceeded budget limit ({self.budget.max_recovery_attempts}). Safe abort enforced."
                ),
            )

        # 2. Actuator Mechanical Failure (NO_OP or PARTIAL)
        if failure.failure_class in (FailureClass.ACTUATOR_NO_OP, FailureClass.ACTUATOR_PARTIAL, FailureClass.ACTUATOR_WRONG_STATE):
            steps = [
                RecoveryStep(
                    action_type=ActionType.INSPECT_TARGET,
                    target=target,
                    parameters={"camera": "closeup_ptz_01", "lighting": "high"},
                    description=f"Perform optical closeup inspection of {target} mechanical stem and solenoid.",
                    expected_gain="HIGH",
                    is_consequential=False,
                ),
                RecoveryStep(
                    action_type=ActionType.WAIT_FOR_STABLE_STATE,
                    target=target,
                    parameters={"duration_seconds": 1.0},
                    description="Allow manifold line pressure and solenoid coil to thermally equilibrate.",
                    expected_gain="LOW",
                    is_consequential=False,
                ),
            ]

            # If an alternate isolation path is requested or component is quarantined/faulted
            suggested_alternate = None
            if available_alternate_targets or comp_status in (QuarantineStatus.QUARANTINED, QuarantineStatus.RECOVERY_REQUIRED):
                candidates = available_alternate_targets or (["valve_a"] if target == "valve_b" and "valve_a" in world_state.valves else [])
                for alt_target in candidates:
                    rec_alt = qm.get_record(alt_target)
                    if rec_alt is None or rec_alt.status == QuarantineStatus.HEALTHY:
                        suggested_alternate = ActionProposal(
                            action_type=ActionType.CLOSE_VALVE,
                            target=alt_target,
                            rationale=f"Autonomous diversion: {target} failed; isolating branch via {alt_target}",
                            parameters={"reason": f"Autonomous diversion: {target} failed; isolating branch via {alt_target}"},
                            model_confidence=0.95,
                            supporting_evidence_ids=[e.id for e in evidence_pool if e.target in (alt_target, target)],
                        )
                        break

            strategy = RecoveryStrategy.TRY_ALTERNATE_ALLOWED_PATH if suggested_alternate else RecoveryStrategy.INSPECT_TARGET

            return RecoveryPlan(
                failure_id=failure.failure_id,
                strategy=strategy,
                steps=steps,
                required_evidence=["vision_closeup", "acoustic_spectral"],
                expected_information_gain=0.85,
                risk_level=RiskLevel.MEDIUM,
                rationale=f"Diagnose mechanical jam on {target} via optical inspection; propose alternate isolation path if admissible.",
                suggested_alternate_proposal=suggested_alternate,
            )

        # 3. Sensor Failure / Stale / Contradiction
        if failure.failure_class in (FailureClass.SENSOR_FAILURE, FailureClass.SENSOR_STALE, FailureClass.SENSOR_CONTRADICTION):
            steps = [
                RecoveryStep(
                    action_type=ActionType.RESAMPLE_SENSOR,
                    target=target,
                    parameters={"resample_window_ms": 250},
                    description=f"Resample telemetry from secondary redundant instrumentation for {target}.",
                    expected_gain="HIGH",
                    is_consequential=False,
                ),
                RecoveryStep(
                    action_type=ActionType.INSPECT_TARGET,
                    target="manifold_line" if "pressure" in target else target,
                    parameters={"camera": "wide_angle_camera"},
                    description="Corroborate pipe physical integrity via independent optical feed.",
                    expected_gain="HIGH",
                    is_consequential=False,
                ),
            ]
            return RecoveryPlan(
                failure_id=failure.failure_id,
                strategy=RecoveryStrategy.GATHER_ALTERNATE_EVIDENCE,
                steps=steps,
                required_evidence=["secondary_sensor_sample", "independent_optical"],
                expected_information_gain=0.90,
                risk_level=RiskLevel.LOW,
                rationale="Exclude unreliable sensor channel and acquire independent corroborating evidence.",
            )

        # 4. Environmental Drift (TOCTOU)
        if failure.failure_class == FailureClass.ENVIRONMENT_DRIFT:
            steps = [
                RecoveryStep(
                    action_type=ActionType.READ_SENSOR,
                    target="human_zone" if "human" in failure.details else "plant_state",
                    description="Resample safety zone boundary to confirm whether human has cleared.",
                    expected_gain="HIGH",
                    is_consequential=False,
                ),
                RecoveryStep(
                    action_type=ActionType.WAIT_FOR_STABLE_STATE,
                    target="plant_state",
                    parameters={"duration_seconds": 0.5},
                    description="Wait for transient physical state mutation to settle.",
                    expected_gain="MEDIUM",
                    is_consequential=False,
                ),
            ]
            return RecoveryPlan(
                failure_id=failure.failure_id,
                strategy=RecoveryStrategy.WAIT_FOR_STABILITY,
                steps=steps,
                required_evidence=["human_zone_telemetry"],
                expected_information_gain=0.95,
                risk_level=RiskLevel.LOW,
                rationale="Wait for environmental disturbance to clear, followed by a completely fresh authorization cycle.",
            )

        # 5. Default Fallback Diagnostic
        return RecoveryPlan(
            failure_id=failure.failure_id,
            strategy=RecoveryStrategy.INSPECT_TARGET,
            steps=[
                RecoveryStep(
                    action_type=ActionType.INSPECT_TARGET,
                    target=target,
                    description=f"Diagnostic inspection for unclassified failure on {target}.",
                    is_consequential=False,
                )
            ],
            required_evidence=[],
            expected_information_gain=0.5,
            risk_level=RiskLevel.LOW,
            rationale="Perform baseline inspection for unknown failure signature.",
        )
