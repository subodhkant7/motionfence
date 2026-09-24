"""Comprehensive test suite for Phase 2M Mock Physical Hardware Endpoint & Actuator Boundary.

Verifies:
1. Valid ticket actuates physical system.
2. Missing ticket locks actuator.
3. Invalid cryptographic signature locks actuator.
4. Expired ticket locks actuator.
5. Target mismatch locks actuator.
6. Action mismatch locks actuator.
7. Replayed/consumed ticket locks actuator (single-use semantics).
8. Stale world-bound ticket cannot actuate.
9. Hardware NO_OP produces verification failure in PostActionVerifier.
10. Partial actuation produces correct telemetry observation and verification failure.
11. Wrong final state produces verification failure.
12. Hardware endpoint cannot mint tickets (zero minting authority).
13. Hardware endpoint cannot modify safety policies (zero policy authority).
14. Hardware endpoint cannot bypass SafetyEnclave.
15. Hardware events appear in audit event stream.
16. DecisionRecord integrates hardware execution record.
17. Hardware event replay is deterministic and side-effect free.
18. No secret material appears in hardware execution records or events.
19. Z3 formal bounded assurance properties PROP_045 through PROP_051 verified.
"""

import time
import pytest

from motionfence.models.actions import (
    ActionProposal,
    ActionType,
    AuthorizationTicket,
    ExecutionResult,
)
from motionfence.models.world import WorldState, ValveState, CoolingState, HumanZoneState
from motionfence.models.events import EventType
from motionfence.simulation.world import PhysicalWorld
from motionfence.simulation.actuator import PhysicalActuator
from motionfence.runtime.events import EventBus
from motionfence.runtime.ticket import TicketAuthority
from motionfence.runtime.verification import PostActionVerifier, VerificationStatus
from motionfence.runtime.core import MotionFenceRuntime
from motionfence.hardware.models import (
    ActuatorType,
    HardwareExecutionRecord,
    HardwareExecutionStatus,
    HardwareFaultType,
)
from motionfence.hardware.mock import MockHardwareEndpoint
from motionfence.hardware.validation import HardwareTicketValidator
from motionfence.assurance.invariants import AssurancePropertyRegistry
from motionfence.assurance.checker import BoundedAssuranceChecker, FindingStatus


@pytest.fixture
def test_world():
    world = PhysicalWorld()
    world.valves["valve_b"] = ValveState.OPEN
    world.set_pump_state("pump_p1", "INACTIVE")
    world.cooling = CoolingState.ACTIVE
    world.set_human_zone(HumanZoneState.CLEAR)
    world.leak.active = True
    world.leak.target = "valve_b"
    world.leak.flow_rate_lpm = 14.2
    world.leak.severity = 0.85
    return world


@pytest.fixture
def ticket_auth():
    return TicketAuthority(secret_key="motionfence_runtime_kernel_secret")


@pytest.fixture
def valid_proposal():
    return ActionProposal(
        id="prop_test_001",
        action_type=ActionType.CLOSE_VALVE,
        target="valve_b",
        parameters={},
        rationale="Isolate verified leaking line.",
        model_confidence=0.96,
    )


@pytest.fixture
def valid_ticket(ticket_auth, valid_proposal, test_world):
    return ticket_auth.mint_ticket(
        proposal=valid_proposal,
        ttl_seconds=30.0,
        world_state=test_world.get_state(),
    )


class TestMockHardwareBoundary:
    """Core hardware-boundary enforcement and state transition tests."""

    def test_valid_ticket_actuates(self, test_world, valid_proposal, valid_ticket):
        """1. A valid, unconsumed AuthorizationTicket successfully commands actuation."""
        event_bus = EventBus()
        endpoint = MockHardwareEndpoint(world=test_world, event_bus=event_bus)

        record = endpoint.receive_and_actuate(proposal=valid_proposal, ticket=valid_ticket)

        assert record.execution_status == HardwareExecutionStatus.ACTUATED
        assert record.is_actuated is True
        assert record.ticket_status == "VALID"
        assert record.signature_status == "VALID"
        assert record.target == "valve_b"
        assert test_world.valves["valve_b"] == ValveState.CLOSED
        assert test_world.leak.active is False
        assert valid_ticket.consumed is True

    def test_no_ticket_locks_actuator(self, test_world, valid_proposal):
        """2. Presentation of a raw proposal without a ticket strictly locks the actuator."""
        endpoint = MockHardwareEndpoint(world=test_world)

        record = endpoint.receive_and_actuate(proposal=valid_proposal, ticket=None)

        assert record.execution_status == HardwareExecutionStatus.LOCKED
        assert record.is_actuated is False
        assert endpoint.is_locked is True
        assert test_world.valves["valve_b"] == ValveState.OPEN  # Zero physical mutation
        assert "No AuthorizationTicket presented" in record.message

    def test_invalid_signature_locks_actuator(self, test_world, valid_proposal, valid_ticket):
        """3. An invalid cryptographic signature strictly locks the actuator."""
        endpoint = MockHardwareEndpoint(world=test_world)
        # Tamper with the HMAC signature
        valid_ticket.signature = "ffffffffffffffffffffffffffffffffffffffffffffffffffffffffffffffff"

        record = endpoint.receive_and_actuate(proposal=valid_proposal, ticket=valid_ticket)

        assert record.execution_status == HardwareExecutionStatus.INVALID_TICKET
        assert endpoint.is_locked is True
        assert test_world.valves["valve_b"] == ValveState.OPEN
        assert "Invalid cryptographic signature" in record.message

    def test_expired_ticket_locks_actuator(self, test_world, valid_proposal, valid_ticket):
        """4. An expired ticket is rejected and actuator locked."""
        endpoint = MockHardwareEndpoint(world=test_world)
        valid_ticket.expires_at = time.time() - 10.0  # Expired 10 seconds ago

        record = endpoint.receive_and_actuate(proposal=valid_proposal, ticket=valid_ticket)

        assert record.execution_status == HardwareExecutionStatus.EXPIRED_TICKET
        assert endpoint.is_locked is True
        assert test_world.valves["valve_b"] == ValveState.OPEN
        assert "expired" in record.message

    def test_target_mismatch_locks_actuator(self, test_world, valid_ticket):
        """5. Mismatch between ticket target and requested target locks actuator."""
        endpoint = MockHardwareEndpoint(world=test_world)
        mismatched_proposal = ActionProposal(
            id="prop_mismatch_001",
            action_type=ActionType.CLOSE_VALVE,
            target="valve_c",  # Ticket was minted for valve_b
            parameters={},
            rationale="Tampered target request.",
            model_confidence=0.96,
        )

        record = endpoint.receive_and_actuate(proposal=mismatched_proposal, ticket=valid_ticket)

        assert record.execution_status == HardwareExecutionStatus.TARGET_MISMATCH
        assert endpoint.is_locked is True
        assert test_world.valves["valve_b"] == ValveState.OPEN
        assert "Target mismatch" in record.message

    def test_action_mismatch_locks_actuator(self, test_world, valid_ticket):
        """6. Mismatch between ticket action and requested action locks actuator."""
        endpoint = MockHardwareEndpoint(world=test_world)
        mismatched_proposal = ActionProposal(
            id="prop_mismatch_002",
            action_type=ActionType.OPEN_VALVE,  # Ticket authorizes CLOSE_VALVE
            target="valve_b",
            parameters={},
            rationale="Tampered action request.",
            model_confidence=0.96,
        )

        record = endpoint.receive_and_actuate(proposal=mismatched_proposal, ticket=valid_ticket)

        assert record.execution_status == HardwareExecutionStatus.ACTION_MISMATCH
        assert endpoint.is_locked is True
        assert test_world.valves["valve_b"] == ValveState.OPEN
        assert "Action mismatch" in record.message

    def test_replayed_ticket_locks_actuator(self, test_world, valid_proposal, valid_ticket):
        """7. Second presentation of an already consumed ticket is rejected as REPLAYED_TICKET."""
        endpoint = MockHardwareEndpoint(world=test_world)

        # First presentation: Success
        rec1 = endpoint.receive_and_actuate(proposal=valid_proposal, ticket=valid_ticket)
        assert rec1.execution_status == HardwareExecutionStatus.ACTUATED
        assert test_world.valves["valve_b"] == ValveState.CLOSED

        # Reset valve physically to open to test if second presentation can mutate
        test_world.valves["valve_b"] = ValveState.OPEN
        endpoint.unlock()

        # Second presentation: Replay rejection
        rec2 = endpoint.receive_and_actuate(proposal=valid_proposal, ticket=valid_ticket)
        assert rec2.execution_status == HardwareExecutionStatus.REPLAYED_TICKET
        assert endpoint.is_locked is True
        assert test_world.valves["valve_b"] == ValveState.OPEN  # Must NOT close again
        assert "already been consumed" in rec2.message

    def test_stale_world_bound_ticket_cannot_actuate(self, test_world, valid_proposal, ticket_auth):
        """8. Ticket bound to world version 1 cannot actuate when world version drifts to 2."""
        endpoint = MockHardwareEndpoint(world=test_world)
        # Mint ticket at current world state (version 1)
        ticket = ticket_auth.mint_ticket(
            proposal=valid_proposal,
            ttl_seconds=30.0,
            world_state=test_world.get_state(),
        )
        assert ticket.world_state_version == test_world.version

        # Simulate environmental state drift (version increments to 2)
        test_world.set_human_zone(HumanZoneState.OCCUPIED)
        assert test_world.version > ticket.world_state_version

        # Present ticket with drifted world state
        record = endpoint.receive_and_actuate(proposal=valid_proposal, ticket=ticket)

        assert record.execution_status == HardwareExecutionStatus.INVALID_TICKET
        assert endpoint.is_locked is True
        assert test_world.valves["valve_b"] == ValveState.OPEN
        assert "Stale authorization context" in record.message


class TestHardwareFaultSimulation:
    """Deterministic hardware fault simulation feeding existing verification pipeline."""

    def test_hardware_noop_produces_verification_failure(self, test_world, valid_proposal, valid_ticket):
        """9. NO_OP fault: Command accepted, but physical valve does not move; verification fails."""
        endpoint = MockHardwareEndpoint(world=test_world)
        endpoint.inject_fault(HardwareFaultType.NO_OP)

        pre_state = test_world.get_state()
        record = endpoint.receive_and_actuate(proposal=valid_proposal, ticket=valid_ticket)

        assert record.execution_status == HardwareExecutionStatus.HARDWARE_FAULT
        assert test_world.valves["valve_b"] == ValveState.OPEN  # Valve stayed open
        post_state = test_world.get_state()

        exec_res = ExecutionResult(
            success=False,
            action_id=valid_proposal.id,
            ticket_id=valid_ticket.ticket_id,
            executed_action=valid_proposal.action_type,
            target=valid_proposal.target,
            message=record.message,
            state_version_before=pre_state.version,
            state_version_after=post_state.version,
            timestamp=record.timestamp,
        )

        verification = PostActionVerifier.verify(
            proposal=valid_proposal,
            execution=exec_res,
            pre_state=pre_state,
            post_state=post_state,
        )

        assert verification.status == VerificationStatus.VERIFICATION_FAILED
        assert any("mismatch" in d.lower() or "failed" in d.lower() for d in verification.discrepancies)

    def test_partial_actuation_produces_correct_observation(self, test_world, valid_proposal, valid_ticket):
        """10. PARTIAL_ACTUATION: Valve strokes partially (seal unseated), observed flow rate reflects partial seal."""
        endpoint = MockHardwareEndpoint(world=test_world)
        endpoint.inject_fault(HardwareFaultType.PARTIAL_ACTUATION)

        pre_state = test_world.get_state()
        record = endpoint.receive_and_actuate(proposal=valid_proposal, ticket=valid_ticket)

        assert record.execution_status == HardwareExecutionStatus.HARDWARE_FAULT
        assert test_world.valves["valve_b"] == ValveState.OPEN
        assert test_world.leak.flow_rate_lpm == 7.1  # 50% reduced flow observed
        post_state = test_world.get_state()

        exec_res = ExecutionResult(
            success=False,
            action_id=valid_proposal.id,
            ticket_id=valid_ticket.ticket_id,
            executed_action=valid_proposal.action_type,
            target=valid_proposal.target,
            message=record.message,
            state_version_before=pre_state.version,
            state_version_after=post_state.version,
            timestamp=record.timestamp,
        )

        verification = PostActionVerifier.verify(
            proposal=valid_proposal,
            execution=exec_res,
            pre_state=pre_state,
            post_state=post_state,
        )
        assert verification.status == VerificationStatus.VERIFICATION_FAILED

    def test_wrong_final_state_produces_verification_failure(self, test_world, valid_proposal, valid_ticket):
        """11. WRONG_FINAL_STATE: Actuator moves to inverted position; verification catches mismatch."""
        endpoint = MockHardwareEndpoint(world=test_world)
        endpoint.inject_fault(HardwareFaultType.WRONG_FINAL_STATE)

        pre_state = test_world.get_state()
        record = endpoint.receive_and_actuate(proposal=valid_proposal, ticket=valid_ticket)

        assert record.execution_status == HardwareExecutionStatus.HARDWARE_FAULT
        assert test_world.valves["valve_b"] == ValveState.OPEN  # Did not close
        post_state = test_world.get_state()

        exec_res = ExecutionResult(
            success=False,
            action_id=valid_proposal.id,
            ticket_id=valid_ticket.ticket_id,
            executed_action=valid_proposal.action_type,
            target=valid_proposal.target,
            message=record.message,
            state_version_before=pre_state.version,
            state_version_after=post_state.version,
            timestamp=record.timestamp,
        )

        verification = PostActionVerifier.verify(
            proposal=valid_proposal,
            execution=exec_res,
            pre_state=pre_state,
            post_state=post_state,
        )
        assert verification.status == VerificationStatus.VERIFICATION_FAILED


class TestHardwareSecurityBoundary:
    """Authority isolation tests asserting hardware endpoint cannot grant itself permissions."""

    def test_hardware_cannot_mint_tickets(self, test_world):
        """12. Hardware endpoint has ZERO ticket minting methods."""
        endpoint = MockHardwareEndpoint(world=test_world)
        assert not hasattr(endpoint, "mint_ticket")
        assert not hasattr(endpoint, "create_ticket")
        assert not hasattr(endpoint, "authorize")

    def test_hardware_cannot_modify_policy(self, test_world):
        """13. Hardware endpoint has ZERO policy authoring or mutation methods."""
        endpoint = MockHardwareEndpoint(world=test_world)
        assert not hasattr(endpoint, "set_policy")
        assert not hasattr(endpoint, "mutate_policy")
        assert not hasattr(endpoint, "override_safety_rule")

    def test_hardware_cannot_call_enclave_to_create_authority(self, test_world):
        """14. Hardware endpoint does not hold a reference to SafetyEnclave or signing keys."""
        endpoint = MockHardwareEndpoint(world=test_world)
        assert not hasattr(endpoint, "safety_enclave")
        assert not hasattr(endpoint, "_safety_enclave")
        assert not hasattr(endpoint, "secret_key")  # Private validator encapsulation

    def test_hardware_events_appear_in_audit_trail(self, test_world, valid_proposal, valid_ticket):
        """15. Hardware events appear in the central EventBus audit stream."""
        event_bus = EventBus()
        endpoint = MockHardwareEndpoint(world=test_world, event_bus=event_bus)

        events_captured = []
        event_bus.subscribe(lambda e: events_captured.append(e))

        endpoint.receive_and_actuate(proposal=valid_proposal, ticket=valid_ticket)

        event_types = [e.event_type for e in events_captured]
        assert EventType.HARDWARE_TICKET_RECEIVED in event_types
        assert EventType.HARDWARE_TICKET_VALIDATED in event_types
        assert EventType.HARDWARE_ACTUATION_STARTED in event_types
        assert EventType.HARDWARE_ACTUATION_COMPLETED in event_types
        assert EventType.HARDWARE_OBSERVATION_RECORDED in event_types

    def test_decision_record_references_hardware_execution(self, test_world):
        """16. MotionFenceRuntime cycle populates DecisionRecord with hardware execution references."""
        runtime = MotionFenceRuntime(world=test_world)

        cycle = runtime.run_cycle(
            intent="Isolate coolant leak on valve_b",
            initial_evidence=test_world.generate_targeted_evidence("valve_b"),
        )

        assert cycle.is_success is True
        assert cycle.hardware_execution is not None
        assert cycle.hardware_execution.execution_status == HardwareExecutionStatus.ACTUATED
        assert cycle.decision_record is not None
        assert cycle.decision_record.hardware_execution_id == cycle.hardware_execution.record_id
        assert cycle.decision_record.hardware_status == "ACTUATED"

    def test_no_secret_material_appears_in_records_or_events(self, test_world, valid_proposal, valid_ticket):
        """18. Secrets (HMAC key, kernel secret) never appear in serialized records or events."""
        event_bus = EventBus()
        endpoint = MockHardwareEndpoint(world=test_world, event_bus=event_bus)

        events_captured = []
        event_bus.subscribe(lambda e: events_captured.append(e))

        record = endpoint.receive_and_actuate(proposal=valid_proposal, ticket=valid_ticket)

        rec_dump = record.model_dump_json()
        assert "motionfence_runtime_kernel_secret" not in rec_dump
        assert "secret_key" not in rec_dump

        for evt in events_captured:
            evt_dump = evt.model_dump_json()
            assert "motionfence_runtime_kernel_secret" not in evt_dump
            assert "secret_key" not in evt_dump


class TestBoundedAssurancePhase2M:
    """Formal Z3 SMT properties PROP_045 through PROP_051 for Phase 2M."""

    def test_registry_contains_51_properties(self):
        """Registry must contain all 51 formal properties (44 existing + 7 Phase 2M)."""
        registry = AssurancePropertyRegistry()
        all_props = registry.list_all()
        assert len(all_props) == 51

        prop_ids = [p.property_id for p in all_props]
        assert "PROP_045_HARDWARE_CANNOT_ACTUATE_WITHOUT_AUTHORIZATION" in prop_ids
        assert "PROP_046_INVALID_TICKET_CANNOT_ACTUATE" in prop_ids
        assert "PROP_047_EXPIRED_TICKET_CANNOT_ACTUATE" in prop_ids
        assert "PROP_048_REPLAYED_TICKET_CANNOT_ACTUATE" in prop_ids
        assert "PROP_049_TARGET_MISMATCH_CANNOT_ACTUATE" in prop_ids
        assert "PROP_050_ACTION_MISMATCH_CANNOT_ACTUATE" in prop_ids
        assert "PROP_051_STALE_AUTHORIZATION_CANNOT_ACTUATE" in prop_ids

    def test_all_51_properties_satisfied_under_standard_policy(self):
        """Z3 proves all 51 properties SATISFIED under standard deterministic policy rules."""
        checker = BoundedAssuranceChecker()
        findings = checker.check_all()
        assert len(findings) == 51
        for f in findings:
            assert f.status == FindingStatus.SATISFIED, f"Property {f.property_id} was {f.status.value}: {f.explanation}"

    def test_prop_045_counterexample_when_unauthorized_actuation_allowed(self):
        """PROP_045 counterexample discovered if unauthorized actuation is permitted."""
        checker = BoundedAssuranceChecker()
        finding = checker.check_property(
            "PROP_045_HARDWARE_CANNOT_ACTUATE_WITHOUT_AUTHORIZATION",
            policy_mutations={"allow_hardware_unauthorized_actuation": True},
        )
        assert finding.status == FindingStatus.VIOLATED
        assert finding.counterexample is not None

    def test_prop_046_counterexample_when_invalid_ticket_actuation_allowed(self):
        """PROP_046 counterexample discovered if invalid ticket actuation is permitted."""
        checker = BoundedAssuranceChecker()
        finding = checker.check_property(
            "PROP_046_INVALID_TICKET_CANNOT_ACTUATE",
            policy_mutations={"allow_hardware_unauthorized_actuation": True},
        )
        assert finding.status == FindingStatus.VIOLATED

    def test_prop_047_counterexample_when_expired_ticket_actuation_allowed(self):
        """PROP_047 counterexample discovered if expired ticket actuation is permitted."""
        checker = BoundedAssuranceChecker()
        finding = checker.check_property(
            "PROP_047_EXPIRED_TICKET_CANNOT_ACTUATE",
            policy_mutations={"allow_hardware_unauthorized_actuation": True},
        )
        assert finding.status == FindingStatus.VIOLATED

    def test_prop_048_counterexample_when_replayed_ticket_actuation_allowed(self):
        """PROP_048 counterexample discovered if replayed ticket actuation is permitted."""
        checker = BoundedAssuranceChecker()
        finding = checker.check_property(
            "PROP_048_REPLAYED_TICKET_CANNOT_ACTUATE",
            policy_mutations={"allow_hardware_unauthorized_actuation": True},
        )
        assert finding.status == FindingStatus.VIOLATED

    def test_prop_049_counterexample_when_target_mismatch_actuation_allowed(self):
        """PROP_049 counterexample discovered if target mismatch actuation is permitted."""
        checker = BoundedAssuranceChecker()
        finding = checker.check_property(
            "PROP_049_TARGET_MISMATCH_CANNOT_ACTUATE",
            policy_mutations={"allow_hardware_unauthorized_actuation": True},
        )
        assert finding.status == FindingStatus.VIOLATED

    def test_prop_050_counterexample_when_action_mismatch_actuation_allowed(self):
        """PROP_050 counterexample discovered if action mismatch actuation is permitted."""
        checker = BoundedAssuranceChecker()
        finding = checker.check_property(
            "PROP_050_ACTION_MISMATCH_CANNOT_ACTUATE",
            policy_mutations={"allow_hardware_unauthorized_actuation": True},
        )
        assert finding.status == FindingStatus.VIOLATED

    def test_prop_051_counterexample_when_stale_authorization_actuation_allowed(self):
        """PROP_051 counterexample discovered if stale authorization actuation is permitted."""
        checker = BoundedAssuranceChecker()
        finding = checker.check_property(
            "PROP_051_STALE_AUTHORIZATION_CANNOT_ACTUATE",
            policy_mutations={"allow_hardware_unauthorized_actuation": True},
        )
        assert finding.status == FindingStatus.VIOLATED


class TestHardwareBoundaryDemosAndReplay:
    """Tests for canonical CLI demonstration runners and offline event replay."""

    def test_canonical_demo_scenarios(self, tmp_path):
        """Test all 4 canonical demo scenarios execute and produce valid JSON records."""
        from scripts.run_hardware_boundary_demo import (
            run_scenario_allowed,
            run_scenario_denied,
            run_scenario_stale_ticket,
            run_scenario_actuator_failure,
        )
        import io

        buf1 = io.StringIO()
        rec_json1 = run_scenario_allowed(stream=buf1)
        rec1 = HardwareExecutionRecord.model_validate_json(rec_json1)
        assert rec1.execution_status == HardwareExecutionStatus.ACTUATED

        buf2 = io.StringIO()
        rec_json2 = run_scenario_denied(stream=buf2)
        rec2 = HardwareExecutionRecord.model_validate_json(rec_json2)
        assert rec2.execution_status == HardwareExecutionStatus.LOCKED

        buf3 = io.StringIO()
        rec_json3 = run_scenario_stale_ticket(stream=buf3)
        rec3 = HardwareExecutionRecord.model_validate_json(rec_json3)
        assert rec3.execution_status == HardwareExecutionStatus.INVALID_TICKET

        buf4 = io.StringIO()
        rec_json4 = run_scenario_actuator_failure(stream=buf4)
        rec4 = HardwareExecutionRecord.model_validate_json(rec_json4)
        assert rec4.execution_status == HardwareExecutionStatus.HARDWARE_FAULT

    def test_deterministic_offline_replay(self):
        """Test offline replay validates recorded records without side effects."""
        from scripts.replay_hardware_event import replay_hardware_record

        # Test nominal actuated replay
        rec_actuated = HardwareExecutionRecord(
            hardware_id="HWR_TEST",
            actuator_type=ActuatorType.VALVE_ACTUATOR,
            target="valve_b",
            requested_action="CLOSE_VALVE",
            ticket_id="tkt_test_123",
            ticket_status="VALID",
            signature_status="VALID",
            execution_status=HardwareExecutionStatus.ACTUATED,
            observed_state={"target_state": "CLOSED"},
        )
        assert replay_hardware_record(rec_actuated) is True

        # Test locked replay
        rec_locked = HardwareExecutionRecord(
            hardware_id="HWR_TEST",
            actuator_type=ActuatorType.VALVE_ACTUATOR,
            target="valve_b",
            requested_action="CLOSE_VALVE",
            ticket_id=None,
            ticket_status="NONE",
            signature_status="INVALID",
            execution_status=HardwareExecutionStatus.LOCKED,
            observed_state={"target_state": "OPEN"},
        )
        assert replay_hardware_record(rec_locked) is True
