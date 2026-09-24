"""Tests for NebiusTokenFactory + NVIDIA Nemotron provider, validation, and authority invariants."""

import json
from unittest.mock import MagicMock
import pytest
from openai import (
    APITimeoutError,
    AuthenticationError,
    RateLimitError,
)

from motionfence.agent.provider import ActionProposalProvider
from motionfence.agent.nebius_provider import NebiusNemotronProvider
from motionfence.agent.exceptions import (
    NebiusProviderError,
    ModelProposalValidationError,
)
from motionfence.models.actions import ActionType
from motionfence.models.world import WorldState, HumanZoneState, CoolingState, ValveState
from motionfence.evidence.models import Evidence, EvidenceSource
from motionfence.runtime.core import MotionFenceRuntime
from motionfence.simulation.world import PhysicalWorld


@pytest.fixture
def mock_evidence() -> list[Evidence]:
    return [
        Evidence(
            id="ev_vis_01",
            source=EvidenceSource.VISION,
            target="valve_b",
            observation={"leak_detected": True},
            confidence=0.94,
            provenance="camera_zoom_01",
        ),
        Evidence(
            id="ev_therm_02",
            source=EvidenceSource.THERMAL_SENSOR,
            target="valve_b",
            observation={"leak_confirmed": True},
            confidence=0.96,
            provenance="flir_ptu_02",
        ),
    ]


@pytest.fixture
def base_world() -> WorldState:
    return WorldState(
        valves={"valve_a": ValveState.OPEN, "valve_b": ValveState.OPEN},
        cooling=CoolingState.ACTIVE,
        human_zone=HumanZoneState.CLEAR,
    )


def create_mock_client(response_content: str) -> MagicMock:
    """Helper to mock OpenAI chat completions response."""
    mock_client = MagicMock()
    mock_choice = MagicMock()
    mock_choice.message.content = response_content
    mock_choice.finish_reason = "stop"
    mock_resp = MagicMock()
    mock_resp.choices = [mock_choice]
    mock_client.chat.completions.create.return_value = mock_resp
    return mock_client


# --- Contract & Offline Protocol Tests ---

def test_provider_satisfies_action_proposal_provider_protocol():
    """Verify NebiusNemotronProvider conforms to ActionProposalProvider protocol."""
    provider = NebiusNemotronProvider(api_key="mock_key", client=MagicMock())
    assert isinstance(provider, ActionProposalProvider)


def test_valid_model_response_creates_action_proposal(base_world: WorldState, mock_evidence: list[Evidence]):
    """A valid JSON response from Nemotron creates a validated ActionProposal."""
    payload = {
        "action": "CLOSE_VALVE",
        "target": "valve_b",
        "confidence": 0.94,
        "rationale": "Thermal and visual readings confirm leak on valve B.",
        "evidence_refs": ["ev_vis_01", "ev_therm_02"],
    }
    client = create_mock_client(json.dumps(payload))
    provider = NebiusNemotronProvider(api_key="mock_key", client=client)

    proposal = provider.propose("Isolate leak", base_world, mock_evidence)
    assert proposal.action_type == ActionType.CLOSE_VALVE
    assert proposal.target == "valve_b"
    assert proposal.model_confidence == 0.94
    assert proposal.supporting_evidence_ids == ["ev_vis_01", "ev_therm_02"]
    assert "Thermal and visual" in proposal.rationale


def test_malformed_json_response_is_rejected(base_world: WorldState, mock_evidence: list[Evidence]):
    """Non-JSON model output must raise ModelProposalValidationError."""
    client = create_mock_client("I suggest closing valve B because it looks leaky.")
    provider = NebiusNemotronProvider(api_key="mock_key", client=client)

    with pytest.raises(ModelProposalValidationError) as exc_info:
        provider.propose("Isolate leak", base_world, mock_evidence)
    assert "not valid JSON" in str(exc_info.value)


def test_unknown_evidence_reference_is_rejected(base_world: WorldState, mock_evidence: list[Evidence]):
    """Strict evidence discipline: citing an unknown evidence ID must reject the proposal."""
    payload = {
        "action": "CLOSE_VALVE",
        "target": "valve_b",
        "confidence": 0.92,
        "rationale": "Citing hallucinated sensor ID.",
        "evidence_refs": ["ev_vis_01", "vision_hallucinated_999"],
    }
    client = create_mock_client(json.dumps(payload))
    provider = NebiusNemotronProvider(api_key="mock_key", client=client)

    with pytest.raises(ModelProposalValidationError) as exc_info:
        provider.propose("Isolate leak", base_world, mock_evidence)
    assert "Unknown evidence reference 'vision_hallucinated_999'" in str(exc_info.value)


def test_invalid_action_type_is_rejected(base_world: WorldState, mock_evidence: list[Evidence]):
    """Proposals containing unpermitted action types must be rejected."""
    payload = {
        "action": "OVERRIDE_SCRAM_SHUTDOWN",
        "target": "valve_b",
        "confidence": 0.95,
        "rationale": "Illegal command.",
        "evidence_refs": ["ev_vis_01"],
    }
    client = create_mock_client(json.dumps(payload))
    provider = NebiusNemotronProvider(api_key="mock_key", client=client)

    with pytest.raises(ModelProposalValidationError) as exc_info:
        provider.propose("Isolate leak", base_world, mock_evidence)
    assert "Unknown action" in str(exc_info.value)


def test_invalid_confidence_range_is_rejected(base_world: WorldState, mock_evidence: list[Evidence]):
    """Confidence outside [0.0, 1.0] must be rejected."""
    payload = {
        "action": "CLOSE_VALVE",
        "target": "valve_b",
        "confidence": 1.45,
        "rationale": "Exaggerated confidence.",
        "evidence_refs": ["ev_vis_01"],
    }
    client = create_mock_client(json.dumps(payload))
    provider = NebiusNemotronProvider(api_key="mock_key", client=client)

    with pytest.raises(ModelProposalValidationError) as exc_info:
        provider.propose("Isolate leak", base_world, mock_evidence)
    assert "outside permissible range" in str(exc_info.value)


def test_missing_required_fields_rejected(base_world: WorldState, mock_evidence: list[Evidence]):
    """Proposals missing required fields must be rejected."""
    payload = {
        "action": "CLOSE_VALVE",
        # missing target
        "confidence": 0.95,
        "rationale": "Missing target.",
    }
    client = create_mock_client(json.dumps(payload))
    provider = NebiusNemotronProvider(api_key="mock_key", client=client)

    with pytest.raises(ModelProposalValidationError) as exc_info:
        provider.propose("Isolate leak", base_world, mock_evidence)
    assert "target" in str(exc_info.value)


# --- Security Invariant & Failure Safety Tests ---

def test_provider_timeout_causes_no_world_mutation(mock_evidence: list[Evidence]):
    """When model inference times out, no action is authorized and physical state remains unchanged."""
    world = PhysicalWorld(leak_target="valve_b")
    v_initial = world.version

    mock_client = MagicMock()
    mock_client.chat.completions.create.side_effect = APITimeoutError(request=MagicMock())
    provider = NebiusNemotronProvider(api_key="mock_key", client=mock_client, max_retries=1)

    runtime = MotionFenceRuntime(world=world, proposal_provider=provider)
    result = runtime.run_cycle("Isolate leak", initial_evidence=mock_evidence)

    assert not result.is_success
    assert result.error is not None
    assert result.ticket is None
    assert result.execution_result is None
    assert world.version == v_initial
    assert world.valves["valve_b"] == ValveState.OPEN
    assert world.leak.active is True


def test_provider_auth_failure_causes_no_world_mutation(mock_evidence: list[Evidence]):
    """Authentication errors with Nebius must halt cleanly without mutating state."""
    world = PhysicalWorld(leak_target="valve_b")
    v_initial = world.version

    mock_client = MagicMock()
    mock_client.chat.completions.create.side_effect = AuthenticationError(
        message="Invalid Token Factory API Key",
        response=MagicMock(status_code=401),
        body={},
    )
    provider = NebiusNemotronProvider(api_key="invalid_key", client=mock_client)

    runtime = MotionFenceRuntime(world=world, proposal_provider=provider)
    result = runtime.run_cycle("Isolate leak", initial_evidence=mock_evidence)

    assert not result.is_success
    assert "AuthenticationError" in result.error or "Invalid Token Factory" in result.error
    assert result.ticket is None
    assert world.version == v_initial
    assert world.valves["valve_b"] == ValveState.OPEN


def test_valid_model_proposal_still_denied_when_policy_violated(mock_evidence: list[Evidence]):
    """Even if Nemotron returns a perfect proposal, PolicyEngine strictly DENIES if safety zone is occupied."""
    world = PhysicalWorld(leak_target="valve_b")
    world.set_human_zone(HumanZoneState.OCCUPIED)

    payload = {
        "action": "CLOSE_VALVE",
        "target": "valve_b",
        "confidence": 0.99,
        "rationale": "High confidence closure proposal.",
        "evidence_refs": ["ev_vis_01", "ev_therm_02"],
    }
    client = create_mock_client(json.dumps(payload))
    provider = NebiusNemotronProvider(api_key="mock_key", client=client)

    runtime = MotionFenceRuntime(world=world, proposal_provider=provider)
    result = runtime.run_cycle("Isolate leak", initial_evidence=mock_evidence)

    assert not result.is_success
    assert result.policy_decision is not None
    assert result.policy_decision.is_denied
    assert result.ticket is None
    assert result.execution_result is None
    # State must not mutate
    assert world.valves["valve_b"] == ValveState.OPEN


def test_valid_model_proposal_results_in_need_more_evidence_when_confidence_low(base_world: WorldState):
    """When Nemotron proposes with confidence < 0.90, PolicyEngine returns NEED_MORE_EVIDENCE."""
    low_ev = [
        Evidence(
            id="ev_ambiguous_01",
            source=EvidenceSource.VISION,
            target="valve_b",
            observation={"leak_detected": True},
            confidence=0.78,
            provenance="wide_cam",
        )
    ]
    world = PhysicalWorld(leak_target="valve_b")

    payload = {
        "action": "CLOSE_VALVE",
        "target": "valve_b",
        "confidence": 0.78,
        "rationale": "Candidate valve B looks slightly more vaporous.",
        "evidence_refs": ["ev_ambiguous_01"],
    }
    client = create_mock_client(json.dumps(payload))
    provider = NebiusNemotronProvider(api_key="mock_key", client=client)

    runtime = MotionFenceRuntime(world=world, proposal_provider=provider)
    result = runtime.run_cycle("Isolate leak", initial_evidence=low_ev, gather_additional_evidence_on_request=False)

    assert not result.is_success
    assert result.policy_decision.needs_evidence
    assert result.ticket is None
    assert world.valves["valve_b"] == ValveState.OPEN


def test_successful_end_to_end_path_with_nebius_provider(mock_evidence: list[Evidence]):
    """End-to-end: Model Proposal -> Policy Engine ALLOW -> Ticket -> Actuator -> Verification."""
    world = PhysicalWorld(leak_target="valve_b")

    payload = {
        "action": "CLOSE_VALVE",
        "target": "valve_b",
        "confidence": 0.95,
        "rationale": "Thermal and visual sensors confirm valve B gasket leak.",
        "evidence_refs": ["ev_vis_01", "ev_therm_02"],
    }
    client = create_mock_client(json.dumps(payload))
    provider = NebiusNemotronProvider(api_key="mock_key", client=client)

    runtime = MotionFenceRuntime(world=world, proposal_provider=provider)
    result = runtime.run_cycle("Isolate leaking line while keeping cooling active.", initial_evidence=mock_evidence)

    assert result.is_success
    assert result.policy_decision.is_allowed
    assert result.ticket is not None
    assert result.execution_result.success is True
    assert result.verification_result.is_verified

    # World physically changed
    assert world.valves["valve_b"] == ValveState.CLOSED
    assert world.leak.active is False
