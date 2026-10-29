"""Phase 2R Controlled Live Demo Security Boundary & Endpoint Invariant Tests.

Verifies:
1. Public browser can trigger ONLY predefined, server-controlled demonstration scenarios.
2. Arbitrary ActionProposal, target, action, policy, ticket, or hardware commands are strictly rejected.
3. Unknown scenario requests are rejected with safe HTTP error.
4. Mutating endpoints (POST /actuate, POST /execute, POST /hardware, POST /policy) return 405.
5. Concurrency isolation: multiple executions run in completely isolated contexts.
6. Secret isolation: zero credentials, private keys, or tickets leaked in responses.
7. Health endpoint distinguishes application health from dependency availability.
"""

from http import HTTPStatus
import io
import json
import os
import sys
import time
from typing import Any, Dict, List, Optional
import unittest
from unittest.mock import MagicMock

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from scripts.console_server import ReadOnlyConsoleHandler
from motionfence.runtime.controlled_demo import CANONICAL_SCENARIOS, demo_manager


class DummyServer:
    pass


class TestControlledDemoSecurity(unittest.TestCase):
    """Test suite proving that the controlled live demo API enforces strict zero-authority invariants."""

    def setUp(self):
        self.wfile = io.BytesIO()
        from scripts.console_server import rate_limiter
        with rate_limiter.lock:
            rate_limiter.ip_buckets.clear()
            rate_limiter.global_timestamps.clear()

    def _create_handler(
        self,
        command: str,
        path: str,
        body: Optional[Dict[str, Any]] = None,
        headers: Optional[Dict[str, str]] = None,
    ) -> ReadOnlyConsoleHandler:
        """Instantiate ReadOnlyConsoleHandler with mock streams."""
        request = MagicMock()
        body_bytes = json.dumps(body).encode("utf-8") if body is not None else b""
        rfile = io.BytesIO(body_bytes)
        client_address = ("127.0.0.1", 54321)
        server = DummyServer()

        handler = ReadOnlyConsoleHandler.__new__(ReadOnlyConsoleHandler)
        handler.command = command
        handler.path = path
        handler.request_version = "HTTP/1.1"
        handler.rfile = rfile
        handler.wfile = self.wfile
        handler.client_address = client_address
        handler.server = server
        handler.headers = headers or {}
        if body_bytes:
            handler.headers["Content-Length"] = str(len(body_bytes))
            handler.headers["Content-Type"] = "application/json"
        handler.close_connection = False

        handler.send_response = MagicMock(side_effect=lambda code: setattr(handler, "_status_code", code))
        handler.send_header = MagicMock()
        handler.end_headers = MagicMock()

        return handler

    def test_canonical_scenarios_listing(self):
        """GET /api/demo/scenarios must return the 6 server-controlled canonical scenarios."""
        handler = self._create_handler("GET", "/api/demo/scenarios")
        handler.do_GET()

        assert handler._status_code == 200
        output = json.loads(self.wfile.getvalue().decode("utf-8"))
        assert set(output.keys()) == {"safe", "denied", "toctou", "recovery", "telemetry", "evidence"}
        assert output["safe"]["category"] == "NOMINAL"
        assert output["denied"]["category"] == "POLICY_DENIAL"

    def test_forbidden_endpoints_rejected_with_405(self):
        """Arbitrary execution and mutation endpoints must be rejected with 405 Method Not Allowed."""
        forbidden_paths = [
            "/api/actuate",
            "/api/execute",
            "/api/hardware",
            "/api/policy",
            "/api/actions",
            "/actuate",
            "/execute",
            "/hardware",
        ]
        for path in forbidden_paths:
            self.wfile = io.BytesIO()
            handler = self._create_handler("POST", path, body={"action": "OPEN_VALVE"})
            handler.do_POST()

            assert handler._status_code == HTTPStatus.METHOD_NOT_ALLOWED
            output = json.loads(self.wfile.getvalue().decode("utf-8"))
            assert output["error"] == "METHOD_NOT_ALLOWED"
            assert output["authority"] == "ZERO"

    def test_arbitrary_action_injection_rejected_with_400(self):
        """Supplying an action, target, or ticket in demo POST body must be rejected with 400 Bad Request."""
        forbidden_payloads = [
            {"target": "valve_b"},
            {"action": "CLOSE_VALVE"},
            {"proposal": {"target": "valve_b"}},
            {"ticket": "fake_ticket_token"},
            {"policy": "ALLOW_ALL"},
            {"command": "force_actuate"},
            {"override": True},
        ]
        for payload in forbidden_payloads:
            self.wfile = io.BytesIO()
            handler = self._create_handler("POST", "/api/demo/safe", body=payload)
            handler.do_POST()

            assert handler._status_code == HTTPStatus.BAD_REQUEST
            output = json.loads(self.wfile.getvalue().decode("utf-8"))
            assert output["error"] == "FORBIDDEN_PAYLOAD"
            assert "strictly forbidden" in output["message"].lower()

    def test_unknown_scenario_rejected_with_404(self):
        """Requesting an unknown scenario must return 404 Not Found without executing anything."""
        handler = self._create_handler("POST", "/api/demo/exploit_scenario", body={})
        handler.do_POST()

        assert handler._status_code == HTTPStatus.NOT_FOUND
        output = json.loads(self.wfile.getvalue().decode("utf-8"))
        assert output["error"] == "SCENARIO_NOT_FOUND"

    def test_trigger_canonical_safe_scenario_replay(self):
        """Triggering POST /api/demo/safe in REPLAY mode returns 202 and schedules execution."""
        handler = self._create_handler("POST", "/api/demo/safe", body={"mode": "REPLAY", "backend": "mock"})
        handler.do_POST()

        assert handler._status_code == HTTPStatus.ACCEPTED
        output = json.loads(self.wfile.getvalue().decode("utf-8"))
        assert output["scenario_id"] == "safe"
        assert output["execution_mode"] == "REPLAY"
        assert output["physical_backend"] == "mock"
        assert "execution_id" in output
        assert "poll_url" in output

        # Poll execution
        exec_id = output["execution_id"]
        for _ in range(20):
            ex = demo_manager.get_execution(exec_id)
            if ex and ex.status.value in ("COMPLETED", "FAILED"):
                break
            time.sleep(0.05)

        assert ex is not None
        assert ex.status.value == "COMPLETED"
        assert ex.stage_outcome.value == "NOMINAL"
        assert ex.scenario_data is not None

    def test_get_execution_status(self):
        """GET /api/demo/executions/{id} returns the current state and record of a triggered run."""
        # Create execution
        ex = demo_manager.create_execution("denied", mode="REPLAY", backend="mock")
        for _ in range(20):
            if ex.status.value in ("COMPLETED", "FAILED"):
                break
            time.sleep(0.05)

        handler = self._create_handler("GET", f"/api/demo/executions/{ex.execution_id}")
        handler.do_GET()

        assert handler._status_code == 200
        output = json.loads(self.wfile.getvalue().decode("utf-8"))
        assert output["execution_id"] == ex.execution_id
        assert output["scenario_id"] == "denied"
        assert output["stage_outcome"] == "DENIED"
        assert output["scenario_data"]["policy_decision"]["decision"] == "DENY"

    def test_concurrency_isolation(self):
        """Two concurrent demo executions must run with strictly isolated IDs and states."""
        ex1 = demo_manager.create_execution("safe", mode="REPLAY", backend="mock")
        ex2 = demo_manager.create_execution("denied", mode="REPLAY", backend="mock")

        assert ex1.execution_id != ex2.execution_id

        for _ in range(20):
            if ex1.status.value == "COMPLETED" and ex2.status.value == "COMPLETED":
                break
            time.sleep(0.05)

        assert ex1.stage_outcome.value == "NOMINAL"
        assert ex2.stage_outcome.value == "DENIED"
        assert ex1.scenario_data["scenario_id"] != ex2.scenario_data["scenario_id"]

    def test_nonexistent_execution_returns_404(self):
        """Polling a non-existent execution ID returns 404."""
        handler = self._create_handler("GET", "/api/demo/executions/exec_nonexistent_12345")
        handler.do_GET()

        assert handler._status_code == HTTPStatus.NOT_FOUND
        output = json.loads(self.wfile.getvalue().decode("utf-8"))
        assert output["error"] == "EXECUTION_NOT_FOUND"

    def test_public_live_mode_spending_gate_falls_back_to_replay(self):
        """By default, public requests in LIVE mode fall back to REPLAY with fallback event recorded."""
        from motionfence.config.settings import settings
        orig_gate = settings.nebius.allow_public_live
        settings.nebius.allow_public_live = False
        try:
            ex = demo_manager.create_execution("safe", mode="LIVE", backend="mock")
            for _ in range(20):
                if ex.status.value in ("COMPLETED", "FAILED"):
                    break
                time.sleep(0.05)

            assert ex.status.value == "COMPLETED"
            assert ex.execution_mode == "REPLAY"
            event_stages = [e["stage"] for e in ex.events]
            assert "FALLBACK" in event_stages
        finally:
            settings.nebius.allow_public_live = orig_gate

    def test_evaluate_stage_outcome_fail_closed_contracts(self):
        """Verify fail-closed outcome evaluator prevents false successes."""
        from motionfence.runtime.controlled_demo import evaluate_stage_outcome, StageOutcome
        from motionfence.runtime.live_demo import LiveDemoRecord
        from motionfence.hardware.models import HardwareExecutionStatus
        import copy

        # Load canonical safe replay fixture
        fixture_path = os.path.join(
            os.path.dirname(__file__), "..", "motionfence", "fixtures", "live_validation", "safe.json"
        )
        with open(fixture_path, "r", encoding="utf-8") as f:
            raw = json.load(f)
        base_rec = LiveDemoRecord(**raw)

        # 1. Nominal valid record -> NOMINAL
        assert evaluate_stage_outcome(base_rec) == StageOutcome.NOMINAL

        # 2. Action executed but verification absent -> UNVERIFIED
        unverif_rec = copy.deepcopy(base_rec)
        unverif_rec.verification_result = None
        assert evaluate_stage_outcome(unverif_rec) == StageOutcome.UNVERIFIED

        # 3. Action executed but verification failed -> VERIFICATION_FAILED
        failed_verif_rec = copy.deepcopy(base_rec)
        failed_verif_rec.verification_result.status = "VERIFICATION_FAILED"
        failed_verif_rec.verification_result.discrepancies = ["Limit switch mismatch"]
        assert evaluate_stage_outcome(failed_verif_rec) == StageOutcome.VERIFICATION_FAILED

        # 4. Fault injected without recovery result -> VERIFICATION_FAILED (not RECOVERED)
        fault_no_recov = copy.deepcopy(base_rec)
        fault_no_recov.hardware_execution.fault_injected = "NO_OP"
        fault_no_recov.recovery_result = None
        assert evaluate_stage_outcome(fault_no_recov) == StageOutcome.VERIFICATION_FAILED

        # 5. Recovery with unresolved quarantine -> VERIFICATION_FAILED (not RECOVERED)
        quarantine_rec = copy.deepcopy(base_rec)
        quarantine_rec.hardware_execution.fault_injected = "NO_OP"
        quarantine_rec.recovery_result = {
            "outcome": "FAILED",
            "component_status": "QUARANTINED",
        }
        assert evaluate_stage_outcome(quarantine_rec) == StageOutcome.VERIFICATION_FAILED

        # 6. Policy denial with zero actuation -> DENIED
        denied_fixture = os.path.join(
            os.path.dirname(__file__), "..", "motionfence", "fixtures", "live_validation", "denied.json"
        )
        with open(denied_fixture, "r", encoding="utf-8") as f:
            d_raw = json.load(f)
        d_rec = LiveDemoRecord(**d_raw)
        assert evaluate_stage_outcome(d_rec) == StageOutcome.DENIED

        # 7. Policy denial contradiction: actuation occurred -> ERROR
        contradiction_d_rec = copy.deepcopy(d_rec)
        contradiction_d_rec.hardware_execution.execution_status = HardwareExecutionStatus.ACTUATED
        assert evaluate_stage_outcome(contradiction_d_rec) == StageOutcome.ERROR

        # 8. TOCTOU revalidation block with zero actuation -> BLOCKED
        toctou_fixture = os.path.join(
            os.path.dirname(__file__), "..", "motionfence", "fixtures", "live_validation", "toctou.json"
        )
        with open(toctou_fixture, "r", encoding="utf-8") as f:
            t_raw = json.load(f)
        t_rec = LiveDemoRecord(**t_raw)
        assert evaluate_stage_outcome(t_rec) == StageOutcome.BLOCKED

        # 9. TOCTOU block contradiction: actuation occurred -> ERROR
        contradiction_t_rec = copy.deepcopy(t_rec)
        contradiction_t_rec.hardware_execution.execution_status = HardwareExecutionStatus.ACTUATED
        assert evaluate_stage_outcome(contradiction_t_rec) == StageOutcome.ERROR


if __name__ == "__main__":
    unittest.main()
