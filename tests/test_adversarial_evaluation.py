"""Adversarial evaluation, boundary fuzzing, knowledge distortion, and security isolation tests."""

import pytest
from motionfence.assurance.adversarial import AdversarialGenerator
from motionfence.assurance.evaluator import AdversarialEvaluator
from motionfence.assurance.models import AdversarialOutcomeCategory
from motionfence.models.actions import ActionProposal, ActionType
from motionfence.models.world import WorldState, ValveState, CoolingState, HumanZoneState, LeakState
from motionfence.policy.engine import PolicyEngine
from motionfence.policy.models import DecisionType
from motionfence.evidence.models import Evidence, EvidenceSource


def test_adversarial_confidence_threshold_boundaries():
    """Verify exact policy behavior around confidence boundaries (0.89, 0.899, 0.90, 0.901)."""
    world = WorldState(
        valves={"valve_a": ValveState.OPEN, "valve_b": ValveState.OPEN},
        cooling=CoolingState.ACTIVE,
        leak=LeakState(active=True, target="valve_b", severity=0.8),
        human_zone=HumanZoneState.CLEAR,
        pumps={"pump_p1": "INACTIVE"},
        observations={},
    )

    def eval_at_conf(conf: float):
        ev = Evidence(
            source=EvidenceSource.PRESSURE_SENSOR,
            target="valve_b",
            observation={"leak": True},
            confidence=conf,
            provenance="test_sensor",
        )
        prop = ActionProposal(
            action_type=ActionType.CLOSE_VALVE,
            target="valve_b",
            parameters={},
            model_confidence=conf,
            rationale=f"Probe at {conf}",
            supporting_evidence_ids=[ev.id],
        )
        return PolicyEngine.evaluate(prop, world, [ev])

    # 1. 0.89 -> Below 0.90 threshold -> NEED_MORE_EVIDENCE
    assert eval_at_conf(0.89).decision == DecisionType.NEED_MORE_EVIDENCE

    # 2. 0.899 -> Below threshold -> NEED_MORE_EVIDENCE
    assert eval_at_conf(0.899).decision == DecisionType.NEED_MORE_EVIDENCE

    # 3. 0.90 -> Exact threshold -> ALLOW
    assert eval_at_conf(0.90).decision == DecisionType.ALLOW

    # 4. 0.901 -> Above threshold -> ALLOW
    assert eval_at_conf(0.901).decision == DecisionType.ALLOW


def test_adversarial_sensor_contradiction_fuzzing():
    """Verify that multi-sensor discordant combinations correctly trigger high contradiction."""
    evaluator = AdversarialEvaluator()
    generator = AdversarialGenerator()
    contradiction_cases = generator.generate_contradiction_cases()

    for case in contradiction_cases:
        res = evaluator._evaluate_contradiction_case(case)
        assert res.category != AdversarialOutcomeCategory.FALSE_ALLOW
        assert res.is_safe is True


def test_adversarial_knowledge_distortion_fuzzing():
    """Verify that adversarially distorted claims are not erroneously accepted as SUPPORTED."""
    evaluator = AdversarialEvaluator()
    generator = AdversarialGenerator()
    knowledge_cases = generator.generate_knowledge_adversaries()

    for kcase in knowledge_cases:
        res = evaluator._evaluate_knowledge_case(kcase)
        assert res.category != AdversarialOutcomeCategory.FALSE_ALLOW
        assert res.is_safe is True


def test_adversarial_source_trust_fuzzing():
    """Verify that untrusted domains, mirror duplicates, and foreign pump manuals are rejected."""
    evaluator = AdversarialEvaluator()
    generator = AdversarialGenerator()
    source_cases = generator.generate_source_trust_adversaries()

    for scase in source_cases:
        res = evaluator._evaluate_source_trust_case(scase)
        assert res.category != AdversarialOutcomeCategory.FALSE_ALLOW
        assert res.is_safe is True


def test_adversarial_evaluator_zero_false_allows_across_scenarios():
    """Run comprehensive adversarial evaluation on 200 randomized + boundary cases and verify 0 false ALLOWs."""
    evaluator = AdversarialEvaluator(seed=123)
    report = evaluator.run_evaluation(num_random_cases=200)

    assert report.adversarial_cases >= 200
    assert report.unsafe_authorizations_discovered == 0
    assert report.adversarial_outcomes[AdversarialOutcomeCategory.FALSE_ALLOW.value] == 0


def test_adversarial_evaluation_deterministic_reproducibility():
    """Verify that running with identical seeds produces identical test outputs."""
    evaluator_1 = AdversarialEvaluator(seed=999)
    report_1 = evaluator_1.run_evaluation(num_random_cases=50)

    evaluator_2 = AdversarialEvaluator(seed=999)
    report_2 = evaluator_2.run_evaluation(num_random_cases=50)

    assert report_1.adversarial_cases == report_2.adversarial_cases
    assert report_1.adversarial_outcomes == report_2.adversarial_outcomes
    assert report_1.unsafe_authorizations_discovered == report_2.unsafe_authorizations_discovered


def test_adversarial_evaluator_security_invariants():
    """Security Invariant: Adversarial evaluator has zero actuator authority and cannot mutate state."""
    evaluator = AdversarialEvaluator()

    assert not hasattr(evaluator, "actuator")
    assert not hasattr(evaluator, "ticket_authority")
    assert not hasattr(evaluator, "mint_ticket")
