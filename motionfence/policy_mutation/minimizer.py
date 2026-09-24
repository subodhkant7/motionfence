"""Counterexample minimization for policy mutation regressions (Phase 2J).

Extracts and minimizes the smallest concrete scenario attributes demonstrating
why a policy mutation caused a safety regression (e.g. false ALLOW or property violation).
"""

from typing import Any, Dict, List, Optional
from motionfence.policy_mutation.models import (
    MutationCounterexample,
    PolicyMutation,
    PolicyMutationType,
    PolicyRegressionType,
)


class MutationCounterexampleMinimizer:
    """Isolates the minimal sufficient scenario parameters triggering a policy regression."""

    @staticmethod
    def minimize(
        mutation: PolicyMutation,
        full_scenario: Dict[str, Any],
        baseline_decision: str,
        mutated_decision: str,
        regression_type: PolicyRegressionType,
        explanation: Optional[str] = None,
    ) -> MutationCounterexample:
        """Filter out non-causal scenario attributes to produce a minimal counterexample."""
        minimized: Dict[str, Any] = {}

        # Extract standard scenario parameters
        action_type = str(full_scenario.get("action_type", "CLOSE_VALVE"))
        target = str(full_scenario.get("target", "valve_b"))
        human_zone = str(full_scenario.get("human_zone", "CLEAR"))
        cooling = str(full_scenario.get("cooling", "ACTIVE"))
        contradiction_sev = str(full_scenario.get("contradiction_severity", "NONE"))
        confidence = float(full_scenario.get("confidence", 0.95))

        # Always include minimal action intent
        minimized["action"] = action_type
        minimized["target"] = target

        # Isolate cause based on mutation target and type
        target_name = mutation.mutation_target.lower()
        mut_type = mutation.mutation_type

        if "human_zone" in target_name or mut_type in (
            PolicyMutationType.CONDITION_REMOVAL,
            PolicyMutationType.CONDITION_INVERSION,
        ):
            minimized["human_zone"] = human_zone
            default_expl = (
                f"Policy mutation removed human safety zone guard; scenario with human_zone='{human_zone}' "
                f"transitioned from {baseline_decision} to {mutated_decision}."
            )

        elif "cooling" in target_name or "require_cooling_active" in target_name:
            minimized["cooling"] = cooling
            default_expl = (
                f"Policy mutation deleted cooling invariant; scenario with cooling='{cooling}' "
                f"transitioned from {baseline_decision} to {mutated_decision}."
            )

        elif "confidence" in target_name or mut_type == PolicyMutationType.THRESHOLD_WEAKENING:
            minimized["confidence"] = confidence
            default_expl = (
                f"Policy mutation weakened confidence threshold to {mutation.after_value}; "
                f"proposal with confidence={confidence:.2f} transitioned from {baseline_decision} to {mutated_decision}."
            )

        elif "contradiction" in target_name or mut_type == PolicyMutationType.CONTRADICTION_WEAKENING:
            minimized["contradiction_severity"] = contradiction_sev
            default_expl = (
                f"Policy mutation weakened contradiction blocking to {mutation.after_value}; "
                f"scenario with contradiction_severity='{contradiction_sev}' transitioned from {baseline_decision} to {mutated_decision}."
            )

        elif "prohibited_actions" in target_name:
            minimized["action"] = action_type
            default_expl = (
                f"Policy mutation cleared prohibited actions; prohibited action '{action_type}' "
                f"transitioned from {baseline_decision} to {mutated_decision}."
            )

        elif "toctou" in target_name or "revalidation" in target_name:
            minimized["toctou_violation"] = full_scenario.get("toctou_violation", True)
            default_expl = (
                f"Policy mutation weakened execution-time revalidation; post-authorization state drift "
                f"evaded TOCTOU defenses, transitioning from {baseline_decision} to {mutated_decision}."
            )

        elif "quarantine" in target_name:
            minimized["component_quarantined"] = full_scenario.get("quarantined", True)
            default_expl = (
                f"Policy mutation attempted quarantine bypass; quarantined component actuation "
                f"transitioned from {baseline_decision} to {mutated_decision}."
            )

        elif "freshness" in target_name or "age" in target_name:
            minimized["knowledge_age_seconds"] = full_scenario.get("knowledge_age_seconds", 3600.0)
            default_expl = (
                f"Policy mutation weakened freshness requirement; stale knowledge "
                f"transitioned from {baseline_decision} to {mutated_decision}."
            )

        else:
            # General fallback: include non-default parameters
            if human_zone != "CLEAR":
                minimized["human_zone"] = human_zone
            if cooling != "ACTIVE":
                minimized["cooling"] = cooling
            if contradiction_sev != "NONE":
                minimized["contradiction_severity"] = contradiction_sev
            if confidence < 0.90:
                minimized["confidence"] = confidence
            default_expl = (
                f"Policy mutation '{mutation.mutation_id}' resulted in regression {regression_type.value}: "
                f"{baseline_decision} -> {mutated_decision}."
            )

        return MutationCounterexample(
            mutation_id=mutation.mutation_id,
            action_type=action_type,
            target=target,
            human_zone=human_zone,
            cooling=cooling,
            contradiction_severity=contradiction_sev,
            confidence=confidence,
            baseline_decision=baseline_decision,
            mutated_decision=mutated_decision,
            regression=regression_type,
            explanation=explanation or default_expl,
            minimized_scenario=minimized,
        )

    @staticmethod
    def minimize_trajectory(
        trajectory_id: str,
        steps: List[Any],
        regression_type: PolicyRegressionType = PolicyRegressionType.NEW_UNSAFE_ALLOW,
        failing_step_index: Optional[int] = None,
        explanation: Optional[str] = None,
    ) -> Dict[str, Any]:
        """Produce the shortest causal trajectory reproducing a dynamic safety regression."""
        causal_events: List[str] = []
        causal_steps: List[Dict[str, Any]] = []

        # Filter out informational / passive telemetry steps, retaining causal state transitions
        for step in steps:
            if isinstance(step, dict):
                event_name = step.get("event_name", "")
                fault = step.get("fault", None)
                action = step.get("action", None)
            else:
                event_name = getattr(step, "event_name", "") or ""
                fault = getattr(step, "fault", None)
                action = getattr(step, "action", None)

            is_causal = (
                fault is not None
                or action is not None
                or "AUTHORIZATION" in event_name
                or "EXECUTION" in event_name
                or "HUMAN" in event_name
                or "COOLING" in event_name
                or "PUMP" in event_name
                or "CONTRADICTION" in event_name
                or "QUARANTINE" in event_name
            )

            if is_causal:
                causal_events.append(event_name)
                causal_steps.append({
                    "step_index": getattr(step, "step_index", len(causal_steps)),
                    "event_name": event_name,
                    "fault": fault,
                    "action": action,
                })

        formatted_report = (
            f"TRAJECTORY REGRESSION\n"
            f"Trajectory ID: {trajectory_id}\n"
            f"REGRESSION:    {regression_type.value}\n"
            f"MINIMIZED TRAJECTORY: {causal_events}\n"
            f"EXPLANATION:   {explanation or 'Dynamic physical trajectory regression minimized to shortest causal sequence.'}"
        )

        return {
            "trajectory_id": trajectory_id,
            "regression_type": regression_type.value,
            "minimized_events": causal_events,
            "minimized_steps": causal_steps,
            "formatted_report": formatted_report,
            "failing_step_index": failing_step_index,
        }

