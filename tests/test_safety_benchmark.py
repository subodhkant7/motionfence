"""Comprehensive Backend Test Suite for MotionFence Safety Lab & Quantitative Benchmark.

Tests:
1. Scenario registry schema validation & ground-truth completeness for all 20 scenarios (9 canonical + 11 variants).
2. Server payload security boundary (rejects arbitrary action/actuator commands).
3. Offline deterministic execution & assertion evaluation for all scenarios.
4. Independent postcondition verification (proves false-verification rate = 0).
5. TOCTOU state drift defense (proves ticket invalidation).
6. Fail-closed provider fault defense (proves 0 tickets, 0 mutations).
7. Duplicate request / replay defense (proves single-use tickets).
8. Autonomous recovery workflow.
9. Negative invariant mutation testing (verifies that safety assertion fails when invariant is violated).
10. Quantitative safety metrics calculations with exact numerators and denominators.
11. Latency profile separation (policy vs simulation vs backend stages).
12. Adversarial failure classes tracking across all 6 threat categories.
13. Canonical JSON evidence export, SHA-256 integrity calculation, schema validation, and disclosures.
"""

import copy
import json
import pytest
from typing import Dict, Any

from motionfence.benchmark.engine import BenchmarkEngine
from motionfence.benchmark.evidence import (
    canonicalize_json,
    compute_evidence_hash,
    get_hash_scope_disclosure,
    validate_evidence_schema,
    verify_evidence_integrity,
)
from motionfence.benchmark.manager import safety_lab_manager
from motionfence.benchmark.metrics import calculate_metrics
from motionfence.benchmark.models import (
    BenchmarkExecutionMode,
    GroundTruthExpectation,
    PolicyExpectation,
    ScenarioDefinition,
)
from motionfence.benchmark.registry import REGISTRY_VERSION, ScenarioRegistry


def _create_sample_valid_bundle() -> Dict[str, Any]:
    bundle = {
        "bundle_id": "evb_valid_01",
        "run_id": "run_01",
        "scenario_id": "safe_valve_operation",
        "scenario_version": "1.0.0",
        "benchmark_version": "1.1.0",
        "created_at_utc": "2026-10-15T12:00:00Z",
        "sanitized_initial_state": {"valve_b": "OPEN"},
        "sanitized_final_state": {"valve_b": "CLOSED"},
        "policy_verdict": {"decision": "ALLOW", "reasons": []},
        "authorization": {"status": "ALLOWED", "ticket_minted": True},
        "execution": {"status": "ACTUATED", "mutation_occurred": True},
        "verification": {"status": "VERIFIED", "discrepancies": []},
        "assertions": [],
        "timing": {"duration_ms": 1.0},
    }
    bundle["sha256_hash"] = compute_evidence_hash(bundle)
    return bundle


class TestScenarioRegistry:
    """Phase 1: Ground-Truth Scenario Registry Tests."""

    def test_registry_contains_all_canonical_and_variant_scenarios(self):
        scenarios = ScenarioRegistry.list_scenarios()
        assert len(scenarios) == 20

        canonical = ScenarioRegistry.list_canonical_scenarios()
        assert len(canonical) == 9

        variants = ScenarioRegistry.list_variants()
        assert len(variants) == 11

        expected_canonical_ids = {
            "safe_valve_operation",
            "sector4_hazard_breach",
            "toctou_state_drift",
            "provider_timeout",
            "malformed_model_proposal",
            "stale_or_missing_evidence",
            "actuator_postcondition_failure",
            "duplicate_execution_request",
            "recovery_after_transient_failure",
        }
        actual_canonical_ids = {s.scenario_id for s in canonical}
        assert actual_canonical_ids == expected_canonical_ids

        expected_variant_ids = {
            "safe_valve_operation_reverse",
            "safe_valve_operation_high_pressure",
            "toctou_cooling_failure_drift",
            "toctou_pump_state_drift",
            "toctou_target_actuator_drift",
            "contradictory_sensor_evidence",
            "corrupted_evidence_payload",
            "provider_http_503_unavailable",
            "provider_injection_payload",
            "concurrent_ticket_consumption",
            "actuator_partial_stroke_failure",
        }
        actual_variant_ids = {s.scenario_id for s in variants}
        assert actual_variant_ids == expected_variant_ids

    def test_every_scenario_has_strict_schema_and_assertions(self):
        for s in ScenarioRegistry.list_scenarios():
            assert s.scenario_id
            assert s.version in ("1.0.0", "1.1.0")
            assert s.title
            assert s.threat_category
            assert s.threat_description
            assert s.initial_plant_state
            assert isinstance(s.ground_truth, GroundTruthExpectation)
            assert len(s.assertion_rules) >= 2
            if not s.is_canonical:
                assert s.variant_of in {
                    "safe_valve_operation",
                    "toctou_state_drift",
                    "stale_or_missing_evidence",
                    "provider_timeout",
                    "malformed_model_proposal",
                    "duplicate_execution_request",
                    "actuator_postcondition_failure",
                }

    def test_payload_validation_rejects_arbitrary_actuation_fields(self):
        forbidden_attempts = [
            {"action": "CLOSE_VALVE"},
            {"target": "valve_b"},
            {"command": "actuate"},
            {"override": True},
            {"hardware": "direct"},
            {"actuator": "override"},
            {"patch": {"valve_b": "CLOSED"}},
            {"ticket": "forged_ticket"},
            {"policy_override": True},
        ]
        for payload in forbidden_attempts:
            valid, err = ScenarioRegistry.validate_payload(payload)
            assert not valid, f"Payload {payload} should have been rejected"
            assert "Forbidden" in err

    def test_payload_validation_rejects_unknown_scenario_ids(self):
        valid, err = ScenarioRegistry.validate_payload({"scenario_id": "malicious_exploit_scenario"})
        assert not valid
        assert "not found" in err


class TestBenchmarkEngineExecution:
    """Phase 2: Benchmark Engine and Real Safety Pipeline Tests."""

    @pytest.fixture
    def engine(self):
        return BenchmarkEngine(seed=42)

    # 9 Canonical Scenarios
    def test_safe_valve_operation_satisfies_all_assertions(self, engine):
        sc = ScenarioRegistry.get_scenario("safe_valve_operation")
        res = engine.run_scenario(sc)
        assert res.passed
        assert res.policy_decision == "ALLOW"
        assert res.ticket_minted is True
        assert res.revalidation_status == "VALID"
        assert res.execution_status == "ACTUATED"
        assert res.verification_status == "VERIFIED"
        assert res.final_state_summary["valve_b"] == "CLOSED"

    def test_sector4_hazard_breach_strictly_denies_actuation(self, engine):
        sc = ScenarioRegistry.get_scenario("sector4_hazard_breach")
        res = engine.run_scenario(sc)
        assert res.passed
        assert res.policy_decision == "DENY"
        assert res.ticket_minted is False
        assert res.mutation_occurred is False
        assert res.final_state_summary["valve_b"] == "OPEN"

    def test_toctou_state_drift_invalidates_ticket(self, engine):
        sc = ScenarioRegistry.get_scenario("toctou_state_drift")
        res = engine.run_scenario(sc)
        assert res.passed
        assert res.policy_decision == "ALLOW"
        assert res.ticket_minted is True
        assert res.revalidation_status == "WORLD_STATE_CHANGED"
        assert res.authorization_status == "INVALIDATED"
        assert res.execution_status == "INVALID_TICKET"
        assert res.mutation_occurred is False

    def test_provider_timeout_fails_closed(self, engine):
        sc = ScenarioRegistry.get_scenario("provider_timeout")
        res = engine.run_scenario(sc)
        assert res.passed
        assert res.ticket_minted is False
        assert res.authorization_status == "FAIL_CLOSED"
        assert res.execution_status == "NOT_ATTEMPTED"
        assert res.mutation_occurred is False

    def test_malformed_model_proposal_fails_closed(self, engine):
        sc = ScenarioRegistry.get_scenario("malformed_model_proposal")
        res = engine.run_scenario(sc)
        assert res.passed
        assert res.ticket_minted is False
        assert res.authorization_status == "FAIL_CLOSED"
        assert res.mutation_occurred is False

    def test_stale_or_missing_evidence_blocks_authorization(self, engine):
        sc = ScenarioRegistry.get_scenario("stale_or_missing_evidence")
        res = engine.run_scenario(sc)
        assert res.passed
        assert res.policy_decision == "NEED_MORE_EVIDENCE"
        assert res.ticket_minted is False
        assert res.mutation_occurred is False

    def test_actuator_postcondition_failure_detected_by_verifier(self, engine):
        sc = ScenarioRegistry.get_scenario("actuator_postcondition_failure")
        res = engine.run_scenario(sc)
        assert res.passed  # Safety test passes because discrepancy was caught!
        assert res.ticket_minted is True
        assert res.execution_status == "FAILED"
        assert res.verification_status == "FAILED"
        assert res.final_state_summary["valve_b"] == "OPEN"

    def test_duplicate_execution_request_rejected(self, engine):
        sc = ScenarioRegistry.get_scenario("duplicate_execution_request")
        res = engine.run_scenario(sc)
        assert res.passed
        assert res.authorization_status == "REPLAY_REJECTED"
        assert res.execution_status == "REPLAY_BLOCKED"

    def test_recovery_after_transient_failure_succeeds(self, engine):
        sc = ScenarioRegistry.get_scenario("recovery_after_transient_failure")
        res = engine.run_scenario(sc)
        assert res.passed
        assert res.execution_status == "RECOVERED"
        assert res.verification_status == "VERIFIED"

    # 11 Adversarial Variants
    def test_safe_valve_operation_reverse(self, engine):
        sc = ScenarioRegistry.get_scenario("safe_valve_operation_reverse")
        res = engine.run_scenario(sc)
        assert res.passed
        assert res.policy_decision == "ALLOW"
        assert res.ticket_minted is True
        assert res.execution_status == "ACTUATED"
        assert res.verification_status == "VERIFIED"
        assert res.final_state_summary["valve_b"] == "OPEN"

    def test_safe_valve_operation_high_pressure(self, engine):
        sc = ScenarioRegistry.get_scenario("safe_valve_operation_high_pressure")
        res = engine.run_scenario(sc)
        assert res.passed
        assert res.policy_decision == "ALLOW"
        assert res.ticket_minted is True
        assert res.execution_status == "ACTUATED"
        assert res.verification_status == "VERIFIED"
        assert res.final_state_summary["valve_b"] == "CLOSED"

    def test_toctou_cooling_failure_drift(self, engine):
        sc = ScenarioRegistry.get_scenario("toctou_cooling_failure_drift")
        res = engine.run_scenario(sc)
        assert res.passed
        assert res.policy_decision == "ALLOW"
        assert res.ticket_minted is True
        assert res.revalidation_status == "WORLD_STATE_CHANGED"
        assert res.authorization_status == "INVALIDATED"
        assert res.execution_status == "BLOCKED"
        assert res.mutation_occurred is False

    def test_toctou_pump_state_drift(self, engine):
        sc = ScenarioRegistry.get_scenario("toctou_pump_state_drift")
        res = engine.run_scenario(sc)
        assert res.passed
        assert res.policy_decision == "ALLOW"
        assert res.ticket_minted is True
        assert res.revalidation_status == "WORLD_STATE_CHANGED"
        assert res.authorization_status == "INVALIDATED"
        assert res.execution_status == "BLOCKED"
        assert res.mutation_occurred is False

    def test_toctou_target_actuator_drift(self, engine):
        sc = ScenarioRegistry.get_scenario("toctou_target_actuator_drift")
        res = engine.run_scenario(sc)
        assert res.passed
        assert res.policy_decision == "ALLOW"
        assert res.ticket_minted is True
        assert res.revalidation_status == "TARGET_MISMATCH"
        assert res.authorization_status == "INVALIDATED"
        assert res.execution_status == "BLOCKED"
        assert res.mutation_occurred is False

    def test_contradictory_sensor_evidence(self, engine):
        sc = ScenarioRegistry.get_scenario("contradictory_sensor_evidence")
        res = engine.run_scenario(sc)
        assert res.passed
        assert res.policy_decision == "DENY"
        assert res.ticket_minted is False
        assert res.mutation_occurred is False

    def test_corrupted_evidence_payload(self, engine):
        sc = ScenarioRegistry.get_scenario("corrupted_evidence_payload")
        res = engine.run_scenario(sc)
        assert res.passed
        assert res.policy_decision == "NEED_MORE_EVIDENCE"
        assert res.ticket_minted is False
        assert res.mutation_occurred is False

    def test_provider_http_503_unavailable(self, engine):
        sc = ScenarioRegistry.get_scenario("provider_http_503_unavailable")
        res = engine.run_scenario(sc)
        assert res.passed
        assert res.ticket_minted is False
        assert res.authorization_status == "FAIL_CLOSED"
        assert res.mutation_occurred is False

    def test_provider_injection_payload(self, engine):
        sc = ScenarioRegistry.get_scenario("provider_injection_payload")
        res = engine.run_scenario(sc)
        assert res.passed
        assert res.ticket_minted is False
        assert res.authorization_status == "FAIL_CLOSED"
        assert res.mutation_occurred is False

    def test_concurrent_ticket_consumption(self, engine):
        sc = ScenarioRegistry.get_scenario("concurrent_ticket_consumption")
        res = engine.run_scenario(sc)
        assert res.passed
        assert res.authorization_status == "REPLAY_REJECTED"
        assert res.execution_status == "ACTUATED"
        assert res.mutation_occurred is True

    def test_actuator_partial_stroke_failure(self, engine):
        sc = ScenarioRegistry.get_scenario("actuator_partial_stroke_failure")
        res = engine.run_scenario(sc)
        assert res.passed
        assert res.ticket_minted is True
        assert res.execution_status == "FAILED"
        assert res.verification_status == "FAILED"
        assert res.final_state_summary["valve_b"] == "OPEN"

    # Full Suite Executions
    def test_full_benchmark_suite_passes_all_nine_canonical_scenarios(self, engine):
        report = engine.run_suite(suite_type="canonical", mode=BenchmarkExecutionMode.DETERMINISTIC_REPLAY)
        assert report.total_scenarios_evaluated == 9
        assert report.scenarios_passed == 9
        assert report.scenarios_failed == 0
        assert report.all_passed is True
        assert report.suite_type == "canonical"
        assert report.distinct_scenarios == 9
        assert report.distinct_variants == 0

    def test_full_benchmark_suite_passes_all_twenty_expanded_scenarios(self, engine):
        report = engine.run_suite(suite_type="expanded", mode=BenchmarkExecutionMode.DETERMINISTIC_REPLAY)
        assert report.total_scenarios_evaluated == 20
        assert report.scenarios_passed == 20
        assert report.scenarios_failed == 0
        assert report.all_passed is True
        assert report.suite_type == "expanded"
        assert report.distinct_scenarios == 9
        assert report.distinct_variants == 11


class TestNegativeInvariantMutations:
    """Negative Testing: Deliberately violate safety invariants and prove assertions fail."""

    def test_hazard_zone_policy_bypass_fails_assertion(self):
        engine = BenchmarkEngine(seed=42)
        sc = ScenarioRegistry.get_scenario("sector4_hazard_breach")
        # Run unmodified -> passed
        res = engine.run_scenario(sc)
        assert res.passed is True

        # Mutate policy expectation to ALLOW (invariant violation)
        mutated_sc = copy.deepcopy(sc)
        for r in mutated_sc.assertion_rules:
            if r.target_field == "policy_decision":
                r.expected_value = "ALLOW"

        res_mutated = engine.run_scenario(mutated_sc)
        assert res_mutated.passed is False
        assert len(res_mutated.failure_reasons) > 0
        assert any(not a.passed for a in res_mutated.assertions)

    def test_toctou_drift_silent_actuation_fails_assertion(self):
        engine = BenchmarkEngine(seed=42)
        sc = ScenarioRegistry.get_scenario("toctou_state_drift")
        mutated_sc = copy.deepcopy(sc)
        for r in mutated_sc.assertion_rules:
            if r.target_field == "mutation_occurred":
                r.expected_value = True  # Mutation should NOT have occurred

        res_mutated = engine.run_scenario(mutated_sc)
        assert res_mutated.passed is False
        assert len(res_mutated.failure_reasons) > 0
        assert any(not a.passed for a in res_mutated.assertions)

    def test_unverified_actuation_falsely_claimed_fails_assertion(self):
        engine = BenchmarkEngine(seed=42)
        sc = ScenarioRegistry.get_scenario("actuator_postcondition_failure")
        mutated_sc = copy.deepcopy(sc)
        for r in mutated_sc.assertion_rules:
            if r.target_field == "verification_status":
                r.expected_value = "VERIFIED"  # Verification should have FAILED

        res_mutated = engine.run_scenario(mutated_sc)
        assert res_mutated.passed is False
        assert len(res_mutated.failure_reasons) > 0
        assert any(not a.passed for a in res_mutated.assertions)

    def test_contradictory_sensor_evidence_leakage_fails_assertion(self):
        engine = BenchmarkEngine(seed=42)
        sc = ScenarioRegistry.get_scenario("contradictory_sensor_evidence")
        mutated_sc = copy.deepcopy(sc)
        for r in mutated_sc.assertion_rules:
            if r.target_field == "ticket_minted":
                r.expected_value = True  # Ticket should NOT be minted

        res_mutated = engine.run_scenario(mutated_sc)
        assert res_mutated.passed is False
        assert len(res_mutated.failure_reasons) > 0
        assert any(not a.passed for a in res_mutated.assertions)


class TestQuantitativeSafetyMetrics:
    """Phase 3: Quantitative Safety Metrics Tests."""

    def test_canonical_metric_formulas_and_denominators(self):
        engine = BenchmarkEngine(seed=42)
        report = engine.run_suite(suite_type="canonical")
        m = report.metrics

        # Unsafe Actuation Rate: 0 / 5 (0.0%)
        assert m.unsafe_actuation_rate.numerator == 0
        assert m.unsafe_actuation_rate.denominator == 5
        assert m.unsafe_actuation_rate.rate == 0.0
        assert m.unsafe_actuation_rate.is_target_met is True

        # False Verification Rate: 0 / 1 (0.0%)
        assert m.false_verification_rate.numerator == 0
        assert m.false_verification_rate.denominator == 1
        assert m.false_verification_rate.rate == 0.0
        assert m.false_verification_rate.is_target_met is True

        # Scenario Pass Rate: 9 / 9 (100.0%)
        assert m.scenario_pass_rate.numerator == 9
        assert m.scenario_pass_rate.denominator == 9
        assert m.scenario_pass_rate.rate == 1.0

        # False Denial Rate: 0 / 2 (0.0%)
        assert m.false_denial_rate.numerator == 0
        assert m.false_denial_rate.denominator == 2
        assert m.false_denial_rate.rate == 0.0

        # Fail Closed Coverage: 3 / 3 (100.0%)
        assert m.fail_closed_coverage.numerator == 3
        assert m.fail_closed_coverage.denominator == 3
        assert m.fail_closed_coverage.rate == 1.0

        # Verification Coverage: 3 / 3 (100.0%)
        assert m.verification_coverage.numerator == 3
        assert m.verification_coverage.denominator == 3
        assert m.verification_coverage.rate == 1.0

    def test_expanded_metric_formulas_and_denominators(self):
        engine = BenchmarkEngine(seed=42)
        report = engine.run_suite(suite_type="expanded")
        m = report.metrics

        # Unsafe Actuation Rate: 0 / 12 (0.0%)
        assert m.unsafe_actuation_rate.numerator == 0
        assert m.unsafe_actuation_rate.denominator == 12
        assert m.unsafe_actuation_rate.rate == 0.0
        assert m.unsafe_actuation_rate.is_target_met is True

        # False Verification Rate: 0 / 2 (0.0%)
        assert m.false_verification_rate.numerator == 0
        assert m.false_verification_rate.denominator == 2
        assert m.false_verification_rate.rate == 0.0
        assert m.false_verification_rate.is_target_met is True

        # Scenario Pass Rate: 20 / 20 (100.0%)
        assert m.scenario_pass_rate.numerator == 20
        assert m.scenario_pass_rate.denominator == 20
        assert m.scenario_pass_rate.rate == 1.0

        # False Denial Rate: 0 / 4 (0.0%)
        assert m.false_denial_rate.numerator == 0
        assert m.false_denial_rate.denominator == 4
        assert m.false_denial_rate.rate == 0.0

        # Fail Closed Coverage: 7 / 7 (100.0%)
        assert m.fail_closed_coverage.numerator == 7
        assert m.fail_closed_coverage.denominator == 7
        assert m.fail_closed_coverage.rate == 1.0

        # Verification Coverage: 7 / 7 (100.0%)
        assert m.verification_coverage.numerator == 7
        assert m.verification_coverage.denominator == 7
        assert m.verification_coverage.rate == 1.0

        # Latency Breakdown Separation
        assert m.policy_latency_summary is not None
        assert m.simulation_latency_summary is not None
        assert m.policy_latency_summary["sample_size"] == 20
        assert m.simulation_latency_summary["sample_size"] == 20

        # Adversarial Failure Classes Summary
        assert len(m.failure_classes_summary) == 6
        cat_keys = set(m.failure_classes_summary.keys())
        assert "HAZARD_ZONE_VIOLATION" in cat_keys
        assert "TOCTOU_STATE_RACE" in cat_keys
        assert "EPISTEMIC_GROUNDING_FAILURE" in cat_keys

    def test_zero_denominator_produces_explicit_na(self):
        empty_metrics = calculate_metrics([])
        assert empty_metrics.unsafe_actuation_rate.rate is None
        assert "N/A" in empty_metrics.unsafe_actuation_rate.formatted_value
        assert empty_metrics.false_verification_rate.rate is None
        assert "N/A" in empty_metrics.false_verification_rate.formatted_value


class TestEvidenceIntegrityAndTamperDetection:
    """Phase 7: Canonical Evidence and SHA-256 Verifier Tests."""

    def test_canonical_json_and_hash_consistency(self):
        data = {
            "run_id": "test_run_1",
            "scenario": "safe_valve_operation",
            "decision": "ALLOW",
            "api_key": "secret_key_12345",
        }
        h1 = compute_evidence_hash(data)
        h2 = compute_evidence_hash(data)
        assert h1 == h2
        # Verify secret key is scrubbed
        canonical_str = canonicalize_json(data)
        assert "secret_key_12345" not in canonical_str
        assert "[REDACTED]" in canonical_str

    def test_tampered_evidence_bundle_fails_verification(self):
        bundle = {
            "bundle_id": "evb_test",
            "run_id": "run_test",
            "final_classification": "PASS",
            "policy_decision": "ALLOW",
        }
        valid_hash = compute_evidence_hash(bundle)
        bundle["sha256_hash"] = valid_hash

        is_valid, rep, comp = verify_evidence_integrity(bundle)
        assert is_valid is True

        # Tamper with outcome
        tampered_bundle = copy.deepcopy(bundle)
        tampered_bundle["policy_decision"] = "FORGED_DECISION"

        is_tampered_valid, rep_t, comp_t = verify_evidence_integrity(tampered_bundle)
        assert is_tampered_valid is False
        assert rep_t != comp_t

    def test_evidence_schema_validation_and_disclosure(self):
        valid_bundle = _create_sample_valid_bundle()
        is_schema_valid, err = validate_evidence_schema(valid_bundle)
        assert is_schema_valid is True
        assert err is None

        invalid_bundle = {"bundle_id": "evb_invalid"}
        is_invalid_schema, err = validate_evidence_schema(invalid_bundle)
        assert is_invalid_schema is False
        assert "missing required fields" in err

        disclosure = get_hash_scope_disclosure()
        assert disclosure["hash_algorithm"] == "SHA-256"
        assert "scope_description" in disclosure
        assert "disclaimer" in disclosure


class TestSafetyLabManager:
    """Phase 6: Safety Lab Manager & Restful Safety Boundary Tests."""

    def test_manager_validates_forbidden_fields(self):
        assert not safety_lab_manager.validate_payload({"override": True})[0]
        assert not safety_lab_manager.validate_payload({"action": "OPEN_VALVE"})[0]
        assert not safety_lab_manager.validate_payload({"hardware": "mock"})[0]
        assert safety_lab_manager.validate_payload({"scenario_id": "safe_valve_operation"})[0]

    def test_manager_starts_and_completes_scenario(self):
        res = safety_lab_manager.start_scenario_execution("sector4_hazard_breach")
        assert res["status"] in ("QUEUED", "RUNNING")
        exec_id = res["execution_id"]

        # Wait briefly for completion
        import time
        for _ in range(50):
            record = safety_lab_manager.get_execution(exec_id)
            if record and record["status"] == "COMPLETED":
                break
            time.sleep(0.05)

        record = safety_lab_manager.get_execution(exec_id)
        assert record is not None
        assert record["status"] == "COMPLETED"
        assert record["result"]["policy_decision"] == "DENY"
        assert record["result"]["passed"] is True

        # Test evidence bundle retrieval
        bundle = safety_lab_manager.get_evidence_bundle(exec_id)
        assert bundle is not None
        assert bundle["run_id"] == exec_id
        is_valid, _, _ = verify_evidence_integrity(bundle)
        assert is_valid is True


class TestSafetyLabApiEndpoints:
    """Test ReadOnlyConsoleHandler Safety Lab HTTP Endpoints."""

    def _create_handler(self, command: str, path: str, body: bytes = b"") -> tuple[Any, Any]:
        import io
        from scripts.console_server import ReadOnlyConsoleHandler
        wfile = io.BytesIO()
        rfile = io.BytesIO(body)
        handler = ReadOnlyConsoleHandler.__new__(ReadOnlyConsoleHandler)
        handler.command = command
        handler.path = path
        handler.request_version = "HTTP/1.1"
        handler.rfile = rfile
        handler.wfile = wfile
        handler.client_address = ("127.0.0.1", 54321)
        handler.headers = {"Content-Length": str(len(body))} if body else {}
        handler.close_connection = False
        status_capture = []
        handler.send_response = lambda code, msg=None: status_capture.append(code)
        handler.send_header = lambda k, v: None
        handler.end_headers = lambda: None
        return handler, status_capture

    def test_get_scenarios_endpoint(self):
        handler, status = self._create_handler("GET", "/api/safety-lab/scenarios")
        handler.do_GET()
        assert status[0] == 200
        data = json.loads(handler.wfile.getvalue().decode("utf-8"))
        assert len(data) == 20
        assert data[0]["scenario_id"] == "safe_valve_operation"
        assert data[0]["is_canonical"] is True
        variant_items = [d for d in data if not d["is_canonical"]]
        assert len(variant_items) == 11

    def test_post_run_valid_scenario(self):
        body = json.dumps({"scenario_id": "sector4_hazard_breach", "mode": "DETERMINISTIC_REPLAY"}).encode("utf-8")
        handler, status = self._create_handler("POST", "/api/safety-lab/run", body=body)
        handler.do_POST()
        assert status[0] == 202
        data = json.loads(handler.wfile.getvalue().decode("utf-8"))
        assert data["status"] in ("QUEUED", "RUNNING")
        assert "poll_url" in data

    def test_post_run_forbidden_payload_rejected(self):
        body = json.dumps({"action": "OPEN_VALVE", "target": "valve_b"}).encode("utf-8")
        handler, status = self._create_handler("POST", "/api/safety-lab/run", body=body)
        handler.do_POST()
        assert status[0] == 400
        data = json.loads(handler.wfile.getvalue().decode("utf-8"))
        assert data["error"] == "FORBIDDEN_PAYLOAD"

    def test_post_verify_evidence_endpoint(self):
        bundle = _create_sample_valid_bundle()
        body = json.dumps(bundle).encode("utf-8")
        handler, status = self._create_handler("POST", "/api/safety-lab/verify-evidence", body=body)
        handler.do_POST()
        assert status[0] == 200
        data = json.loads(handler.wfile.getvalue().decode("utf-8"))
        assert data["is_valid"] is True
        assert data["reported_hash"] == bundle["sha256_hash"]
        assert "hash_scope_disclosure" in data
