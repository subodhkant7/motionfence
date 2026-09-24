"""Deterministic Policy Engine for physical AI action authorization.

CRITICAL INVARIANT: This engine contains ZERO LLM calls.
All evaluations are deterministic, reproducible, and rule-based.
"""

from typing import List, Optional
import time

from motionfence.models.actions import ActionProposal, ActionType
from motionfence.models.world import WorldState, HumanZoneState, CoolingState
from motionfence.evidence.models import Evidence, ContradictionSeverity
from motionfence.evidence.contradiction import ContradictionDetector
from motionfence.policy.models import (
    Policy,
    PolicyDecision,
    PolicyReason,
    DecisionType,
)


class PolicyEngine:
    """Evaluates proposed physical actions against declarative safety policies and evidence."""

    @classmethod
    def evaluate(
        cls,
        proposal: ActionProposal,
        world_state: WorldState,
        evidence: List[Evidence],
        policy: Optional[Policy] = None,
    ) -> PolicyDecision:
        """Deterministically evaluate an ActionProposal against WorldState, Evidence, and Policy."""
        if policy is None:
            policy = Policy()

        reasons: List[PolicyReason] = []
        is_denied = False
        needs_evidence = False

        # --- 1. Prohibited Action Evaluation ---
        if proposal.action_type in policy.prohibited_actions:
            reasons.append(
                PolicyReason(
                    constraint="prohibited_action",
                    observed=proposal.action_type.value,
                    required=f"Not in {[a.value for a in policy.prohibited_actions]}",
                    status="failed",
                    details=f"Action '{proposal.action_type.value}' is strictly prohibited by policy.",
                )
            )
            is_denied = True
        else:
            reasons.append(
                PolicyReason(
                    constraint="prohibited_action",
                    observed=proposal.action_type.value,
                    required="Permitted action category",
                    status="passed",
                    details="Action category is allowed.",
                )
            )

        # --- 2. Allowed Target Evaluation ---
        if proposal.target not in policy.allowed_actuator_targets:
            reasons.append(
                PolicyReason(
                    constraint="allowed_actuator_target",
                    observed=proposal.target,
                    required=f"One of {policy.allowed_actuator_targets}",
                    status="failed",
                    details=f"Target '{proposal.target}' is outside permitted actuator boundaries.",
                )
            )
            is_denied = True
        else:
            reasons.append(
                PolicyReason(
                    constraint="allowed_actuator_target",
                    observed=proposal.target,
                    required=f"One of {policy.allowed_actuator_targets}",
                    status="passed",
                    details="Target actuator is within authorized scope.",
                )
            )

        # --- 3. Human Safety Zone Hard Invariant ---
        if policy.require_human_zone_clear:
            if world_state.human_zone != HumanZoneState.CLEAR:
                reasons.append(
                    PolicyReason(
                        constraint="human_safety_zone",
                        observed=world_state.human_zone.value,
                        required=HumanZoneState.CLEAR.value,
                        status="failed",
                        details="Human detected in safety zone! Physical actuation strictly forbidden.",
                    )
                )
                is_denied = True
            else:
                reasons.append(
                    PolicyReason(
                        constraint="human_safety_zone",
                        observed=world_state.human_zone.value,
                        required=HumanZoneState.CLEAR.value,
                        status="passed",
                        details="Human safety zone is verified CLEAR.",
                    )
                )

        # --- 4. Cooling System Hard Invariant ---
        if policy.require_cooling_active:
            if world_state.cooling != CoolingState.ACTIVE:
                reasons.append(
                    PolicyReason(
                        constraint="cooling_system_active",
                        observed=world_state.cooling.value,
                        required=CoolingState.ACTIVE.value,
                        status="failed",
                        details="Cooling is not active; critical thermal limit protection active.",
                    )
                )
                is_denied = True
            else:
                reasons.append(
                    PolicyReason(
                        constraint="cooling_system_active",
                        observed=world_state.cooling.value,
                        required=CoolingState.ACTIVE.value,
                        status="passed",
                        details="Cooling system verified ACTIVE.",
                    )
                )

        # --- 5. Contradiction Detection ---
        contradiction_report = ContradictionDetector.detect(evidence, target=proposal.target)
        if contradiction_report.contradiction:
            if contradiction_report.severity == ContradictionSeverity.HIGH:
                reasons.append(
                    PolicyReason(
                        constraint="contradiction_check",
                        observed=f"HIGH ({contradiction_report.sources})",
                        required="No HIGH severity contradictions",
                        status="failed",
                        details=f"High-severity contradiction detected: {contradiction_report.details}",
                    )
                )
                # High severity contradiction blocks execution
                is_denied = True
            elif contradiction_report.severity == ContradictionSeverity.MEDIUM:
                reasons.append(
                    PolicyReason(
                        constraint="contradiction_check",
                        observed=f"MEDIUM ({contradiction_report.sources})",
                        required="No unresolved sensor conflicts",
                        status="requires_evidence",
                        details=f"Medium sensor contradiction detected: {contradiction_report.details}",
                    )
                )
                needs_evidence = True
        else:
            reasons.append(
                PolicyReason(
                    constraint="contradiction_check",
                    observed="NONE",
                    required="No contradictions",
                    status="passed",
                    details="No sensor contradictions detected across evidence sources.",
                )
            )

        # --- 6. Target Identification & Confidence Evaluation ---
        # Find evidence pointing to this target
        target_evidences = [
            e for e in evidence
            if e.target == proposal.target or proposal.target in e.target
        ]

        max_evidence_confidence = 0.0
        if target_evidences:
            max_evidence_confidence = max(e.confidence for e in target_evidences)

        # The effective confidence requires both the model proposal and grounded evidence
        effective_confidence = min(max_evidence_confidence, proposal.model_confidence) if target_evidences else 0.0

        if effective_confidence < policy.min_target_confidence:
            reasons.append(
                PolicyReason(
                    constraint="target_identity_confidence",
                    observed=round(effective_confidence, 3),
                    required=policy.min_target_confidence,
                    status="failed",
                    details=(
                        f"Effective target confidence {effective_confidence:.2f} is below "
                        f"required threshold {policy.min_target_confidence:.2f}."
                    ),
                )
            )
            needs_evidence = True
        else:
            reasons.append(
                PolicyReason(
                    constraint="target_identity_confidence",
                    observed=round(effective_confidence, 3),
                    required=policy.min_target_confidence,
                    status="passed",
                    details=(
                        f"Effective confidence {effective_confidence:.2f} meets or exceeds "
                        f"threshold {policy.min_target_confidence:.2f}."
                    ),
                )
            )

        # --- 7. Required Evidence Sources Evaluation ---
        if policy.required_evidence_sources:
            available_sources = {e.source for e in target_evidences}
            missing_sources = [
                s.value for s in policy.required_evidence_sources
                if s not in available_sources
            ]
            if missing_sources:
                reasons.append(
                    PolicyReason(
                        constraint="required_evidence_sources",
                        observed=list(s.value for s in available_sources),
                        required=list(s.value for s in policy.required_evidence_sources),
                        status="requires_evidence",
                        details=f"Missing mandatory evidence from source(s): {missing_sources}",
                    )
                )
                needs_evidence = True
            else:
                reasons.append(
                    PolicyReason(
                        constraint="required_evidence_sources",
                        observed=list(s.value for s in available_sources),
                        required=list(s.value for s in policy.required_evidence_sources),
                        status="passed",
                        details="All required evidence sources are represented.",
                    )
                )

        # --- Final Decision Resolution ---
        if is_denied:
            decision = DecisionType.DENY
        elif needs_evidence:
            decision = DecisionType.NEED_MORE_EVIDENCE
        else:
            decision = DecisionType.ALLOW

        return PolicyDecision(
            decision=decision,
            proposal_id=proposal.id,
            target=proposal.target,
            reasons=reasons,
            contradiction_severity=contradiction_report.severity,
            timestamp=time.time(),
        )
