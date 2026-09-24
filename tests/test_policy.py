"""Tests for deterministic PolicyEngine authorization logic."""

import pytest

from motionfence.policy.engine import PolicyEngine
from motionfence.policy.models import Policy, DecisionType
from motionfence.models.actions import ActionProposal, ActionType
from motionfence.models.world import WorldState, HumanZoneState, CoolingState
from motionfence.evidence.models import Evidence, EvidenceSource


@pytest.fixture
def base_world() -> WorldState:
    return WorldState(
        valves={"valve_a": "OPEN", "valve_b": "OPEN"},
        cooling=CoolingState.ACTIVE,
        human_zone=HumanZoneState.CLEAR,
    )


@pytest.fixture
def high_conf_evidence() -> list[Evidence]:
    return [
        Evidence(
            source=EvidenceSource.VISION,
            target="valve_b",
            observation={"leak_detected": True, "visual_vapor_detected": True},
            confidence=0.95,
            provenance="camera_zoom_macro_01",
        ),
        Evidence(
            source=EvidenceSource.THERMAL_SENSOR,
            target="valve_b",
            observation={"leak_confirmed": True, "thermal_gradient_c": 15.0},
            confidence=0.96,
            provenance="flir_thermal_ptu_02",
        ),
    ]


def test_policy_allows_valid_high_confidence_proposal(base_world: WorldState, high_conf_evidence: list[Evidence]):
    """A valid proposal with high confidence and satisfied safety invariants must be ALLOWED."""
    proposal = ActionProposal(
        action_type=ActionType.CLOSE_VALVE,
        target="valve_b",
        rationale="Isolate verified leaking line.",
        model_confidence=0.95,
        supporting_evidence_ids=[e.id for e in high_conf_evidence],
    )
    decision = PolicyEngine.evaluate(proposal, base_world, high_conf_evidence)
    assert decision.decision == DecisionType.ALLOW
    assert decision.is_allowed
    assert not decision.is_denied
    assert not decision.needs_evidence


def test_policy_requires_more_evidence_when_confidence_low(base_world: WorldState):
    """When target evidence confidence is below threshold, verdict must be NEED_MORE_EVIDENCE."""
    low_conf_evidence = [
        Evidence(
            source=EvidenceSource.VISION,
            target="valve_b",
            observation={"leak_detected": True},
            confidence=0.76,  # Below 0.90 threshold
            provenance="camera_wide_overhead",
        )
    ]
    proposal = ActionProposal(
        action_type=ActionType.CLOSE_VALVE,
        target="valve_b",
        rationale="Possible leak detected.",
        model_confidence=0.76,
        supporting_evidence_ids=[low_conf_evidence[0].id],
    )
    decision = PolicyEngine.evaluate(proposal, base_world, low_conf_evidence)
    assert decision.decision == DecisionType.NEED_MORE_EVIDENCE
    assert decision.needs_evidence

    failed_reasons = [r for r in decision.reasons if r.constraint == "target_identity_confidence"]
    assert len(failed_reasons) == 1
    assert failed_reasons[0].status == "failed"
    assert failed_reasons[0].observed == 0.76
    assert failed_reasons[0].required == 0.90


def test_policy_denies_when_human_in_safety_zone(base_world: WorldState, high_conf_evidence: list[Evidence]):
    """If a human enters the safety zone, actuation must be strictly DENIED regardless of confidence."""
    base_world.human_zone = HumanZoneState.OCCUPIED

    proposal = ActionProposal(
        action_type=ActionType.CLOSE_VALVE,
        target="valve_b",
        rationale="Emergency leak closure.",
        model_confidence=0.99,
        supporting_evidence_ids=[e.id for e in high_conf_evidence],
    )
    decision = PolicyEngine.evaluate(proposal, base_world, high_conf_evidence)
    assert decision.decision == DecisionType.DENY
    assert decision.is_denied

    safety_reasons = [r for r in decision.reasons if r.constraint == "human_safety_zone"]
    assert len(safety_reasons) == 1
    assert safety_reasons[0].status == "failed"


def test_policy_denies_when_cooling_inactive(base_world: WorldState, high_conf_evidence: list[Evidence]):
    """If cooling system is not active, action must be DENIED to prevent thermal runaway."""
    base_world.cooling = CoolingState.INACTIVE

    proposal = ActionProposal(
        action_type=ActionType.CLOSE_VALVE,
        target="valve_b",
        rationale="Closing valve.",
        model_confidence=0.95,
        supporting_evidence_ids=[e.id for e in high_conf_evidence],
    )
    decision = PolicyEngine.evaluate(proposal, base_world, high_conf_evidence)
    assert decision.decision == DecisionType.DENY

    cooling_reasons = [r for r in decision.reasons if r.constraint == "cooling_system_active"]
    assert len(cooling_reasons) == 1
    assert cooling_reasons[0].status == "failed"


def test_policy_denies_prohibited_action(base_world: WorldState, high_conf_evidence: list[Evidence]):
    """Prohibited actions like ADJUST_COOLING must be DENIED unconditionally."""
    proposal = ActionProposal(
        action_type=ActionType.ADJUST_COOLING,
        target="valve_b",
        rationale="Attempting to modify cooling loops.",
        model_confidence=0.99,
    )
    decision = PolicyEngine.evaluate(proposal, base_world, high_conf_evidence)
    assert decision.decision == DecisionType.DENY

    prohibited_reasons = [r for r in decision.reasons if r.constraint == "prohibited_action"]
    assert len(prohibited_reasons) == 1
    assert prohibited_reasons[0].status == "failed"


def test_policy_denies_unauthorized_target(base_world: WorldState, high_conf_evidence: list[Evidence]):
    """Targets outside allowed actuator scope must be DENIED."""
    proposal = ActionProposal(
        action_type=ActionType.CLOSE_VALVE,
        target="reactor_main_feed",  # Not in ['valve_a', 'valve_b']
        rationale="Closing unpermitted target.",
        model_confidence=0.95,
    )
    decision = PolicyEngine.evaluate(proposal, base_world, high_conf_evidence)
    assert decision.decision == DecisionType.DENY

    target_reasons = [r for r in decision.reasons if r.constraint == "allowed_actuator_target"]
    assert len(target_reasons) == 1
    assert target_reasons[0].status == "failed"


def test_policy_handles_high_severity_contradiction(base_world: WorldState):
    """High-severity sensor contradiction must prevent ALLOW."""
    contradictory_evidence = [
        Evidence(
            source=EvidenceSource.VISION,
            target="valve_b",
            observation={"leak_detected": True, "visual_vapor": True},
            confidence=0.92,
            provenance="camera_zoom_macro_01",
        ),
        Evidence(
            source=EvidenceSource.PRESSURE_SENSOR,
            target="valve_b",
            observation={"pressure_anomaly": False, "pressure_normal": True, "leak_detected": False},
            confidence=0.88,
            provenance="sensor_piezo_pressure_01",
        ),
    ]
    proposal = ActionProposal(
        action_type=ActionType.CLOSE_VALVE,
        target="valve_b",
        rationale="Isolate leak despite pressure sensor conflict.",
        model_confidence=0.92,
        supporting_evidence_ids=[contradictory_evidence[0].id],
    )
    decision = PolicyEngine.evaluate(proposal, base_world, contradictory_evidence)
    assert decision.decision == DecisionType.DENY
    contradiction_reasons = [r for r in decision.reasons if r.constraint == "contradiction_check"]
    assert len(contradiction_reasons) == 1
    assert contradiction_reasons[0].status == "failed"
