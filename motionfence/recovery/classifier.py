"""Deterministic failure classifier identifying physical, perceptual, and temporal failure signatures."""

from typing import Any, Dict, List, Optional
import time

from motionfence.models.actions import ActionProposal, ActionType, ExecutionResult
from motionfence.models.world import ValveState, WorldState
from motionfence.evidence.models import Evidence
from motionfence.runtime.verification import VerificationResult, VerificationStatus
from motionfence.runtime.revalidation import AuthorizationRevalidationResult, RevalidationStatus
from motionfence.recovery.models import ComponentType, FailureClass, FailureRecord


class FailureClassifier:
    """Classifies runtime faults into deterministic taxonomic failure classes without LLMs."""

    @classmethod
    def classify(
        cls,
        proposal: Optional[ActionProposal] = None,
        execution: Optional[ExecutionResult] = None,
        verification: Optional[VerificationResult] = None,
        revalidation: Optional[AuthorizationRevalidationResult] = None,
        world_state: Optional[WorldState] = None,
        evidence: Optional[List[Evidence]] = None,
        sensor_id: Optional[str] = None,
        additional_context: Optional[Dict[str, Any]] = None,
    ) -> FailureRecord:
        """Deterministically determine the FailureClass from concrete execution artifacts."""
        context = additional_context or {}
        target = proposal.target if proposal else (execution.target if execution else (sensor_id or "system"))
        comp_type = ComponentType.SENSOR if sensor_id else ComponentType.ACTUATOR

        # --- Rule 1: TOCTOU Revalidation Gate Failures (Pre-Execution Drift) ---
        if revalidation is not None and revalidation.status != RevalidationStatus.VALID:
            if revalidation.status in (RevalidationStatus.WORLD_STATE_CHANGED, RevalidationStatus.TICKET_EXPIRED):
                return FailureRecord(
                    failure_class=FailureClass.ENVIRONMENT_DRIFT,
                    target_component=target,
                    component_type=ComponentType.ZONE if "human" in str(revalidation.reasons) else comp_type,
                    details=f"Environmental drift detected before execution: {revalidation.reasons}",
                    revalidation_status=revalidation.status.value,
                    proposal_id=proposal.id if proposal else None,
                )
            elif revalidation.status == RevalidationStatus.EVIDENCE_CHANGED:
                return FailureRecord(
                    failure_class=FailureClass.SENSOR_CONTRADICTION,
                    target_component=target,
                    component_type=ComponentType.SENSOR,
                    details=f"Evidence context shifted during authorization latency: {revalidation.reasons}",
                    revalidation_status=revalidation.status.value,
                    proposal_id=proposal.id if proposal else None,
                )
            elif revalidation.status == RevalidationStatus.POLICY_CHANGED:
                return FailureRecord(
                    failure_class=FailureClass.POLICY_FAILURE,
                    target_component=target,
                    component_type=ComponentType.CONTROLLER,
                    details=f"Policy version drifted after ticket issuance: {revalidation.reasons}",
                    revalidation_status=revalidation.status.value,
                    proposal_id=proposal.id if proposal else None,
                )
            elif revalidation.status == RevalidationStatus.CONSTRAINT_CHANGED:
                return FailureRecord(
                    failure_class=FailureClass.KNOWLEDGE_FAILURE,
                    target_component=target,
                    component_type=ComponentType.KNOWLEDGE_SOURCE,
                    details=f"Active constraint set modified or invalidated: {revalidation.reasons}",
                    revalidation_status=revalidation.status.value,
                    proposal_id=proposal.id if proposal else None,
                )

        # --- Rule 2: Actuator Execution Layer Rejections & Faults ---
        if execution is not None and not execution.success:
            msg = (execution.message or "").lower()
            if "jam" in msg or "stuck" in msg or "mechanical failure" in msg:
                return FailureRecord(
                    failure_class=FailureClass.ACTUATOR_NO_OP,
                    target_component=execution.target,
                    component_type=ComponentType.ACTUATOR,
                    details=f"Actuator mechanical jam encountered during stroke: {execution.message}",
                    execution_result=execution,
                    proposal_id=proposal.id if proposal else None,
                    ticket_id=execution.ticket_id,
                )
            elif "delay" in msg or "timeout" in msg:
                return FailureRecord(
                    failure_class=FailureClass.ACTUATOR_DELAY,
                    target_component=execution.target,
                    component_type=ComponentType.ACTUATOR,
                    details=f"Actuator stroke exceeded latency threshold: {execution.message}",
                    execution_result=execution,
                    proposal_id=proposal.id if proposal else None,
                    ticket_id=execution.ticket_id,
                )

        # --- Rule 3: Post-Action Verification Gate Invariant Mismatches ---
        if verification is not None and verification.status == VerificationStatus.VERIFICATION_FAILED:
            discrepancies = verification.discrepancies
            exp = verification.expected_postconditions
            obs = verification.observed_postconditions

            target_valve_key = f"valves.{verification.target}"
            obs_valve = obs.get(target_valve_key)
            exp_valve = exp.get(target_valve_key)

            # 3a. Valve stopped in TRANSITIONING state
            if obs_valve == ValveState.TRANSITIONING.value or any("transitioning" in d.lower() for d in discrepancies):
                return FailureRecord(
                    failure_class=FailureClass.ACTUATOR_PARTIAL,
                    target_component=verification.target,
                    component_type=ComponentType.ACTUATOR,
                    details=f"Actuator halted mid-stroke in TRANSITIONING state: {discrepancies}",
                    verification_result=verification,
                    execution_result=execution,
                    proposal_id=proposal.id if proposal else None,
                )

            # 3b. Valve state completely unchanged (e.g. expected CLOSED, observed OPEN)
            if exp_valve == ValveState.CLOSED.value and obs_valve == ValveState.OPEN.value:
                return FailureRecord(
                    failure_class=FailureClass.ACTUATOR_NO_OP,
                    target_component=verification.target,
                    component_type=ComponentType.ACTUATOR,
                    details=f"Actuator NO-OP: commanded CLOSE_VALVE but valve remained fully OPEN: {discrepancies}",
                    verification_result=verification,
                    execution_result=execution,
                    proposal_id=proposal.id if proposal else None,
                )

            # 3c. Valve seated into wrong/opposite state
            if obs_valve is not None and exp_valve is not None and obs_valve != exp_valve:
                return FailureRecord(
                    failure_class=FailureClass.ACTUATOR_WRONG_STATE,
                    target_component=verification.target,
                    component_type=ComponentType.ACTUATOR,
                    details=f"Actuator seated into incorrect state (expected {exp_valve}, observed {obs_valve}): {discrepancies}",
                    verification_result=verification,
                    execution_result=execution,
                    proposal_id=proposal.id if proposal else None,
                )

            # 3d. Generic verification failure
            return FailureRecord(
                failure_class=FailureClass.VERIFICATION_FAILURE,
                target_component=verification.target,
                component_type=ComponentType.ACTUATOR,
                details=f"Postcondition verification failed: {discrepancies}",
                verification_result=verification,
                execution_result=execution,
                proposal_id=proposal.id if proposal else None,
            )

        # --- Rule 4: Sensor-Specific Failure Signatures ---
        if sensor_id or context.get("sensor_failure_type") or evidence:
            now = time.time()
            if evidence:
                for ev in evidence:
                    if (now - ev.timestamp) > 10.0:
                        return FailureRecord(
                            failure_class=FailureClass.SENSOR_STALE,
                            target_component=sensor_id or ev.provenance or "sensor",
                            component_type=ComponentType.SENSOR,
                            details=f"Sensor telemetry is stale (age={now - ev.timestamp:.1f}s): {ev.id}",
                        )
                    if ev.confidence == 0.0:
                        return FailureRecord(
                            failure_class=FailureClass.SENSOR_FAILURE,
                            target_component=sensor_id or ev.provenance or "sensor",
                            component_type=ComponentType.SENSOR,
                            details=f"Sensor signal dropped out / zero confidence: {ev.id}",
                        )

            s_type = context.get("sensor_failure_type", "")
            if s_type == "SENSOR_STALE" or context.get("stale_seconds", 0) > 30.0:
                return FailureRecord(
                    failure_class=FailureClass.SENSOR_STALE,
                    target_component=sensor_id or "sensor",
                    component_type=ComponentType.SENSOR,
                    details=f"Sensor telemetry is stale (age > threshold): {context}",
                )
            elif s_type == "SENSOR_CONTRADICTION" or context.get("contradiction_detected"):
                return FailureRecord(
                    failure_class=FailureClass.SENSOR_CONTRADICTION,
                    target_component=sensor_id or "sensor",
                    component_type=ComponentType.SENSOR,
                    details=f"Sensor contradicts independent reference instrumentation: {context}",
                )
            elif s_type in ("SENSOR_FAILURE", "SENSOR_STUCK", "SENSOR_DROPOUT"):
                return FailureRecord(
                    failure_class=FailureClass.SENSOR_FAILURE,
                    target_component=sensor_id or "sensor",
                    component_type=ComponentType.SENSOR,
                    details=f"Sensor transducer failed, stuck, or dropped out: {context}",
                )

        # --- Rule 5: Fallback Unknown ---
        return FailureRecord(
            failure_class=FailureClass.UNKNOWN_FAILURE,
            target_component=target,
            component_type=comp_type,
            details=f"Unclassified failure event in component '{target}'.",
            execution_result=execution,
            verification_result=verification,
            proposal_id=proposal.id if proposal else None,
        )
