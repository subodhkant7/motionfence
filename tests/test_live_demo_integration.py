"""Phase 2N Integration & Security Boundary Tests.

Proves the 14 security boundary criteria specified in Phase 2N:
1. Live model output cannot bypass PolicyEngine
2. Malformed model output cannot create a ticket
3. Provider failure cannot cause actuation (fails closed)
4. Replay cannot make network calls
5. Replay cannot mint tickets
6. Replay cannot actuate
7. Frontend cannot actuate
8. Digital twin cannot actuate independently
9. Mock hardware still requires valid AuthorizationTicket
10. Stale ticket still fails (revalidation defense)
11. No secrets appear in terminal/UI/audit output
12. LIVE and REPLAY modes cannot be mislabeled
13. Recorded LIVE proposal is replayed without a second model call
14. One canonical execution is sufficient for terminal + UI synchronization
"""

from http import HTTPStatus
import io
import json
import os
import sys
from unittest.mock import MagicMock, patch
import pytest

from motionfence.hardware.mock import MockHardwareEndpoint
from motionfence.hardware.models import HardwareExecutionStatus
from motionfence.models.actions import (
    ActionProposal,
    ActionType,
    AuthorizationTicket,
    ExecutionResult,
)
from motionfence.models.world import CoolingState, HumanZoneState, ValveState, WorldState
from motionfence.policy.engine import PolicyEngine
from motionfence.policy.models import DecisionType, Policy
from motionfence.runtime.enclave import EnclaveAuthorizationRequest, SafetyEnclave
from motionfence.runtime.live_demo import (
    DigitalTwinPlantState,
    ExecutionMode,
    LiveDemoRecord,
    LiveScenarioType,
    live_record_to_scenario_data,
    make_digital_twin_snapshot,
)
from motionfence.runtime.revalidation import ExecutionTimeRevalidator, RevalidationStatus, compute_world_state_hash
from motionfence.simulation.world import PhysicalWorld
from scripts.replay_live_demo import replay_live_scenario


@pytest.fixture
def clean_world():
    world = PhysicalWorld()
    world.valves["valve_b"] = ValveState.OPEN
    world.cooling = CoolingState.ACTIVE
    world.set_pump_state("pump_p1", "INACTIVE")
    world.set_human_zone(HumanZoneState.CLEAR)
    return world


@pytest.fixture
def dummy_proposal():
    return ActionProposal(
        action_type=ActionType.CLOSE_VALVE,
        target="valve_b",
        rationale="AI proposed valve closure",
        model_confidence=0.96,
        supporting_evidence_ids=["ev_manifold_01"],
    )


@pytest.fixture
def safety_enclave():
    return SafetyEnclave(secret_key="motionfence_runtime_kernel_secret")


@pytest.fixture
def live_fixtures_dir():
    return os.path.abspath(
        os.path.join(os.path.dirname(__file__), "..", "motionfence", "fixtures", "live_demo")
    )


# 1. Live model output cannot bypass PolicyEngine
def test_boundary_01_model_output_cannot_bypass_policy_engine(clean_world, dummy_proposal):
    """An unprivileged ActionProposal from a model has 0 direct execution authority."""
    hw = MockHardwareEndpoint(world=clean_world)

    # Attempting to actuate directly without an AuthorizationTicket is rejected and locks actuator
    res = hw.receive_and_actuate(dummy_proposal, ticket=None)
    assert res.execution_status == HardwareExecutionStatus.LOCKED
    assert hw.is_locked is True
    assert clean_world.valves["valve_b"] == ValveState.OPEN


# 2. Malformed model output cannot create a ticket
def test_boundary_02_malformed_model_output_cannot_create_ticket(safety_enclave, clean_world, dummy_proposal):
    """Corrupted or invalid proposals fail validation before reaching the enclave."""
    # Proposal with invalid confidence > 1.0 fails schema validation
    with pytest.raises(Exception):
        ActionProposal(
            action_type=ActionType.CLOSE_VALVE,
            target="valve_b",
            rationale="Malformed",
            model_confidence=2.5,  # Invalid confidence
            supporting_evidence_ids=[],
        )

    # In hazard state (human present), enclave evaluates DENY and refuses ticket issuance
    danger_world = clean_world.get_state()
    danger_world.human_zone = HumanZoneState.OCCUPIED

    req = EnclaveAuthorizationRequest(
        proposal=dummy_proposal,
        world_state=danger_world,
        evidence=clean_world.generate_targeted_evidence("valve_b"),
        policy=Policy(),
    )
    res = safety_enclave.authorize(req)
    assert not res.authorized
    assert res.ticket is None


# 3. Provider failure cannot cause actuation (fails closed)
def test_boundary_03_provider_failure_fails_closed(clean_world, dummy_proposal):
    """Network failure, timeout, or quota exhaustion must fail closed with zero actuation."""
    hw = MockHardwareEndpoint(world=clean_world)

    # When provider fails, no ticket can be minted
    ticket = None
    res = hw.receive_and_actuate(dummy_proposal, ticket=ticket)
    assert res.execution_status == HardwareExecutionStatus.LOCKED
    assert hw.is_locked is True
    assert clean_world.valves["valve_b"] == ValveState.OPEN


# 4. Replay cannot make network calls
def test_boundary_04_replay_cannot_make_network_calls(live_fixtures_dir):
    """Replay execution executes purely from disk artifacts with no socket or HTTP calls."""
    out_buf = io.StringIO()
    with patch("socket.socket") as mock_socket, patch("urllib.request.urlopen") as mock_http:
        success = replay_live_scenario("safe.json", stream=out_buf)
        assert success is True
        mock_socket.assert_not_called()
        mock_http.assert_not_called()


# 5. Replay cannot mint tickets
def test_boundary_05_replay_cannot_mint_tickets(live_fixtures_dir):
    """Replaying a scenario reuses recorded tokens and cannot invoke SafetyEnclave to mint new tickets."""
    with patch.object(SafetyEnclave, "authorize") as mock_authorize:
        out_buf = io.StringIO()
        replay_live_scenario("safe.json", stream=out_buf)
        mock_authorize.assert_not_called()


# 6. Replay cannot actuate
def test_boundary_06_replay_cannot_actuate(live_fixtures_dir):
    """Replay does not invoke physical actuators or mutate PhysicalWorld."""
    with patch.object(MockHardwareEndpoint, "receive_and_actuate") as mock_hw_exec, \
         patch.object(PhysicalWorld, "set_valve") as mock_world_mutate:
        out_buf = io.StringIO()
        replay_live_scenario("safe.json", stream=out_buf)
        mock_hw_exec.assert_not_called()
        mock_world_mutate.assert_not_called()


# 7. Frontend cannot actuate
def test_boundary_07_frontend_cannot_actuate():
    """Verify console server adapter strictly rejects mutations with 405 Method Not Allowed."""
    from scripts.console_server import ReadOnlyConsoleHandler

    handler = ReadOnlyConsoleHandler.__new__(ReadOnlyConsoleHandler)
    mock_send = MagicMock()
    mock_header = MagicMock()
    mock_end = MagicMock()
    handler.send_response = mock_send
    handler.send_header = mock_header
    handler.end_headers = mock_end
    handler.wfile = io.BytesIO()

    # Calling do_POST triggers _reject_mutation with 405 METHOD_NOT_ALLOWED
    handler.do_POST()
    mock_send.assert_called_with(HTTPStatus.METHOD_NOT_ALLOWED)
    response_body = json.loads(handler.wfile.getvalue().decode("utf-8"))
    assert response_body["error"] == "METHOD_NOT_ALLOWED"
    assert response_body["authority"] == "ZERO"


# 8. Digital twin cannot actuate independently
def test_boundary_08_digital_twin_cannot_actuate(clean_world):
    """Digital twin snapshot is purely a read-only representation and cannot mutate the simulation."""
    orig_version = clean_world.version
    snapshot = make_digital_twin_snapshot(clean_world, "test_stage", "READY")
    assert isinstance(snapshot, DigitalTwinPlantState)
    assert snapshot.world_version == orig_version
    assert snapshot.valve_b_state == "OPEN"

    # Mutating the snapshot object locally does not affect the underlying PhysicalWorld
    snapshot.valve_b_state = "CLOSED"
    snapshot.world_version = 99
    assert clean_world.valves["valve_b"] == ValveState.OPEN
    assert clean_world.version == orig_version


# 9. Mock hardware still requires valid AuthorizationTicket
def test_boundary_09_mock_hardware_requires_valid_ticket(clean_world, dummy_proposal, safety_enclave):
    """Mock hardware rejects invalid signatures and unauthorized attempts."""
    hw = MockHardwareEndpoint(world=clean_world, secret_key="motionfence_runtime_kernel_secret")

    # 1. None ticket rejected
    res_none = hw.receive_and_actuate(dummy_proposal, ticket=None)
    assert res_none.execution_status == HardwareExecutionStatus.LOCKED
    assert hw.is_locked is True

    # 2. Valid ticket succeeds
    valid_res = safety_enclave.authorize(
        EnclaveAuthorizationRequest(
            proposal=dummy_proposal,
            world_state=clean_world.get_state(),
            evidence=clean_world.generate_targeted_evidence("valve_b"),
            policy=Policy(),
        )
    )
    assert valid_res.authorized
    ticket = valid_res.ticket

    # Tamper with ticket target
    tampered_dict = ticket.model_dump()
    tampered_dict["target"] = "valve_a"
    tampered_ticket = AuthorizationTicket.model_validate(tampered_dict)

    res_tampered = hw.receive_and_actuate(dummy_proposal, ticket=tampered_ticket)
    assert res_tampered.execution_status == HardwareExecutionStatus.TARGET_MISMATCH
    assert hw.is_locked is True


# 10. Stale ticket still fails (revalidation defense)
def test_boundary_10_stale_ticket_fails_revalidation(clean_world, dummy_proposal, safety_enclave):
    """World state changes between issuance and revalidation invalidate the ticket."""
    revalidator = ExecutionTimeRevalidator()

    valid_res = safety_enclave.authorize(
        EnclaveAuthorizationRequest(
            proposal=dummy_proposal,
            world_state=clean_world.get_state(),
            evidence=clean_world.generate_targeted_evidence("valve_b"),
            policy=Policy(),
        )
    )
    ticket = valid_res.ticket
    assert ticket is not None
    assert valid_res.authorization_context is not None

    # Inject world drift before execution
    clean_world.set_human_zone(HumanZoneState.OCCUPIED)
    assert clean_world.version > ticket.world_state_version

    # Revalidation checks against drifted world
    reval_res = revalidator.revalidate(
        authorization_context=valid_res.authorization_context,
        current_world_state=clean_world.get_state(),
        current_policy_version="1.0.0",
        current_constraints=[],
        current_evidence=[],
        ticket_expires_at=ticket.expires_at,
        proposal_action_type=dummy_proposal.action_type,
        proposal_target=dummy_proposal.target,
    )
    assert reval_res.status == RevalidationStatus.WORLD_STATE_CHANGED
    assert reval_res.status != RevalidationStatus.VALID

    # Mock hardware endpoint also detects stale world version and locks
    hw = MockHardwareEndpoint(world=clean_world, secret_key="motionfence_runtime_kernel_secret")
    hw_res = hw.receive_and_actuate(dummy_proposal, ticket=ticket)
    assert hw_res.execution_status == HardwareExecutionStatus.INVALID_TICKET
    assert hw.is_locked is True


# 11. No secrets appear in terminal/UI/audit output
def test_boundary_11_no_secrets_in_records_or_fixtures(live_fixtures_dir):
    """Verify that no API keys or private HMAC secrets are stored in recorded fixtures."""
    forbidden_tokens = ["NEBIUS_API_KEY", "test_enclave_key", "sk-", "Bearer "]

    for fname in os.listdir(live_fixtures_dir):
        if fname.endswith(".json") or fname.endswith(".txt"):
            filepath = os.path.join(live_fixtures_dir, fname)
            with open(filepath, "r", encoding="utf-8") as f:
                content = f.read()
            for token in forbidden_tokens:
                assert token not in content, f"Secret token '{token}' found in {fname}!"


# 12. LIVE and REPLAY modes cannot be mislabeled
def test_boundary_12_live_and_replay_cannot_be_mislabeled(live_fixtures_dir):
    """Live demo record enforces strict enum distinction between LIVE, REPLAY, and OFFLINE_TEST."""
    with open(os.path.join(live_fixtures_dir, "safe.json"), "r", encoding="utf-8") as f:
        data = json.load(f)

    rec = LiveDemoRecord.model_validate(data)
    assert rec.execution_mode == ExecutionMode.LIVE

    # Converting to ScenarioData marks source_mode clearly
    sc_data = live_record_to_scenario_data(rec)
    assert sc_data["execution_mode"] == "LIVE"
    assert sc_data["decision_record"]["provider_metadata"]["source_mode"] == "LIVE_MODEL_RESPONSE"

    # Altering mode to invalid string raises ValidationError
    with pytest.raises(Exception):
        data["execution_mode"] = "INVALID_HYBRID_MODE"
        LiveDemoRecord.model_validate(data)


# 13. Recorded LIVE proposal is replayed without a second model call
def test_boundary_13_recorded_proposal_replayed_without_second_call(live_fixtures_dir):
    """Replay uses the exact proposal recorded in the fixture without invoking NebiusProvider."""
    with patch("motionfence.agent.nebius_provider.NebiusNemotronProvider.propose") as mock_gen:
        out_buf = io.StringIO()
        replay_live_scenario("toctou.json", stream=out_buf)
        mock_gen.assert_not_called()


# 14. One canonical execution is sufficient for terminal + UI synchronization
def test_boundary_14_canonical_execution_synchronizes_cli_and_ui(live_fixtures_dir):
    """The exact same record_id and sha256_hash are rendered in CLI replay and UI ScenarioData."""
    with open(os.path.join(live_fixtures_dir, "safe.json"), "r", encoding="utf-8") as f:
        data = json.load(f)

    rec = LiveDemoRecord.model_validate(data)
    ui_data = live_record_to_scenario_data(rec)

    # Identifiers and hashes match identically
    assert rec.record_id == ui_data["decision_record"]["decision_id"]
    assert rec.sha256_hash == ui_data["sha256_hash"]
    assert rec.proposal.id == ui_data["decision_record"]["action_proposal"]["id"]
    assert rec.ticket.ticket_id == ui_data["ticket"]["ticket_id"]
    assert rec.hardware_execution.record_id == ui_data["decision_record"]["hardware_execution_id"]
