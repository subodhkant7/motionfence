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
                # Phase 2F: State-binding and TOCTOU
                "auth_world_version",
                "exec_world_version",
                "auth_policy_version",
                "exec_policy_version",
                "auth_constraint_hash",
                "exec_constraint_hash",
                "revalidation_passed",
                "execution_attempted",
                # Phase 2G: Active Evidence Acquisition & Capability Boundaries
                "action_class",
                "is_info_action",
                "is_consequential_action",
                "planner_can_actuate",
                "planner_can_mint_ticket",
                "evidence_iterations",
                "evidence_budget",
                "has_new_evidence",
                "is_planner_proposal",
                # Phase 2H: Adversarial Physical Environment & Robustness
                "human_transition_to_occupied",
                "has_admissible_new_evidence",
                "actuator_fault",
                "verification_status",
                "prev_decision",
                "safety_degraded",
                "adversary_can_mint_ticket",
                "adversary_can_bypass_enclave",
                "environmental_drift",
                # Phase 2I: Fault Containment, Quarantine & Recovery
                "action_failed",
                "ticket_invalidated",
                "component_quarantined",
                "blocked_capability_executed",
                "recovery_reuses_stale_ticket",
                "recovery_fresh_eval_done",
                "consequential_action_authorized",
                "sensor_quarantined",
                "quarantined_sensor_evidence_admitted",
                "recovery_attempts",
                "recovery_budget",
                "recovery_action_class",
                "recovery_planner_can_escalate",
                # Phase 2J: Policy Mutation Firewall & Safety Regression Detection
                "human_guard_removed",
                "regression_detected_human_zone",
                "confidence_weakened",
                "evades_assurance",
                "regression_detected_confidence",
                "contradiction_guard_removed",
                "regression_detected_contradiction",
                "state_binding_disabled",
                "regression_detected_state_bound",
                "revalidation_disabled",
                "regression_detected_revalidation",
                "recovery_containment_disabled",
                "regression_detected_recovery",
                # Phase 2K: Combinatorial Attacks, Dynamic Trajectories & Safe Repairs
                "is_compound_mutation",
                "compound_regression_detected",
                "is_amplifying_interaction",
                "amplifying_detected",
                "trajectory_regression_present",
                "trajectory_blockable_by_reval",
                "repair_modifies_production_policy",
                "repair_proposal_applied_without_validation",
                "repair_weakens_auth_boundary",
                "repair_accepted_with_weakened_boundary",
                "trajectory_counterexample_deterministic",
                "repair_is_inconclusive",
                "inconclusive_repair_auto_applied",
            ]


        minimized: Dict[str, Any] = {}
        for key in essential_keys:
            if key in counterexample:
                minimized[key] = counterexample[key]

        # If none of the essential keys matched, preserve original to avoid losing data
        return minimized if minimized else dict(counterexample)
