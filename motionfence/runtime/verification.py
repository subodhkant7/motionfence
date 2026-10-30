"""Post-action verification gate for deterministic physical outcome confirmation."""

from enum import Enum
from typing import Any, Dict, List, Optional
import time
import math
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
            if pre_state.leak.target == proposal.target or post_state.leak.target == proposal.target:
                expected["leak.active"] = False
                observed["leak.active"] = post_state.leak.active

        elif proposal.action_type == ActionType.OPEN_VALVE:
            expected[f"valves.{proposal.target}"] = ValveState.OPEN.value
            observed[f"valves.{proposal.target}"] = post_state.valves.get(proposal.target, ValveState.CLOSED).value

        # Invariant check: cooling must remain active
        expected["cooling"] = CoolingState.ACTIVE.value
        observed["cooling"] = post_state.cooling.value

        # Custom conditions supplement required valve/cooling/leak invariants.
        if expected_postconditions:
            for key, value in expected_postconditions.items():
                if key in expected and not cls._values_equal(value, expected[key]):
                    discrepancies.append(f"Custom postcondition conflicts with required invariant: {key!r}")
                    continue
                expected[key] = value
                found, actual = cls._resolve_field(post_state, key)
                if not found:
                    discrepancies.append(f"Unresolvable postcondition path: {key!r}")
                observed[key] = actual

        # 3. Check for discrepancies between expected and observed state
        for key, exp_val in expected.items():
            obs_val = observed.get(key)
            if not cls._values_equal(obs_val, exp_val):
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

    @staticmethod
    def _resolve_field(world_state: WorldState, key: str) -> tuple[bool, Any]:
        """Resolve dotted serialized-world keys, distinguishing missing from recorded null.

        Mapping traversal only; no methods, inherited properties, array indices
        or implicit aliases. Structured JSON values are supported as leaves.
        """
        if not isinstance(key, str):
            return False, None
        parts = key.split(".")
        if any(not part for part in parts):
            return False, None
        value: Any = world_state.model_dump(mode="json")
        for part in parts:
            if not isinstance(value, dict) or part not in value:
                return False, None
            value = value[part]
        return True, value

    @staticmethod
    def _values_equal(left: Any, right: Any) -> bool:
        """JSON structural equality; booleans are distinct from numbers."""
        if left is None or right is None:
            return left is None and right is None
        if isinstance(left, bool) or isinstance(right, bool):
            return type(left) is bool and type(right) is bool and left == right
        if isinstance(left, (int, float)) and isinstance(right, (int, float)):
            return math.isfinite(left) and math.isfinite(right) and left == right
        if isinstance(left, str) and isinstance(right, str):
            return left == right
        if isinstance(left, list) and isinstance(right, list):
            return len(left) == len(right) and all(PostActionVerifier._values_equal(a, b) for a, b in zip(left, right))
        if isinstance(left, dict) and isinstance(right, dict):
            return left.keys() == right.keys() and all(PostActionVerifier._values_equal(value, right[key]) for key, value in left.items())
        return False

    @classmethod
    def _extract_field(cls, world_state: WorldState, key: str) -> Any:
        """Compatibility accessor; verification uses the resolver's presence flag."""
        return cls._resolve_field(world_state, key)[1]
