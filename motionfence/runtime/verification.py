"""Post-action verification gate for deterministic physical outcome confirmation."""

from enum import Enum
from typing import Any, Dict, List, Optional
import time
from pydantic import BaseModel, Field

from motionfence.models.actions import ActionProposal, ActionType, ExecutionResult
from motionfence.models.world import WorldState, ValveState, CoolingState


class VerificationStatus(str, Enum):
    """Evaluation status of post-action physical verification."""
    VERIFIED = "VERIFIED"
    VERIFICATION_FAILED = "VERIFICATION_FAILED"


class VerificationResult(BaseModel):
    """Machine-readable audit record distinguishing execution from verified physical outcome."""
    action_id: str = Field(..., description="ID of the executed proposal.")
    target: str = Field(..., description="Physical entity targeted.")
    action_occurred: bool = Field(..., description="Whether the actuator command was executed.")
    expected_postconditions: Dict[str, Any] = Field(
        default_factory=dict,
        description="Declared physical postconditions expected by policy."
    )
    observed_postconditions: Dict[str, Any] = Field(
        default_factory=dict,
        description="Actual sensor/physical states observed after actuation."
    )
    status: VerificationStatus = Field(..., description="VERIFIED or VERIFICATION_FAILED.")
    discrepancies: List[str] = Field(
        default_factory=list,
        description="List of mismatched states between expected and observed reality."
    )
    timestamp: float = Field(default_factory=time.time)

    @property
    def is_verified(self) -> bool:
        return self.status == VerificationStatus.VERIFIED


class PostActionVerifier:
    """Deterministic verifier comparing commanded action against ground-truth physical state."""

    @classmethod
    def verify(
        cls,
        proposal: ActionProposal,
        execution: ExecutionResult,
        pre_state: WorldState,
        post_state: WorldState,
        expected_postconditions: Optional[Dict[str, Any]] = None,
    ) -> VerificationResult:
        """Verify that physical state transitions match expected postconditions."""
        discrepancies: List[str] = []
        expected: Dict[str, Any] = {}
        observed: Dict[str, Any] = {}

        # 1. Check if execution succeeded at the actuator layer
        if not execution.success:
            discrepancies.append(f"Actuator execution failed: {execution.message}")

        # 2. Derive standard physical postconditions for the action
        if proposal.action_type == ActionType.CLOSE_VALVE:
            expected[f"valves.{proposal.target}"] = ValveState.CLOSED.value
            observed[f"valves.{proposal.target}"] = post_state.valves.get(proposal.target, ValveState.OPEN).value

            # If target was leak source, leak must be stopped
            if post_state.leak.target == proposal.target:
                expected["leak.active"] = False
                observed["leak.active"] = post_state.leak.active

        elif proposal.action_type == ActionType.OPEN_VALVE:
            expected[f"valves.{proposal.target}"] = ValveState.OPEN.value
            observed[f"valves.{proposal.target}"] = post_state.valves.get(proposal.target, ValveState.CLOSED).value

        # Invariant check: cooling must remain active
        expected["cooling"] = CoolingState.ACTIVE.value
        observed["cooling"] = post_state.cooling.value

        # Integrate custom expected postconditions if supplied
        if expected_postconditions:
            expected.update(expected_postconditions)
            for key in expected_postconditions:
                if key not in observed:
                    observed[key] = cls._extract_field(post_state, key)

        # 3. Check for discrepancies between expected and observed state
        for key, exp_val in expected.items():
            obs_val = observed.get(key)
            if obs_val != exp_val:
                discrepancies.append(
                    f"Postcondition mismatch for '{key}': expected {exp_val!r}, observed {obs_val!r}"
                )

        status = VerificationStatus.VERIFIED if (len(discrepancies) == 0 and execution.success) else VerificationStatus.VERIFICATION_FAILED

        return VerificationResult(
            action_id=proposal.id,
            target=proposal.target,
            action_occurred=execution.success,
            expected_postconditions=expected,
            observed_postconditions=observed,
            status=status,
            discrepancies=discrepancies,
            timestamp=time.time(),
        )

    @classmethod
    def _extract_field(cls, world_state: WorldState, key: str) -> Any:
        """Helper to extract dot-path attributes from WorldState."""
        parts = key.split(".")
        val: Any = world_state
        for p in parts:
            if isinstance(val, dict):
                val = val.get(p)
            elif hasattr(val, p):
                val = getattr(val, p)
            else:
                return None
            if hasattr(val, "value"):  # Handle Enums
                val = val.value
        return val
