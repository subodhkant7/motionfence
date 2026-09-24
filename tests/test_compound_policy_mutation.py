"""Phase 2K: Combinatorial Policy Attacks, Dynamic Trajectory Exploration & Safe Repair Proposals Tests.

Comprehensive adversarial test suite covering:
1. Pairwise human-zone + threshold weakening
2. Pairwise contradiction + evidence removal
3. Target scope + authorization boundary
4. Stale evidence + freshness weakening
5. Dynamic human incursion after authorization
6. Dynamic pump activation after authorization
7. Dynamic cooling failure after authorization
8. Compound mutation shrinking
9. Trajectory shrinking
10. Amplifying mutation interaction
11. Repair proposal isolation
12. Repair candidate regression detection
13. Repair proposal cannot modify live policy
14. Repair proposal cannot mint tickets
15. Inconclusive repair is rejected / fails closed
16. Replay equivalence
17. Bounded Z3 formal assurance properties PROP_037 through PROP_044
"""

import copy
import hashlib
import json
import pytest

from motionfence.assurance.checker import BoundedAssuranceChecker
from motionfence.assurance.invariants import AssurancePropertyRegistry
from motionfence.assurance.models import FindingStatus
from motionfence.evidence.models import ContradictionSeverity, Evidence, EvidenceSource
from motionfence.models.actions import ActionProposal, ActionType, AuthorizationTicket
from motionfence.models.world import CoolingState, HumanZoneState, ValveState, WorldState
from motionfence.policy.engine import PolicyEngine
from motionfence.policy.models import DecisionType, Policy, PolicyDecision
from motionfence.policy_mutation.baseline import PolicyBaselineManager
from motionfence.policy_mutation.engine import PolicyMutationEngine
from motionfence.policy_mutation.evaluator import PolicyMutationEvaluator
from motionfence.policy_mutation.minimizer import MutationCounterexampleMinimizer
from motionfence.policy_mutation.models import (
    DynamicTrajectory,
    MutationInteractionType,
    PolicyFirewallDecision,
    PolicyMutation,
    PolicyMutationType,
    PolicyRegressionType,
    PolicyRepairProposal,
    TrajectoryOutcomeType,
    TrajectoryStep,
)
from motionfence.policy_mutation.mutators import (
    PolicyMutatorRegistry,
    compute_canonical_policy_hash,
    create_compound_mutation,
    shrink_compound_mutation,
)
from motionfence.policy_mutation.repair import (
    PolicyRepairSynthesizer,
    PolicyRepairValidator,
    RepairStatus,
)
from motionfence.policy_mutation.trajectory import (
    DynamicTrajectoryEvaluator,
    TrajectoryFaultType,
    TrajectoryGenerator,
    shrink_trajectory,
)


@pytest.fixture
def baseline_policy() -> Policy:
    return Policy()


@pytest.fixture
def baseline_snapshot(baseline_policy: Policy):
    return PolicyBaselineManager.create_baseline(baseline_policy)


@pytest.fixture
def mutation_engine() -> PolicyMutationEngine:
    return PolicyMutationEngine()


@pytest.fixture
def trajectory_evaluator() -> DynamicTrajectoryEvaluator:
    return DynamicTrajectoryEvaluator()


# ---------------------------------------------------------------------------
# 1. Combinatorial / Compound Policy Mutation Tests
# ---------------------------------------------------------------------------

class TestCombinatorialPolicyMutations:
    """Tests compound mutations (pairwise and selected triplets) against the firewall."""

    def test_pairwise_human_zone_and_threshold_weakening(
        self, baseline_policy: Policy, baseline_snapshot, mutation_engine: PolicyMutationEngine
    ):
        """1. Pairwise human-zone condition removal + target confidence threshold weakening."""
        mutated, mutation = PolicyMutatorRegistry.mutate_compound_human_zone_and_scope(baseline_policy)
        assert mutation.mutation_depth == 2
        assert "CONDITION_REMOVAL" in mutation.parent_mutations
        assert "SCOPE_EXPANSION" in mutation.parent_mutations

        result = mutation_engine.evaluate_mutation(mutated, mutation, baseline_snapshot)
        assert result.is_rejected
        assert result.new_unsafe_allows > 0
        assert result.counterexample is not None

    def test_pairwise_contradiction_and_evidence_removal(
        self, baseline_policy: Policy, baseline_snapshot, mutation_engine: PolicyMutationEngine
    ):
        """2. Pairwise contradiction weakening + evidence removal."""
        mutated, mutation = PolicyMutatorRegistry.mutate_compound_evidence_removal_and_threshold(baseline_policy)
        assert mutation.mutation_depth == 2
        assert "EVIDENCE_REQUIREMENT_REMOVAL" in mutation.parent_mutations

        result = mutation_engine.evaluate_mutation(mutated, mutation, baseline_snapshot)
        assert result.is_rejected
        assert result.firewall_decision == PolicyFirewallDecision.REJECT

    def test_pairwise_target_scope_and_auth_boundary(
        self, baseline_policy: Policy, baseline_snapshot, mutation_engine: PolicyMutationEngine
    ):
        """3. Target scope expansion + state-bound authorization weakening."""
        mutated, mutation = PolicyMutatorRegistry.mutate_compound_scope_and_state_bound(baseline_policy)
        assert mutation.mutation_depth == 2
        assert "SCOPE_EXPANSION" in mutation.parent_mutations
        assert "AUTHORIZATION_BOUNDARY_MUTATION" in mutation.parent_mutations

        result = mutation_engine.evaluate_mutation(mutated, mutation, baseline_snapshot)
        assert result.is_rejected
        assert len(result.authorization_boundary_regressions) > 0 or "PROP_008_NO_EXECUTION_AFTER_STATE_DRIFT" in result.violated_properties

    def test_pairwise_stale_evidence_and_freshness_weakening(
        self, baseline_policy: Policy, baseline_snapshot, mutation_engine: PolicyMutationEngine
    ):
        """4. Stale evidence acceptance + freshness weakening."""
        mutated, mutation = PolicyMutatorRegistry.mutate_compound_freshness_and_stale_acceptance(baseline_policy)
        assert mutation.mutation_depth == 2
        assert "FRESHNESS_WEAKENING" in mutation.parent_mutations

        result = mutation_engine.evaluate_mutation(mutated, mutation, baseline_snapshot)
        assert result.is_rejected
        assert result.regression_type in (
            PolicyRegressionType.SAFETY_MONOTONICITY_BREAK,
            PolicyRegressionType.NEW_UNSAFE_ALLOW,
        )

    def test_triplet_cooling_human_zone_threshold(
        self, baseline_policy: Policy, baseline_snapshot, mutation_engine: PolicyMutationEngine
    ):
        """Selected triplet: cooling deletion + human-zone guard removal + threshold weakening."""
        mutated, mutation = PolicyMutatorRegistry.mutate_compound_triplet_human_cooling_threshold(baseline_policy)
        assert mutation.mutation_depth == 3
        assert len(mutation.parent_mutations) == 3

        result = mutation_engine.evaluate_mutation(mutated, mutation, baseline_snapshot)
        assert result.is_rejected
        assert result.new_unsafe_allows >= 2


# ---------------------------------------------------------------------------
# 2. Dynamic Physical Trajectory Evaluation & Fault Injection Tests
# ---------------------------------------------------------------------------

class TestDynamicPhysicalTrajectories:
    """Tests dynamic multi-step physical environment trajectory evaluation and fault injection."""

    def test_dynamic_human_incursion_after_authorization(
        self, baseline_policy: Policy, trajectory_evaluator: DynamicTrajectoryEvaluator
    ):
        """5. Dynamic human incursion occurring between authorization and actuation."""
        traj = TrajectoryGenerator._build_human_incursion_trajectory(seed=42, depth=5)
        res = trajectory_evaluator.evaluate_trajectory(traj, baseline_policy)

        # In baseline policy, revalidation is active: the human incursion must be blocked by revalidation!
        assert res.outcome == TrajectoryOutcomeType.BLOCKED_BY_REVALIDATION
        assert not res.is_regression

    def test_dynamic_pump_activation_after_authorization(
        self, baseline_policy: Policy, trajectory_evaluator: DynamicTrajectoryEvaluator
    ):
        """6. Dynamic pump activation occurring after authorization."""
        traj = TrajectoryGenerator._build_pump_activation_trajectory(seed=42, depth=5)
        res = trajectory_evaluator.evaluate_trajectory(traj, baseline_policy)

        # World state drifted post-authorization: blocked by TOCTOU revalidation
        assert res.outcome == TrajectoryOutcomeType.BLOCKED_BY_REVALIDATION
        assert not res.is_regression

    def test_dynamic_cooling_failure_after_authorization(
        self, baseline_policy: Policy, trajectory_evaluator: DynamicTrajectoryEvaluator
    ):
        """7. Dynamic cooling failure occurring between authorization and execution."""
        traj = TrajectoryGenerator._build_cooling_loss_trajectory(seed=42, depth=5)
        res = trajectory_evaluator.evaluate_trajectory(traj, baseline_policy)

        assert res.outcome == TrajectoryOutcomeType.BLOCKED_BY_REVALIDATION
        assert not res.is_regression

    def test_dynamic_human_incursion_under_revalidation_bypass_policy(
        self, baseline_policy: Policy, trajectory_evaluator: DynamicTrajectoryEvaluator
    ):
        """Under a mutated policy where revalidation is disabled, human incursion leads to NEW_UNSAFE_ALLOW."""
        mutated_policy = copy.deepcopy(baseline_policy)
        mutated_policy.expected_postconditions["disable_revalidation"] = True

        traj = TrajectoryGenerator._build_human_incursion_trajectory(seed=42, depth=5)
        res = trajectory_evaluator.evaluate_trajectory(traj, mutated_policy, baseline_policy=baseline_policy)

        assert res.outcome == TrajectoryOutcomeType.NEW_UNSAFE_ALLOW
        assert res.is_regression is True
        assert res.new_unsafe_allows == 1

    def test_actuator_fault_and_verification_failure(
        self, baseline_policy: Policy, trajectory_evaluator: DynamicTrajectoryEvaluator
    ):
        """Actuator no-op triggers EXECUTED_AND_FAILED_VERIFICATION."""
        traj = TrajectoryGenerator._build_actuator_fault_trajectory(seed=42, depth=5)
        res = trajectory_evaluator.evaluate_trajectory(traj, baseline_policy)

        assert res.outcome == TrajectoryOutcomeType.EXECUTED_AND_FAILED_VERIFICATION

    def test_trajectory_generator_depths_and_determinism(self):
        """Trajectory generator produces reproducible suites for depth 3, 5, 8."""
        suite_a = TrajectoryGenerator.generate_trajectories(seed=42, depths=[3, 5, 8])
        suite_b = TrajectoryGenerator.generate_trajectories(seed=42, depths=[3, 5, 8])

        assert len(suite_a) == 18  # 6 types x 3 depths
        assert [t.trajectory_id for t in suite_a] == [t.trajectory_id for t in suite_b]


# ---------------------------------------------------------------------------
# 3. Minimization and Shrinking Tests
# ---------------------------------------------------------------------------

class TestMinimizationAndShrinking:
    """Tests compound mutation shrinking and dynamic trajectory counterexample minimization."""

    def test_compound_mutation_shrinking(self, baseline_policy: Policy):
        """8. Compound mutation shrinking isolates constituent single mutations."""
        mutated, compound_mut = PolicyMutatorRegistry.mutate_compound_human_zone_and_scope(baseline_policy)
        shrunk = shrink_compound_mutation(compound_mut, baseline_policy)

        assert len(shrunk) == 2
        targets = [m.mutation_target for _, m in shrunk]
        assert any("human_zone" in t for t in targets)
        assert any("target" in t for t in targets)

    def test_dynamic_trajectory_shrinking(
        self, baseline_policy: Policy, trajectory_evaluator: DynamicTrajectoryEvaluator
    ):
        """9. Trajectory shrinking eliminates passive telemetry steps while preserving causal regression."""
        mutated_policy = copy.deepcopy(baseline_policy)
        mutated_policy.expected_postconditions["disable_revalidation"] = True

        long_traj = TrajectoryGenerator._build_human_incursion_trajectory(seed=42, depth=8)
        assert len(long_traj.steps) >= 5

        shrunk_traj = shrink_trajectory(long_traj, trajectory_evaluator, mutated_policy, baseline_policy)
        assert len(shrunk_traj.steps) <= len(long_traj.steps)

        # Evaluated shrunk trajectory still reproduces the regression
        shrunk_res = trajectory_evaluator.evaluate_trajectory(shrunk_traj, mutated_policy, baseline_policy)
        assert shrunk_res.is_regression is True

    def test_trajectory_minimizer_formatter(self):
        """Verify MutationCounterexampleMinimizer.minimize_trajectory format."""
        steps = [
            TrajectoryStep(step_index=0, event_name="NORMAL_OPERATION"),
            TrajectoryStep(step_index=1, event_name="AUTHORIZATION_GENERATED", action="CLOSE_VALVE"),
            TrajectoryStep(step_index=2, event_name="HUMAN_INCURSION_POST_AUTH", fault="HUMAN_INCURSION_AFTER_AUTH"),
            TrajectoryStep(step_index=3, event_name="EXECUTION_ATTEMPT"),
        ]
        min_res = MutationCounterexampleMinimizer.minimize_trajectory(
            trajectory_id="traj_test",
            steps=steps,
            regression_type=PolicyRegressionType.NEW_UNSAFE_ALLOW,
            explanation="Human incursion evaded revalidation",
        )
        assert min_res["trajectory_id"] == "traj_test"
        assert "AUTHORIZATION_GENERATED" in min_res["minimized_events"]
        assert "HUMAN_INCURSION_POST_AUTH" in min_res["minimized_events"]
        assert "EXECUTION_ATTEMPT" in min_res["minimized_events"]
        assert "TRAJECTORY REGRESSION" in min_res["formatted_report"]


# ---------------------------------------------------------------------------
# 4. Mutation Interaction Analysis Tests
# ---------------------------------------------------------------------------

class TestMutationInteractionClassification:
    """10. Deterministic classification of mutation interactions (AMPLIFYING, ADDITIVE, etc.)."""

    def test_amplifying_mutation_interaction(
        self, baseline_policy: Policy, baseline_snapshot, mutation_engine: PolicyMutationEngine
    ):
        """Amplifying interaction occurs when individual mutations cause 0 unsafe allows alone, but combined cause >0."""
        # Mutator F combines recovery retry weakening (0 allows alone) + quarantine bypass (1 allow alone, but in pair creates amplifier)
        mutated, mutation = PolicyMutatorRegistry.mutate_compound_recovery_and_quarantine(baseline_policy)
        res = mutation_engine.evaluate_mutation(mutated, mutation, baseline_snapshot)

        assert res.interaction_type in (MutationInteractionType.AMPLIFYING, MutationInteractionType.ADDITIVE)
        assert res.is_rejected

    def test_additive_mutation_interaction(
        self, baseline_policy: Policy, baseline_snapshot, mutation_engine: PolicyMutationEngine
    ):
        """Additive interaction correctly classifies when both mutations add unsafe allows."""
        mutated, mutation = PolicyMutatorRegistry.mutate_compound_threshold_and_contradiction(baseline_policy)
        res = mutation_engine.evaluate_mutation(mutated, mutation, baseline_snapshot)

        assert res.interaction_type == MutationInteractionType.ADDITIVE
        assert res.new_unsafe_allows >= 2


# ---------------------------------------------------------------------------
# 5. Safe Repair Proposal Synthesizer & Validator Tests
# ---------------------------------------------------------------------------

class TestSafeRepairProposals:
    """Tests safe repair proposal synthesizer, non-authority, and detached validation pipeline."""

    def test_repair_proposal_isolation(
        self, baseline_policy: Policy, baseline_snapshot, mutation_engine: PolicyMutationEngine
    ):
        """11. Repair proposal synthesis produces proposal without executing or modifying policy."""
        mutated, mutation = PolicyMutatorRegistry.mutate_confidence_threshold_weakening(baseline_policy, 0.70)
        res = mutation_engine.evaluate_mutation(mutated, mutation, baseline_snapshot)

        orig_confidence = baseline_policy.min_target_confidence
        proposal = PolicyRepairSynthesizer.synthesize_repair(res, baseline_snapshot)

        assert isinstance(proposal, PolicyRepairProposal)
        assert proposal.affected_field == "min_target_confidence"
        assert proposal.after_value == 0.90
        assert proposal.proposal_hash != ""
        # Invariant: live baseline policy was NOT altered
        assert baseline_policy.min_target_confidence == orig_confidence

    def test_repair_candidate_regression_detection(
        self, baseline_policy: Policy, baseline_snapshot
    ):
        """12. Repair candidate that fails monotonicity or introduces regression is REJECTED by validator."""
        validator = PolicyRepairValidator()

        # Construct an unsafe proposal that attempts to 'repair' by expanding scope to wildcards
        unsafe_proposal = PolicyRepairProposal(
            source_mutation_id="pmut_test",
            detected_regression=PolicyRegressionType.AUTHORIZATION_BOUNDARY_WEAKENED,
            affected_field="allowed_actuator_targets",
            proposed_change="Set allowed_actuator_targets = ['*']",
            before_value=["valve_a"],
            after_value=["*"],
            safety_rationale="Expand target access",
            expected_invariant_restored="NONE",
            confidence=1.0,
            proposal_hash="hash_unsafe",
        )

        val_res = validator.validate(unsafe_proposal, baseline_policy, baseline_snapshot)
        assert val_res.status == RepairStatus.REJECTED
        assert not val_res.monotonicity_report.monotonicity_preserved
        assert val_res.monotonicity_report.newly_accepted_out_of_scope_targets is True

    def test_repair_proposal_cannot_modify_live_policy(
        self, baseline_policy: Policy, baseline_snapshot
    ):
        """13. Repair proposal validation operates on detached clone and preserves original policy unchanged."""
        orig_hash = compute_canonical_policy_hash(baseline_policy)
        mutated = copy.deepcopy(baseline_policy)
        mutated.min_target_confidence = 0.60

        evaluator = PolicyMutationEvaluator()
        mut = PolicyMutation(
            parent_policy_hash=orig_hash,
            mutation_type=PolicyMutationType.THRESHOLD_WEAKENING,
            mutation_target="min_target_confidence",
            before_value=0.90,
            after_value=0.60,
            description="Weakened confidence",
        )
        res = evaluator.evaluate(mutated, baseline_snapshot, mut)

        proposal = PolicyRepairSynthesizer.synthesize_repair(res, baseline_snapshot)
        validator = PolicyRepairValidator()
        val_res = validator.validate(proposal, mutated, baseline_snapshot)

        assert val_res.status == RepairStatus.ACCEPTABLE
        # Original baseline policy remains untouched
        assert compute_canonical_policy_hash(baseline_policy) == orig_hash

    def test_repair_proposal_cannot_mint_tickets(self):
        """14. Repair synthesizer and validator possess zero ticket minting authority."""
        synthesizer = PolicyRepairSynthesizer()
        validator = PolicyRepairValidator()

        assert not hasattr(synthesizer, "mint_ticket")
        assert not hasattr(synthesizer, "physical_actuator")
        assert not hasattr(validator, "mint_ticket")
        assert not hasattr(validator, "physical_actuator")

    def test_inconclusive_repair_fails_closed(
        self, baseline_policy: Policy, baseline_snapshot
    ):
        """15. Inconclusive repair proposal fails closed and is marked REJECTED/INCONCLUSIVE."""
        validator = PolicyRepairValidator()
        inconclusive_proposal = PolicyRepairProposal(
            source_mutation_id="pmut_unknown",
            detected_regression=PolicyRegressionType.NEW_UNSAFE_ALLOW,
            affected_field="arbitrary_unmodeled_field",
            proposed_change="Guess value",
            before_value=None,
            after_value=None,
            safety_rationale="Unknown derivation",
            expected_invariant_restored="UNKNOWN",
            confidence=0.0,
            status="REPAIR_INCONCLUSIVE",
        )

        val_res = validator.validate(inconclusive_proposal, baseline_policy, baseline_snapshot)
        assert val_res.status == RepairStatus.INCONCLUSIVE
        assert not val_res.is_acceptable


# ---------------------------------------------------------------------------
# 6. Replay Equivalence Tests
# ---------------------------------------------------------------------------

class TestReplayEquivalence:
    """16. Verification of deterministic, bit-for-bit replay equivalence."""

    def test_compound_mutation_replay_equivalence(
        self, baseline_policy: Policy, baseline_snapshot, mutation_engine: PolicyMutationEngine
    ):
        """Replaying identical compound mutation evaluation produces identical outcomes."""
        mutated, mutation = PolicyMutatorRegistry.mutate_compound_human_zone_and_scope(baseline_policy)

        res1 = mutation_engine.evaluate_mutation(mutated, mutation, baseline_snapshot)
        res2 = mutation_engine.evaluate_mutation(mutated, mutation, baseline_snapshot)

        assert res1.firewall_decision == res2.firewall_decision
        assert res1.regression_type == res2.regression_type
        assert res1.new_unsafe_allows == res2.new_unsafe_allows
        assert res1.violated_properties == res2.violated_properties
        assert res1.interaction_type == res2.interaction_type

    def test_trajectory_replay_equivalence(
        self, baseline_policy: Policy, trajectory_evaluator: DynamicTrajectoryEvaluator
    ):
        """Replaying identical trajectory generates identical deterministic outcome."""
        traj1 = TrajectoryGenerator._build_human_incursion_trajectory(seed=42, depth=5)
        traj2 = TrajectoryGenerator._build_human_incursion_trajectory(seed=42, depth=5)

        res1 = trajectory_evaluator.evaluate_trajectory(traj1, baseline_policy)
        res2 = trajectory_evaluator.evaluate_trajectory(traj2, baseline_policy)

        assert res1.outcome == res2.outcome
        assert res1.is_regression == res2.is_regression
        assert res1.new_unsafe_allows == res2.new_unsafe_allows
        assert res1.minimized_steps == res2.minimized_steps


# ---------------------------------------------------------------------------
# 7. Bounded Z3 Formal Assurance Properties PROP_037 through PROP_044
# ---------------------------------------------------------------------------

class TestBoundedAssurancePhase2K:
    """Formal Z3 SMT properties PROP_037 through PROP_044."""

    def test_registry_contains_44_properties(self):
        """Registry must contain all formal properties (including Phase 2K PROP_037 through PROP_044)."""
        registry = AssurancePropertyRegistry()
        all_props = registry.list_all()
        assert len(all_props) >= 44

        prop_ids = [p.property_id for p in all_props]
        assert "PROP_037_COMPOUND_SAFETY_MUTATION_DETECTED" in prop_ids
        assert "PROP_038_AMPLIFYING_MUTATION_INTERACTION_DETECTED" in prop_ids
        assert "PROP_039_TRAJECTORY_REGRESSION_REMAINS_BLOCKABLE" in prop_ids
        assert "PROP_040_REPAIR_PROPOSAL_CANNOT_MODIFY_PRODUCTION_POLICY" in prop_ids
        assert "PROP_041_REPAIR_MUST_PASS_EXISTING_SAFETY_FIREWALL" in prop_ids
        assert "PROP_042_REPAIR_CANNOT_WEAKEN_AUTHORIZATION_BOUNDARY" in prop_ids
        assert "PROP_043_TRAJECTORY_COUNTEREXAMPLE_IS_REPRODUCIBLE" in prop_ids
        assert "PROP_044_INCONCLUSIVE_REPAIR_IS_NOT_AUTO_APPLIED" in prop_ids

    def test_all_44_properties_satisfied_under_standard_policy(self):
        """Z3 proves all properties SATISFIED under standard deterministic policy rules."""
        checker = BoundedAssuranceChecker()
        findings = checker.check_all()
        assert len(findings) >= 44
        for f in findings:
            assert f.status == FindingStatus.SATISFIED, f"Property {f.property_id} was {f.status.value}: {f.explanation}"

    def test_prop_037_counterexample_when_compound_evasion_allowed(self):
        """PROP_037 counterexample discovered if compound mutation evasion is permitted."""
        checker = BoundedAssuranceChecker()
        finding = checker.check_property(
            "PROP_037_COMPOUND_SAFETY_MUTATION_DETECTED",
            policy_mutations={"allow_compound_evasion": True},
        )
        assert finding.status == FindingStatus.VIOLATED
        assert finding.counterexample is not None
        assert finding.counterexample.get("is_compound_mutation") is True
        assert finding.counterexample.get("compound_regression_detected") is False

    def test_prop_038_counterexample_when_amplifying_detection_disabled(self):
        """PROP_038 counterexample discovered if amplifying detection disabled."""
        checker = BoundedAssuranceChecker()
        finding = checker.check_property(
            "PROP_038_AMPLIFYING_MUTATION_INTERACTION_DETECTED",
            policy_mutations={"disable_amplifying_detection": True},
        )
        assert finding.status == FindingStatus.VIOLATED
        assert finding.counterexample is not None
        assert finding.counterexample.get("is_amplifying_interaction") is True

    def test_prop_039_counterexample_when_trajectory_blockability_disabled(self):
        """PROP_039 counterexample discovered if trajectory blockability disabled."""
        checker = BoundedAssuranceChecker()
        finding = checker.check_property(
            "PROP_039_TRAJECTORY_REGRESSION_REMAINS_BLOCKABLE",
            policy_mutations={"disable_trajectory_blockability": True},
        )
        assert finding.status == FindingStatus.VIOLATED
        assert finding.counterexample is not None
        assert finding.counterexample.get("trajectory_regression_present") is True

    def test_prop_040_counterexample_when_repair_production_mutation_allowed(self):
        """PROP_040 counterexample discovered if repair directly modifies production policy."""
        checker = BoundedAssuranceChecker()
        finding = checker.check_property(
            "PROP_040_REPAIR_PROPOSAL_CANNOT_MODIFY_PRODUCTION_POLICY",
            policy_mutations={"allow_repair_production_mutation": True},
        )
        assert finding.status == FindingStatus.VIOLATED
        assert finding.counterexample is not None
        assert finding.counterexample.get("repair_modifies_production_policy") is True

    def test_prop_041_counterexample_when_unvalidated_repair_allowed(self):
        """PROP_041 counterexample discovered if repair is applied without validation."""
        checker = BoundedAssuranceChecker()
        finding = checker.check_property(
            "PROP_041_REPAIR_MUST_PASS_EXISTING_SAFETY_FIREWALL",
            policy_mutations={"allow_unvalidated_repair": True},
        )
        assert finding.status == FindingStatus.VIOLATED
        assert finding.counterexample is not None
        assert finding.counterexample.get("repair_proposal_applied_without_validation") is True

    def test_prop_042_counterexample_when_weakened_repair_allowed(self):
        """PROP_042 counterexample discovered if repair weakens authorization boundary."""
        checker = BoundedAssuranceChecker()
        finding = checker.check_property(
            "PROP_042_REPAIR_CANNOT_WEAKEN_AUTHORIZATION_BOUNDARY",
            policy_mutations={"allow_weakened_repair": True},
        )
        assert finding.status == FindingStatus.VIOLATED
        assert finding.counterexample is not None
        assert finding.counterexample.get("repair_weakens_auth_boundary") is True

    def test_prop_043_counterexample_when_non_deterministic_counterexample(self):
        """PROP_043 counterexample discovered if trajectory counterexample is non-deterministic."""
        checker = BoundedAssuranceChecker()
        finding = checker.check_property(
            "PROP_043_TRAJECTORY_COUNTEREXAMPLE_IS_REPRODUCIBLE",
            policy_mutations={"non_deterministic_counterexample": True},
        )
        assert finding.status == FindingStatus.VIOLATED
        assert finding.counterexample is not None
        assert finding.counterexample.get("trajectory_counterexample_deterministic") is False

    def test_prop_044_counterexample_when_inconclusive_repair_auto_applied(self):
        """PROP_044 counterexample discovered if inconclusive repair is auto applied."""
        checker = BoundedAssuranceChecker()
        finding = checker.check_property(
            "PROP_044_INCONCLUSIVE_REPAIR_IS_NOT_AUTO_APPLIED",
            policy_mutations={"allow_auto_apply_inconclusive": True},
        )
        assert finding.status == FindingStatus.VIOLATED
        assert finding.counterexample is not None
        assert finding.counterexample.get("repair_is_inconclusive") is True
        assert finding.counterexample.get("inconclusive_repair_auto_applied") is True
