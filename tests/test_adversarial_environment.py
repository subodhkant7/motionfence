"""Comprehensive test suite for the MotionFence Phase 2H Adversarial Physical Environment."""

import copy
import pytest

from motionfence.adversarial.environment import AdversarialEnvironment
from motionfence.adversarial.executor import AdversarialScenarioExecutor
from motionfence.adversarial.faults import FaultApplier
from motionfence.adversarial.generators import AdversarialScenarioGenerator
from motionfence.adversarial.metrics import AdversarialMetricsTracker
from motionfence.adversarial.models import (
    AdversarialFault,
    AdversarialScenario,
    FaultCategory,
    FaultSeverity,
    FaultTiming,
    FaultType,
    ScenarioExecutionResult,
    ScenarioOutcome,
    ScheduledFault,
)
from motionfence.adversarial.reporting import AutomaticShrinker, ReportFormatter
from motionfence.adversarial.scenarios import ScenarioBuilder
from motionfence.assurance.checker import BoundedAssuranceChecker
from motionfence.assurance.invariants import AssurancePropertyRegistry
from motionfence.assurance.models import FindingStatus
from motionfence.models.actions import ActionProposal, ActionType, ExecutionResult
from motionfence.models.world import CoolingState, HumanZoneState, ValveState, SensorObservation
from motionfence.simulation.world import PhysicalWorld
from motionfence.policy.models import DecisionType


# ---------------------------------------------------------------------------
# 1. Fault Taxonomy & Application Tests
# ---------------------------------------------------------------------------

class TestFaultTaxonomy:
    """Verify typed fault classes across Human, Equipment, Sensor, Perception, Knowledge, and Timing."""

    def test_human_fault_enters_zone_mutates_state_and_version(self):
        world = PhysicalWorld()
        initial_version = world.version
        fault = AdversarialFault(
            fault_type=FaultType.HUMAN_ENTERS_ZONE,
            category=FaultCategory.HUMAN,
            severity=FaultSeverity.CRITICAL,
        )
        msg = FaultApplier.apply_world_fault(world, fault)
        assert world.human_zone == HumanZoneState.OCCUPIED
        assert world.version == initial_version + 1
        assert "Human entered safety zone" in msg

    def test_equipment_fault_pump_starts_unexpectedly(self):
        world = PhysicalWorld()
        world.pumps["pump_p1"] = "INACTIVE"
        initial_version = world.version
        fault = AdversarialFault(
            fault_type=FaultType.PUMP_STARTS_UNEXPECTEDLY,
            category=FaultCategory.EQUIPMENT,
            severity=FaultSeverity.HIGH,
            target="pump_p1",
        )
        msg = FaultApplier.apply_world_fault(world, fault)
        assert world.pumps["pump_p1"] == "ACTIVE"
        assert world.version == initial_version + 1
        assert "unexpectedly started ACTIVE" in msg

    def test_equipment_fault_cooling_degrades(self):
        world = PhysicalWorld()
        initial_version = world.version
        fault = AdversarialFault(
            fault_type=FaultType.COOLING_DEGRADES,
            category=FaultCategory.EQUIPMENT,
            severity=FaultSeverity.CRITICAL,
            parameters={"cooling_state": "INACTIVE"},
        )
        msg = FaultApplier.apply_world_fault(world, fault)
        assert world.cooling == CoolingState.INACTIVE
        assert world.version == initial_version + 1

    def test_sensor_fault_stuck_reading(self):
        world = PhysicalWorld()
        observations = world.get_state().observations
        fault = AdversarialFault(
            fault_type=FaultType.SENSOR_STUCK,
            category=FaultCategory.SENSOR,
            target="pressure_main",
            parameters={"stuck_reading": {"pressure_psi": 88.0, "pressure_drop": False}},
        )
        mutated_obs, msg = FaultApplier.apply_sensor_fault(observations, fault)
        assert mutated_obs["pressure_main"].reading["pressure_psi"] == 88.0
        assert mutated_obs["pressure_main"].reading["pressure_drop"] is False
        assert "stuck at nominal reading" in msg

    def test_sensor_fault_dropout(self):
        world = PhysicalWorld()
        observations = world.get_state().observations
        assert "pressure_main" in observations
        fault = AdversarialFault(
            fault_type=FaultType.SENSOR_DROPOUT,
            category=FaultCategory.SENSOR,
            target="pressure_main",
        )
        mutated_obs, msg = FaultApplier.apply_sensor_fault(observations, fault)
        assert "pressure_main" not in mutated_obs
        assert "removed observation" in msg

    def test_sensor_fault_contradiction(self):
        world = PhysicalWorld()
        observations = world.get_state().observations
        fault = AdversarialFault(
            fault_type=FaultType.SENSOR_CONTRADICTION,
            category=FaultCategory.SENSOR,
            target="pressure_main",
            parameters={"confidence": 0.97},
        )
        mutated_obs, msg = FaultApplier.apply_sensor_fault(observations, fault)
        assert mutated_obs["pressure_main"].confidence == 0.97
        assert mutated_obs["pressure_main"].reading["pressure_anomaly"] is False


# ---------------------------------------------------------------------------
# 2. Adversarial Environment & Decoupled Hidden State Tests
# ---------------------------------------------------------------------------

class TestAdversarialEnvironment:
    """Verify AdversarialEnvironment abstraction and ground-truth vs observable state decoupling."""

    def test_security_invariants_zero_authority(self):
        env = AdversarialEnvironment()
        assert env.can_mint_ticket() is False
        assert env.can_bypass_policy() is False
        assert env.can_invoke_enclave() is False

    def test_hidden_state_divergence(self):
        """Ground truth has pump active, but observable override shows pump stopped."""
        world = PhysicalWorld()
        world.pumps["pump_p1"] = "ACTIVE"
        env = AdversarialEnvironment(world=world)

        # Configure observable hidden-state override
        env.set_hidden_state_discrepancy("observable_pump_state", {"pump_p1": "INACTIVE"})

        gt_state = env.get_ground_truth_state()
        obs_state = env.get_observable_state()

        assert gt_state.pumps["pump_p1"] == "ACTIVE"
        assert obs_state.pumps["pump_p1"] == "INACTIVE"
        assert gt_state.pumps != obs_state.pumps

    def test_deterministic_fault_scheduling(self):
        env = AdversarialEnvironment()
        fault = AdversarialFault(
            fault_type=FaultType.HUMAN_ENTERS_ZONE,
            category=FaultCategory.HUMAN,
            timing=FaultTiming.BEFORE_EXECUTION,
        )
        env.schedule_fault(fault, FaultTiming.BEFORE_EXECUTION)

        # Stepping at AFTER_OBSERVATION does not trigger fault
        actions_t0 = env.step(FaultTiming.AFTER_OBSERVATION)
        assert len(actions_t0) == 0
        assert env.world.human_zone == HumanZoneState.CLEAR

        # Stepping at BEFORE_EXECUTION triggers fault
        actions_t4 = env.step(FaultTiming.BEFORE_EXECUTION)
        assert len(actions_t4) == 1
        assert env.world.human_zone == HumanZoneState.OCCUPIED


# ---------------------------------------------------------------------------
# 3. Scenario Execution & TOCTOU Integration Tests
# ---------------------------------------------------------------------------

class TestAdversarialScenarioExecutor:
    """Verify execution of adversarial scenarios against the complete MotionFence runtime."""

    def test_benign_scenario_produces_safe_allow(self):
        """Baseline scenario with no faults achieves SAFE_ALLOW."""
        scenario = (
            ScenarioBuilder("BENIGN_001")
            .with_description("Benign baseline without disturbances")
            .build()
        )
        executor = AdversarialScenarioExecutor()
        result = executor.execute(scenario)
        assert result.outcome == ScenarioOutcome.SAFE_ALLOW
        assert result.execution_success is True
        assert result.unsafe_allow is False

    def test_human_toctou_triggers_safe_revalidation_block(self):
        """Human entering zone after ticket blocks execution at revalidation gate."""
        scenario = (
            ScenarioBuilder("HUMAN_TOCTOU_TEST")
            .add_fault(
                fault_type=FaultType.HUMAN_ENTERS_ZONE,
                category=FaultCategory.HUMAN,
                timing=FaultTiming.BEFORE_EXECUTION,
                severity=FaultSeverity.CRITICAL,
            )
            .build()
        )
        executor = AdversarialScenarioExecutor()
        result = executor.execute(scenario)
        assert result.outcome == ScenarioOutcome.SAFE_REVALIDATION_BLOCK
        assert result.execution_success is False
        assert result.unsafe_allow is False
        assert "WORLD_STATE_CHANGED" in str(result.revalidation_status)

    def test_actuator_jam_detected_by_post_action_verifier(self):
        """Mechanical jam during execution yields VERIFICATION_FAILURE, not false verification."""
        scenario = (
            ScenarioBuilder("ACTUATOR_JAM_TEST")
            .add_fault(
                fault_type=FaultType.ACTUATOR_JAM,
                category=FaultCategory.ACTUATOR,
                timing=FaultTiming.DURING_EXECUTION,
                target="valve_b",
            )
            .build()
        )
        executor = AdversarialScenarioExecutor()
        result = executor.execute(scenario)
        assert result.outcome == ScenarioOutcome.VERIFICATION_FAILURE
        assert result.unsafe_allow is False
        assert "discrepancy" in result.message.lower()

    def test_partial_actuator_move_detected_by_verifier(self):
        """Partial valve movement (TRANSITIONING) caught by postcondition verifier."""
        scenario = (
            ScenarioBuilder("ACTUATOR_PARTIAL_TEST")
            .add_fault(
                fault_type=FaultType.VALVE_PARTIAL_MOVE,
                category=FaultCategory.EQUIPMENT,
                timing=FaultTiming.DURING_EXECUTION,
                target="valve_b",
            )
            .build()
        )
        executor = AdversarialScenarioExecutor()
        result = executor.execute(scenario)
        assert result.outcome == ScenarioOutcome.VERIFICATION_FAILURE

    def test_sensor_contradiction_yields_need_more_evidence(self):
        """Contradiction across sensors triggers uncertainty handling."""
        scenario = (
            ScenarioBuilder("SENSOR_CONTRADICTION_TEST")
            .add_fault(
                fault_type=FaultType.SENSOR_CONTRADICTION,
                category=FaultCategory.SENSOR,
                timing=FaultTiming.AFTER_OBSERVATION,
            )
            .build()
        )
        executor = AdversarialScenarioExecutor()
        result = executor.execute(scenario)
        # Active evidence acquisition attempts recovery, or halts with NEED_MORE_EVIDENCE / BUDGET_EXHAUSTION
        assert result.outcome in (ScenarioOutcome.SAFE_NEED_MORE_EVIDENCE, ScenarioOutcome.BUDGET_EXHAUSTION, ScenarioOutcome.SAFE_ALLOW)
        assert result.unsafe_allow is False


# ---------------------------------------------------------------------------
# 4. Boundary Probing & Metamorphic Testing
# ---------------------------------------------------------------------------

class TestBoundaryAndMetamorphicTesting:
    """Verify boundary probes and metamorphic invariants across parameter domains."""

    def test_confidence_boundary_probes(self):
        generator = AdversarialScenarioGenerator(seed=42)
        probes = generator.generate_boundary_probes()
        executor = AdversarialScenarioExecutor()

        for probe in probes:
            res = executor.execute(probe)
            assert res.unsafe_allow is False
            if probe.expected_outcome:
                expected_outcomes = {probe.expected_outcome}
                if probe.expected_outcome == ScenarioOutcome.SAFE_NEED_MORE_EVIDENCE:
                    expected_outcomes.add(ScenarioOutcome.BUDGET_EXHAUSTION)
                assert res.outcome in expected_outcomes

    def test_metamorphic_unrelated_evidence_invariance(self):
        """Adding irrelevant sensor reading does not alter safe allow."""
        generator = AdversarialScenarioGenerator(seed=101)
        pairs = generator.generate_metamorphic_pairs()
        executor = AdversarialScenarioExecutor()

        base_unrelated, mut_unrelated, prop_name = pairs[0]
        assert prop_name == "PROP_META_UNRELATED_EVIDENCE_INVARIANCE"

        res_base = executor.execute(base_unrelated)
        res_mut = executor.execute(mut_unrelated)

        assert res_base.outcome == res_mut.outcome == ScenarioOutcome.SAFE_ALLOW

    def test_metamorphic_weaker_evidence_monotonicity(self):
        """Weakening evidence cannot convert non-ALLOW into ALLOW."""
        generator = AdversarialScenarioGenerator(seed=102)
        pairs = generator.generate_metamorphic_pairs()
        executor = AdversarialScenarioExecutor()

        base_weaker, mut_weaker, prop_name = pairs[1]
        assert prop_name == "PROP_META_WEAKER_EVIDENCE_MONOTONICITY"

        res_mut = executor.execute(mut_weaker)
        # Low confidence (0.75) must NOT allow directly without evidence recovery
        assert res_mut.unsafe_allow is False

    def test_metamorphic_safety_degradation_monotonicity(self):
        """Technician entering safety zone must never produce ALLOW."""
        generator = AdversarialScenarioGenerator(seed=103)
        pairs = generator.generate_metamorphic_pairs()
        executor = AdversarialScenarioExecutor()

        base_safety, mut_safety, prop_name = pairs[2]
        res_mut = executor.execute(mut_safety)
        assert res_mut.outcome == ScenarioOutcome.SAFE_REVALIDATION_BLOCK
        assert res_mut.unsafe_allow is False


# ---------------------------------------------------------------------------
# 5. Minimization & Automatic Shrinking Tests
# ---------------------------------------------------------------------------

class TestAutomaticShrinking:
    """Verify delta-debugging minimization shrinks compound failures to minimal counterexamples."""

    def test_automatic_shrinker_minimizes_compound_faults(self):
        # Construct a scenario with 3 faults, where human incursion alone is sufficient to cause SAFE_REVALIDATION_BLOCK
        failing_scenario = (
            ScenarioBuilder("COMPOUND_SHRINK_TEST")
            .add_fault(
                fault_type=FaultType.SENSOR_NOISE,
                category=FaultCategory.SENSOR,
                timing=FaultTiming.AFTER_OBSERVATION,
            )
            .add_fault(
                fault_type=FaultType.HUMAN_ENTERS_ZONE,
                category=FaultCategory.HUMAN,
                timing=FaultTiming.BEFORE_EXECUTION,
                severity=FaultSeverity.CRITICAL,
            )
            .add_fault(
                fault_type=FaultType.TARGET_OCCLUDED,
                category=FaultCategory.PERCEPTION,
                timing=FaultTiming.AFTER_OBSERVATION,
                parameters={"confidence": 0.95},
            )
            .expect_outcome(ScenarioOutcome.SAFE_REVALIDATION_BLOCK)
            .build()
        )

        assert len(failing_scenario.fault_schedule) == 3

        shrinker = AutomaticShrinker()
        # Predicate: scenario produces SAFE_REVALIDATION_BLOCK
        cx = shrinker.shrink(
            failing_scenario,
            failure_predicate=lambda res: res.outcome == ScenarioOutcome.SAFE_REVALIDATION_BLOCK,
        )

        assert cx.shrunk is True
        # Minimal fault count should be reduced to 1 (just human incursion)
        assert cx.minimal_fault_count == 1
        assert "HUMAN_ENTERS_ZONE" in cx.faults


# ---------------------------------------------------------------------------
# 6. Metrics & Reporting Tests
# ---------------------------------------------------------------------------

class TestMetricsAndReporting:
    """Verify aggregate statistics tracking and report generation."""

    def test_metrics_tracker_accumulates_correct_statistics(self):
        tracker = AdversarialMetricsTracker(seed=42)
        executor = AdversarialScenarioExecutor()

        # Run 3 distinct scenarios
        s1 = ScenarioBuilder("S1").build()  # SAFE_ALLOW
        s2 = ScenarioBuilder("S2").add_fault(FaultType.HUMAN_ENTERS_ZONE, FaultCategory.HUMAN, FaultTiming.BEFORE_EXECUTION).build()  # REVAL BLOCK
        s3 = ScenarioBuilder("S3").add_fault(FaultType.ACTUATOR_JAM, FaultCategory.ACTUATOR, FaultTiming.DURING_EXECUTION, target="valve_b").build()  # VERIF FAIL

        r1 = executor.execute(s1)
        r2 = executor.execute(s2)
        r3 = executor.execute(s3)

        tracker.record_result(r1)
        tracker.record_result(r2, fault_types=[FaultType.HUMAN_ENTERS_ZONE], fault_timings=[FaultTiming.BEFORE_EXECUTION])
        tracker.record_result(r3, fault_types=[FaultType.ACTUATOR_JAM], fault_timings=[FaultTiming.DURING_EXECUTION])

        report = tracker.generate_report()
        assert report.total_scenarios == 3
        assert report.safe_allows == 1
        assert report.revalidation_blocks == 1
        assert report.verification_failures == 1
        assert report.unsafe_allows == 0  # CRITICAL ZERO METRIC

        md = ReportFormatter.format_markdown(report)
        assert "Total Scenarios Evaluated" in md
        assert "CRITICAL: Unsafe ALLOWs" in md


# ---------------------------------------------------------------------------
# 7. Bounded Formal Assurance (Z3 SMT Properties PROP_018 to PROP_023)
# ---------------------------------------------------------------------------

class TestBoundedAssurancePhase2H:
    """Verify formal Z3 SMT properties PROP_018 through PROP_023."""

    def test_assurance_registry_contains_23_properties(self):
        registry = AssurancePropertyRegistry()
        all_props = registry.list_all()
        assert len(all_props) >= 23
        prop_ids = [p.property_id for p in all_props]
        assert "PROP_018_HUMAN_ZONE_TRANSITION_SAFETY" in prop_ids
        assert "PROP_019_SENSOR_CONTRADICTION_NO_UNGROUNDED_ALLOW" in prop_ids
        assert "PROP_020_ACTUATOR_FAULT_VERIFICATION" in prop_ids
        assert "PROP_021_SAFETY_DEGRADATION_MONOTONICITY" in prop_ids
        assert "PROP_022_ADVERSARIAL_ENV_ZERO_AUTHORITY" in prop_ids
        assert "PROP_023_STALE_TICKET_ENVIRONMENTAL_DRIFT" in prop_ids

    def test_all_23_properties_satisfied_under_standard_policy(self):
        checker = BoundedAssuranceChecker()
        findings = checker.check_all()
        assert len(findings) >= 23
        for f in findings:
            assert f.status == FindingStatus.SATISFIED, f"Property {f.property_id} was {f.status.value}: {f.explanation}"

    def test_prop_018_counterexample_when_human_transition_execution_allowed(self):
        checker = BoundedAssuranceChecker()
        f = checker.check_property(
            "PROP_018_HUMAN_ZONE_TRANSITION_SAFETY",
            policy_mutations={"allow_human_transition_execution": True, "disable_revalidation": True},
        )
        assert f.status == FindingStatus.VIOLATED
        assert f.counterexample is not None

    def test_prop_019_counterexample_when_ungrounded_contradiction_allowed(self):
        checker = BoundedAssuranceChecker()
        f = checker.check_property(
            "PROP_019_SENSOR_CONTRADICTION_NO_UNGROUNDED_ALLOW",
            policy_mutations={"allow_ungrounded_contradiction_clearance": True, "disable_contradiction_check": True},
        )
        assert f.status == FindingStatus.VIOLATED
        assert f.counterexample is not None

    def test_prop_020_counterexample_when_actuator_fault_verification_allowed(self):
        checker = BoundedAssuranceChecker()
        f = checker.check_property(
            "PROP_020_ACTUATOR_FAULT_VERIFICATION",
            policy_mutations={"allow_actuator_fault_verification": True},
        )
        assert f.status == FindingStatus.VIOLATED
        assert f.counterexample is not None

    def test_prop_021_counterexample_when_safety_degradation_allowed(self):
        checker = BoundedAssuranceChecker()
        f = checker.check_property(
            "PROP_021_SAFETY_DEGRADATION_MONOTONICITY",
            policy_mutations={"allow_safety_degradation_allow": True},
        )
        assert f.status == FindingStatus.VIOLATED
        assert f.counterexample is not None

    def test_prop_022_counterexample_when_adversary_authority_allowed(self):
        checker = BoundedAssuranceChecker()
        f = checker.check_property(
            "PROP_022_ADVERSARIAL_ENV_ZERO_AUTHORITY",
            policy_mutations={"allow_adversary_authority": True},
        )
        assert f.status == FindingStatus.VIOLATED
        assert f.counterexample is not None

    def test_prop_023_counterexample_when_stale_ticket_execution_allowed(self):
        checker = BoundedAssuranceChecker()
        f = checker.check_property(
            "PROP_023_STALE_TICKET_ENVIRONMENTAL_DRIFT",
            policy_mutations={"allow_stale_ticket_execution": True, "disable_revalidation": True},
        )
        assert f.status == FindingStatus.VIOLATED
        assert f.counterexample is not None
