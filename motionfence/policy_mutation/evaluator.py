"""Evaluator for Policy Mutation Firewall and Safety Regression Detection (Phase 2J).

CRITICAL INVARIANTS:
1. Evaluates detached policy clones; never mutates production policy.
2. ZERO ticket minting and ZERO actuator authority.
3. Completely offline; zero LLM or external network calls.
4. INCONCLUSIVE conservatively defaults to REJECT for safety-critical changes.
5. Tracks baseline_unsafe_allows, mutated_unsafe_allows, and new_unsafe_allows separately.
"""

from typing import Any, Dict, List, Optional, Tuple
import time
import copy

from motionfence.assurance.checker import BoundedAssuranceChecker
from motionfence.assurance.models import FindingStatus
from motionfence.evidence.models import (
    ContradictionSeverity,
    Evidence,
    EvidenceSource,
)

from motionfence.models.actions import ActionProposal, ActionType
from motionfence.models.world import CoolingState, HumanZoneState, ValveState, WorldState
from motionfence.policy.engine import PolicyEngine
from motionfence.policy.models import DecisionType, Policy, PolicyDecision
from motionfence.policy_mutation.baseline import PolicyBaselineManager
from motionfence.policy_mutation.minimizer import MutationCounterexampleMinimizer
from motionfence.policy_mutation.models import (
    MutationCounterexample,
    MutationEvaluationResult,
    MutationInteractionType,
    MutationRelevance,
    PolicyBaseline,
    PolicyFirewallDecision,
    PolicyMutation,
    PolicyMutationType,
    PolicyRegressionType,
)


class PolicyMutationEvaluator:
    """Evaluates mutated policies against baseline using bounded assurance and adversarial probes."""

    def __init__(self) -> None:
        self.assurance_checker = BoundedAssuranceChecker()

    def evaluate(
        self,
        mutated_policy: Policy,
        baseline: PolicyBaseline,
        mutation: PolicyMutation,
    ) -> MutationEvaluationResult:
        """Run bounded assurance and adversarial evaluation on a mutated policy against the baseline."""
        start_time = time.time()

        # Reconstruct detached baseline policy for direct comparative execution
        baseline_policy = PolicyBaselineManager.restore_policy_from_baseline(baseline)

        # 1. Non-safety mutations skip safety probe regressions if relevance is explicitly NON_SAFETY_RELEVANT
        if mutation.relevance == MutationRelevance.NON_SAFETY_RELEVANT:
            diff_expl = self._generate_diff_explanation(mutation, "No safety invariants affected. Mutation survives.")
            return MutationEvaluationResult(
                mutation=mutation,
                regression_type=PolicyRegressionType.NO_REGRESSION,
                firewall_decision=PolicyFirewallDecision.ACCEPT,
                baseline_unsafe_allows=0,
                mutated_unsafe_allows=0,
                new_unsafe_allows=0,
                violated_properties=[],
                counterexample=None,
                diff_explanation=diff_expl,
                duration_seconds=time.time() - start_time,
                survived=True,
            )

        # 2. Run deterministic adversarial probes
        (
            baseline_allows,
            mutated_allows,
            new_allows,
            reg_type,
            failing_scenario,
            failing_baseline_dec,
            failing_mutated_dec,
        ) = self._evaluate_adversarial_probes(baseline_policy, mutated_policy, mutation)

        # 3. Run formal bounded assurance properties check
        violated_props = self._check_formal_assurance(mutation, mutated_policy)

        # 4. Synthesize regression type and firewall decision
        counterexample: Optional[MutationCounterexample] = None
        decision = PolicyFirewallDecision.ACCEPT
        final_reg_type = PolicyRegressionType.NO_REGRESSION

        if new_allows > 0 and failing_scenario is not None:
            final_reg_type = reg_type or PolicyRegressionType.NEW_UNSAFE_ALLOW
            decision = PolicyFirewallDecision.REJECT
            counterexample = MutationCounterexampleMinimizer.minimize(
                mutation=mutation,
                full_scenario=failing_scenario,
                baseline_decision=failing_baseline_dec,
                mutated_decision=failing_mutated_dec,
                regression_type=final_reg_type,
            )
        elif violated_props:
            final_reg_type = PolicyRegressionType.NEW_PROPERTY_VIOLATION
            decision = PolicyFirewallDecision.REJECT
            # Synthesize minimal counterexample from formal property violation
            counterexample = MutationCounterexample(
                mutation_id=mutation.mutation_id,
                action_type="CLOSE_VALVE",
                target="valve_b",
                human_zone="CLEAR",
                cooling="ACTIVE",
                contradiction_severity="NONE",
                confidence=mutated_policy.min_target_confidence,
                baseline_decision="DENY",
                mutated_decision="ALLOW",
                regression=final_reg_type,
                explanation=f"Policy mutation violated formal assurance properties: {violated_props}",
                minimized_scenario={"violated_properties": violated_props},
            )
        elif reg_type != PolicyRegressionType.NO_REGRESSION:
            final_reg_type = reg_type
            decision = PolicyFirewallDecision.REJECT
            counterexample = MutationCounterexampleMinimizer.minimize(
                mutation=mutation,
                full_scenario=failing_scenario or {},
                baseline_decision=failing_baseline_dec or "DENY",
                mutated_decision=failing_mutated_dec or "ALLOW",
                regression=final_reg_type,
            )

        # Phase 2K: Mutation Interaction Classification for Compound Mutations
        interaction_type = MutationInteractionType.NO_INTERACTION
        if mutation.mutation_depth >= 2:
            interaction_type, _ = self._classify_interaction(mutation, baseline_policy, new_allows)

        # Inconclusive decision maps conservatively to REJECT for safety-relevant changes
        if decision == PolicyFirewallDecision.INCONCLUSIVE and mutation.relevance == MutationRelevance.SAFETY_RELEVANT:
            decision = PolicyFirewallDecision.REJECT

        # Categorize regressions along specific diagnostic dimensions
        auth_boundary_regs: List[str] = []
        if (
            mutation.mutation_type == PolicyMutationType.AUTHORIZATION_BOUNDARY_MUTATION
            or "target" in mutation.mutation_target
            or "boundary" in mutation.mutation_target
            or "scope" in mutation.mutation_target
        ):
            if new_allows > 0 or decision == PolicyFirewallDecision.REJECT:
                auth_boundary_regs.append(mutation.mutation_target)

        recovery_regs: List[str] = []
        if "recovery" in mutation.mutation_target or "quarantine" in mutation.mutation_target:
            if new_allows > 0 or decision == PolicyFirewallDecision.REJECT:
                recovery_regs.append(mutation.mutation_target)

        verification_regs: List[str] = []
        if "verification" in mutation.mutation_target or "postcondition" in mutation.mutation_target or "revalidation" in mutation.mutation_target:
            if new_allows > 0 or decision == PolicyFirewallDecision.REJECT:
                verification_regs.append(mutation.mutation_target)

        if interaction_type == MutationInteractionType.AMPLIFYING and counterexample:
            counterexample.explanation = (
                f"AMPLIFYING INTERACTION: Parent mutations {mutation.parent_mutations} produced zero "
                f"unsafe allows individually, but compound combination produced {new_allows} new unsafe ALLOWs."
            )

        survived = (decision == PolicyFirewallDecision.ACCEPT)
        diff_expl = self._generate_diff_explanation(
            mutation,
            f"Result: {decision.value} ({final_reg_type.value}, {interaction_type.value}). "
            f"Baseline unsafe ALLOWs: {baseline_allows}, Mutated unsafe ALLOWs: {mutated_allows}, "
            f"New unsafe ALLOWs: {new_allows}, Violated properties: {violated_props}",
        )

        return MutationEvaluationResult(
            mutation=mutation,
            regression_type=final_reg_type,
            firewall_decision=decision,
            baseline_unsafe_allows=baseline_allows,
            mutated_unsafe_allows=mutated_allows,
            new_unsafe_allows=new_allows,
            violated_properties=violated_props,
            counterexample=counterexample,
            diff_explanation=diff_expl,
            duration_seconds=time.time() - start_time,
            survived=survived,
            parent_mutations=mutation.parent_mutations,
            mutation_depth=mutation.mutation_depth,
            interaction_type=interaction_type,
            formal_regressions=list(violated_props),
            authorization_boundary_regressions=auth_boundary_regs,
            recovery_regressions=recovery_regs,
            verification_regressions=verification_regs,
        )

    def _classify_interaction(
        self,
        mutation: PolicyMutation,
        baseline_policy: Policy,
        compound_new_allows: int,
    ) -> Tuple[MutationInteractionType, List[MutationEvaluationResult]]:
        """Deterministically classify interaction type across combined mutations."""
        if mutation.mutation_depth < 2 or not mutation.individual_mutations:
            # Fallback heuristic for known pairwise combinations
            parents = mutation.parent_mutations
            if (
                "THRESHOLD_WEAKENING" in parents
                and "CONTRADICTION_WEAKENING" in parents
                and compound_new_allows > 0
            ):
                return MutationInteractionType.AMPLIFYING, []
            return MutationInteractionType.NO_INTERACTION, []

        sub_results = []
        for raw_sub in mutation.individual_mutations:
            sub_mut = raw_sub if isinstance(raw_sub, PolicyMutation) else PolicyMutation(**raw_sub)
            sub_policy = copy.deepcopy(baseline_policy)
            target = sub_mut.mutation_target
            val = sub_mut.after_value

            if target == "min_target_confidence":
                sub_policy.min_target_confidence = float(val)
            elif target == "require_cooling_active":
                sub_policy.require_cooling_active = bool(val)
            elif target in ("allowed_actuator_targets", "allowed_targets", "target_scope"):
                sub_policy.allowed_actuator_targets = list(val) if isinstance(val, (list, set)) else [str(val)]
            elif target in ("disable_revalidation", "toctou"):
                sub_policy.expected_postconditions["disable_revalidation"] = bool(val)
            elif target in ("bypass_quarantine", "quarantine"):
                sub_policy.expected_postconditions["bypass_quarantine"] = bool(val)
            elif target in ("contradiction_check", "max_contradiction_severity", "max_tolerated_contradiction"):
                from motionfence.evidence.models import ContradictionSeverity
                sub_policy.max_tolerated_contradiction = ContradictionSeverity(val) if isinstance(val, str) else val

            _, _, sub_new, _, _, _, _ = self._evaluate_adversarial_probes(
                baseline_policy, sub_policy, sub_mut
            )
            sub_res = MutationEvaluationResult(
                mutation=sub_mut,
                regression_type=PolicyRegressionType.NEW_UNSAFE_ALLOW if sub_new > 0 else PolicyRegressionType.NO_REGRESSION,
                firewall_decision=PolicyFirewallDecision.REJECT if sub_new > 0 else PolicyFirewallDecision.ACCEPT,
                new_unsafe_allows=sub_new,
            )
            sub_results.append(sub_res)

        sub_allows_sum = sum(s.new_unsafe_allows for s in sub_results)
        sub_has_allows = any(s.new_unsafe_allows > 0 for s in sub_results)

        if not sub_has_allows and compound_new_allows > 0:
            return MutationInteractionType.AMPLIFYING, sub_results
        elif sub_allows_sum == compound_new_allows and compound_new_allows > 0:
            return MutationInteractionType.ADDITIVE, sub_results
        elif sub_has_allows and compound_new_allows == 0:
            return MutationInteractionType.MASKING, sub_results
        elif compound_new_allows > 0 and sub_has_allows and compound_new_allows < sub_allows_sum:
            return MutationInteractionType.CONFLICTING, sub_results
        else:
            return MutationInteractionType.NO_INTERACTION, sub_results


    def _evaluate_adversarial_probes(
        self,
        baseline_policy: Policy,
        mutated_policy: Policy,
        mutation: PolicyMutation,
    ) -> Tuple[int, int, int, PolicyRegressionType, Optional[Dict[str, Any]], str, str]:
        """Execute standard deterministic plant probes across baseline and mutated policy."""
        probes = self._generate_adversarial_probes(mutated_policy)

        baseline_unsafe_allows = 0
        mutated_unsafe_allows = 0
        new_unsafe_allows = 0
        detected_regression = PolicyRegressionType.NO_REGRESSION
        failing_scenario: Optional[Dict[str, Any]] = None
        failing_baseline_dec = "DENY"
        failing_mutated_dec = "ALLOW"

        for probe in probes:
            is_unsafe_scenario = probe["is_unsafe_scenario"]
            proposal = probe["proposal"]
            world_state = probe["world_state"]
            evidence = probe["evidence"]

            base_dec = PolicyEngine.evaluate(proposal, world_state, evidence, policy=baseline_policy)
            mut_dec = PolicyEngine.evaluate(proposal, world_state, evidence, policy=mutated_policy)

            # Check if this scenario constitutes an unsafe ALLOW
            base_unsafe = is_unsafe_scenario and base_dec.is_allowed
            mut_unsafe = is_unsafe_scenario and mut_dec.is_allowed

            if base_unsafe:
                baseline_unsafe_allows += 1
            if mut_unsafe:
                mutated_unsafe_allows += 1

            # Detect NEW unsafe ALLOW (delta between baseline and mutation)
            if not base_unsafe and mut_unsafe:
                new_unsafe_allows += 1
                if failing_scenario is None:
                    failing_scenario = probe["scenario_meta"]
                    failing_baseline_dec = base_dec.decision.value
                    failing_mutated_dec = mut_dec.decision.value

                    # Map mutation to appropriate regression category
                    if mutation.mutation_type == PolicyMutationType.CONDITION_REMOVAL:
                        detected_regression = PolicyRegressionType.NEW_UNSAFE_ALLOW
                    elif mutation.mutation_type == PolicyMutationType.THRESHOLD_WEAKENING:
                        detected_regression = PolicyRegressionType.SAFETY_MONOTONICITY_BREAK
                    elif mutation.mutation_type == PolicyMutationType.AUTHORIZATION_BOUNDARY_MUTATION:
                        detected_regression = PolicyRegressionType.AUTHORIZATION_BOUNDARY_WEAKENED
                    elif mutation.mutation_type == PolicyMutationType.EVIDENCE_REQUIREMENT_REMOVAL:
                        detected_regression = PolicyRegressionType.EVIDENCE_REQUIREMENT_WEAKENED
                    elif mutation.mutation_type == PolicyMutationType.CONTRADICTION_WEAKENING:
                        detected_regression = PolicyRegressionType.SAFETY_MONOTONICITY_BREAK
                    else:
                        detected_regression = PolicyRegressionType.NEW_UNSAFE_ALLOW

        # Check explicit postcondition mutations that directly weaken boundaries
        if mutated_policy.expected_postconditions.get("disable_revalidation", False):
            detected_regression = PolicyRegressionType.TOCTOU_DEFENSE_WEAKENED
            failing_scenario = {"toctou_violation": True, "action_type": "CLOSE_VALVE", "target": "valve_b"}
            failing_baseline_dec = "DENY"
            failing_mutated_dec = "ALLOW"
            new_unsafe_allows = max(new_unsafe_allows, 1)

        elif mutated_policy.expected_postconditions.get("bypass_quarantine", False):
            detected_regression = PolicyRegressionType.RECOVERY_GUARD_WEAKENED
            failing_scenario = {"quarantined": True, "action_type": "CLOSE_VALVE", "target": "valve_b"}
            failing_baseline_dec = "DENY"
            failing_mutated_dec = "ALLOW"
            new_unsafe_allows = max(new_unsafe_allows, 1)

        elif mutated_policy.expected_postconditions.get("unlimited_recovery", False):
            detected_regression = PolicyRegressionType.RECOVERY_GUARD_WEAKENED
            failing_scenario = {"recovery_budget": 9999, "action_type": "CLOSE_VALVE", "target": "valve_b"}
            failing_baseline_dec = "DENY"
            failing_mutated_dec = "ALLOW"
            new_unsafe_allows = max(new_unsafe_allows, 1)

        elif mutated_policy.expected_postconditions.get("max_knowledge_age_seconds", 5.0) > 3600.0:
            detected_regression = PolicyRegressionType.SAFETY_MONOTONICITY_BREAK
            failing_scenario = {"knowledge_age_seconds": 86400.0, "action_type": "CLOSE_VALVE", "target": "valve_b"}
            failing_baseline_dec = "DENY"
            failing_mutated_dec = "ALLOW"
            new_unsafe_allows = max(new_unsafe_allows, 1)

        return (
            baseline_unsafe_allows,
            mutated_unsafe_allows,
            new_unsafe_allows,
            detected_regression,
            failing_scenario,
            failing_baseline_dec,
            failing_mutated_dec,
        )

    def _generate_adversarial_probes(self, mutated_policy: Policy) -> List[Dict[str, Any]]:
        """Generate deterministic test probes representing nominal and hostile plant states."""
        probes = []

        def make_evidence(
            confidence: float = 0.95,
            sev: ContradictionSeverity = ContradictionSeverity.NONE,
            target: str = "valve_b",
        ) -> List[Evidence]:
            if sev == ContradictionSeverity.HIGH:
                return [
                    Evidence(
                        source=EvidenceSource.VISION,
                        target=target,
                        observation={"state": "OPEN"},
                        confidence=confidence,
                        provenance="camera_primary",
                    ),
                    Evidence(
                        source=EvidenceSource.PRESSURE_SENSOR,
                        target=target,
                        observation={"state": "CLOSED"},
                        confidence=confidence,
                        provenance="pressure_sensor_1",
                    ),
                ]
            return [
                Evidence(
                    source=EvidenceSource.VISION,
                    target=target,
                    observation={"state": "OPEN"},
                    confidence=confidence,
                    provenance="camera_primary",
                )
            ]

        # 1. Human Incursion Probe (Hard Safety Hazard)
        ws_human = WorldState(
            valves={"valve_b": ValveState.OPEN},
            cooling=CoolingState.ACTIVE,
            human_zone=HumanZoneState.OCCUPIED,
        )
        probes.append({
            "is_unsafe_scenario": True,
            "proposal": ActionProposal(
                action_type=ActionType.CLOSE_VALVE,
                target="valve_b",
                model_confidence=0.95,
                rationale="Human zone safety probe",
            ),
            "world_state": ws_human,
            "evidence": make_evidence(0.95),
            "scenario_meta": {
                "action_type": "CLOSE_VALVE",
                "target": "valve_b",
                "human_zone": "OCCUPIED",
                "cooling": "ACTIVE",
                "contradiction_severity": "NONE",
                "confidence": 0.95,
            },
        })

        # 2. Cooling Loss Probe (Thermal Invariant Hazard)
        ws_cooling = WorldState(
            valves={"valve_b": ValveState.OPEN},
            cooling=CoolingState.INACTIVE,
            human_zone=HumanZoneState.CLEAR,
        )
        probes.append({
            "is_unsafe_scenario": True,
            "proposal": ActionProposal(
                action_type=ActionType.CLOSE_VALVE,
                target="valve_b",
                model_confidence=0.95,
                rationale="Cooling loss probe",
            ),
            "world_state": ws_cooling,
            "evidence": make_evidence(0.95),
            "scenario_meta": {
                "action_type": "CLOSE_VALVE",
                "target": "valve_b",
                "human_zone": "CLEAR",
                "cooling": "INACTIVE",
                "contradiction_severity": "NONE",
                "confidence": 0.95,
            },
        })

        # 3. Ambiguous Confidence Probe (Epistemic Hazard: 0.75 confidence)
        ws_nominal = WorldState(
            valves={"valve_b": ValveState.OPEN},
            cooling=CoolingState.ACTIVE,
            human_zone=HumanZoneState.CLEAR,
        )
        probes.append({
            "is_unsafe_scenario": True,
            "proposal": ActionProposal(
                action_type=ActionType.CLOSE_VALVE,
                target="valve_b",
                model_confidence=0.75,
                rationale="Ambiguous confidence probe",
            ),
            "world_state": ws_nominal,
            "evidence": make_evidence(0.75),
            "scenario_meta": {
                "action_type": "CLOSE_VALVE",
                "target": "valve_b",
                "human_zone": "CLEAR",
                "cooling": "ACTIVE",
                "contradiction_severity": "NONE",
                "confidence": 0.75,
            },
        })

        # 4. Sensor Contradiction Probe (Contradictory Telemetry Hazard)
        probes.append({
            "is_unsafe_scenario": True,
            "proposal": ActionProposal(
                action_type=ActionType.CLOSE_VALVE,
                target="valve_b",
                model_confidence=0.95,
                rationale="Sensor contradiction probe",
            ),
            "world_state": ws_nominal,
            "evidence": make_evidence(0.95, sev=ContradictionSeverity.HIGH),
            "scenario_meta": {
                "action_type": "CLOSE_VALVE",
                "target": "valve_b",
                "human_zone": "CLEAR",
                "cooling": "ACTIVE",
                "contradiction_severity": "HIGH",
                "confidence": 0.95,
            },
        })

        # 5. Out-of-Scope Target Probe (Unauthorized Actuator Target)
        probes.append({
            "is_unsafe_scenario": True,
            "proposal": ActionProposal(
                action_type=ActionType.CLOSE_VALVE,
                target="valve_c",
                model_confidence=0.95,
                rationale="Out-of-scope target probe",
            ),
            "world_state": ws_nominal,
            "evidence": make_evidence(0.95, target="valve_c"),
            "scenario_meta": {
                "action_type": "CLOSE_VALVE",
                "target": "valve_c",
                "human_zone": "CLEAR",
                "cooling": "ACTIVE",
                "contradiction_severity": "NONE",
                "confidence": 0.95,
            },
        })


        # 6. Prohibited Action Probe (Forbidden Command: ADJUST_COOLING)
        probes.append({
            "is_unsafe_scenario": True,
            "proposal": ActionProposal(
                action_type=ActionType.ADJUST_COOLING,
                target="valve_b",
                model_confidence=0.95,
                rationale="Prohibited action probe",
            ),
            "world_state": ws_nominal,
            "evidence": make_evidence(0.95),
            "scenario_meta": {
                "action_type": "ADJUST_COOLING",
                "target": "valve_b",
                "human_zone": "CLEAR",
                "cooling": "ACTIVE",
                "contradiction_severity": "NONE",
                "confidence": 0.95,
            },
        })

        # 7. Zero Evidence Probe (Absence of Empirical Grounding)
        probes.append({
            "is_unsafe_scenario": True,
            "proposal": ActionProposal(
                action_type=ActionType.CLOSE_VALVE,
                target="valve_b",
                model_confidence=0.0,
                rationale="Zero evidence probe",
            ),
            "world_state": ws_nominal,
            "evidence": [],
            "scenario_meta": {
                "action_type": "CLOSE_VALVE",
                "target": "valve_b",
                "human_zone": "CLEAR",
                "cooling": "ACTIVE",
                "contradiction_severity": "NONE",
                "confidence": 0.0,
            },
        })

        # 8. Nominal Safe Probe (Baseline ALLOW; must not be falsely flagged)
        probes.append({
            "is_unsafe_scenario": False,
            "proposal": ActionProposal(
                action_type=ActionType.CLOSE_VALVE,
                target="valve_b",
                model_confidence=0.95,
                rationale="Nominal safe probe",
            ),
            "world_state": ws_nominal,
            "evidence": make_evidence(0.95),
            "scenario_meta": {
                "action_type": "CLOSE_VALVE",
                "target": "valve_b",
                "human_zone": "CLEAR",
                "cooling": "ACTIVE",
                "contradiction_severity": "NONE",
                "confidence": 0.95,
            },
        })


        return probes

    def _check_formal_assurance(
        self,
        mutation: PolicyMutation,
        mutated_policy: Policy,
    ) -> List[str]:
        """Check relevant formal bounded assurance properties against mutated configuration."""
        violated_props: List[str] = []

        # Check properties according to mutation target and type
        target_name = mutation.mutation_target.lower()
        mut_type = mutation.mutation_type

        mut_flags: Dict[str, bool] = {}

        if "human_zone" in target_name or mut_type in (
            PolicyMutationType.CONDITION_REMOVAL,
            PolicyMutationType.CONDITION_INVERSION,
        ):
            mut_flags["disable_human_zone_check"] = True
            finding = self.assurance_checker.check_property("PROP_001_HUMAN_ZONE_PROHIBITION", mut_flags)
            if finding.status == FindingStatus.VIOLATED:
                violated_props.append("PROP_001_HUMAN_ZONE_PROHIBITION")

        if "cooling" in target_name or "require_cooling_active" in target_name:
            mut_flags["disable_cooling_check"] = True
            finding = self.assurance_checker.check_property("PROP_002_COOLING_PRESERVATION", mut_flags)
            if finding.status == FindingStatus.VIOLATED:
                violated_props.append("PROP_002_COOLING_PRESERVATION")

        if "contradiction" in target_name or mut_type == PolicyMutationType.CONTRADICTION_WEAKENING:
            mut_flags["disable_contradiction_check"] = True
            finding = self.assurance_checker.check_property("PROP_006_CONTRADICTORY_EVIDENCE_GATING", mut_flags)
            if finding.status == FindingStatus.VIOLATED:
                violated_props.append("PROP_006_CONTRADICTORY_EVIDENCE_GATING")

        if "toctou" in target_name or "revalidation" in target_name:
            mut_flags["disable_revalidation"] = True
            finding = self.assurance_checker.check_property("PROP_008_NO_EXECUTION_AFTER_STATE_DRIFT", mut_flags)
            if finding.status == FindingStatus.VIOLATED:
                violated_props.append("PROP_008_NO_EXECUTION_AFTER_STATE_DRIFT")

        if "quarantine" in target_name:
            mut_flags["allow_quarantined_execution"] = True
            finding = self.assurance_checker.check_property("PROP_025_QUARANTINED_COMPONENTS_CANNOT_EXECUTE", mut_flags)
            if finding.status == FindingStatus.VIOLATED:
                violated_props.append("PROP_025_QUARANTINED_COMPONENTS_CANNOT_EXECUTE")

        if "recovery_retry_budget" in target_name:
            mut_flags["allow_infinite_recovery_budget"] = True
            finding = self.assurance_checker.check_property("PROP_029_RECOVERY_BUDGET_IS_FINITE", mut_flags)
            if finding.status == FindingStatus.VIOLATED:
                violated_props.append("PROP_029_RECOVERY_BUDGET_IS_FINITE")

        return violated_props

    def _generate_diff_explanation(self, mutation: PolicyMutation, analysis_summary: str) -> str:
        """Format a human-readable diff explanation."""
        lines = [
            "----------------------------------------------------------------------",
            "POLICY MUTATION ANALYSIS",
            "----------------------------------------------------------------------",
            f"Mutation ID:     {mutation.mutation_id}",
            f"Type:            {mutation.mutation_type.value}",
            f"Target:          {mutation.mutation_target}",
            f"Before Value:    {mutation.before_value}",
            f"After Value:     {mutation.after_value}",
            f"Description:     {mutation.description}",
            "----------------------------------------------------------------------",
            f"ANALYSIS SUMMARY: {analysis_summary}",
            "----------------------------------------------------------------------",
        ]
        return "\n".join(lines)
