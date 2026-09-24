"""Containment, quarantine, and recovery budget policy definitions."""

from typing import Dict, List, Optional, Set
from pydantic import BaseModel, Field

from motionfence.models.actions import ActionType
from motionfence.recovery.models import FailureClass, QuarantineStatus, ComponentType


class QuarantinePolicy(BaseModel):
    """Deterministic escalation thresholds for component suspicion and quarantine."""
    policy_id: str = "default_quarantine_policy"
    suspect_threshold: int = Field(default=1, ge=1, description="Failures to mark SUSPECT.")
    recovery_required_threshold: int = Field(default=2, ge=1, description="Failures to require RECOVERY_REQUIRED.")
    quarantine_threshold: int = Field(default=3, ge=1, description="Consecutive failures to trigger QUARANTINED.")
    scoped_capability_isolation: bool = Field(default=True, description="Enforce scoped rather than global quarantine.")
    auto_recertification_allowed: bool = Field(default=False, description="Disallow silent unquarantine without evidence.")

    # Consequential actions automatically blocked on an actuator component when QUARANTINED
    consequential_actuator_actions: List[ActionType] = Field(
        default_factory=lambda: [
            ActionType.CLOSE_VALVE,
            ActionType.OPEN_VALVE,
            ActionType.START_PUMP,
            ActionType.STOP_PUMP,
            ActionType.ADJUST_COOLING,
        ]
    )

    # Informational actions that remain permitted on a quarantined component for diagnostics
    permitted_diagnostic_actions: List[ActionType] = Field(
        default_factory=lambda: [
            ActionType.INSPECT,
            ActionType.INSPECT_TARGET,
            ActionType.READ_SENSOR,
            ActionType.RESAMPLE_SENSOR,
            ActionType.WAIT_FOR_STABLE_STATE,
        ]
    )

    def determine_status(self, consecutive_failures: int) -> QuarantineStatus:
        """Determine QuarantineStatus from consecutive failure streak."""
        if consecutive_failures >= self.quarantine_threshold:
            return QuarantineStatus.QUARANTINED
        elif consecutive_failures >= self.recovery_required_threshold:
            return QuarantineStatus.RECOVERY_REQUIRED
        elif consecutive_failures >= self.suspect_threshold:
            return QuarantineStatus.SUSPECT
        return QuarantineStatus.HEALTHY


class ContainmentPolicy(BaseModel):
    """Declarative containment rules executed immediately upon failure detection."""
    policy_id: str = "default_containment_policy"
    invalidate_active_tickets: bool = Field(default=True, description="Strictly invalidate tickets on failure.")
    freeze_affected_target: bool = Field(default=True, description="Block immediate consequential repeat.")
    remove_failing_sensor_from_evidence: bool = Field(default=True, description="Exclude bad sensor from policy pool.")
    require_fresh_authorization_on_retry: bool = Field(default=True, description="Never reuse previous ticket.")

    def get_actions_to_freeze(self, failure_class: FailureClass, target: str) -> List[str]:
        """Determine action types that must be immediately frozen for this failure."""
        if failure_class in (
            FailureClass.ACTUATOR_NO_OP,
            FailureClass.ACTUATOR_PARTIAL,
            FailureClass.ACTUATOR_WRONG_STATE,
            FailureClass.ACTUATOR_DELAY,
            FailureClass.VERIFICATION_FAILURE,
        ):
            return [
                ActionType.CLOSE_VALVE.value,
                ActionType.OPEN_VALVE.value,
            ]
        elif failure_class in (FailureClass.SENSOR_FAILURE, FailureClass.SENSOR_STALE):
            return ["TRUST_SENSOR_READING"]
        return []

    def get_actions_to_permit(self, failure_class: FailureClass, target: str) -> List[str]:
        """Determine diagnostic informational actions that remain safe."""
        return [
            ActionType.INSPECT_TARGET.value,
            ActionType.RESAMPLE_SENSOR.value,
            ActionType.READ_SENSOR.value,
            ActionType.WAIT_FOR_STABLE_STATE.value,
        ]


class RecoveryBudget(BaseModel):
    """Finite operational limits preventing unbounded autonomous recovery loops."""
    max_recovery_attempts: int = Field(default=3, ge=1, description="Max recovery plan cycles per incident.")
    max_recovery_actions: int = Field(default=5, ge=1, description="Max informational actions per plan.")
    max_total_wait_seconds: float = Field(default=30.0, description="Max cumulative simulated wait latency.")
    timeout_seconds: float = Field(default=60.0, description="Hard wall-clock timeout for recovery execution.")

    def is_exhausted(self, current_attempt: int, actions_executed: int) -> bool:
        """Check whether recovery budget has been exhausted."""
        return (
            current_attempt >= self.max_recovery_attempts
            or actions_executed >= self.max_recovery_actions
        )
