"""Counterexample representation, minimization, and human-readable formatting."""

from typing import Any, Dict, List, Optional
from motionfence.assurance.models import FindingStatus


class CounterexampleFormatter:
    """Deterministic, human-readable counterexample formatter avoiding raw SMT internals."""

    @staticmethod
    def format_counterexample(
        property_name: str,
        counterexample: Dict[str, Any],
        status: FindingStatus = FindingStatus.VIOLATED,
        explanation: Optional[str] = None,
    ) -> str:
        """Format a counterexample into a clean, human-readable diagnostic report."""
        lines = [
            "--------------------------------------------------",
            f"PROPERTY: {property_name}",
            f"STATUS:   {status.value}",
            "COUNTEREXAMPLE:",
        ]
        for key, val in counterexample.items():
            lines.append(f"  {key} = {val}")

        if explanation:
            lines.append(f"EXPLANATION: {explanation}")
        lines.append("--------------------------------------------------")
        return "\n".join(lines)

    @staticmethod
    def minimize(counterexample: Dict[str, Any], essential_keys: Optional[List[str]] = None) -> Dict[str, Any]:
        """Shrink a counterexample dictionary to only its most essential variables.

        Removes redundant diagnostic noise to highlight the root cause of the violation.
        """
        if essential_keys is None:
            # Default priority keys across MotionFence physical policy rules
            essential_keys = [
                "human_zone",
                "action",
                "target",
                "cooling",
                "pump_p1",
                "policy_decision",
                "contradiction_severity",
                "confidence",
                "has_ticket",
                "world_mutated",
                "has_conflicted_constraint",
                "has_stale_constraint",
            ]

        minimized: Dict[str, Any] = {}
        for key in essential_keys:
            if key in counterexample:
                minimized[key] = counterexample[key]

        # If none of the essential keys matched, preserve original to avoid losing data
        return minimized if minimized else dict(counterexample)
