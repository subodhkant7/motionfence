"""Phase 2L Security Boundary Tests: Read-Only Console & Zero Authority Invariants.

Verifies:
1. Console server / adapter cannot mint AuthorizationTicket.
2. Console server / adapter cannot invoke PhysicalActuator.
3. Console server / adapter cannot modify PolicyEngine or baseline.
4. Console server / adapter cannot approve repairs or apply policy changes.
5. Console server / adapter cannot execute recovery or bypass SafetyEnclave.
6. All state-mutating HTTP methods (POST, PUT, DELETE, PATCH) are rejected with 405.
7. Responses contain strictly read-only audit records and security headers.
"""

from http import HTTPStatus
import io
import json
import os
import sys
import unittest
from unittest.mock import MagicMock

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from scripts.console_server import ReadOnlyConsoleHandler


class MockWFile(io.BytesIO):
    """Captures response body written by handler."""
    pass


class DummyServer:
    pass


class TestConsoleSecurityBoundary(unittest.TestCase):
    """Prove that the console adapter has zero authority and strictly preserves safety invariants."""

    def setUp(self):
        self.wfile = io.BytesIO()

    def _create_handler(self, command: str, path: str, body: bytes = b"") -> ReadOnlyConsoleHandler:
        """Instantiate ReadOnlyConsoleHandler with mock request/response streams."""
        request = MagicMock()
        rfile = io.BytesIO(body)
        client_address = ("127.0.0.1", 54321)
        server = DummyServer()

        # Mock handler without invoking socket initialization
        handler = ReadOnlyConsoleHandler.__new__(ReadOnlyConsoleHandler)
        handler.command = command
        handler.path = path
        handler.request_version = "HTTP/1.1"
        handler.rfile = rfile
        handler.wfile = self.wfile
        handler.client_address = client_address
        handler.server = server
        handler.headers = {}
        handler.close_connection = False

        # Mock header writers
        handler._headers_buffer = []
        handler.send_response = MagicMock()
        handler.send_header = MagicMock()
        handler.end_headers = MagicMock()

        return handler

    def test_handler_has_no_actuator_or_enclave_authority(self):
        """Security Invariant: Console adapter must not possess any actuator or ticket-minting authority."""
        import scripts.console_server as cs

        # Ensure no dangerous execution classes are imported or bound in the module
        assert not hasattr(cs, "PhysicalActuator"), "Console module must NOT import PhysicalActuator"
        assert not hasattr(cs, "TicketAuthority"), "Console module must NOT import TicketAuthority"
        assert not hasattr(cs, "SafetyEnclave"), "Console module must NOT import SafetyEnclave"

    def test_post_mutation_rejected_with_405(self):
        """Attempts to POST (e.g. mint ticket, execute action) must be rejected with 405."""
        handler = self._create_handler("POST", "/api/actuate", b'{"action": "CLOSE_VALVE"}')
        handler.do_POST()

        handler.send_response.assert_called_with(HTTPStatus.METHOD_NOT_ALLOWED)
        output = json.loads(self.wfile.getvalue().decode("utf-8"))
        assert output["error"] == "METHOD_NOT_ALLOWED"
        assert output["authority"] == "ZERO"
        assert "zero actuation or policy mutation authority" in output["message"].lower()

    def test_put_policy_modification_rejected_with_405(self):
        """Attempts to PUT (e.g. modify policy baseline) must be rejected with 405."""
        handler = self._create_handler("PUT", "/api/policy", b'{"require_human_zone_clear": false}')
        handler.do_PUT()

        handler.send_response.assert_called_with(HTTPStatus.METHOD_NOT_ALLOWED)
        output = json.loads(self.wfile.getvalue().decode("utf-8"))
        assert output["error"] == "METHOD_NOT_ALLOWED"
        assert output["authority"] == "ZERO"

    def test_delete_quarantine_bypass_rejected_with_405(self):
        """Attempts to DELETE (e.g. remove quarantine) must be rejected with 405."""
        handler = self._create_handler("DELETE", "/api/quarantine/valve_b")
        handler.do_DELETE()

        handler.send_response.assert_called_with(HTTPStatus.METHOD_NOT_ALLOWED)
        output = json.loads(self.wfile.getvalue().decode("utf-8"))
        assert output["error"] == "METHOD_NOT_ALLOWED"
        assert output["authority"] == "ZERO"

    def test_patch_repair_approval_rejected_with_405(self):
        """Attempts to PATCH (e.g. approve a repair proposal) must be rejected with 405."""
        handler = self._create_handler("PATCH", "/api/repairs/prep_12345", b'{"status": "APPLIED"}')
        handler.do_PATCH()

        handler.send_response.assert_called_with(HTTPStatus.METHOD_NOT_ALLOWED)
        output = json.loads(self.wfile.getvalue().decode("utf-8"))
        assert output["error"] == "METHOD_NOT_ALLOWED"
        assert output["authority"] == "ZERO"

    def test_get_status_reports_zero_authority(self):
        """GET /api/status explicitly documents zero execution authority."""
        handler = self._create_handler("GET", "/api/status")
        handler.do_GET()

        handler.send_response.assert_called_with(200)
        output = json.loads(self.wfile.getvalue().decode("utf-8"))
        assert output["status"] == "OPERATIONAL"
        assert output["authority"]["ticket_minting"] is False
        assert output["authority"]["physical_actuation"] is False
        assert output["authority"]["policy_modification"] is False
        assert output["authority"]["repair_approval"] is False
        assert output["authority"]["read_only"] is True

    def test_get_repairs_confirms_proposals_are_non_authoritative(self):
        """GET /api/repairs verifies that all proposals are marked non-authoritative."""
        handler = self._create_handler("GET", "/api/repairs")
        handler.do_GET()

        handler.send_response.assert_called_with(200)
        output = json.loads(self.wfile.getvalue().decode("utf-8"))
        assert isinstance(output, list)
        for repair in output:
            assert repair["is_authoritative"] is False
            assert repair["is_applied"] is False

    def test_security_headers_present(self):
        """Security headers must declare strictly read-only authority."""
        handler = self._create_handler("GET", "/api/scenarios")
        handler._set_headers(200)

        header_calls = {call[0][0]: call[0][1] for call in handler.send_header.call_args_list}
        assert header_calls.get("X-MotionFence-Authority") == "STRICTLY_READ_ONLY"
        assert header_calls.get("X-Content-Type-Options") == "nosniff"

    def test_health_endpoint(self):
        """GET /health and /api/health must report operational health and actual configured capabilities."""
        for path in ("/health", "/api/health"):
            self.wfile = io.BytesIO()
            handler = self._create_handler("GET", path)
            handler.do_GET()

            handler.send_response.assert_called_with(200)
            output = json.loads(self.wfile.getvalue().decode("utf-8"))
            assert output["status"] == "healthy"
            assert output["application"] == "motionfence"
            assert "LIVE" in output["execution_modes"] or "REPLAY" in output["execution_modes"]
            assert output["safety_runtime"] == "deterministic"
            assert "mock" in output["physical_backends"]
            assert "replay" in output["physical_backends"]
            # No credentials exposed
            assert "api_key" not in output
            assert "secret" not in output

    def test_head_method_emits_headers_without_body(self):
        """HEAD /health must return 200 and headers without writing body content."""
        handler = self._create_handler("HEAD", "/health")
        handler.do_HEAD()

        handler.send_response.assert_called_with(200)
        assert len(self.wfile.getvalue()) == 0

    def test_isaac_endpoints_status_and_export(self):
        """GET /api/isaac/status, /api/isaac/scene.usda, and /api/isaac/runner.py must return stage metadata and exports."""
        # Status
        self.wfile = io.BytesIO()
        handler = self._create_handler("GET", "/api/isaac/status")
        handler.do_GET()
        handler.send_response.assert_called_with(200)
        status_data = json.loads(self.wfile.getvalue().decode("utf-8"))
        assert status_data["simulation_backend"] == "isaac"
        assert status_data["root_prim"] == "/World/IndustrialCell"
        assert "valve_b" in status_data["prim_paths"]
        assert "environment_instructions" in status_data

        # OpenUSD ASCII Stage
        self.wfile = io.BytesIO()
        handler_usd = self._create_handler("GET", "/api/isaac/scene.usda")
        handler_usd.do_GET()
        handler_usd.send_response.assert_called_with(200)
        usd_text = self.wfile.getvalue().decode("utf-8")
        assert "#usda 1.0" in usd_text
        assert "IndustrialCell" in usd_text

        # Python Runner Script
        self.wfile = io.BytesIO()
        handler_runner = self._create_handler("GET", "/api/isaac/runner.py")
        handler_runner.do_GET()
        handler_runner.send_response.assert_called_with(200)
        runner_text = self.wfile.getvalue().decode("utf-8")
        assert "isaacsim" in runner_text
        assert "run_simulation" in runner_text or "run_standalone_simulation" in runner_text


if __name__ == "__main__":
    unittest.main()

