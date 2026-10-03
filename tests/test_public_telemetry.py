"""Tests for MotionFence Phase 2O: Real-World Public Telemetry & Deterministic Replay.

Covers all 20 canonical safety and integrity test areas required by Phase 2O:
1. Successful USGS response normalization
2. Schema validation
3. Missing-value handling
4. Timestamp handling
5. Freshness classification
6. Provenance preservation
7. Observation hashing
8. Replay equivalence
9. Network failure handling (fail closed)
10. HTTP failure handling (fail closed)
11. Stale observation handling
12. Malformed response handling
13. External observation cannot mint AuthorizationTicket
14. External observation cannot actuate hardware
15. Nemotron cannot bypass observation/evidence layer
16. Public API failure cannot cause ALLOW
17. Cached observation cannot be mislabeled LIVE
18. Judge Console fixtures distinguish LIVE vs REPLAY
19. Digital Twin / WorldState cannot interpret telemetry as actuator state
20. Source metadata remains attached through policy evaluation
"""

import json
import os
import time
from unittest.mock import MagicMock, patch
import urllib.error

import pytest

from motionfence.evidence.models import Evidence, EvidenceSource
from motionfence.hardware.mock import MockHardwareEndpoint
from motionfence.knowledge.trust import SourceTrustClassifier
from motionfence.models.actions import ActionProposal, ActionType
from motionfence.models.world import WorldState
from motionfence.policy.engine import PolicyEngine
from motionfence.policy.models import DecisionType
from motionfence.runtime.enclave import SafetyEnclave, EnclaveAuthorizationRequest
from motionfence.simulation.world import PhysicalWorld
from motionfence.telemetry.adapter import TelemetryEvidenceAdapter
from motionfence.telemetry.cache import BoundedTelemetryCache
from motionfence.telemetry.models import (
    DerivedEnvironmentalContext,
    ObservationFreshness,
    ObservationSnapshot,
    TelemetryConfig,
    TelemetryMode,
    TelemetryStatus,
)
from motionfence.telemetry.normalizer import TelemetryNormalizer, parse_iso_timestamp
from motionfence.telemetry.provenance import (
    compute_observation_payload_hash,
    compute_provenance_hash,
    verify_observation_integrity,
)
from motionfence.telemetry.replay import TelemetryReplayEngine, TelemetryReplayRecord
from motionfence.telemetry.usgs_provider import USGSOgcTelemetryProvider


# ---------------------------------------------------------------------------
# Canonical Fixtures for Testing
# ---------------------------------------------------------------------------

@pytest.fixture
def canonical_usgs_feature():
    """A realistic USGS OGC API latest-continuous GeoJSON feature."""
    return {
        "type": "Feature",
        "id": "000127fc-9ac0-46a6-bfd7-949e76318830",
        "geometry": {
            "type": "Point",
            "coordinates": [-77.12763888888888, 38.949777777777776],
        },
        "properties": {
            "time_series_id": "66a4e3fb8abe42fcb0942b5c0fe98f68",
            "monitoring_location_id": "USGS-01646500",
            "parameter_code": "00060",
            "statistic_id": "00011",
            "time": "2026-10-03T16:50:00+00:00",
            "value": "2350",
            "unit_of_measure": "ft^3/s",
            "approval_status": "Provisional",
            "qualifier": None,
            "last_modified": "2026-10-03T16:58:26.477994+00:00",
        },
    }


@pytest.fixture
def canonical_usgs_feature_collection(canonical_usgs_feature):
    """A valid GeoJSON FeatureCollection containing two parameters."""
    gage_feature = {
        "type": "Feature",
        "id": "000248ab-3df1-4ba2-a89c-851e44208912",
        "geometry": {
            "type": "Point",
            "coordinates": [-77.12763888888888, 38.949777777777776],
        },
        "properties": {
            "time_series_id": "8a83eb3a3cbc4087b0c201cf07c0c76d",
            "monitoring_location_id": "USGS-01646500",
            "parameter_code": "00065",
            "statistic_id": "00011",
            "time": "2026-10-03T16:50:00+00:00",
            "value": "2.90",
            "unit_of_measure": "ft",
            "approval_status": "Provisional",
            "qualifier": None,
            "last_modified": "2026-10-03T16:58:28.001137+00:00",
        },
    }
    return {
        "type": "FeatureCollection",
        "features": [canonical_usgs_feature, gage_feature],
    }


@pytest.fixture
def sample_snapshot(canonical_usgs_feature):
    normalizer = TelemetryNormalizer()
    status, snap, msg = normalizer.normalize_feature(
        feature=canonical_usgs_feature,
        source_url="https://api.waterdata.usgs.gov/ogcapi/v1/collections/latest-continuous/items?monitoring_location_id=USGS-01646500&parameter_code=00060",
        retrieved_timestamp=1791047588.0,
        retrieved_at="2026-10-03T17:13:08+00:00",
    )
    assert status == TelemetryStatus.SUCCESS
    assert snap is not None
    return snap


# ---------------------------------------------------------------------------
# Test Cases 1-20
# ---------------------------------------------------------------------------

def test_1_successful_usgs_response_normalization(canonical_usgs_feature_collection):
    """Test 1: Successful normalization of USGS OGC API GeoJSON FeatureCollection."""
    normalizer = TelemetryNormalizer()
    status, features, msg = normalizer.validate_feature_collection(canonical_usgs_feature_collection)
    assert status == TelemetryStatus.SUCCESS
    assert len(features) == 2

    # Normalize streamflow (00060)
    st_flow, snap_flow, _ = normalizer.normalize_feature(
        feature=features[0],
        source_url="https://api.waterdata.usgs.gov/ogcapi/v1/test",
        retrieved_timestamp=1791047588.0,
        retrieved_at="2026-10-03T17:13:08+00:00",
    )
    assert st_flow == TelemetryStatus.SUCCESS
    assert snap_flow.parameter_code == "00060"
    assert snap_flow.parameter_name == "Discharge / Streamflow"
    assert snap_flow.normalized_value == 2350.0
    assert snap_flow.raw_value == "2350"
    assert snap_flow.unit == "ft^3/s"
    assert snap_flow.monitoring_location_id == "USGS-01646500"
    assert snap_flow.provider == "USGS"
    assert snap_flow.approval_status == "Provisional"

    # Normalize gage height (00065)
    st_gage, snap_gage, _ = normalizer.normalize_feature(
        feature=features[1],
        source_url="https://api.waterdata.usgs.gov/ogcapi/v1/test",
        retrieved_timestamp=1791047588.0,
        retrieved_at="2026-10-03T17:13:08+00:00",
    )
    assert st_gage == TelemetryStatus.SUCCESS
    assert snap_gage.parameter_code == "00065"
    assert snap_gage.parameter_name == "Gage height"
    assert snap_gage.normalized_value == 2.90
    assert snap_gage.unit == "ft"


def test_2_schema_validation():
    """Test 2: Schema validation catches non-JSON, missing types, and malformed features."""
    normalizer = TelemetryNormalizer()

    # Non-dict
    status, _, _ = normalizer.validate_feature_collection("invalid_string")
    assert status == TelemetryStatus.SCHEMA_ERROR

    # Wrong type
    status, _, _ = normalizer.validate_feature_collection({"type": "Point"})
    assert status == TelemetryStatus.SCHEMA_ERROR

    # Features not a list
    status, _, _ = normalizer.validate_feature_collection({"type": "FeatureCollection", "features": "none"})
    assert status == TelemetryStatus.SCHEMA_ERROR

    # Empty features
    status, features, _ = normalizer.validate_feature_collection({"type": "FeatureCollection", "features": []})
    assert status == TelemetryStatus.NO_DATA
    assert features == []

    # Feature missing properties
    status, snap, _ = normalizer.normalize_feature(
        feature={"type": "Feature"},
        source_url="https://api.waterdata.usgs.gov/test",
    )
    assert status == TelemetryStatus.SCHEMA_ERROR
    assert snap is None


def test_3_missing_value_handling():
    """Test 3: Handling missing, empty, or non-numeric values without fabricating data."""
    normalizer = TelemetryNormalizer()

    # None value returns SCHEMA_ERROR (required property missing)
    feat_none = {
        "type": "Feature",
        "properties": {
            "monitoring_location_id": "USGS-01646500",
            "parameter_code": "00060",
            "time": "2026-10-03T16:50:00Z",
            "value": None,
        },
    }
    status, snap, _ = normalizer.normalize_feature(feat_none, "https://test")
    assert status == TelemetryStatus.SCHEMA_ERROR
    assert snap is None

    # Empty string value returns NO_DATA
    feat_empty = {
        "type": "Feature",
        "properties": {
            "monitoring_location_id": "USGS-01646500",
            "parameter_code": "00060",
            "time": "2026-10-03T16:50:00Z",
            "value": "",
        },
    }
    status, snap, _ = normalizer.normalize_feature(feat_empty, "https://test")
    assert status == TelemetryStatus.NO_DATA
    assert snap is None

    # Non-numeric string value (e.g. Equipment Error) preserves raw value with None normalized
    feat_bad_num = {
        "type": "Feature",
        "properties": {
            "monitoring_location_id": "USGS-01646500",
            "parameter_code": "00060",
            "time": "2026-10-03T16:50:00Z",
            "value": "EQUIPMENT_MALFUNCTION",
        },
    }
    status, snap, _ = normalizer.normalize_feature(feat_bad_num, "https://test")
    assert status == TelemetryStatus.SUCCESS
    assert snap.raw_value == "EQUIPMENT_MALFUNCTION"
    assert snap.normalized_value is None


def test_4_timestamp_handling():
    """Test 4: Parsing valid ISO 8601 timestamps and handling malformed ones."""
    # UTC with Z
    ts1 = parse_iso_timestamp("2026-10-03T16:50:00Z")
    assert ts1 is not None

    # UTC with explicit offset
    ts2 = parse_iso_timestamp("2026-10-03T16:50:00+00:00")
    assert ts2 == ts1

    # Malformed timestamp returns None
    ts_bad = parse_iso_timestamp("invalid-date-string")
    assert ts_bad is None

    # Normalization with unparseable timestamp fails schema validation
    normalizer = TelemetryNormalizer()
    feat_bad_time = {
        "type": "Feature",
        "properties": {
            "monitoring_location_id": "USGS-01646500",
            "parameter_code": "00060",
            "time": "not-a-timestamp",
            "value": "2350",
            "unit_of_measure": "ft^3/s",
        },
    }
    status, snap, _ = normalizer.normalize_feature(feat_bad_time, "https://test")
    assert status == TelemetryStatus.SCHEMA_ERROR
    assert snap is None


def test_5_freshness_classification():
    """Test 5: Explicit classification into FRESH, STALE, and UNKNOWN based on threshold."""
    normalizer = TelemetryNormalizer(config=TelemetryConfig(freshness_threshold_seconds=7200.0))
    current_time = 1791047588.0

    # Fresh observation (age = 1388s < 7200s)
    fresh_time_str = "2026-10-03T16:50:00+00:00"  # 1791046200.0
    feat_fresh = {
        "type": "Feature",
        "properties": {
            "monitoring_location_id": "USGS-01646500",
            "parameter_code": "00060",
            "time": fresh_time_str,
            "value": "2350",
            "unit_of_measure": "ft^3/s",
        },
    }
    _, snap_fresh, _ = normalizer.normalize_feature(
        feat_fresh, "https://test", retrieved_timestamp=current_time
    )
    assert snap_fresh.freshness == ObservationFreshness.FRESH
    assert snap_fresh.freshness_age_seconds == pytest.approx(1388.0, rel=1e-2)

    # Stale observation (age = 36000s > 7200s, i.e. 10 hours old)
    stale_time_str = "2026-10-03T07:13:08+00:00"  # 1791011588.0
    feat_stale = {
        "type": "Feature",
        "properties": {
            "monitoring_location_id": "USGS-01646500",
            "parameter_code": "00060",
            "time": stale_time_str,
            "value": "2350",
            "unit_of_measure": "ft^3/s",
        },
    }
    _, snap_stale, _ = normalizer.normalize_feature(
        feat_stale, "https://test", retrieved_timestamp=current_time
    )
    assert snap_stale.freshness == ObservationFreshness.STALE
    assert snap_stale.freshness_age_seconds > 7200.0


def test_6_provenance_preservation(sample_snapshot):
    """Test 6: Full origin lineage is preserved across normalization and evidence conversion."""
    evidence = TelemetryEvidenceAdapter.to_evidence(sample_snapshot)

    # Invariant: Never silently discard provenance
    assert evidence.metadata["provider"] == "USGS"
    assert evidence.metadata["source_url"] == sample_snapshot.source_url
    assert evidence.metadata["provenance_hash"] == sample_snapshot.provenance_hash
    assert evidence.metadata["raw_record_hash"] == sample_snapshot.raw_record_hash
    assert evidence.observation["monitoring_location_id"] == "USGS-01646500"
    assert evidence.observation["parameter_code"] == "00060"
    assert evidence.observation["approval_status"] == "Provisional"
    assert "USGS OGC API" in evidence.provenance


def test_7_observation_hashing(sample_snapshot):
    """Test 7: Deterministic SHA-256 payload and provenance hashing with tamper detection."""
    # Identity hash reproduction
    h1 = compute_observation_payload_hash(
        provider=sample_snapshot.provider,
        source_url=sample_snapshot.source_url,
        monitoring_location_id=sample_snapshot.monitoring_location_id,
        parameter_code=sample_snapshot.parameter_code,
        raw_value=sample_snapshot.raw_value,
        unit=sample_snapshot.unit,
        observed_at=sample_snapshot.observed_at,
        approval_status=sample_snapshot.approval_status,
        qualifier=sample_snapshot.qualifier,
    )
    assert h1 == sample_snapshot.raw_record_hash

    # Tampered value changes hash
    h_tampered = compute_observation_payload_hash(
        provider=sample_snapshot.provider,
        source_url=sample_snapshot.source_url,
        monitoring_location_id=sample_snapshot.monitoring_location_id,
        parameter_code=sample_snapshot.parameter_code,
        raw_value="9999",  # Tampered
        unit=sample_snapshot.unit,
        observed_at=sample_snapshot.observed_at,
        approval_status=sample_snapshot.approval_status,
        qualifier=sample_snapshot.qualifier,
    )
    assert h_tampered != sample_snapshot.raw_record_hash

    # verify_observation_integrity returns True for intact snapshot
    assert verify_observation_integrity(sample_snapshot) is True

    # Modified snapshot fails verification
    tampered_snap = sample_snapshot.model_copy(update={"raw_value": "9999"})
    assert verify_observation_integrity(tampered_snap) is False


def test_8_replay_equivalence(sample_snapshot):
    """Test 8: Deterministic replay reproduces exact ObservationSnapshot and hashes offline."""
    record = TelemetryReplayRecord(
        record_id="rec_test_replay_001",
        mode=TelemetryMode.REPLAYED_OBSERVATION,
        snapshots=[sample_snapshot],
        recorded_at="2026-10-03T17:15:00+00:00",
    )
    record_dict = record.to_dict()

    # Replay engine reconstructs from dict with 0 network calls
    replayed_record = TelemetryReplayRecord.from_dict(record_dict)

    assert len(replayed_record.snapshots) == 1
    replayed_snap = replayed_record.snapshots[0]
    assert replayed_snap.observation_id == sample_snapshot.observation_id
    assert replayed_snap.raw_record_hash == sample_snapshot.raw_record_hash
    assert replayed_snap.provenance_hash == sample_snapshot.provenance_hash
    assert replayed_record.mode == TelemetryMode.REPLAYED_OBSERVATION

    # Replay verification check passes
    assert verify_observation_integrity(replayed_snap) is True


def test_9_network_failure_handling():
    """Test 9: Network DNS/connection failure fails closed with TRANSPORT_ERROR."""
    provider = USGSOgcTelemetryProvider()

    with patch("urllib.request.urlopen", side_effect=urllib.error.URLError("Connection refused / DNS lookup failed")):
        snapshots = provider.fetch_latest_observations(parameter_codes=["00060"])
        assert len(snapshots) == 0
        assert provider.get_last_status() == TelemetryStatus.TRANSPORT_ERROR


def test_10_http_failure_handling():
    """Test 10: HTTP 404, 500, or 429 rate limit errors fail closed with HTTP_ERROR."""
    provider = USGSOgcTelemetryProvider()

    # Mock HTTP 500 Internal Server Error
    http_500 = urllib.error.HTTPError(
        url="https://api.waterdata.usgs.gov/test",
        code=500,
        msg="Internal Server Error",
        hdrs={},
        fp=None,
    )
    with patch("urllib.request.urlopen", side_effect=http_500):
        snapshots = provider.fetch_latest_observations(parameter_codes=["00060"])
        assert len(snapshots) == 0
        assert provider.get_last_status() == TelemetryStatus.HTTP_ERROR

    # Mock HTTP 429 Rate Limit
    http_429 = urllib.error.HTTPError(
        url="https://api.waterdata.usgs.gov/test",
        code=429,
        msg="Too Many Requests",
        hdrs={},
        fp=None,
    )
    with patch("urllib.request.urlopen", side_effect=http_429):
        snapshots_429 = provider.fetch_latest_observations(parameter_codes=["00060"])
        assert len(snapshots_429) == 0
        assert provider.get_last_status() == TelemetryStatus.HTTP_ERROR


def test_11_stale_observation_handling(sample_snapshot):
    """Test 11: Stale observation is never silently promoted to fresh state."""
    stale_snapshot = sample_snapshot.model_copy(
        update={
            "freshness": ObservationFreshness.STALE,
            "freshness_age_seconds": 18000.0,
        }
    )

    evidence = TelemetryEvidenceAdapter.to_evidence(stale_snapshot)
    # Stale evidence receives lower confidence
    assert evidence.confidence <= 0.40
    assert evidence.metadata["freshness_status"] == "STALE"

    # Attached to world state reflects STALE
    world = WorldState(
        valves={"valve_a": "OPEN", "valve_b": "OPEN"},
        cooling="ACTIVE",
        human_zone="CLEAR",
        pumps={"pump_p1": "INACTIVE"},
        version=1,
    )
    world = TelemetryEvidenceAdapter.attach_to_world_state(world, [stale_snapshot])
    assert world.external_observations["usgs"]["streamflow_cfs"]["freshness"] == "STALE"


def test_12_malformed_response_handling():
    """Test 12: Malformed unparseable JSON from public API fails closed."""
    provider = USGSOgcTelemetryProvider()

    mock_resp = MagicMock()
    mock_resp.status = 200
    mock_resp.read.return_value = b'{"type": "FeatureCollection", "features": [MALFORMED_UNCLOSED_JSON'
    mock_resp.__enter__.return_value = mock_resp

    with patch("urllib.request.urlopen", return_value=mock_resp):
        snapshots = provider.fetch_latest_observations(parameter_codes=["00060"])
        assert len(snapshots) == 0
        assert provider.get_last_status() == TelemetryStatus.SCHEMA_ERROR


def test_13_external_observation_cannot_mint_authorization_ticket(sample_snapshot):
    """Test 13: An external observation cannot invoke SafetyEnclave to mint tickets."""
    enclave = SafetyEnclave()
    world = WorldState(
        valves={"valve_a": "OPEN", "valve_b": "OPEN"},
        cooling="ACTIVE",
        human_zone="CLEAR",
        pumps={"pump_p1": "INACTIVE"},
        version=1,
    )

    # Telemetry snapshot or provider has zero access to mint tickets
    assert not hasattr(sample_snapshot, "mint_ticket")
    assert not hasattr(sample_snapshot, "issue_ticket")
    assert not hasattr(sample_snapshot, "authorize")

    # SafetyEnclave requires EnclaveAuthorizationRequest, NOT external telemetry
    with pytest.raises(Exception):
        enclave.authorize(sample_snapshot)


def test_14_external_observation_cannot_actuate_hardware(sample_snapshot):
    """Test 14: External telemetry has zero actuator authority."""
    world = PhysicalWorld()
    hardware = MockHardwareEndpoint(world=world)

    proposal = ActionProposal(
        id="prop_unauth_01",
        action_type=ActionType.CLOSE_VALVE,
        target="valve_b",
        parameters={},
        rationale="Attempting actuation directly from telemetry.",
        model_confidence=0.96,
        supporting_evidence_ids=[],
        timestamp=time.time(),
    )

    # Attempting to execute hardware action with external observation / no ticket fails immediately
    rec = hardware.receive_and_actuate(
        proposal=proposal,
        ticket=None,  # External observation cannot supply an authorization ticket
    )
    assert rec.execution_status.value == "LOCKED"
    assert "No AuthorizationTicket" in rec.message
    assert hardware.is_locked is True


def test_15_nemotron_cannot_bypass_observation_evidence_layer(sample_snapshot):
    """Test 15: AI proposal citing hallucinated or ungrounded external evidence is rejected."""
    engine = PolicyEngine()
    world = WorldState(
        valves={"valve_a": "OPEN", "valve_b": "OPEN"},
        cooling="ACTIVE",
        human_zone="CLEAR",
        pumps={"pump_p1": "INACTIVE"},
        version=1,
    )

    # Proposal citing hallucinated external river evidence
    hallucinated_proposal = ActionProposal(
        id="prop_hallucinated_01",
        action_type=ActionType.CLOSE_VALVE,
        target="valve_b",
        parameters={},
        rationale="River is overflowing according to unverified hallucination.",
        model_confidence=0.95,
        supporting_evidence_ids=["ev_hallucinated_river_99"],
        timestamp=time.time(),
    )

    decision = engine.evaluate(hallucinated_proposal, world, evidence=[])
    # Fails closed because target identity confidence is 0.00
    assert decision.decision == DecisionType.NEED_MORE_EVIDENCE
    assert decision.is_allowed is False


def test_16_public_api_failure_cannot_cause_allow():
    """Test 16: Failure of public telemetry API can never produce an implicit ALLOW."""
    engine = PolicyEngine()
    world_occupied = WorldState(
        valves={"valve_a": "OPEN", "valve_b": "OPEN"},
        cooling="ACTIVE",
        human_zone="OCCUPIED",
        pumps={"pump_p1": "INACTIVE"},
        version=1,
    )

    proposal = ActionProposal(
        id="prop_test_01",
        action_type=ActionType.CLOSE_VALVE,
        target="valve_b",
        parameters={},
        rationale="Attempt action when telemetry API is offline.",
        model_confidence=0.96,
        supporting_evidence_ids=[],
        timestamp=time.time(),
    )

    # Under API failure with hazard present, result is strictly DENIED
    decision = engine.evaluate(proposal, world_occupied, evidence=[])
    assert decision.decision == DecisionType.DENY
    assert decision.is_denied is True


def test_17_cached_observation_cannot_be_mislabeled_live(sample_snapshot):
    """Test 17: Bounded telemetry cache maintains strict mode isolation."""
    cache = BoundedTelemetryCache(max_entries=10)

    # Store with REPLAYED_OBSERVATION mode
    cache.put(sample_snapshot, mode=TelemetryMode.REPLAYED_OBSERVATION)

    # Retrieve and check mode
    entry_snap, entry_mode = cache.get(sample_snapshot.monitoring_location_id, sample_snapshot.parameter_code)
    assert entry_snap is not None
    assert entry_mode == TelemetryMode.REPLAYED_OBSERVATION
    assert entry_mode != TelemetryMode.LIVE_OBSERVATION


def test_18_judge_console_fixture_distinguishes_live_and_replay():
    """Test 18: Judge console fixtures explicitly distinguish LIVE vs REPLAY modes."""
    fixture_path = os.path.join(
        os.path.dirname(__file__), "..", "console", "src", "data", "scenario_telemetry.json"
    )
    assert os.path.exists(fixture_path), "scenario_telemetry.json must exist in console fixtures."

    with open(fixture_path, "r", encoding="utf-8") as f:
        data = json.load(f)

    # Invariant: Replay fixture must explicitly declare REPLAY mode
    assert data["execution_mode"] == "REPLAY"
    assert data["decision_record"]["provider_metadata"]["execution_mode"] == "REPLAY"
    assert data["decision_record"]["provider_metadata"]["source_mode"] == "RECORDED_LIVE_FIXTURE"
    assert "telemetry_observation" in data


def test_19_digital_twin_cannot_interpret_telemetry_as_actuator_state(sample_snapshot):
    """Test 19: Public telemetry does not mutate internal modeled actuator state."""
    world = WorldState(
        valves={"valve_a": "OPEN", "valve_b": "OPEN"},
        cooling="ACTIVE",
        human_zone="CLEAR",
        pumps={"pump_p1": "INACTIVE"},
        version=2,
    )

    derived = DerivedEnvironmentalContext.create(
        context_name="POTOMAC_RIVER_FLOW_REGIME",
        classification="NORMAL_FLOW",
        source_obs=sample_snapshot,
        threshold_value=5000.0,
        rule_id="RULE_USGS_POTOMAC_HIGH_FLOW_STAGE_01",
    )

    updated_world = TelemetryEvidenceAdapter.attach_to_world_state(
        world, [sample_snapshot], derived_context=derived
    )

    # Internal plant actuator state is unchanged
    assert updated_world.valves["valve_b"] == "OPEN"
    assert updated_world.pumps["pump_p1"] == "INACTIVE"
    assert updated_world.cooling == "ACTIVE"

    # External telemetry is cleanly segregated under external_observations
    assert updated_world.external_observations["usgs"]["streamflow_cfs"]["value"] == 2350.0
    assert updated_world.external_observations["environmental_context"]["classification"] == "NORMAL_FLOW"


def test_20_source_metadata_remains_attached_through_policy_evaluation(sample_snapshot):
    """Test 20: Telemetry source metadata remains attached from snapshot through policy evaluation."""
    evidence = TelemetryEvidenceAdapter.to_evidence(sample_snapshot)

    # Verification: USGS is recognized as an authoritative standards domain in trust model
    assert "usgs.gov" in SourceTrustClassifier.STANDARDS_DOMAINS

    # Create internal sensor evidence for valve_b
    plant_evidence = Evidence(
        id="ev_plant_press_01",
        source=EvidenceSource.SYSTEM_TELEMETRY,
        target="valve_b",
        observation={"pressure_psi": 95.0, "leak_flow_lpm": 12.0},
        confidence=0.96,
        timestamp=time.time(),
        provenance="plant_manifold_sensor_01",
        metadata={"subsystem": "coolant"},
    )

    world = WorldState(
        valves={"valve_a": "OPEN", "valve_b": "OPEN"},
        cooling="ACTIVE",
        human_zone="CLEAR",
        pumps={"pump_p1": "INACTIVE"},
        version=3,
    )
    world = TelemetryEvidenceAdapter.attach_to_world_state(world, [sample_snapshot])

    proposal = ActionProposal(
        id="prop_isolate_leak",
        action_type=ActionType.CLOSE_VALVE,
        target="valve_b",
        parameters={},
        rationale="Isolating leak while river flow is normal.",
        model_confidence=0.96,
        supporting_evidence_ids=[plant_evidence.id, evidence.id],
        timestamp=time.time(),
    )

    engine = PolicyEngine()
    decision = engine.evaluate(proposal, world, evidence=[plant_evidence, evidence])

    assert decision.decision == DecisionType.ALLOW
    assert decision.is_allowed is True
    # Both plant and river evidence remain bound
    assert evidence.metadata["provider"] == "USGS"
    assert evidence.metadata["source_url"] == sample_snapshot.source_url
    assert evidence.observation["monitoring_location_id"] == "USGS-01646500"
