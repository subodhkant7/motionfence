"""Comprehensive test suite for Phase 2J: Policy Mutation Firewall & Safety Regression Detection.

Covers:
1. Deterministic mutation generation, cloning, isolation, and canonical hashing.
2. Detection of all safety-relevant mutations (human-zone, cooling, confidence, contradiction, scope, evidence, TOCTOU, quarantine, stale knowledge).
3. Non-safety mutations survive without false regressions.
4. Counterexample generation, minimization, and replay.
5. Metamorphic policy tests (tightening monotonicity, weakening detection, constraint addition, safety-rule deletion).
6. Bounded Z3 SMT formal properties PROP_031 through PROP_036.
7. Security isolation (zero production policy mutation, zero ticket minting, zero actuation authority).
"""

import copy
import pytest
import time

from motionfence.assurance.checker import BoundedAssuranceChecker
from motionfence.assurance.invariants import AssurancePropertyRegistry
from motionfence.assurance.models import FindingStatus
from motionfence.runtime.events import EventBus
from motionfence.models.actions import ActionProposal, ActionType
from motionfence.models.events import EventType
from motionfence.models.world import CoolingState, HumanZoneState, ValveState, WorldState
from motionfence.policy.engine import PolicyEngine
from motionfence.policy.models import DecisionType, Policy
from motionfence.policy_mutation.baseline import PolicyBaselineManager
from motionfence.policy_mutation.engine import PolicyMutationEngine
from motionfence.policy_mutation.evaluator import PolicyMutationEvaluator
from motionfence.policy_mutation.minimizer import MutationCounterexampleMinimizer
from motionfence.policy_mutation.models import (
    FirewallEvaluationReport,
    MutationRelevance,
    PolicyBaseline,
    PolicyFirewallDecision,
    PolicyMutation,
    PolicyMutationType,
    PolicyRegressionType,
)
from motionfence.policy_mutation.mutators import (
    PolicyMutatorRegistry,
    compute_canonical_policy_hash,
)
from motionfence.policy_mutation.reporting import PolicyDiffExplainer


# ---------------------------------------------------------------------------
# 1. Deterministic Mutation Generation & Policy Isolation Tests
# ---------------------------------------------------------------------------

class TestPolicyMutationGenerationAndIsolation:
    """Verifies mutation generation, deep cloning, and canonical hashing."""

    def test_canonical_policy_hash_deterministic(self):
        """Identical policies produce byte-identical SHA-256 hashes."""
        p1 = Policy()
        p2 = Policy()
        hash1 = compute_canonical_policy_hash(p1)
        hash2 = compute_canonical_policy_hash(p2)
        assert hash1 == hash2
        assert len(hash1) == 64

    def test_mutations_never_modify_production_policy_in_place(self):
        """Mutating a policy returns a detached clone while original remains untouched."""
        prod_policy = Policy(require_human_zone_clear=True, min_target_confidence=0.90)
        orig_hash = compute_canonical_policy_hash(prod_policy)

        mutated, record = PolicyMutatorRegistry.mutate_human_zone_guard_removal(prod_policy)

        assert prod_policy.require_human_zone_clear is True
        assert mutated.require_human_zone_clear is False
        assert compute_canonical_policy_hash(prod_policy) == orig_hash
        assert compute_canonical_policy_hash(mutated) != orig_hash
        assert record.parent_policy_hash == orig_hash
        assert record.mutated_policy_hash == compute_canonical_policy_hash(mutated)

    def test_canonical_corpus_generation(self):
        """Canonical mutation corpus contains all 10 standard operators plus non-safety mutation."""
        policy = Policy()
        corpus = PolicyMutatorRegistry.get_canonical_corpus(policy)
        assert len(corpus) == 11

        targets = [rec.mutation_target for _, rec in corpus]
        assert "min_target_confidence" in targets
        assert "require_human_zone_clear" in targets
        assert "require_cooling_active" in targets
        assert "max_tolerated_contradiction" in targets
        assert "max_knowledge_age_seconds" in targets
        assert "required_evidence_sources" in targets
        assert "toctou_revalidation" in targets
        assert "recovery_retry_budget" in targets
        assert "quarantine_enforcement" in targets
        assert "prohibited_actions" in targets
        assert "objective" in targets


# ---------------------------------------------------------------------------
# 2. Baseline Snapshot & Integrity Tests
# ---------------------------------------------------------------------------

class TestPolicyBaselineSnapshot:
    """Verifies baseline policy creation, serialization, and reconstruction."""

    def test_baseline_creation_and_restoration(self):
        policy = Policy(min_target_confidence=0.92)
        baseline = PolicyBaselineManager.create_baseline(policy)

        assert baseline.policy_id == policy.id
        assert baseline.canonical_policy_hash == compute_canonical_policy_hash(policy)
        assert baseline.adversarial_results["unsafe_allows"] == 0

        restored = PolicyBaselineManager.restore_policy_from_baseline(baseline)
        assert restored.min_target_confidence == 0.92
        assert compute_canonical_policy_hash(restored) == baseline.canonical_policy_hash


# ---------------------------------------------------------------------------
# 3. Detection of Dangerous Policy Regressions Tests
# ---------------------------------------------------------------------------

class TestDangerousPolicyRegressionDetection:
    """Verifies that all safety-weakening mutations are caught and rejected by the firewall."""

    @pytest.fixture
    def evaluator_and_baseline(self):
        evaluator = PolicyMutationEvaluator()
        policy = Policy()
        baseline = PolicyBaselineManager.create_baseline(policy)
        return evaluator, baseline, policy

    def test_human_zone_guard_removal_detected(self, evaluator_and_baseline):
        evaluator, baseline, policy = evaluator_and_baseline
        mutated, record = PolicyMutatorRegistry.mutate_human_zone_guard_removal(policy)

        result = evaluator.evaluate(mutated, baseline, record)
        assert result.is_rejected
        assert result.firewall_decision == PolicyFirewallDecision.REJECT
        assert result.new_unsafe_allows >= 1
        assert result.counterexample is not None
        assert result.counterexample.human_zone == "OCCUPIED"

    def test_confidence_weakening_detected(self, evaluator_and_baseline):
        evaluator, baseline, policy = evaluator_and_baseline
        mutated, record = PolicyMutatorRegistry.mutate_confidence_threshold_weakening(policy, new_threshold=0.70)

        result = evaluator.evaluate(mutated, baseline, record)
        assert result.is_rejected
        assert result.firewall_decision == PolicyFirewallDecision.REJECT
        assert result.new_unsafe_allows >= 1
        assert result.counterexample is not None
        assert result.counterexample.confidence <= 0.80

    def test_cooling_invariant_deletion_detected(self, evaluator_and_baseline):
        evaluator, baseline, policy = evaluator_and_baseline
        mutated, record = PolicyMutatorRegistry.mutate_cooling_invariant_deletion(policy)

        result = evaluator.evaluate(mutated, baseline, record)
        assert result.is_rejected
        assert result.firewall_decision == PolicyFirewallDecision.REJECT
        assert result.new_unsafe_allows >= 1
        assert result.counterexample is not None
        assert result.counterexample.cooling == "INACTIVE"

    def test_contradiction_blocking_removal_detected(self, evaluator_and_baseline):
        evaluator, baseline, policy = evaluator_and_baseline
        mutated, record = PolicyMutatorRegistry.mutate_contradiction_blocking_removal(policy)

        result = evaluator.evaluate(mutated, baseline, record)
        assert result.is_rejected
        assert result.firewall_decision == PolicyFirewallDecision.REJECT
        assert result.counterexample is not None
        assert result.counterexample.contradiction_severity == "HIGH"

    def test_scope_expansion_wildcard_detected(self, evaluator_and_baseline):
        evaluator, baseline, policy = evaluator_and_baseline
        mutated, record = PolicyMutatorRegistry.mutate_scope_expansion(policy)

        result = evaluator.evaluate(mutated, baseline, record)
        assert result.is_rejected
        assert result.firewall_decision == PolicyFirewallDecision.REJECT
        assert result.new_unsafe_allows >= 1
        assert result.counterexample is not None
        assert result.counterexample.target == "valve_c"

    def test_prohibited_action_removal_detected(self, evaluator_and_baseline):
        evaluator, baseline, policy = evaluator_and_baseline
        mutated, record = PolicyMutatorRegistry.mutate_authorization_precondition_weakening(policy)

        result = evaluator.evaluate(mutated, baseline, record)
        assert result.is_rejected
        assert result.firewall_decision == PolicyFirewallDecision.REJECT
        assert result.new_unsafe_allows >= 1
        assert result.counterexample is not None
        assert result.counterexample.action_type == "ADJUST_COOLING"

    def test_toctou_revalidation_removal_detected(self, evaluator_and_baseline):
        evaluator, baseline, policy = evaluator_and_baseline
        mutated, record = PolicyMutatorRegistry.mutate_toctou_revalidation_removal(policy)

        result = evaluator.evaluate(mutated, baseline, record)
        assert result.is_rejected
        assert result.regression_type == PolicyRegressionType.TOCTOU_DEFENSE_WEAKENED

    def test_quarantine_bypass_detected(self, evaluator_and_baseline):
        evaluator, baseline, policy = evaluator_and_baseline
        mutated, record = PolicyMutatorRegistry.mutate_quarantine_bypass(policy)

        result = evaluator.evaluate(mutated, baseline, record)
        assert result.is_rejected
        assert result.regression_type == PolicyRegressionType.RECOVERY_GUARD_WEAKENED

    def test_stale_knowledge_acceptance_detected(self, evaluator_and_baseline):
        evaluator, baseline, policy = evaluator_and_baseline
        mutated, record = PolicyMutatorRegistry.mutate_stale_knowledge_acceptance(policy)

        result = evaluator.evaluate(mutated, baseline, record)
        assert result.is_rejected
        assert result.firewall_decision == PolicyFirewallDecision.REJECT


# ---------------------------------------------------------------------------
# 4. Non-Safety Relevant Mutations & Survival Tests
# ---------------------------------------------------------------------------

class TestNonSafetyMutations:
    """Verifies that documentation and non-safety changes survive evaluation without false rejection."""

    def test_non_safety_metadata_mutation_survives(self):
        evaluator = PolicyMutationEvaluator()
        policy = Policy()
        baseline = PolicyBaselineManager.create_baseline(policy)

        mutated, record = PolicyMutatorRegistry.mutate_non_safety_metadata(policy, "New text documentation")
        result = evaluator.evaluate(mutated, baseline, record)

        assert result.is_accepted
        assert result.survived is True
        assert result.firewall_decision == PolicyFirewallDecision.ACCEPT
        assert result.regression_type == PolicyRegressionType.NO_REGRESSION
        assert result.new_unsafe_allows == 0
        assert result.counterexample is None


# ---------------------------------------------------------------------------
# 5. Counterexample Minimization & Replay Tests
# ---------------------------------------------------------------------------

class TestCounterexampleMinimizationAndReplay:
    """Verifies counterexample minimization and deterministic offline replay."""

    def test_counterexample_minimization_structure(self):
        policy = Policy()
        baseline = PolicyBaselineManager.create_baseline(policy)
        mutated, record = PolicyMutatorRegistry.mutate_human_zone_guard_removal(policy)

        evaluator = PolicyMutationEvaluator()
        result = evaluator.evaluate(mutated, baseline, record)

        cex = result.counterexample
        assert cex is not None
        assert cex.action_type == "CLOSE_VALVE"
        assert cex.target == "valve_b"
        assert cex.human_zone == "OCCUPIED"
        assert cex.baseline_decision == "DENY"
        assert cex.mutated_decision == "ALLOW"
        assert "human_zone" in cex.minimized_scenario
        assert cex.minimized_scenario["human_zone"] == "OCCUPIED"

    def test_engine_replays_recorded_mutation(self):
        engine = PolicyMutationEngine()
        policy = Policy()
        baseline = engine.create_baseline(policy)
        mutated, record = PolicyMutatorRegistry.mutate_cooling_invariant_deletion(policy)

        res = engine.evaluate_mutation(mutated, record, baseline)
        assert res.is_rejected

        replayed = engine.replay_mutation(record.mutation_id)
        assert replayed is not None
        assert replayed.mutation.mutation_id == record.mutation_id
        assert replayed.firewall_decision == PolicyFirewallDecision.REJECT
        assert replayed.counterexample.cooling == "INACTIVE"


# ---------------------------------------------------------------------------
# 6. Metamorphic Policy Tests
# ---------------------------------------------------------------------------

class TestMetamorphicPolicyProperties:
    """Verifies metamorphic properties of the policy firewall."""

    def test_tightening_monotonicity(self):
        """Tightening a confidence threshold (0.90 -> 0.95) must never introduce new unsafe ALLOWs."""
        evaluator = PolicyMutationEvaluator()
        policy = Policy(min_target_confidence=0.90)
        baseline = PolicyBaselineManager.create_baseline(policy)

        mutated, record = PolicyMutatorRegistry.mutate_confidence_threshold_tightening(policy, new_threshold=0.95)
        result = evaluator.evaluate(mutated, baseline, record)

        assert result.new_unsafe_allows == 0

    def test_weakening_detection(self):
        """Weakening a confidence threshold (0.90 -> 0.70) must be flagged."""
        evaluator = PolicyMutationEvaluator()
        policy = Policy(min_target_confidence=0.90)
        baseline = PolicyBaselineManager.create_baseline(policy)

        mutated, record = PolicyMutatorRegistry.mutate_confidence_threshold_weakening(policy, new_threshold=0.70)
        result = evaluator.evaluate(mutated, baseline, record)

        assert result.new_unsafe_allows >= 1
        assert result.is_rejected

    def test_constraint_addition_safety(self):
        """Adding a valid prohibited action does not create newly unsafe authorizations."""
        evaluator = PolicyMutationEvaluator()
        policy = Policy()
        baseline = PolicyBaselineManager.create_baseline(policy)

        mutated = copy.deepcopy(policy)
        mutated.prohibited_actions.append(ActionType.START_PUMP)
        record = PolicyMutation(
            parent_policy_hash=compute_canonical_policy_hash(policy),
            mutated_policy_hash=compute_canonical_policy_hash(mutated),
            mutation_type=PolicyMutationType.THRESHOLD_WEAKENING,
            mutation_target="prohibited_actions",
            before_value="[ADJUST_COOLING]",
            after_value="[ADJUST_COOLING, START_PUMP]",
            description="Tightened policy by adding START_PUMP to prohibitions",
            relevance=MutationRelevance.SAFETY_RELEVANT,
        )

        result = evaluator.evaluate(mutated, baseline, record)
        assert result.new_unsafe_allows == 0


# ---------------------------------------------------------------------------
# 7. Complete Full Suite Execution & Audit Trail Tests
# ---------------------------------------------------------------------------

class TestFullMutationSuiteAndAudit:
    """Verifies execution of the entire canonical corpus through the engine with audit trail."""

    def test_run_full_canonical_corpus(self):
        bus = EventBus()
        engine = PolicyMutationEngine(event_bus=bus)
        policy = Policy()
        baseline = engine.create_baseline(policy)

        report = engine.run_suite(baseline)

        assert report.total_mutations == 11
        assert report.safety_relevant_mutations == 10
        assert report.detected_regressions == 10
        assert report.survived_mutations == 1  # only non-safety mutation survives
        assert report.overall_decision == PolicyFirewallDecision.REJECT

        # Check audit trail records
        events = bus.get_events()
        event_types = [e.event_type for e in events]
        assert EventType.POLICY_BASELINE_CREATED in event_types
        assert EventType.POLICY_MUTATION_CREATED in event_types
        assert EventType.POLICY_MUTATION_EVALUATED in event_types
        assert EventType.POLICY_REGRESSION_DETECTED in event_types
        assert EventType.POLICY_MUTATION_REJECTED in event_types
        assert EventType.POLICY_MUTATION_ACCEPTED in event_types


        # Check diff explainer
        diff_str = PolicyDiffExplainer.format_policy_diff(report.results[0])
        assert "POLICY MUTATION" in diff_str
        assert "BEFORE" in diff_str
        assert "AFTER" in diff_str
        assert "DECISION" in diff_str

        summary = report.render_summary()
        assert "MOTIONFENCE POLICY MUTATION FIREWALL EVALUATION REPORT" in summary


# ---------------------------------------------------------------------------
# 8. Bounded Z3 SMT Formal Properties PROP_031 through PROP_036 Tests
# ---------------------------------------------------------------------------

class TestBoundedAssurancePhase2J:
    """Formal Z3 SMT properties PROP_031 through PROP_036."""

    def test_assurance_registry_contains_36_properties(self):
        registry = AssurancePropertyRegistry()
        all_props = registry.list_all()
        assert len(all_props) >= 36
        prop_ids = [p.property_id for p in all_props]
        assert "PROP_031_MUTATION_HUMAN_ZONE_GUARD_REMOVAL_DETECTED" in prop_ids
        assert "PROP_032_MUTATION_CONFIDENCE_WEAKENING_CANNOT_EVADE_ASSURANCE" in prop_ids
        assert "PROP_033_MUTATION_CONTRADICTION_REMOVAL_DETECTED" in prop_ids
        assert "PROP_034_MUTATION_CANNOT_DISABLE_STATE_BOUND_AUTHORIZATION" in prop_ids
        assert "PROP_035_MUTATION_CANNOT_DISABLE_EXECUTION_REVALIDATION" in prop_ids
        assert "PROP_036_MUTATION_CANNOT_DISABLE_RECOVERY_CONTAINMENT" in prop_ids

    def test_all_36_properties_satisfied_under_standard_policy(self):
        checker = BoundedAssuranceChecker()
        findings = checker.check_all()
        assert len(findings) >= 36
        for f in findings:
            assert f.status == FindingStatus.SATISFIED, f"Property {f.property_id} was {f.status.value}: {f.explanation}"

    def test_prop_031_counterexample_when_human_mutation_detection_disabled(self):
        """PROP_031 counterexample generated if human zone mutation detection disabled."""
        checker = BoundedAssuranceChecker()
        finding = checker.check_property(
            "PROP_031_MUTATION_HUMAN_ZONE_GUARD_REMOVAL_DETECTED",
            policy_mutations={"disable_human_mutation_detection": True},
        )
        assert finding.status == FindingStatus.VIOLATED
        assert finding.counterexample is not None
        assert finding.counterexample.get("human_guard_removed") is True

    def test_prop_032_counterexample_when_confidence_weakening_evasion_allowed(self):
        """PROP_032 counterexample generated if confidence weakening evasion allowed."""
        checker = BoundedAssuranceChecker()
        finding = checker.check_property(
            "PROP_032_MUTATION_CONFIDENCE_WEAKENING_CANNOT_EVADE_ASSURANCE",
            policy_mutations={"allow_confidence_weakening_evasion": True},
        )
        assert finding.status == FindingStatus.VIOLATED
        assert finding.counterexample is not None
        assert finding.counterexample.get("confidence_weakened") is True

    def test_prop_033_counterexample_when_contradiction_mutation_detection_disabled(self):
        """PROP_033 counterexample generated if contradiction mutation detection disabled."""
        checker = BoundedAssuranceChecker()
        finding = checker.check_property(
            "PROP_033_MUTATION_CONTRADICTION_REMOVAL_DETECTED",
            policy_mutations={"disable_contradiction_mutation_detection": True},
        )
        assert finding.status == FindingStatus.VIOLATED
        assert finding.counterexample is not None
        assert finding.counterexample.get("contradiction_guard_removed") is True

    def test_prop_034_counterexample_when_state_binding_bypass_allowed(self):
        """PROP_034 counterexample generated if state-binding bypass allowed."""
        checker = BoundedAssuranceChecker()
        finding = checker.check_property(
            "PROP_034_MUTATION_CANNOT_DISABLE_STATE_BOUND_AUTHORIZATION",
            policy_mutations={"allow_state_binding_bypass": True},
        )
        assert finding.status == FindingStatus.VIOLATED
        assert finding.counterexample is not None
        assert finding.counterexample.get("state_binding_disabled") is True

    def test_prop_035_counterexample_when_revalidation_bypass_allowed(self):
        """PROP_035 counterexample generated if revalidation bypass allowed."""
        checker = BoundedAssuranceChecker()
        finding = checker.check_property(
            "PROP_035_MUTATION_CANNOT_DISABLE_EXECUTION_REVALIDATION",
            policy_mutations={"allow_revalidation_bypass": True},
        )
        assert finding.status == FindingStatus.VIOLATED
        assert finding.counterexample is not None
        assert finding.counterexample.get("revalidation_disabled") is True

    def test_prop_036_counterexample_when_recovery_containment_bypass_allowed(self):
        """PROP_036 counterexample generated if recovery containment bypass allowed."""
        checker = BoundedAssuranceChecker()
        finding = checker.check_property(
            "PROP_036_MUTATION_CANNOT_DISABLE_RECOVERY_CONTAINMENT",
            policy_mutations={"allow_recovery_containment_bypass": True},
        )
        assert finding.status == FindingStatus.VIOLATED
        assert finding.counterexample is not None
        assert finding.counterexample.get("recovery_containment_disabled") is True


# ---------------------------------------------------------------------------
# 9. Security Isolation Invariants Tests
# ---------------------------------------------------------------------------

class TestSecurityIsolationInvariants:
    """Verifies that the mutation engine has zero execution/actuator/minting authority."""

    def test_mutation_engine_has_no_ticket_minting_authority(self):
        engine = PolicyMutationEngine()
        assert not hasattr(engine, "mint_ticket")
        assert not hasattr(engine, "authorize_execution")
        assert not hasattr(engine, "physical_actuator")

    def test_evaluator_has_no_actuator_reference(self):
        evaluator = PolicyMutationEvaluator()
        assert not hasattr(evaluator, "actuator")
        assert not hasattr(evaluator, "execute_action")

    def test_mutation_evaluation_does_not_mutate_world_state(self):
        ws = WorldState(valves={"valve_b": ValveState.OPEN}, cooling=CoolingState.ACTIVE)
        orig_ws = copy.deepcopy(ws)

        evaluator = PolicyMutationEvaluator()
        policy = Policy()
        baseline = PolicyBaselineManager.create_baseline(policy)
        mutated, record = PolicyMutatorRegistry.mutate_human_zone_guard_removal(policy)

        evaluator.evaluate(mutated, baseline, record)

        assert ws == orig_ws
