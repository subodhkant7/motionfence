"""Tests for NebiusTokenFactory + NVIDIA Nemotron provider, validation, and authority invariants."""

import json
import time
from unittest.mock import MagicMock, patch
import pytest
from openai import (
    APITimeoutError,
    APIConnectionError,
    AuthenticationError,
    PermissionDeniedError,
    BadRequestError,
    NotFoundError,
    RateLimitError,
    InternalServerError,
)

from motionfence.agent.provider import ActionProposalProvider
from motionfence.agent.nebius_provider import NebiusNemotronProvider
from motionfence.agent.exceptions import (
    NebiusProviderError,
    NebiusConfigurationError,
    NebiusAuthenticationError,
    NebiusAuthorizationError,
    NebiusInvalidModelOrRequestError,
    NebiusRateLimitError,
    NebiusUpstreamServerError,
    NebiusTimeoutError,
    NebiusTransportError,
    NebiusMalformedResponseError,
    ModelProposalValidationError,
)
from motionfence.models.actions import ActionType
from motionfence.models.world import WorldState, HumanZoneState, CoolingState, ValveState
from motionfence.evidence.models import Evidence, EvidenceSource
from motionfence.runtime.core import MotionFenceRuntime
from motionfence.runtime.controlled_demo import (
    ControlledDemoManager,
    ExecutionStatus,
    StageOutcome,
)
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


# --- Phase 6 Comprehensive Regression Tests ---

def test_missing_or_invalid_configuration():
    """Missing or empty credentials, model, or base_url must raise NebiusConfigurationError."""
    # 1. Missing / whitespace API key
    with pytest.raises(NebiusConfigurationError) as exc_key:
        NebiusNemotronProvider(api_key="   ", client=MagicMock())
    assert exc_key.value.classification == "CONFIGURATION_ERROR"
    assert "empty or whitespace" in str(exc_key.value)

    # 2. Empty model
    with pytest.raises(NebiusConfigurationError) as exc_model:
        NebiusNemotronProvider(api_key="valid_mock_key", model="  ", client=MagicMock())
    assert exc_model.value.classification == "CONFIGURATION_ERROR"
    assert "model" in str(exc_model.value)

    # 3. Empty base URL
    with pytest.raises(NebiusConfigurationError) as exc_url:
        NebiusNemotronProvider(api_key="valid_mock_key", base_url="   ", client=MagicMock())
    assert exc_url.value.classification == "CONFIGURATION_ERROR"
    assert "base" in str(exc_url.value).lower()


def test_authentication_error_classification_and_metadata(base_world: WorldState, mock_evidence: list[Evidence]):
    """HTTP 401 AuthenticationError must be classified with correlation ID and diagnostic metadata."""
    resp = MagicMock()
    resp.status_code = 401
    resp.headers = {"x-request-id": "req_auth_fail_123"}
    client = MagicMock()
    client.chat.completions.create.side_effect = AuthenticationError(
        message="Invalid token", response=resp, body={"error": {"code": "invalid_api_key"}}
    )

    provider = NebiusNemotronProvider(api_key="bad_key", client=client)
    with pytest.raises(NebiusAuthenticationError) as exc_info:
        provider.propose("Isolate leak", base_world, mock_evidence)

    err = exc_info.value
    assert err.classification == "AUTHENTICATION_ERROR"
    assert err.status_code == 401
    assert err.is_retryable is False
    assert err.correlation_id.startswith("corr_")
    assert "tokenfactory.nebius.com" in err.sanitized_endpoint
    diag = err.to_diagnostic_dict()
    assert diag["classification"] == "AUTHENTICATION_ERROR"
    assert diag["status_code"] == 401
    assert "bad_key" not in str(diag)  # No secret leakage


def test_authorization_rejection_classification_and_metadata(base_world: WorldState, mock_evidence: list[Evidence]):
    """HTTP 403 PermissionDeniedError must be classified as AUTHORIZATION_ERROR."""
    resp = MagicMock()
    resp.status_code = 403
    resp.headers = {"x-request-id": "req_authz_fail_456"}
    client = MagicMock()
    client.chat.completions.create.side_effect = PermissionDeniedError(
        message="Request to api.tokenfactory.nebius.com not allowed by policy",
        response=resp,
        body={"error": {"code": "policy_forbidden"}},
    )

    provider = NebiusNemotronProvider(api_key="valid_key", client=client)
    with pytest.raises(NebiusAuthorizationError) as exc_info:
        provider.propose("Isolate leak", base_world, mock_evidence)

    err = exc_info.value
    assert err.classification == "AUTHORIZATION_ERROR"
    assert err.status_code == 403
    assert err.is_retryable is False
    assert err.correlation_id.startswith("corr_")
    diag = err.to_diagnostic_dict()
    assert diag["classification"] == "AUTHORIZATION_ERROR"
    assert diag["status_code"] == 403


def test_invalid_model_or_request_schema(base_world: WorldState, mock_evidence: list[Evidence]):
    """HTTP 404 (model not found) and 400 (bad request) must be classified as INVALID_MODEL_OR_REQUEST."""
    resp_404 = MagicMock()
    resp_404.status_code = 404
    client_404 = MagicMock()
    client_404.chat.completions.create.side_effect = NotFoundError(
        message="The model nvidia/unknown does not exist",
        response=resp_404,
        body={"error": {"code": "model_not_found"}},
    )

    provider_404 = NebiusNemotronProvider(api_key="valid_key", client=client_404)
    with pytest.raises(NebiusInvalidModelOrRequestError) as exc_404:
        provider_404.propose("Isolate leak", base_world, mock_evidence)

    assert exc_404.value.classification == "INVALID_MODEL_OR_REQUEST"
    assert exc_404.value.status_code == 404

    resp_400 = MagicMock()
    resp_400.status_code = 400
    client_400 = MagicMock()
    client_400.chat.completions.create.side_effect = BadRequestError(
        message="Invalid max_tokens payload",
        response=resp_400,
        body={"error": {"code": "bad_request"}},
    )

    provider_400 = NebiusNemotronProvider(api_key="valid_key", client=client_400)
    with pytest.raises(NebiusInvalidModelOrRequestError) as exc_400:
        provider_400.propose("Isolate leak", base_world, mock_evidence)

    assert exc_400.value.classification == "INVALID_MODEL_OR_REQUEST"
    assert exc_400.value.status_code == 400


def test_rate_limit_retry_exhaustion(base_world: WorldState, mock_evidence: list[Evidence]):
    """HTTP 429 RateLimitError must be retried with backoff and raise NebiusRateLimitError when exhausted."""
    resp = MagicMock()
    resp.status_code = 429
    client = MagicMock()
    client.chat.completions.create.side_effect = RateLimitError(
        message="Too Many Requests",
        response=resp,
        body={"error": {"code": "rate_limit_exceeded"}},
    )

    # Use max_retries=1 to keep test fast
    provider = NebiusNemotronProvider(api_key="valid_key", client=client, max_retries=1)
    with pytest.raises(NebiusRateLimitError) as exc_info:
        provider.propose("Isolate leak", base_world, mock_evidence)

    err = exc_info.value
    assert err.classification == "RATE_LIMIT_ERROR"
    assert err.status_code == 429
    assert err.is_retryable is True
    assert client.chat.completions.create.call_count == 2


def test_upstream_server_error_retry_exhaustion(base_world: WorldState, mock_evidence: list[Evidence]):
    """HTTP 500 InternalServerError must be retried with backoff and raise NebiusUpstreamServerError when exhausted."""
    resp = MagicMock()
    resp.status_code = 500
    client = MagicMock()
    client.chat.completions.create.side_effect = InternalServerError(
        message="Internal Server Error",
        response=resp,
        body={"error": {"code": "internal_error"}},
    )

    provider = NebiusNemotronProvider(api_key="valid_key", client=client, max_retries=1)
    with pytest.raises(NebiusUpstreamServerError) as exc_info:
        provider.propose("Isolate leak", base_world, mock_evidence)

    err = exc_info.value
    assert err.classification == "UPSTREAM_SERVER_ERROR"
    assert err.status_code == 500
    assert err.is_retryable is True
    assert client.chat.completions.create.call_count == 2


def test_network_connection_and_timeout_errors(base_world: WorldState, mock_evidence: list[Evidence]):
    """Connection errors and timeouts must be classified as NETWORK_TRANSPORT_ERROR and TIMEOUT_ERROR."""
    # 1. Transport error
    client_conn = MagicMock()
    client_conn.chat.completions.create.side_effect = APIConnectionError(
        request=MagicMock(), message="Failed to connect to host"
    )
    provider_conn = NebiusNemotronProvider(api_key="valid_key", client=client_conn, max_retries=0)
    with pytest.raises(NebiusTransportError) as exc_conn:
        provider_conn.propose("Isolate leak", base_world, mock_evidence)
    assert exc_conn.value.classification == "NETWORK_TRANSPORT_ERROR"
    assert exc_conn.value.is_retryable is True

    # 2. Timeout error
    client_time = MagicMock()
    client_time.chat.completions.create.side_effect = APITimeoutError(request=MagicMock())
    provider_time = NebiusNemotronProvider(api_key="valid_key", client=client_time, max_retries=0)
    with pytest.raises(NebiusTimeoutError) as exc_time:
        provider_time.propose("Isolate leak", base_world, mock_evidence)
    assert exc_time.value.classification == "TIMEOUT_ERROR"
    assert exc_time.value.is_retryable is True


def test_empty_and_malformed_responses(base_world: WorldState, mock_evidence: list[Evidence]):
    """Empty response choices or empty content must raise NebiusMalformedResponseError."""
    # 1. Empty choices
    mock_resp_empty = MagicMock()
    mock_resp_empty.choices = []
    client_empty = MagicMock()
    client_empty.chat.completions.create.return_value = mock_resp_empty

    provider_empty = NebiusNemotronProvider(api_key="valid_key", client=client_empty, max_retries=0)
    with pytest.raises(NebiusMalformedResponseError) as exc_empty:
        provider_empty.propose("Isolate leak", base_world, mock_evidence)
    assert exc_empty.value.classification == "MALFORMED_RESPONSE_ERROR"

    # 2. Empty string content
    client_blank = create_mock_client("   ")
    provider_blank = NebiusNemotronProvider(api_key="valid_key", client=client_blank, max_retries=0)
    with pytest.raises(NebiusMalformedResponseError) as exc_blank:
        provider_blank.propose("Isolate leak", base_world, mock_evidence)
    assert exc_blank.value.classification == "MALFORMED_RESPONSE_ERROR"


def test_controlled_execution_boundary_remains_fail_closed_on_provider_error():
    """ControlledDemoManager worker halts fail-closed with structured error details when provider fails."""
    manager = ControlledDemoManager(max_concurrent=1)

    # Dispatch a live scenario where provider throws NebiusAuthorizationError
    with patch("motionfence.runtime.controlled_demo.NebiusNemotronProvider") as mock_prov_cls:
        mock_prov_instance = MagicMock()
        mock_prov_instance.propose.side_effect = NebiusAuthorizationError(
            "Nebius policy denied request to api.tokenfactory.nebius.com",
            provider="nebius",
            model="nvidia/nemotron-3-super-120b-a12b",
            sanitized_endpoint="https://api.tokenfactory.nebius.com/v1",
            status_code=403,
            correlation_id="corr_test_failclosed_777",
        )
        mock_prov_cls.return_value = mock_prov_instance

        # Force live execution mode
        with patch("motionfence.runtime.controlled_demo.settings") as mock_settings:
            mock_settings.nebius.api_key = "live_test_key"
            mock_settings.nebius.timeout_seconds = 10.0
            with patch("scripts.live_nebius_demo.run_live_safe_scenario", side_effect=mock_prov_instance.propose):
                execution = manager.create_execution(scenario_id="safe", mode="LIVE")

                # Wait for execution task to terminate
                for _ in range(50):
                    time.sleep(0.05)
                    ex = manager.get_execution(execution.execution_id)
                    if ex and ex.status in (ExecutionStatus.COMPLETED, ExecutionStatus.FAILED):
                        break

                assert ex is not None
                assert ex.status == ExecutionStatus.FAILED
                assert ex.stage_outcome == StageOutcome.ERROR
                assert "Controlled execution terminated fail-closed: NebiusProviderError [AUTHORIZATION_ERROR]" in ex.error_message
                assert "corr_test_failclosed_777" in ex.error_message
                assert ex.error_details is not None
                assert ex.error_details["classification"] == "AUTHORIZATION_ERROR"
                assert ex.error_details["status_code"] == 403
                assert ex.error_details["correlation_id"] == "corr_test_failclosed_777"

                # Check listed executions include error_details and error_message
                listing = manager.list_executions()
                matching = [item for item in listing if item["execution_id"] == ex.execution_id]
                assert len(matching) == 1
                assert matching[0]["error_details"]["classification"] == "AUTHORIZATION_ERROR"
                assert "fail-closed" in matching[0]["error_message"]


def test_transient_failure_recovery_on_retry(base_world: WorldState, mock_evidence: list[Evidence]):
    """Transient rate limit or connection error recovers cleanly on subsequent retry."""
    resp_rate = MagicMock()
    resp_rate.status_code = 429
    err_rate = RateLimitError(
        message="Rate limit",
        response=resp_rate,
        body={"error": {"code": "rate_limit_exceeded"}},
    )

    valid_payload = {
        "action": "CLOSE_VALVE",
        "target": "valve_b",
        "confidence": 0.95,
        "rationale": "Recovered proposal after retry.",
        "evidence_refs": ["ev_vis_01", "ev_therm_02"],
    }
    mock_success_resp = MagicMock()
    mock_choice = MagicMock()
    mock_choice.message.content = json.dumps(valid_payload)
    mock_choice.finish_reason = "stop"
    mock_success_resp.choices = [mock_choice]

    client = MagicMock()
    # First call raises RateLimitError, second call succeeds
    client.chat.completions.create.side_effect = [err_rate, mock_success_resp]

    provider = NebiusNemotronProvider(api_key="valid_key", client=client, max_retries=2)
    proposal = provider.propose("Isolate leak", base_world, mock_evidence)

    assert proposal is not None
    assert proposal.action_type == ActionType.CLOSE_VALVE
    assert proposal.target == "valve_b"
    assert proposal.model_confidence == 0.95
    assert client.chat.completions.create.call_count == 2

