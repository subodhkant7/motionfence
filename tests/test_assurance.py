"""Bounded formal assurance and Z3 SMT invariant verification tests."""

import pytest
from motionfence.assurance.checker import BoundedAssuranceChecker
from motionfence.assurance.temporal import BoundedTemporalChecker
from motionfence.assurance.invariants import AssurancePropertyRegistry
from motionfence.assurance.models import FindingStatus, FindingSeverity, FormalState, AssuranceScope
from motionfence.assurance.counterexample import CounterexampleFormatter
from motionfence.models.world import WorldState, ValveState, CoolingState, HumanZoneState, LeakState
from motionfence.models.actions import ActionType


def test_formal_state_deterministic_conversion():
    """Verify bidirectional roundtrip conversion between WorldState and FormalState."""
    original_world = WorldState(
        valves={"valve_a": ValveState.OPEN, "valve_b": ValveState.CLOSED},
        cooling=CoolingState.ACTIVE,
        leak=LeakState(active=True, target="valve_b", severity=0.75),
        human_zone=HumanZoneState.CLEAR,
        pumps={"pump_p1": "ACTIVE"},
        observations={},
        version=4,
        timestamp=1000.0,
    )

    formal = FormalState.from_world_state(original_world)
    assert formal.valves["valve_a"] == "OPEN"
    assert formal.valves["valve_b"] == "CLOSED"
    assert formal.cooling == "ACTIVE"
    assert formal.human_zone == "CLEAR"
    assert formal.pumps["pump_p1"] == "ACTIVE"
    assert formal.leak_active is True
    assert formal.leak_target == "valve_b"
    assert formal.leak_severity == 0.75

    reconstructed_world = formal.to_world_state(version=4, timestamp=1000.0)
    assert reconstructed_world.valves["valve_a"] == ValveState.OPEN
    assert reconstructed_world.valves["valve_b"] == ValveState.CLOSED
    assert reconstructed_world.cooling == CoolingState.ACTIVE
    assert reconstructed_world.human_zone == HumanZoneState.CLEAR
    assert reconstructed_world.pumps["pump_p1"] == "ACTIVE"
    assert reconstructed_world.leak.active is True
    assert reconstructed_world.leak.target == "valve_b"


def test_z3_static_invariants_satisfied_under_production_policy():
    """Verify that all standard registered safety invariants are SATISFIED under production rules."""
    registry = AssurancePropertyRegistry()
    checker = BoundedAssuranceChecker(registry=registry)

    # 1. Human-zone prohibition
    f1 = checker.check_property("PROP_001_HUMAN_ZONE_PROHIBITION")
    assert f1.status == FindingStatus.SATISFIED
    assert "BOUNDED PROPERTY SATISFIED" in f1.explanation

    # 2. Cooling preservation
    f2 = checker.check_property("PROP_002_COOLING_PRESERVATION")
    assert f2.status == FindingStatus.SATISFIED

    # 3. Actuator authority isolation
    f3 = checker.check_property("PROP_003_UNAUTHORIZED_MUTATION_IMPOSSIBLE")
    assert f3.status == FindingStatus.SATISFIED

    # 4. Conflicted policy blocks authorization
    f4 = checker.check_property("PROP_004_CONFLICTED_POLICY_BLOCKS_AUTHORIZATION")
    assert f4.status == FindingStatus.SATISFIED

    # 5. Stale safety constraint blocks unsafe authorization
    f5 = checker.check_property("PROP_005_STALE_SAFETY_CONSTRAINT_BLOCKS_AUTHORIZATION")
    assert f5.status == FindingStatus.SATISFIED

    # 6. Sensor contradiction gating
    f6 = checker.check_property("PROP_006_CONTRADICTORY_EVIDENCE_GATING")
    assert f6.status == FindingStatus.SATISFIED

    # 7. Temporal cooling preservation
    f7 = checker.check_property("PROP_007_TEMPORAL_COOLING_PRESERVATION")
    assert f7.status == FindingStatus.SATISFIED


def test_deliberate_violation_discovers_concrete_counterexample():
    """Verify that deliberately mutating a policy in a test environment produces a concrete counterexample."""
    checker = BoundedAssuranceChecker()

    # Deliberately disable human-zone safety check to test falsification discovery
    mutated_policy = {"disable_human_zone_check": True}
    finding = checker.check_property("PROP_001_HUMAN_ZONE_PROHIBITION", policy_mutations=mutated_policy)

    assert finding.status == FindingStatus.VIOLATED
    assert finding.counterexample is not None
    assert finding.counterexample["human_zone"] == "OCCUPIED"
    assert finding.counterexample["action"] == "CLOSE_VALVE"
    assert finding.counterexample["policy_decision"] == "ALLOW"


def test_deliberate_cooling_violation_discovers_counterexample():
    """Verify that disabling cooling check generates a concrete cooling counterexample."""
    checker = BoundedAssuranceChecker()

    mutated_policy = {"disable_cooling_check": True}
    finding = checker.check_property("PROP_002_COOLING_PRESERVATION", policy_mutations=mutated_policy)

    assert finding.status == FindingStatus.VIOLATED
    assert finding.counterexample is not None
    assert finding.counterexample["policy_decision"] == "ALLOW"
    assert finding.counterexample["cooling"] != "ACTIVE"


def test_deliberate_authority_mutation_discovers_counterexample():
    """Verify that permitting unauthorized mutation yields a concrete counterexample."""
    checker = BoundedAssuranceChecker()

    mutated_policy = {"allow_unauthorized_mutation": True}
    finding = checker.check_property("PROP_003_UNAUTHORIZED_MUTATION_IMPOSSIBLE", policy_mutations=mutated_policy)

    assert finding.status == FindingStatus.VIOLATED
    assert finding.counterexample is not None
    assert finding.counterexample["world_mutated"] is True
    assert finding.counterexample["has_ticket"] is False


def test_counterexample_formatter_and_shrinking():
    """Verify that CounterexampleFormatter formats cleanly and shrinks non-essential noise."""
    raw_ce = {
        "human_zone": "OCCUPIED",
        "action": "CLOSE_VALVE",
        "policy_decision": "ALLOW",
        "irrelevant_internal_metric": 12345,
        "transient_scratchpad_state": "foo_bar",
    }

    minimized = CounterexampleFormatter.minimize(raw_ce)
    assert "human_zone" in minimized
    assert "action" in minimized
    assert "policy_decision" in minimized
    assert "irrelevant_internal_metric" not in minimized
    assert "transient_scratchpad_state" not in minimized

    text = CounterexampleFormatter.format_counterexample(
        property_name="Human-Zone Actuation Prohibition",
        counterexample=minimized,
        status=FindingStatus.VIOLATED,
    )
    assert "PROPERTY: Human-Zone Actuation Prohibition" in text
    assert "STATUS:   VIOLATED" in text
    assert "human_zone = OCCUPIED" in text
    assert "action = CLOSE_VALVE" in text


def test_bounded_temporal_checker_cooling_sequence():
    """Verify temporal cooling preservation over multi-step action sequence."""
    temporal = BoundedTemporalChecker()
    init_state = FormalState(
        valves={"valve_a": "OPEN", "valve_b": "OPEN"},
        cooling="ACTIVE",
        human_zone="CLEAR",
        pumps={"pump_p1": "INACTIVE"},
    )

    finding = temporal.check_cooling_preservation_sequence(
        initial_state=init_state,
        action_sequence=[ActionType.CLOSE_VALVE, ActionType.OPEN_VALVE, ActionType.CLOSE_VALVE],
        horizon=3,
    )
    assert finding.status == FindingStatus.SATISFIED


def test_bounded_temporal_checker_dynamic_human_incursion():
    """Verify that mid-sequence human entry safely prevents subsequent actuation."""
    temporal = BoundedTemporalChecker()
    finding = temporal.check_dynamic_human_incursion(horizon=3, incursion_step=1)
    assert finding.status == FindingStatus.SATISFIED


def test_assurance_engine_has_zero_actuator_authority():
    """Security Invariant: Assurance engine and Z3 checker have no authority to mutate physical world or mint tickets."""
    checker = BoundedAssuranceChecker()
    temporal = BoundedTemporalChecker()

    assert not hasattr(checker, "actuator")
    assert not hasattr(checker, "ticket_authority")
    assert not hasattr(checker, "mint_ticket")
    assert not hasattr(temporal, "actuator")
    assert not hasattr(temporal, "ticket_authority")


def test_phase_2o_telemetry_properties_satisfied_under_production_policy():
    """Verify that Phase 2O public telemetry properties (PROP_052 - PROP_056) are satisfied."""
    registry = AssurancePropertyRegistry()
    assert len(registry.list_all()) == 56
    checker = BoundedAssuranceChecker(registry=registry)

    for prop_id in [
        "PROP_052_EXTERNAL_TELEMETRY_HAS_NO_ACTUATION_AUTHORITY",
        "PROP_053_MISSING_EXTERNAL_OBSERVATION_CANNOT_CREATE_AUTHORIZATION",
        "PROP_054_STALE_EXTERNAL_EVIDENCE_CANNOT_BE_PRESENTED_AS_FRESH",
        "PROP_055_REPLAYED_EXTERNAL_OBSERVATION_CANNOT_CLAIM_LIVE_STATUS",
        "PROP_056_TELEMETRY_SOURCE_PROVENANCE_REMAINS_BOUND_TO_OBSERVATION",
    ]:
        finding = checker.check_property(prop_id)
        assert finding.status == FindingStatus.SATISFIED, f"{prop_id} was not satisfied: {finding.explanation}"


def test_deliberate_telemetry_violations_discover_counterexamples():
    """Verify that deliberately violating telemetry invariants produces concrete counterexamples."""
    checker = BoundedAssuranceChecker()

    # Test deliberate violation of PROP_052: allowing raw telemetry actuation
    f52 = checker.check_property(
        "PROP_052_EXTERNAL_TELEMETRY_HAS_NO_ACTUATION_AUTHORITY",
        policy_mutations={"allow_raw_telemetry_actuation": True},
    )
    assert f52.status == FindingStatus.VIOLATED

    # Test deliberate violation of PROP_053: allowing authorization without telemetry
    f53 = checker.check_property(
        "PROP_053_MISSING_EXTERNAL_OBSERVATION_CANNOT_CREATE_AUTHORIZATION",
        policy_mutations={"allow_authorization_without_telemetry": True},
    )
    assert f53.status == FindingStatus.VIOLATED

    # Test deliberate violation of PROP_054: allowing stale telemetry as fresh
    f54 = checker.check_property(
        "PROP_054_STALE_EXTERNAL_EVIDENCE_CANNOT_BE_PRESENTED_AS_FRESH",
        policy_mutations={"allow_stale_telemetry_as_fresh": True},
    )
    assert f54.status == FindingStatus.VIOLATED

