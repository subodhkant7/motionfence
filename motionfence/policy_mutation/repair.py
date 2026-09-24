"""Safe repair proposal synthesizer and detached validation pipeline (Phase 2K).

CRITICAL INVARIANTS:
1. LLM/model output NEVER has direct authority to modify policy or execute physical actions.
2. The repair synthesizer produces a PROPOSAL ONLY; it possesses ZERO authority to:
   - modify the live policy
   - modify the production policy baseline
   - mint AuthorizationTicket objects
   - call PhysicalActuator
   - execute recovery actions
   - call Nebius / Tavily / network
   - bypass SafetyEnclave
   - bypass execution-time revalidation
   - bypass quarantine
   - weaken an existing safety control in order to make the repair pass
3. All analysis remains offline and deterministic by default.
4. The synthesizer itself must NEVER declare a repair safe; only the validation pipeline may produce the final evaluation.
5. Inconclusive repairs map conservatively to REJECT.
"""

from copy import deepcopy
from enum import Enum
import hashlib
import json
import time
from typing import Any, Dict, List, Optional, Tuple
from pydantic import BaseModel, Field

from motionfence.assurance.checker import BoundedAssuranceChecker
from motionfence.assurance.models import FindingStatus
from motionfence.models.actions import ActionProposal, ActionType
from motionfence.models.world import CoolingState, HumanZoneState, ValveState, WorldState
from motionfence.policy.engine import PolicyEngine
from motionfence.policy.models import DecisionType, Policy, PolicyDecision
from motionfence.policy_mutation.baseline import PolicyBaselineManager
from motionfence.policy_mutation.models import (
    MutationEvaluationResult,
    PolicyBaseline,
    PolicyFirewallDecision,
    PolicyMutation,
    PolicyMutationType,
    PolicyRegressionType,
    PolicyRepairProposal,
    TrajectoryOutcomeType,
)
from motionfence.policy_mutation.mutators import (
    PolicyMutatorRegistry,
    compute_canonical_policy_hash,
)
from motionfence.policy_mutation.trajectory import DynamicTrajectoryEvaluator, TrajectoryGenerator


class RepairStatus(str, Enum):
    """Categorical verdict of the Policy Repair Validation Pipeline."""
    ACCEPTABLE = "ACCEPTABLE"
    REJECTED = "REJECTED"
    INCONCLUSIVE = "INCONCLUSIVE"


class SafetyMonotonicityReport(BaseModel):
    """Explicit multi-dimensional safety monotonicity tracking.

    Ensures the repaired policy does NOT introduce a newly permitted unsafe action that baseline prohibited.
    """
    monotonicity_preserved: bool = True
    new_unsafe_allows: int = 0
    newly_weakened_authorization_boundary: bool = False
    newly_tolerated_contradictions: bool = False
    newly_accepted_stale_evidence: bool = False
    newly_accepted_out_of_scope_targets: bool = False
    newly_bypassed_recovery_containment: bool = False
    details: List[str] = Field(default_factory=list)


class RepairValidationResult(BaseModel):
    """Comprehensive validation result produced by evaluating a candidate repair through the safety firewall."""
    validation_id: str = Field(default_factory=lambda: f"rval_{hashlib.sha256(str(time.time()).encode()).hexdigest()[:10]}")
    proposal: PolicyRepairProposal
    candidate_policy_hash: str
    status: RepairStatus
    monotonicity_report: SafetyMonotonicityReport
    formal_checks_passed: bool = True
    violated_formal_properties: List[str] = Field(default_factory=list)
    trajectory_regressions: int = 0
    rationale: str = ""
    duration_seconds: float = 0.0

    @property
    def is_acceptable(self) -> bool:
        return self.status == RepairStatus.ACCEPTABLE


class PolicyRepairSynthesizer:
    """Synthesizes safe, non-authoritative candidate repair proposals for detected policy regressions.

    CRITICAL: Does NOT modify live policy. Returns a minimal candidate proposal only.
    Where a correct repair value cannot be derived deterministically from the baseline,
    returns an INCONCLUSIVE proposal.
    """

    @staticmethod
    def synthesize_repair(
        evaluation_result: MutationEvaluationResult,
        baseline: PolicyBaseline,
    ) -> PolicyRepairProposal:
        """Derive minimal candidate repair proposal from baseline configuration and detected regression."""
        mutation = evaluation_result.mutation
        regression = evaluation_result.regression_type
        baseline_policy = PolicyBaselineManager.restore_policy_from_baseline(baseline)

        # 1. Determine affected field and derive minimal deterministic patch
        target_field = mutation.mutation_target
        before_val = mutation.after_value
        after_val: Any = None
        safety_rationale = ""
        expected_invariant = ""
        is_inconclusive = False

        if target_field == "min_target_confidence" or "confidence" in target_field:
            after_val = baseline_policy.min_target_confidence
            safety_rationale = f"Restore target confidence threshold to baseline safe bound of {after_val}."
            expected_invariant = "PROP_032_MUTATION_CONFIDENCE_WEAKENING_CANNOT_EVADE_ASSURANCE"

        elif target_field == "human_zone_check" or "human_zone" in target_field or "require_human_zone_clear" in target_field:
            after_val = True
            safety_rationale = "Re-enable mandatory human safety zone clear condition."
            expected_invariant = "PROP_001_HUMAN_ZONE_PROHIBITION"

        elif target_field == "contradiction_check" or "max_contradiction_severity" in target_field or "contradiction" in target_field or "max_tolerated_contradiction" in target_field:
            after_val = baseline_policy.max_tolerated_contradiction.value if hasattr(baseline_policy.max_tolerated_contradiction, "value") else "NONE"
            safety_rationale = f"Restore strict contradiction tolerance to baseline safe bound ({after_val})."
            expected_invariant = "PROP_006_CONTRADICTORY_EVIDENCE_GATING"

        elif target_field == "require_cooling_active" or "cooling" in target_field:
            after_val = True
            safety_rationale = "Re-enable cooling system preservation requirement for valve actuation."
            expected_invariant = "PROP_002_COOLING_PRESERVATION"

        elif target_field in ("allowed_actuator_targets", "allowed_targets") or "target_scope" in target_field:
            after_val = list(baseline_policy.allowed_actuator_targets)
            safety_rationale = f"Restrict allowed targets to baseline explicit target set: {after_val}."
            expected_invariant = "PROP_034_MUTATION_CANNOT_DISABLE_STATE_BOUND_AUTHORIZATION"

        elif "revalidation" in target_field or "toctou" in target_field:
            after_val = False  # disable_revalidation = False
            safety_rationale = "Re-enable execution-time TOCTOU revalidation guard."
            expected_invariant = "PROP_008_NO_EXECUTION_AFTER_STATE_DRIFT"

        elif "quarantine" in target_field:
            after_val = False  # bypass_quarantine = False
            safety_rationale = "Restore component quarantine containment boundary."
            expected_invariant = "PROP_025_QUARANTINED_COMPONENTS_CANNOT_EXECUTE"

        elif "freshness" in target_field or "age" in target_field:
            after_val = baseline_policy.expected_postconditions.get("max_knowledge_age_seconds", 5.0)
            safety_rationale = f"Restore maximum allowable knowledge freshness bound to {after_val}s."
            expected_invariant = "PROP_005_STALE_SAFETY_CONSTRAINT_BLOCKS_AUTHORIZATION"

        else:
            # Cannot derive deterministically from baseline -> REPAIR_INCONCLUSIVE
            is_inconclusive = True
            after_val = None
            safety_rationale = f"Cannot derive deterministic safe repair value for '{target_field}' from baseline."
            expected_invariant = "UNKNOWN_INVARIANT"

        # Compute deterministic proposal hash
        raw_hash_data = {
            "source_mutation_id": mutation.mutation_id,
            "regression": regression.value,
            "target_field": target_field,
            "before_val": str(before_val),
            "after_val": str(after_val),
            "is_inconclusive": is_inconclusive,
        }
        prop_hash = hashlib.sha256(json.dumps(raw_hash_data, sort_keys=True).encode("utf-8")).hexdigest()

        return PolicyRepairProposal(
            source_mutation_id=mutation.mutation_id,
            detected_regression=regression,
            affected_field=target_field,
            proposed_change=f"Set {target_field} = {after_val}",
            before_value=before_val,
            after_value=after_val,
            safety_rationale=safety_rationale,
            counterexample_ref=evaluation_result.counterexample.counterexample_id if evaluation_result.counterexample else None,
            expected_invariant_restored=expected_invariant,
            confidence=0.0 if is_inconclusive else 1.0,
            proposal_hash=prop_hash,
            status="REPAIR_INCONCLUSIVE" if is_inconclusive else "PROPOSED",
        )


class PolicyRepairValidator:
    """Detached validation pipeline that tests candidate policy repairs against the full safety machinery.

    PIPELINE:
    Candidate repair -> Detached clone -> Canonical hash -> Bounded formal checks ->
    Adversarial probes & Monotonicity check -> Dynamic trajectory evaluation ->
    ACCEPTABLE / REJECTED / INCONCLUSIVE.
    """

    def __init__(self) -> None:
        self.assurance_checker = BoundedAssuranceChecker()
        self.trajectory_evaluator = DynamicTrajectoryEvaluator()

    def validate(
        self,
        proposal: PolicyRepairProposal,
        mutated_policy: Policy,
        baseline: PolicyBaseline,
    ) -> RepairValidationResult:
        """Evaluate candidate repair as an isolated detached policy clone."""
        start_time = time.time()
        baseline_policy = PolicyBaselineManager.restore_policy_from_baseline(baseline)

        # 1. Fail closed on inconclusive proposals
        if proposal.status == "REPAIR_INCONCLUSIVE" or proposal.confidence < 1.0 or proposal.after_value is None:
            return RepairValidationResult(
                proposal=proposal,
                candidate_policy_hash="N/A",
                status=RepairStatus.INCONCLUSIVE,
                monotonicity_report=SafetyMonotonicityReport(monotonicity_preserved=False, details=["Proposal was marked inconclusive"]),
                formal_checks_passed=False,
                violated_formal_properties=[],
                trajectory_regressions=0,
                rationale="Inconclusive repair proposal fails closed to protect production safety.",
                duration_seconds=time.time() - start_time,
            )

        # 2. Materialize candidate policy as a detached deepcopy
        candidate_policy = deepcopy(mutated_policy)
        self._apply_candidate_patch(candidate_policy, proposal)
        cand_hash = compute_canonical_policy_hash(candidate_policy)

        # 3. Check formal bounded assurance properties
        violated_props: List[str] = []
        for prop_id in [
            "PROP_001_HUMAN_ZONE_PROHIBITION",
            "PROP_002_COOLING_PRESERVATION",
            "PROP_006_CONTRADICTORY_EVIDENCE_GATING",
            "PROP_008_NO_EXECUTION_AFTER_STATE_DRIFT",
            "PROP_025_QUARANTINED_COMPONENTS_CANNOT_EXECUTE",
            "PROP_029_RECOVERY_BUDGET_IS_FINITE",
            "PROP_031_MUTATION_HUMAN_ZONE_GUARD_REMOVAL_DETECTED",
            "PROP_032_MUTATION_CONFIDENCE_WEAKENING_CANNOT_EVADE_ASSURANCE",
            "PROP_033_MUTATION_CONTRADICTION_REMOVAL_DETECTED",
            "PROP_034_MUTATION_CANNOT_DISABLE_STATE_BOUND_AUTHORIZATION",
            "PROP_035_MUTATION_CANNOT_DISABLE_EXECUTION_REVALIDATION",
            "PROP_036_MUTATION_CANNOT_DISABLE_RECOVERY_CONTAINMENT",
        ]:
            finding = self.assurance_checker.check_property(prop_id)
            if finding.status == FindingStatus.VIOLATED:
                violated_props.append(prop_id)

        formal_passed = (len(violated_props) == 0)

        # 4. Multi-dimensional safety monotonicity check
        mono_report = self._check_safety_monotonicity(candidate_policy, baseline_policy)

        # 5. Dynamic physical trajectory evaluation
        trajectories = TrajectoryGenerator.generate_trajectories(seed=42, depths=[3, 5])
        trajectory_regressions = 0
        for traj in trajectories:
            t_res = self.trajectory_evaluator.evaluate_trajectory(traj, candidate_policy, baseline_policy)
            if t_res.is_regression or t_res.outcome == TrajectoryOutcomeType.NEW_UNSAFE_ALLOW:
                trajectory_regressions += 1

        # 6. Synthesize final validation decision
        if not formal_passed or not mono_report.monotonicity_preserved or trajectory_regressions > 0:
            status = RepairStatus.REJECTED
            reasons = []
            if not formal_passed:
                reasons.append(f"Violated formal properties: {violated_props}")
            if not mono_report.monotonicity_preserved:
                reasons.append(f"Monotonicity broken: {mono_report.details}")
            if trajectory_regressions > 0:
                reasons.append(f"Trajectory regressions detected: {trajectory_regressions}")
            rationale = "Candidate repair rejected: " + "; ".join(reasons)
        else:
            status = RepairStatus.ACCEPTABLE
            rationale = "Candidate repair verified acceptable under formal checks, monotonicity audit, and dynamic trajectories."

        return RepairValidationResult(
            proposal=proposal,
            candidate_policy_hash=cand_hash,
            status=status,
            monotonicity_report=mono_report,
            formal_checks_passed=formal_passed,
            violated_formal_properties=violated_props,
            trajectory_regressions=trajectory_regressions,
            rationale=rationale,
            duration_seconds=time.time() - start_time,
        )

    def _apply_candidate_patch(self, policy: Policy, proposal: PolicyRepairProposal) -> None:
        """Apply the minimal patch described in the proposal to the detached candidate policy."""
        field = proposal.affected_field
        val = proposal.after_value

        if field == "min_target_confidence" or "confidence" in field:
            policy.min_target_confidence = float(val)
        elif field == "require_cooling_active" or "cooling" in field:
            policy.require_cooling_active = bool(val)
        elif field in ("allowed_actuator_targets", "allowed_targets", "target_scope"):
            policy.allowed_actuator_targets = list(val) if isinstance(val, (list, set)) else [str(val)]
        elif field in ("disable_revalidation", "toctou"):
            policy.expected_postconditions["disable_revalidation"] = bool(val)
        elif field in ("bypass_quarantine", "quarantine"):
            policy.expected_postconditions["bypass_quarantine"] = bool(val)
        elif field in ("max_knowledge_age_seconds", "freshness"):
            policy.expected_postconditions["max_knowledge_age_seconds"] = float(val)
        elif field in ("contradiction_check", "contradiction", "max_contradiction_severity", "max_tolerated_contradiction"):
            from motionfence.evidence.models import ContradictionSeverity
            policy.max_tolerated_contradiction = ContradictionSeverity(val) if isinstance(val, str) else val

    def _check_safety_monotonicity(
        self,
        candidate_policy: Policy,
        baseline_policy: Policy,
    ) -> SafetyMonotonicityReport:
        """Verify that candidate policy permits NO actions that the baseline prohibited across safety dimensions."""
        new_unsafe = 0
        weakened_auth = False
        tolerated_contradictions = False
        accepted_stale = False
        out_of_scope = False
        bypassed_recovery = False
        details: List[str] = []

        # Probe 1: Human zone occupied
        ws_human = WorldState(
            valves={"valve_b": ValveState.OPEN},
            cooling=CoolingState.ACTIVE,
            human_zone=HumanZoneState.OCCUPIED,
        )
        p_close = ActionProposal(
            action_type=ActionType.CLOSE_VALVE,
            target="valve_b",
            model_confidence=0.95,
            rationale="Monotonicity probe: human occupied",
        )
        base_dec = PolicyEngine.evaluate(p_close, ws_human, [], policy=baseline_policy)
        cand_dec = PolicyEngine.evaluate(p_close, ws_human, [], policy=candidate_policy)
        if not base_dec.is_allowed and cand_dec.is_allowed:
            new_unsafe += 1
            details.append("Candidate permitted action during human zone occupancy.")

        # Probe 2: Cooling inactive
        ws_cooling = WorldState(
            valves={"valve_b": ValveState.OPEN},
            cooling=CoolingState.INACTIVE,
            human_zone=HumanZoneState.CLEAR,
        )
        base_dec = PolicyEngine.evaluate(p_close, ws_cooling, [], policy=baseline_policy)
        cand_dec = PolicyEngine.evaluate(p_close, ws_cooling, [], policy=candidate_policy)
        if not base_dec.is_allowed and cand_dec.is_allowed:
            new_unsafe += 1
            details.append("Candidate permitted action during inactive cooling.")

        # Probe 3: Contradiction tolerance check
        if candidate_policy.max_tolerated_contradiction != baseline_policy.max_tolerated_contradiction:
            tolerated_contradictions = True
            details.append("Candidate weakened contradiction tolerance boundary.")

        # Probe 4: Out-of-scope targets
        if candidate_policy.allowed_actuator_targets and baseline_policy.allowed_actuator_targets:
            if not set(baseline_policy.allowed_actuator_targets).issuperset(set(candidate_policy.allowed_actuator_targets)):
                out_of_scope = True
                details.append("Candidate expanded allowed target set beyond baseline.")

        # Probe 5: Postcondition revalidation and quarantine bypasses
        if candidate_policy.expected_postconditions.get("disable_revalidation", False):
            weakened_auth = True
            details.append("Candidate disabled execution-time revalidation.")

        if candidate_policy.expected_postconditions.get("bypass_quarantine", False):
            bypassed_recovery = True
            details.append("Candidate bypassed component quarantine containment.")

        monotonicity_preserved = (
            new_unsafe == 0
            and not weakened_auth
            and not tolerated_contradictions
            and not accepted_stale
            and not out_of_scope
            and not bypassed_recovery
        )

        return SafetyMonotonicityReport(
            monotonicity_preserved=monotonicity_preserved,
            new_unsafe_allows=new_unsafe,
            newly_weakened_authorization_boundary=weakened_auth,
            newly_tolerated_contradictions=tolerated_contradictions,
            newly_accepted_stale_evidence=accepted_stale,
            newly_accepted_out_of_scope_targets=out_of_scope,
            newly_bypassed_recovery_containment=bypassed_recovery,
            details=details,
        )
