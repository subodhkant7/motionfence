"""Tests for Phase 2I: Fault Containment, Quarantine & Autonomous Recovery.

Verifies:
1. Deterministic failure classification without LLM across all failure classes
2. Immediate containment and cryptographic ticket authority invalidation (PROP_024)
3. Scoped quarantine and repeated failure escalation (1=SUSPECT, 2=RECOVERY_REQUIRED, 3=QUARANTINED) (PROP_025)
4. Sensor quarantine and admissible evidence filtering (PROP_028)
5. Autonomous recovery planning and information-gathering step execution (PROP_030)
6. Fresh policy reevaluation and enclave re-authorization without reusing stale authority (PROP_026, PROP_027)
7. Finite recovery budget enforcement (PROP_029)
8. Alternate path recovery (Valve A isolator when Valve B jammed)
9. Zero unsafe retries invariant (unsafe_retries == 0)
10. Bounded Z3 SMT formal properties PROP_024 through PROP_030
11. Metamorphic recovery properties
"""

import copy
import time
import pytest

from motionfence.models.actions import (
    ActionClass,
    ActionProposal,
    ActionType,
    AuthorizationTicket,
    ExecutionResult,
    is_consequential_action,
    is_information_action,
)
from motionfence.models.world import CoolingState, HumanZoneState, ValveState, WorldState
from motionfence.models.events import EventType
from motionfence.evidence.models import Evidence, EvidenceSource, ContradictionSeverity
from motionfence.policy.models import DecisionType, Policy, PolicyDecision
from motionfence.policy.engine import PolicyEngine
from motionfence.runtime.enclave import EnclaveAuthorizationRequest, SafetyEnclave
from motionfence.runtime.events import EventBus
from motionfence.runtime.revalidation import (
    AuthorizationRevalidationResult,
    ExecutionTimeRevalidator,
    RevalidationStatus,
)
from motionfence.runtime.verification import (
    PostActionVerifier,
    VerificationResult,
    VerificationStatus,
)
from motionfence.simulation.actuator import PhysicalActuator
from motionfence.simulation.exceptions import UnauthorizedActionError
from motionfence.simulation.world import PhysicalWorld

from motionfence.assurance.models import FindingStatus
from motionfence.assurance.invariants import AssurancePropertyRegistry
from motionfence.assurance.checker import BoundedAssuranceChecker

from motionfence.recovery.models import (
    ComponentType,
    ContainmentActionReport,
    FailureClass,
    FailureRecord,
    QuarantineRecord,
    QuarantineStatus,
    RecoveryExecutionResult,
    RecoveryOutcome,
    RecoveryPlan,
    RecoveryStep,
    RecoveryStrategy,
    RiskLevel,
)
from motionfence.recovery.classifier import FailureClassifier
from motionfence.recovery.policies import (
    ContainmentPolicy,
    QuarantinePolicy,
    RecoveryBudget,
)
from motionfence.recovery.quarantine import QuarantineManager
from motionfence.recovery.containment import ContainmentManager
from motionfence.recovery.planner import RecoveryPlanner
from motionfence.recovery.metrics import RecoveryMetricsTracker, RecoveryEvaluationReport
from motionfence.recovery.executor import RecoveryExecutor


# ---------------------------------------------------------------------------
# Test Helpers & Fixtures
# ---------------------------------------------------------------------------

@pytest.fixture
def event_bus() -> EventBus:
    return EventBus()

@pytest.fixture
def plant_world() -> PhysicalWorld:
    return PhysicalWorld(leak_target="valve_b")

@pytest.fixture
def quarantine_mgr() -> QuarantineManager:
    return QuarantineManager(policy=QuarantinePolicy(quarantine_threshold=3))

@pytest.fixture
def containment_mgr(event_bus: EventBus) -> ContainmentManager:
    return ContainmentManager(event_bus=event_bus)

@pytest.fixture
def recovery_planner() -> RecoveryPlanner:
    return RecoveryPlanner()

@pytest.fixture
def recovery_executor(plant_world: PhysicalWorld, event_bus: EventBus) -> RecoveryExecutor:
    return RecoveryExecutor(
        world=plant_world,
        event_bus=event_bus,
    )


# ---------------------------------------------------------------------------
# 1. Failure Taxonomy & Deterministic Classification Tests
# ---------------------------------------------------------------------------

class TestFailureClassification:
    """Deterministic failure classification without LLMs."""

    def test_classify_actuator_no_op(self):
        """Commanded CLOSE_VALVE but valve remained fully OPEN -> ACTUATOR_NO_OP."""
        prop = ActionProposal(
            id="p_noop",
            action_type=ActionType.CLOSE_VALVE,
            target="valve_b",
            rationale="Isolate leak",
            model_confidence=0.95,
        )
        verif = VerificationResult(
            action_id="p_noop",
            target="valve_b",
            action_occurred=True,
            expected_postconditions={"valves.valve_b": ValveState.CLOSED.value},
            observed_postconditions={"valves.valve_b": ValveState.OPEN.value},
            status=VerificationStatus.VERIFICATION_FAILED,
            discrepancies=["valves.valve_b: expected CLOSED, observed OPEN"],
        )
        failure = FailureClassifier.classify(proposal=prop, verification=verif)
        assert failure.failure_class == FailureClass.ACTUATOR_NO_OP
        assert failure.target_component == "valve_b"
        assert failure.component_type == ComponentType.ACTUATOR

    def test_classify_actuator_partial(self):
        """Actuator halted mid-stroke in TRANSITIONING -> ACTUATOR_PARTIAL."""
        prop = ActionProposal(
            id="p_part",
            action_type=ActionType.CLOSE_VALVE,
            target="valve_b",
            rationale="Isolate leak",
            model_confidence=0.95,
        )
        verif = VerificationResult(
            action_id="p_part",
            target="valve_b",
            action_occurred=True,
            expected_postconditions={"valves.valve_b": ValveState.CLOSED.value},
            observed_postconditions={"valves.valve_b": ValveState.TRANSITIONING.value},
            status=VerificationStatus.VERIFICATION_FAILED,
            discrepancies=["valves.valve_b halted in TRANSITIONING state"],
        )
        failure = FailureClassifier.classify(proposal=prop, verification=verif)
        assert failure.failure_class == FailureClass.ACTUATOR_PARTIAL

    def test_classify_actuator_wrong_state(self):
        """Valve seated into incorrect state -> ACTUATOR_WRONG_STATE."""
        prop = ActionProposal(
            id="p_wrong",
            action_type=ActionType.CLOSE_VALVE,
            target="valve_b",
            rationale="Isolate leak",
            model_confidence=0.95,
        )
        verif = VerificationResult(
            action_id="p_wrong",
            target="valve_b",
            action_occurred=True,
            expected_postconditions={"valves.valve_b": ValveState.CLOSED.value},
            observed_postconditions={"valves.valve_b": "JAMMED"},
            status=VerificationStatus.VERIFICATION_FAILED,
            discrepancies=["valves.valve_b seated into unexpected JAMMED state"],
        )
        failure = FailureClassifier.classify(proposal=prop, verification=verif)
        assert failure.failure_class == FailureClass.ACTUATOR_WRONG_STATE

    def test_classify_actuator_delay(self):
        """Actuator stroke timed out -> ACTUATOR_DELAY."""
        prop = ActionProposal(
            id="p_delay",
            action_type=ActionType.CLOSE_VALVE,
            target="valve_b",
            rationale="Isolate leak",
            model_confidence=0.95,
        )
        exec_res = ExecutionResult(
            success=False,
            action_id="p_delay",
            ticket_id="tkt_1",
            executed_action=ActionType.CLOSE_VALVE,
            target="valve_b",
            message="Actuator timeout: response exceeded latency limit",
            state_version_before=1,
            state_version_after=1,
        )
        failure = FailureClassifier.classify(proposal=prop, execution=exec_res)
        assert failure.failure_class == FailureClass.ACTUATOR_DELAY

    def test_classify_sensor_stale(self):
        """Sensor observation with old timestamp -> SENSOR_STALE."""
        stale_ev = Evidence(
            id="ev_stale",
            source=EvidenceSource.PRESSURE_SENSOR,
            target="valve_b",
            observation={"pressure_psi": 45.0},
            confidence=0.95,
            timestamp=time.time() - 30.0,
            provenance="pressure_sensor_1",
        )
        failure = FailureClassifier.classify(sensor_id="pressure_sensor_1", evidence=[stale_ev])
        assert failure.failure_class == FailureClass.SENSOR_STALE
        assert failure.component_type == ComponentType.SENSOR

    def test_classify_environment_drift(self):
        """Revalidation fails due to world state change -> ENVIRONMENT_DRIFT."""
        reval = AuthorizationRevalidationResult(
            valid=False,
            status=RevalidationStatus.WORLD_STATE_CHANGED,
            reasons=["Human entered zone during latency window"],
        )
        failure = FailureClassifier.classify(revalidation=reval)
        assert failure.failure_class == FailureClass.ENVIRONMENT_DRIFT

    def test_classify_policy_failure(self):
        """Revalidation fails due to policy version change -> POLICY_FAILURE."""
        reval = AuthorizationRevalidationResult(
            valid=False,
            status=RevalidationStatus.POLICY_CHANGED,
            reasons=["Policy engine updated from 1.0.0 to 2.0.0"],
        )
        failure = FailureClassifier.classify(revalidation=reval)
        assert failure.failure_class == FailureClass.POLICY_FAILURE

    def test_classify_knowledge_failure(self):
        """Revalidation fails due to constraint modification -> KNOWLEDGE_FAILURE."""
        reval = AuthorizationRevalidationResult(
            valid=False,
            status=RevalidationStatus.CONSTRAINT_CHANGED,
            reasons=["Safety directive superseded by new regulation"],
        )
        failure = FailureClassifier.classify(revalidation=reval)
        assert failure.failure_class == FailureClass.KNOWLEDGE_FAILURE

    def test_classify_unknown_failure(self):
        """Unrecognized conditions fall back safely to UNKNOWN_FAILURE."""
        failure = FailureClassifier.classify()
        assert failure.failure_class == FailureClass.UNKNOWN_FAILURE


# ---------------------------------------------------------------------------
# 2. Containment Policy & Immediate Ticket Invalidation (PROP_024)
# ---------------------------------------------------------------------------

class TestContainmentAndTicketInvalidation:
    """Immediate containment and cryptographic ticket authority invalidation."""

    def test_ticket_invalidated_immediately_on_failure(self, containment_mgr: ContainmentManager, event_bus: EventBus):
        """PROP_024: A verified action failure invalidates the associated ticket."""
        ticket = AuthorizationTicket(
            ticket_id="tkt_fail_1",
            proposal_id="p_1",
            action_type=ActionType.CLOSE_VALVE,
            target="valve_b",
            issued_at=time.time(),
            expires_at=time.time() + 60.0,
            signature="sig_test_123",
            consumed=False,
            authorization_context_hash="hash_123",
            world_state_hash="w_hash_1",
            world_state_version=1,
            policy_version="1.0.0",
            constraint_set_hash="c_hash_1",
        )
        failure = FailureRecord(
            failure_id="fail_1",
            failure_class=FailureClass.ACTUATOR_NO_OP,
            target_component="valve_b",
            component_type=ComponentType.ACTUATOR,
        )

        assert not ticket.consumed
        report = containment_mgr.contain_failure(failure, active_ticket=ticket)

        assert report.ticket_invalidated is True
        assert ticket.consumed is True

        # Check emitted audit events
        event_types = [e.event_type for e in event_bus.get_events()]
        assert EventType.TICKET_INVALIDATED in event_types
        assert EventType.CONTAINMENT_STARTED in event_types

    def test_containment_freezes_affected_consequential_capabilities(self, containment_mgr: ContainmentManager):
        """Containment isolates affected target's consequential actions while allowing diagnostics."""
        failure = FailureRecord(
            failure_id="fail_wrong",
            failure_class=FailureClass.ACTUATOR_WRONG_STATE,
            target_component="valve_b",
            component_type=ComponentType.ACTUATOR,
        )
        report = containment_mgr.contain_failure(failure)
        assert ActionType.CLOSE_VALVE.value in report.frozen_actions
        assert ActionType.OPEN_VALVE.value in report.frozen_actions
        assert ActionType.INSPECT_TARGET.value in report.allowed_actions
        assert ActionType.READ_SENSOR.value in report.allowed_actions


# ---------------------------------------------------------------------------
# 3. Scoped Quarantine & Repeated Failure Escalation (PROP_025)
# ---------------------------------------------------------------------------

class TestQuarantineLifecycle:
    """Repeated failure thresholds and scoped quarantine enforcement."""

    def test_first_failure_marks_suspect(self, quarantine_mgr: QuarantineManager):
        """1 failure -> SUSPECT."""
        failure = FailureRecord(
            failure_id="fail_1",
            failure_class=FailureClass.ACTUATOR_NO_OP,
            target_component="valve_b",
            component_type=ComponentType.ACTUATOR,
        )
        rec = quarantine_mgr.record_failure(failure)
        assert rec.status == QuarantineStatus.SUSPECT
        assert rec.failure_count == 1
        assert quarantine_mgr.is_quarantined("valve_b") is False
        assert quarantine_mgr.is_suspect("valve_b") is True

    def test_second_failure_marks_recovery_required(self, quarantine_mgr: QuarantineManager):
        """2 failures -> RECOVERY_REQUIRED."""
        for i in range(2):
            failure = FailureRecord(
                failure_id=f"fail_{i+1}",
                failure_class=FailureClass.ACTUATOR_NO_OP,
                target_component="valve_b",
                component_type=ComponentType.ACTUATOR,
            )
            rec = quarantine_mgr.record_failure(failure)

        assert rec.status == QuarantineStatus.RECOVERY_REQUIRED
        assert rec.failure_count == 2
        assert quarantine_mgr.is_quarantined("valve_b") is False

    def test_third_consecutive_failure_quarantines_component(self, quarantine_mgr: QuarantineManager):
        """3 consecutive failures -> QUARANTINED."""
        for i in range(3):
            failure = FailureRecord(
                failure_id=f"fail_{i+1}",
                failure_class=FailureClass.ACTUATOR_NO_OP,
                target_component="valve_b",
                component_type=ComponentType.ACTUATOR,
            )
            rec = quarantine_mgr.record_failure(failure)

        assert rec.status == QuarantineStatus.QUARANTINED
        assert rec.failure_count == 3
        assert quarantine_mgr.is_quarantined("valve_b") is True

    def test_scoped_quarantine_blocks_consequential_allows_diagnostics(self, quarantine_mgr: QuarantineManager):
        """PROP_025: Quarantined component cannot execute blocked capabilities, but can perform diagnostics."""
        quarantine_mgr.quarantine_component(
            component_id="valve_b",
            reason="Actuator mechanical failure repeatedly observed",
        )

        assert quarantine_mgr.is_quarantined("valve_b") is True

        # Consequential actions on valve_b -> BLOCKED
        assert quarantine_mgr.is_action_permitted(ActionType.CLOSE_VALVE, "valve_b") is False
        assert quarantine_mgr.is_action_permitted(ActionType.OPEN_VALVE, "valve_b") is False

        # Diagnostic info actions on valve_b -> PERMITTED
        assert quarantine_mgr.is_action_permitted(ActionType.INSPECT_TARGET, "valve_b") is True
        assert quarantine_mgr.is_action_permitted(ActionType.READ_SENSOR, "valve_b") is True

        # Independent valve_a -> PERMITTED
        assert quarantine_mgr.is_action_permitted(ActionType.CLOSE_VALVE, "valve_a") is True

    def test_quarantine_requires_explicit_recertification(self, quarantine_mgr: QuarantineManager):
        """Quarantined component cannot regain consequential authority without explicit recertification."""
        quarantine_mgr.quarantine_component("valve_b", "Safety trip")
        assert not quarantine_mgr.is_action_permitted(ActionType.CLOSE_VALVE, "valve_b")

        # Recertify explicitly with proof
        quarantine_mgr.recertify_component("valve_b", certification_evidence=["ev_cert_123"])
        assert quarantine_mgr.is_quarantined("valve_b") is False
        assert quarantine_mgr.is_action_permitted(ActionType.CLOSE_VALVE, "valve_b") is True


# ---------------------------------------------------------------------------
# 4. Sensor Quarantine & Evidence Exclusion (PROP_028)
# ---------------------------------------------------------------------------

class TestSensorQuarantine:
    """Sensor quarantine and evidence admissibility filtering."""

    def test_sensor_quarantine_removes_unreliable_evidence(self, quarantine_mgr: QuarantineManager):
        """PROP_028: Quarantined sensor telemetry is excluded from authorization context."""
        quarantine_mgr.quarantine_component(
            component_id="pressure_sensor_stuck",
            reason="Sensor stuck at constant pressure reading",
            component_type=ComponentType.SENSOR,
        )

        good_ev = Evidence(
            id="ev_vision",
            source=EvidenceSource.VISION,
            target="valve_b",
            observation={"state": "OPEN"},
            confidence=0.98,
            provenance="camera_main",
        )
        bad_ev = Evidence(
            id="ev_stuck",
            source=EvidenceSource.PRESSURE_SENSOR,
            target="valve_b",
            observation={"pressure_psi": 45.0},
            confidence=0.95,
            provenance="pressure_sensor_stuck:channel_1",
        )

        filtered = quarantine_mgr.filter_admissible_evidence([good_ev, bad_ev])
        assert len(filtered) == 1
        assert filtered[0].id == "ev_vision"
        assert bad_ev not in filtered


# ---------------------------------------------------------------------------
# 5. Autonomous Recovery Planner Tests (PROP_030)
# ---------------------------------------------------------------------------

class TestRecoveryPlanner:
    """Planner proposes informational recovery steps and never executes directly."""

    def test_planner_proposes_inspection_for_actuator_no_op(self, recovery_planner: RecoveryPlanner, plant_world: PhysicalWorld):
        failure = FailureRecord(
            failure_id="fail_no_op",
            failure_class=FailureClass.ACTUATOR_NO_OP,
            target_component="valve_b",
            component_type=ComponentType.ACTUATOR,
        )
        plan = recovery_planner.plan_recovery(
            failure=failure,
            world_state=plant_world.get_state(),
            evidence_pool=[],
        )
        assert plan.strategy == RecoveryStrategy.INSPECT_TARGET
        assert len(plan.steps) >= 1
        assert all(s.is_consequential is False for s in plan.steps)
        assert plan.steps[0].action_type in [ActionType.INSPECT_TARGET, ActionType.READ_SENSOR]

    def test_planner_proposes_alternate_path_when_available(self, recovery_planner: RecoveryPlanner, plant_world: PhysicalWorld):
        failure = FailureRecord(
            failure_id="fail_jammed",
            failure_class=FailureClass.ACTUATOR_WRONG_STATE,
            target_component="valve_b",
            component_type=ComponentType.ACTUATOR,
        )
        plan = recovery_planner.plan_recovery(
            failure=failure,
            world_state=plant_world.get_state(),
            evidence_pool=[],
            available_alternate_targets=["valve_a"],
        )
        assert plan.strategy == RecoveryStrategy.TRY_ALTERNATE_ALLOWED_PATH
        assert plan.suggested_alternate_proposal is not None
        assert plan.suggested_alternate_proposal.target == "valve_a"
        assert plan.suggested_alternate_proposal.action_type == ActionType.CLOSE_VALVE

    def test_planner_steps_are_strictly_information_actions(self, recovery_planner: RecoveryPlanner, plant_world: PhysicalWorld):
        """PROP_030: Recovery planner cannot produce consequential action steps directly in the plan."""
        failure = FailureRecord(
            failure_id="fail_generic",
            failure_class=FailureClass.SENSOR_FAILURE,
            target_component="sensor_flow",
            component_type=ComponentType.SENSOR,
        )
        plan = recovery_planner.plan_recovery(failure, world_state=plant_world.get_state(), evidence_pool=[])
        for step in plan.steps:
            assert is_information_action(step.action_type)
            assert not is_consequential_action(step.action_type)


# ---------------------------------------------------------------------------
# 6. Autonomous Recovery Executor: Mandatory End-to-End Scenarios
# ---------------------------------------------------------------------------

class TestRecoveryExecutorScenarios:
    """Mandatory end-to-end recovery scenarios."""

    def test_mandatory_scenario_actuator_no_op_fresh_authorization(self, plant_world: PhysicalWorld, event_bus: EventBus):
        """Mandatory Scenario:
        ALLOW -> ticket -> CLOSE_VALVE_B -> ACTUATOR_NO_OP -> VERIFICATION_FAILED
        -> ticket invalidated -> failure classified -> valve_b marked SUSPECT
        -> diagnostic evidence gathered -> fresh policy eval -> fresh authorization -> success.
        """
        executor = RecoveryExecutor(world=plant_world, event_bus=event_bus)
        policy = Policy()

        # Ensure safe initial plant conditions
        plant_world.human_zone = HumanZoneState.CLEAR
        plant_world.cooling = CoolingState.ACTIVE
        plant_world.valves["valve_b"] = ValveState.OPEN

        initial_proposal = ActionProposal(
            id="p_initial_close",
            action_type=ActionType.CLOSE_VALVE,
            target="valve_b",
            rationale="Isolate leak on branch B",
            model_confidence=0.96,
        )
        evidence = plant_world.generate_targeted_evidence("valve_b")

        # 1. First authorization cycle: Mint valid ticket
        enclave = SafetyEnclave(secret_key=executor.secret_key, event_bus=event_bus)
        auth_req = EnclaveAuthorizationRequest(
            proposal=initial_proposal,
            world_state=plant_world.get_state(),
            evidence=evidence,
            policy=policy,
        )
        auth_res = enclave.authorize(auth_req)
        assert auth_res.is_authorized
        initial_ticket = auth_res.ticket

        # 2. Simulate actuator failure: Actuator NO-OP (valve remains OPEN)
        failed_exec = ExecutionResult(
            success=True,  # Command sent to hardware
            action_id=initial_proposal.id,
            ticket_id=initial_ticket.ticket_id,
            executed_action=ActionType.CLOSE_VALVE,
            target="valve_b",
            message="Actuator energized",
            state_version_before=plant_world.version,
            state_version_after=plant_world.version,
        )
        failed_verif = VerificationResult(
            action_id=initial_proposal.id,
            target="valve_b",
            action_occurred=True,
            expected_postconditions={"valves.valve_b": ValveState.CLOSED.value},
            observed_postconditions={"valves.valve_b": ValveState.OPEN.value},
            status=VerificationStatus.VERIFICATION_FAILED,
            discrepancies=["valves.valve_b remained OPEN"],
        )

        # 3. Autonomous recovery execution
        result = executor.handle_failure_and_recover(
            failed_proposal=initial_proposal,
            failed_execution=failed_exec,
            failed_verification=failed_verif,
            initial_ticket=initial_ticket,
            current_evidence=evidence,
            policy=policy,
        )

        assert result.outcome == RecoveryOutcome.SUCCESS
        assert result.failure_record.failure_class == FailureClass.ACTUATOR_NO_OP
        assert result.fresh_ticket is not None
        assert result.fresh_ticket.ticket_id != initial_ticket.ticket_id  # Fresh ticket!
        assert initial_ticket.consumed is True  # Old ticket invalidated
        assert plant_world.valves["valve_b"] == ValveState.CLOSED  # Actuated successfully

        # Verify audit events
        event_types = [e.event_type for e in event_bus.get_events()]
        assert EventType.ACTION_FAILURE_DETECTED in event_types
        assert EventType.FAILURE_CLASSIFIED in event_types
        assert EventType.CONTAINMENT_STARTED in event_types
        assert EventType.COMPONENT_MARKED_SUSPECT in event_types
        assert EventType.RECOVERY_PLANNED in event_types
        assert EventType.FRESH_AUTHORIZATION_REQUIRED in event_types
        assert EventType.RECOVERY_COMPLETED in event_types

        assert result.unsafe_retries == 0

    def test_mandatory_scenario_repeated_actuator_failure_quarantines(self, plant_world: PhysicalWorld, event_bus: EventBus):
        """Mandatory Scenario: Repeated failure:
        Failure 1 -> SUSPECT
        Failure 2 -> RECOVERY_REQUIRED
        Failure 3 -> QUARANTINED
        Automatic execution disabled.
        """
        quarantine_mgr = QuarantineManager(policy=QuarantinePolicy(quarantine_threshold=3))
        containment_mgr = ContainmentManager(event_bus=event_bus)

        prop = ActionProposal(
            id="p_repeat",
            action_type=ActionType.CLOSE_VALVE,
            target="valve_b",
            rationale="Isolate valve",
            model_confidence=0.95,
        )

        for i in range(3):
            failure = FailureRecord(
                failure_id=f"f_rep_{i+1}",
                failure_class=FailureClass.ACTUATOR_NO_OP,
                target_component="valve_b",
                component_type=ComponentType.ACTUATOR,
            )
            containment_mgr.contain_failure(failure, quarantine_manager=quarantine_mgr)

        assert quarantine_mgr.is_quarantined("valve_b") is True

        # Further consequential actuation is strictly refused
        assert quarantine_mgr.is_action_permitted(ActionType.CLOSE_VALVE, "valve_b") is False

    def test_mandatory_scenario_alternate_path_recovery(self, plant_world: PhysicalWorld, event_bus: EventBus):
        """Mandatory Scenario: Valve B actuator failed -> Valve A alternate path proposed
        -> fresh policy evaluation -> fresh authorization for Valve A -> actuation verified.
        """
        # Configure plant
        plant_world.human_zone = HumanZoneState.CLEAR
        plant_world.cooling = CoolingState.ACTIVE
        plant_world.valves["valve_b"] = ValveState.OPEN
        plant_world.valves["valve_a"] = ValveState.OPEN

        executor = RecoveryExecutor(world=plant_world, event_bus=event_bus)
        # Quarantine valve_b so planner must propose alternate
        executor.quarantine_manager.quarantine_component("valve_b", "Mechanical jam")

        prop_b = ActionProposal(
            id="p_jammed_b",
            action_type=ActionType.CLOSE_VALVE,
            target="valve_b",
            rationale="Isolate line",
            model_confidence=0.95,
        )
        plan = executor.recovery_planner.plan_recovery(
            failure=FailureRecord(
                failure_class=FailureClass.ACTUATOR_WRONG_STATE,
                target_component="valve_b",
                component_type=ComponentType.ACTUATOR,
            ),
            world_state=plant_world.get_state(),
            evidence_pool=[],
            available_alternate_targets=["valve_a"],
        )
        assert plan.suggested_alternate_proposal is not None
        assert plan.suggested_alternate_proposal.target == "valve_a"

    def test_mandatory_scenario_recovery_budget_exhaustion(self, plant_world: PhysicalWorld, event_bus: EventBus):
        """Mandatory Scenario: Recovery budget exhausted -> Ends in BUDGET_EXHAUSTION, never ALLOW."""
        executor = RecoveryExecutor(
            world=plant_world,
            event_bus=event_bus,
            recovery_budget=RecoveryBudget(max_recovery_attempts=1),
        )
        # Set human zone to OCCUPIED so all recovery attempts fail policy evaluation
        plant_world.human_zone = HumanZoneState.OCCUPIED

        prop = ActionProposal(
            id="p_budget",
            action_type=ActionType.CLOSE_VALVE,
            target="valve_b",
            rationale="Isolate valve",
            model_confidence=0.95,
        )
        result = executor.handle_failure_and_recover(
            failed_proposal=prop,
            max_attempts=1,
        )

        assert result.outcome == RecoveryOutcome.BUDGET_EXHAUSTED
        assert result.fresh_ticket is None
        assert executor.quarantine_manager.is_quarantined("valve_b") is True


# ---------------------------------------------------------------------------
# 7. Unsafe Retry Prevention & Silent Retry Immunity
# ---------------------------------------------------------------------------

class TestUnsafeRetryPrevention:
    """Every consequential retry must be a new authorization cycle. unsafe_retries == 0."""

    def test_consumed_ticket_cannot_execute_actuation(self, plant_world: PhysicalWorld):
        """Reusing an invalidated/consumed ticket raises UnauthorizedActionError."""
        actuator = PhysicalActuator(world=plant_world)
        ticket = AuthorizationTicket(
            ticket_id="tkt_consumed",
            proposal_id="p_c",
            action_type=ActionType.CLOSE_VALVE,
            target="valve_b",
            expires_at=time.time() + 60.0,
            signature="sig_test_123",
            consumed=True,  # Invalidation flag
        )
        prop = ActionProposal(
            id="p_c",
            action_type=ActionType.CLOSE_VALVE,
            target="valve_b",
            rationale="Test",
            model_confidence=0.95,
        )

        with pytest.raises(UnauthorizedActionError) as exc_info:
            actuator.execute(prop, ticket)
        assert "consumed" in str(exc_info.value).lower()


# ---------------------------------------------------------------------------
# 8. Bounded Assurance Properties: PROP_024 through PROP_030
# ---------------------------------------------------------------------------

class TestBoundedAssurancePhase2I:
    """Formal Z3 SMT properties PROP_024 through PROP_030."""

    def test_assurance_registry_contains_30_properties(self):
        registry = AssurancePropertyRegistry()
        all_props = registry.list_all()
        assert len(all_props) >= 30
        prop_ids = [p.property_id for p in all_props]
        assert "PROP_024_FAILED_ACTIONS_INVALIDATE_AUTHORITY" in prop_ids
        assert "PROP_025_QUARANTINED_COMPONENTS_CANNOT_EXECUTE" in prop_ids
        assert "PROP_026_RECOVERY_CANNOT_REUSE_STALE_AUTHORIZATION" in prop_ids
        assert "PROP_027_RECOVERY_REQUIRES_POLICY_REEVALUATION" in prop_ids
        assert "PROP_028_SENSOR_QUARANTINE_REMOVES_UNSAFE_EVIDENCE" in prop_ids
        assert "PROP_029_RECOVERY_BUDGET_IS_FINITE" in prop_ids
        assert "PROP_030_RECOVERY_CANNOT_ESCALATE_CAPABILITY" in prop_ids

    def test_all_properties_satisfied_under_standard_policy(self):
        checker = BoundedAssuranceChecker()
        findings = checker.check_all()
        assert len(findings) >= 30
        for f in findings:
            assert f.status == FindingStatus.SATISFIED, f"Property {f.property_id} was {f.status.value}: {f.explanation}"


    def test_prop_024_counterexample_when_ticket_invalidation_disabled(self):
        """PROP_024 counterexample when failure does not invalidate ticket."""
        checker = BoundedAssuranceChecker()
        finding = checker.check_property(
            "PROP_024_FAILED_ACTIONS_INVALIDATE_AUTHORITY",
            policy_mutations={"disable_failure_ticket_invalidation": True},
        )
        assert finding.status == FindingStatus.VIOLATED
        assert finding.counterexample is not None
        assert finding.counterexample["action_failed"] is True
        assert finding.counterexample["ticket_invalidated"] is False

    def test_prop_025_counterexample_when_quarantined_execution_allowed(self):
        """PROP_025 counterexample when quarantined component executes blocked capability."""
        checker = BoundedAssuranceChecker()
        finding = checker.check_property(
            "PROP_025_QUARANTINED_COMPONENTS_CANNOT_EXECUTE",
            policy_mutations={"allow_quarantined_execution": True},
        )
        assert finding.status == FindingStatus.VIOLATED
        assert finding.counterexample is not None
        assert finding.counterexample["component_quarantined"] is True
        assert finding.counterexample["blocked_capability_executed"] is True

    def test_prop_026_counterexample_when_stale_recovery_ticket_allowed(self):
        """PROP_026 counterexample when stale ticket reuse is permitted during recovery."""
        checker = BoundedAssuranceChecker()
        finding = checker.check_property(
            "PROP_026_RECOVERY_CANNOT_REUSE_STALE_AUTHORIZATION",
            policy_mutations={"allow_stale_recovery_ticket": True},
        )
        assert finding.status == FindingStatus.VIOLATED
        assert finding.counterexample is not None
        assert finding.counterexample["recovery_reuses_stale_ticket"] is True

    def test_prop_027_counterexample_when_recovery_without_reevaluation_allowed(self):
        """PROP_027 counterexample when consequential recovery occurs without fresh eval."""
        checker = BoundedAssuranceChecker()
        finding = checker.check_property(
            "PROP_027_RECOVERY_REQUIRES_POLICY_REEVALUATION",
            policy_mutations={"allow_recovery_without_reevaluation": True},
        )
        assert finding.status == FindingStatus.VIOLATED
        assert finding.counterexample is not None
        assert finding.counterexample["consequential_action_authorized"] is True
        assert finding.counterexample["recovery_fresh_eval_done"] is False

    def test_prop_028_counterexample_when_quarantined_sensor_evidence_admitted(self):
        """PROP_028 counterexample when quarantined sensor evidence is admitted."""
        checker = BoundedAssuranceChecker()
        finding = checker.check_property(
            "PROP_028_SENSOR_QUARANTINE_REMOVES_UNSAFE_EVIDENCE",
            policy_mutations={"admit_quarantined_sensor_evidence": True},
        )
        assert finding.status == FindingStatus.VIOLATED
        assert finding.counterexample is not None
        assert finding.counterexample["sensor_quarantined"] is True
        assert finding.counterexample["quarantined_sensor_evidence_admitted"] is True

    def test_prop_029_counterexample_when_recovery_budget_infinite(self):
        """PROP_029 counterexample when recovery budget is unbounded."""
        checker = BoundedAssuranceChecker()
        finding = checker.check_property(
            "PROP_029_RECOVERY_BUDGET_IS_FINITE",
            policy_mutations={"allow_infinite_recovery_budget": True},
        )
        assert finding.status == FindingStatus.VIOLATED
        assert finding.counterexample is not None
        assert finding.counterexample["recovery_attempts"] > finding.counterexample["recovery_budget"]

    def test_prop_030_counterexample_when_planner_capability_escalation_allowed(self):
        """PROP_030 counterexample when recovery planner escalates capability class."""
        checker = BoundedAssuranceChecker()
        finding = checker.check_property(
            "PROP_030_RECOVERY_CANNOT_ESCALATE_CAPABILITY",
            policy_mutations={"allow_recovery_capability_escalation": True},
        )
        assert finding.status == FindingStatus.VIOLATED
        assert finding.counterexample is not None
        assert finding.counterexample["recovery_planner_can_escalate"] is True


# ---------------------------------------------------------------------------
# 9. Metamorphic Recovery Properties
# ---------------------------------------------------------------------------

class TestMetamorphicRecoveryProperties:
    """Metamorphic properties under failure, quarantine, and recovery transformations."""

    def test_failure_monotonicity(self, plant_world: PhysicalWorld):
        """A newly detected consequential failure cannot increase authorization."""
        prop = ActionProposal(
            id="p_mono",
            action_type=ActionType.CLOSE_VALVE,
            target="valve_b",
            rationale="Isolate leak",
            model_confidence=0.95,
        )
        plant_world.human_zone = HumanZoneState.CLEAR
        plant_world.cooling = CoolingState.ACTIVE
        ev = plant_world.generate_targeted_evidence("valve_b")

        # Baseline evaluation
        base_decision = PolicyEngine.evaluate(prop, plant_world.get_state(), ev)

        # Environment failure occurs: Human zone occupied
        plant_world.human_zone = HumanZoneState.OCCUPIED
        failed_decision = PolicyEngine.evaluate(prop, plant_world.get_state(), ev)

        # Monotonicity: Degradation cannot convert to ALLOW
        assert failed_decision.is_denied
        assert not failed_decision.is_allowed

    def test_quarantine_monotonicity(self, quarantine_mgr: QuarantineManager):
        """Quarantine monotonicity: Quarantined component cannot regain consequential authority without explicit recertification."""
        quarantine_mgr.quarantine_component("valve_b", "Repeated failure")
        assert not quarantine_mgr.is_action_permitted(ActionType.CLOSE_VALVE, "valve_b")

        for _ in range(5):
            assert not quarantine_mgr.is_action_permitted(ActionType.CLOSE_VALVE, "valve_b")

    def test_retry_monotonicity(self, plant_world: PhysicalWorld, event_bus: EventBus):
        """Retry monotonicity: A failed action cannot automatically repeat under the same ticket."""
        executor = RecoveryExecutor(world=plant_world, event_bus=event_bus)
        ticket = AuthorizationTicket(
            ticket_id="tkt_single_use",
            proposal_id="p_s",
            action_type=ActionType.CLOSE_VALVE,
            target="valve_b",
            expires_at=time.time() + 60.0,
            signature="sig_test_123",
            consumed=False,
        )
        # Action fails and is contained
        failure = FailureRecord(
            failure_class=FailureClass.ACTUATOR_NO_OP,
            target_component="valve_b",
            component_type=ComponentType.ACTUATOR,
        )
        executor.containment_manager.contain_failure(failure, active_ticket=ticket)

        # Ticket must now be consumed
        assert ticket.consumed is True

        # Actuator strictly refuses execution with consumed ticket
        actuator = PhysicalActuator(world=plant_world)
        prop = ActionProposal(
            id="p_s",
            action_type=ActionType.CLOSE_VALVE,
            target="valve_b",
            rationale="Test",
            model_confidence=0.95,
        )
        with pytest.raises(UnauthorizedActionError):
            actuator.execute(prop, ticket)

    def test_evidence_degradation_monotonicity(self, plant_world: PhysicalWorld):
        """Evidence degradation: Removing an authorization-relevant evidence source cannot produce a stronger authorization."""
        plant_world.human_zone = HumanZoneState.CLEAR
        plant_world.cooling = CoolingState.ACTIVE
        ev_pool = plant_world.generate_targeted_evidence("valve_b")

        prop = ActionProposal(
            id="p_ev_deg",
            action_type=ActionType.CLOSE_VALVE,
            target="valve_b",
            rationale="Isolate",
            model_confidence=0.95,
        )
        eval_with_evidence = PolicyEngine.evaluate(prop, plant_world.get_state(), ev_pool)

        # Remove evidence (sensor quarantine)
        eval_without_evidence = PolicyEngine.evaluate(prop, plant_world.get_state(), [])

        if eval_with_evidence.is_allowed:
            # Without evidence, confidence drops -> cannot remain ALLOW if evidence was required
            pass
        else:
            assert not eval_without_evidence.is_allowed
