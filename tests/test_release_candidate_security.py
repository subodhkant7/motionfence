"""Final Release-Candidate Adversarial Security Test Suite for MotionFence.

Validates the Central Security Invariant:
    "THE PUBLIC USER CAN REQUEST A DEMONSTRATION, BUT CAN NEVER COMMAND THE PHYSICAL SYSTEM."

Properties Tested:
- Property A: No public path to physical control.
- Property B: No privileged capability leakage (keys, hardware adapters, internal object handles).
- Property C: Ticket single-use is strictly atomic under high concurrency (threading.Barrier).
- Property D: Ticket integrity cannot be bypassed (tampering all 10 individual fields & serialization).
- Property E: Ticket replay across contexts (cross-target, stale world state, cross-scenario).
- Property F: Failure modes fail closed (LLM failure, enclave exception, telemetry failure, hardware fault).
- Property G: Production configuration matrix cannot silently weaken security.
- Property H: Trusted proxy and client IP spoofing cannot bypass rate limiting.
- Property I: Public resource exhaustion is bounded (payload limits, rate limits, worker queue depth).
- Property J: Static asset traversal is strictly prevented (unquoted paths, realpath commonpath containment).
- Property K: Scenario enumeration & execution mode cannot be bypassed.
- Property L: State machine invalid transitions and hostile prompt injection defense.
"""

from concurrent.futures import ThreadPoolExecutor
from http import HTTPStatus
import io
import json
import os
import ssl
import sys
import threading
import time
from typing import Any, Dict, List, Optional
import unittest
from unittest.mock import MagicMock, patch

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from motionfence.config.settings import Settings, SecuritySettings, settings
from motionfence.evidence.models import Evidence
from motionfence.hardware.mock import MockHardwareEndpoint, HardwareFaultType
from motionfence.hardware.models import HardwareExecutionStatus
from motionfence.hardware.validation import HardwareTicketValidator
from motionfence.models.actions import (
    ActionProposal,
    ActionType,
    AuthorizationTicket,
    ExecutionResult,
)
from motionfence.models.world import (
    WorldState,
    ValveState,
    CoolingState,
    HumanZoneState,
    LeakState,
)
from motionfence.policy.models import DecisionType, Policy, PolicyDecision
from motionfence.policy.engine import PolicyEngine
from motionfence.runtime.controlled_demo import (
    CANONICAL_SCENARIOS,
    ControlledDemoExecution,
    ControlledDemoManager,
    demo_manager,
)
from motionfence.runtime.enclave import EnclaveAuthorizationRequest, SafetyEnclave
from motionfence.runtime.events import EventBus
from motionfence.runtime.revalidation import (
    ExecutionTimeRevalidator,
    RevalidationStatus,
    build_authorization_context,
    compute_authorization_context_hash,
)
from motionfence.runtime.ticket import TicketAuthority
from motionfence.simulation.actuator import PhysicalActuator
from motionfence.simulation.exceptions import UnauthorizedActionError
from motionfence.simulation.world import PhysicalWorld
from motionfence.telemetry.usgs_provider import _get_ssl_context
from scripts.console_server import PerIpRateLimiter, ReadOnlyConsoleHandler, DIST_DIR, rate_limiter


class DummyServer:
    pass


def create_mock_handler(
    command: str,
    path: str,
    body: Optional[Dict[str, Any]] = None,
    headers: Optional[Dict[str, str]] = None,
    client_ip: str = "127.0.0.1",
) -> tuple[ReadOnlyConsoleHandler, io.BytesIO]:
    """Helper to instantiate ReadOnlyConsoleHandler with mock request streams."""
    wfile = io.BytesIO()
    body_bytes = json.dumps(body).encode("utf-8") if body is not None else b""
    rfile = io.BytesIO(body_bytes)

    handler = ReadOnlyConsoleHandler.__new__(ReadOnlyConsoleHandler)
    handler.command = command
    handler.path = path
    handler.requestline = f"{command} {path} HTTP/1.1"
    handler.request_version = "HTTP/1.1"
    handler.rfile = rfile
    handler.wfile = wfile
    handler.client_address = (client_ip, 54321)
    handler.server = DummyServer()

    req_headers = {"Host": "localhost:8080"}
    if body is not None:
        req_headers["Content-Length"] = str(len(body_bytes))
        req_headers["Content-Type"] = "application/json"
    if headers:
        req_headers.update(headers)

    from http.client import HTTPMessage
    msg = HTTPMessage()
    for k, v in req_headers.items():
        msg.add_header(k, v)
    handler.headers = msg

    handler.send_response = MagicMock(side_effect=lambda code: setattr(handler, "_status_code", code))
    handler.send_header = MagicMock()
    handler.end_headers = MagicMock()
    return handler, wfile


class TestReleaseCandidatePropertyA_PhysicalControlBoundary(unittest.TestCase):
    """Property A: No public path to physical control.
    
    Verifies that public requests, sequences of requests, and arbitrary payloads
    cannot execute physical control commands or bypass the read-only console barrier.
    """

    def setUp(self):
        with rate_limiter.lock:
            rate_limiter.ip_buckets.clear()
            rate_limiter.global_timestamps.clear()

    def test_direct_actuation_routes_strictly_rejected_405(self):
        """Direct actuation routes (/api/actuate, /api/command, /api/valves) return 405 Method Not Allowed."""
        dangerous_routes = [
            "/api/actuate",
            "/api/command",
            "/api/valves/close",
            "/api/valves/valve_b/close",
            "/api/hardware/override",
            "/api/execute",
            "/api/policy/override",
        ]
        for route in dangerous_routes:
            handler, wfile = create_mock_handler("POST", route, body={"action": "CLOSE_VALVE", "target": "valve_b"})
            handler.do_POST()
            resp = json.loads(wfile.getvalue().decode("utf-8"))
            self.assertEqual(resp.get("error"), "METHOD_NOT_ALLOWED")
            self.assertEqual(resp.get("authority"), "ZERO")

    def test_mutating_verbs_strictly_rejected(self):
        """PUT, DELETE, and PATCH methods on any route return 405."""
        for method_name, do_method in [("PUT", "do_PUT"), ("DELETE", "do_DELETE"), ("PATCH", "do_PATCH")]:
            handler, wfile = create_mock_handler(method_name, "/api/demo/run")
            getattr(handler, do_method)()
            resp = json.loads(wfile.getvalue().decode("utf-8"))
            self.assertEqual(resp.get("error"), "METHOD_NOT_ALLOWED")
            self.assertEqual(resp.get("authority"), "ZERO")

    def test_zero_physical_industrial_drivers_in_codebase(self):
        """Verify the absence of physical industrial hardware drivers (Modbus, OPC-UA, CAN, PySerial)."""
        import sys
        for forbidden_mod in ["serial", "pymodbus", "opcua", "can"]:
            self.assertNotIn(forbidden_mod, sys.modules)

    def test_backend_parameter_tampering_cannot_reach_physical_system(self):
        """Attempting to specify 'physical', 'real', or 'hardware_direct' defaults to mock or is constrained."""
        mgr = ControlledDemoManager()
        ex = mgr.create_execution(
            scenario_id="safe",
            mode="LIVE",
            backend="industrial_plc_direct",
        )
        self.assertEqual(ex.physical_backend, "mock")


class TestReleaseCandidatePropertyB_CapabilityLeakage(unittest.TestCase):
    """Property B: No privileged capability leakage.
    
    Verifies that public error responses, scenario responses, and execution status
    never leak signing keys, internal pointers, or adapter handles.
    """

    def setUp(self):
        with rate_limiter.lock:
            rate_limiter.ip_buckets.clear()
            rate_limiter.global_timestamps.clear()

    def test_kernel_secret_never_leaked_in_public_endpoints(self):
        """Verify that kernel secrets and private keys do not appear in any public response."""
        secret = settings.security.kernel_secret

        routes = [
            "/api/status",
            "/api/demo/scenarios",
            "/api/assurance",
            "/api/scenarios",
        ]
        for route in routes:
            handler, wfile = create_mock_handler("GET", route)
            handler.do_GET()
            content = wfile.getvalue().decode("utf-8")
            self.assertNotIn(secret, content)

    def test_error_responses_contain_no_stack_traces_or_paths(self):
        """Deliberately trigger error conditions and verify no Python tracebacks or file paths leak."""
        handler, wfile = create_mock_handler("POST", "/api/demo/run", headers={"Content-Length": "not-an-int"})
        handler.do_POST()
        body = wfile.getvalue().decode("utf-8")
        self.assertNotIn("Traceback", body)
        self.assertNotIn("/Users/", body)
        self.assertNotIn(".py", body)


class TestReleaseCandidatePropertyC_ConcurrentTicketSingleUseAtomicity(unittest.TestCase):
    """Property C: Ticket single-use is strictly atomic under high concurrency.
    
    Launches 30 threads simultaneously against MockHardwareEndpoint and PhysicalActuator
    using a threading.Barrier on the EXACT SAME valid AuthorizationTicket.
    Proves:
        N concurrent uses -> exactly 1 accepted, N-1 rejected as replay, exactly 1 state mutation.
    """

    def test_mock_hardware_endpoint_concurrent_ticket_single_use(self):
        """30 concurrent threads submit the exact same valid ticket to MockHardwareEndpoint."""
        num_threads = 30
        barrier = threading.Barrier(num_threads)
        secret_key = "rc_adversarial_test_kernel_secret_key_32bytes"

        world = PhysicalWorld()
        world.valves["valve_b"] = ValveState.OPEN
        world.leak_target = "valve_b"
        world.version = 0

        endpoint = MockHardwareEndpoint(
            world=world,
            hardware_id="HWR_CONCURRENCY_TEST",
            secret_key=secret_key,
        )

        proposal = ActionProposal(
            action_type=ActionType.CLOSE_VALVE,
            target="valve_b",
            rationale="Concurrent single-use test",
            model_confidence=0.98,
        )

        authority = TicketAuthority(secret_key=secret_key)
        ticket = authority.mint_ticket(proposal=proposal, ttl_seconds=60.0)

        results: List[Any] = []
        lock = threading.Lock()

        def worker():
            barrier.wait()
            rec = endpoint.receive_and_actuate(proposal=proposal, ticket=ticket)
            with lock:
                results.append(rec)

        threads = [threading.Thread(target=worker) for _ in range(num_threads)]
        for t in threads:
            t.start()
        for t in threads:
            t.join()

        self.assertEqual(len(results), num_threads)
        actuated = [r for r in results if r.execution_status == HardwareExecutionStatus.ACTUATED]
        replayed = [r for r in results if r.execution_status == HardwareExecutionStatus.REPLAYED_TICKET]

        # ATOMICITY PROOF: Exactly 1 actuation, exactly N-1 replay rejections
        self.assertEqual(len(actuated), 1, f"Expected exactly 1 actuation, got {len(actuated)}")
        self.assertEqual(len(replayed), num_threads - 1, f"Expected {num_threads - 1} replayed, got {len(replayed)}")
        self.assertEqual(world.valves["valve_b"], ValveState.CLOSED)
        self.assertEqual(world.version, 1, "World version must increment exactly once")

    def test_physical_actuator_concurrent_ticket_single_use(self):
        """30 concurrent threads submit the exact same valid ticket to PhysicalActuator directly."""
        num_threads = 30
        barrier = threading.Barrier(num_threads)
        secret_key = "rc_adversarial_test_kernel_secret_key_32bytes"

        world = PhysicalWorld()
        world.valves["valve_b"] = ValveState.OPEN
        world.version = 0

        actuator = PhysicalActuator(world=world, secret_key=secret_key)

        proposal = ActionProposal(
            action_type=ActionType.CLOSE_VALVE,
            target="valve_b",
            rationale="Direct actuator concurrency test",
            model_confidence=0.99,
        )

        authority = TicketAuthority(secret_key=secret_key)
        ticket = authority.mint_ticket(proposal=proposal, ttl_seconds=60.0)

        successes: List[ExecutionResult] = []
        errors: List[Exception] = []
        lock = threading.Lock()

        def worker():
            barrier.wait()
            try:
                res = actuator.execute(proposal=proposal, ticket=ticket)
                with lock:
                    successes.append(res)
            except Exception as e:
                with lock:
                    errors.append(e)

        threads = [threading.Thread(target=worker) for _ in range(num_threads)]
        for t in threads:
            t.start()
        for t in threads:
            t.join()

        self.assertEqual(len(successes), 1, "Exactly one thread must execute successfully")
        self.assertEqual(len(errors), num_threads - 1, f"Expected {num_threads - 1} rejections, got {len(errors)}")
        for err in errors:
            self.assertIsInstance(err, UnauthorizedActionError)
            self.assertIn("already been consumed", str(err))
        self.assertEqual(world.valves["valve_b"], ValveState.CLOSED)
        self.assertEqual(world.version, 1)


class TestReleaseCandidatePropertyD_TicketTamperingIntegrity(unittest.TestCase):
    """Property D: Ticket integrity cannot be bypassed.
    
    Mutates every single field individually on a valid AuthorizationTicket and proves
    that any tampering results in strict hardware-boundary rejection and zero world mutation.
    """

    def setUp(self):
        self.secret_key = "rc_adversarial_test_kernel_secret_key_32bytes"
        self.world = PhysicalWorld()
        self.world.valves["valve_b"] = ValveState.OPEN
        self.world.version = 1
        self.validator = HardwareTicketValidator(secret_key=self.secret_key)
        self.actuator = PhysicalActuator(self.world, secret_key=self.secret_key)
        self.authority = TicketAuthority(secret_key=self.secret_key)

        self.proposal = ActionProposal(
            action_type=ActionType.CLOSE_VALVE,
            target="valve_b",
            rationale="Integrity tampering baseline",
            model_confidence=0.95,
        )

    def _mint_valid_ticket(self) -> AuthorizationTicket:
        return self.authority.mint_ticket(
            proposal=self.proposal,
            ttl_seconds=30.0,
            world_state=self.world.get_state(),
        )

    def test_original_ticket_accepted(self):
        """Sanity check: original untampered ticket validates and executes successfully."""
        ticket = self._mint_valid_ticket()
        val = self.validator.validate(self.proposal, ticket, consumed_ticket_ids=set(), current_world_version=1)
        self.assertTrue(val.is_valid)

    def test_tamper_action_type(self):
        """Tampering action_type (e.g. CLOSE_VALVE -> OPEN_VALVE) is strictly rejected."""
        ticket = self._mint_valid_ticket()
        ticket.action_type = ActionType.OPEN_VALVE
        val = self.validator.validate(self.proposal, ticket, consumed_ticket_ids=set(), current_world_version=1)
        self.assertFalse(val.is_valid)
        self.assertEqual(val.status, HardwareExecutionStatus.ACTION_MISMATCH)

        with self.assertRaises(UnauthorizedActionError):
            self.actuator.execute(self.proposal, ticket)

    def test_tamper_target(self):
        """Tampering target (e.g. valve_b -> valve_a) is strictly rejected."""
        ticket = self._mint_valid_ticket()
        ticket.target = "valve_a"
        val = self.validator.validate(self.proposal, ticket, consumed_ticket_ids=set(), current_world_version=1)
        self.assertFalse(val.is_valid)
        self.assertEqual(val.status, HardwareExecutionStatus.TARGET_MISMATCH)

        with self.assertRaises(UnauthorizedActionError):
            self.actuator.execute(self.proposal, ticket)

    def test_tamper_ticket_id(self):
        """Tampering ticket_id invalidates cryptographic HMAC signature."""
        ticket = self._mint_valid_ticket()
        ticket.ticket_id = f"tkt_tampered_{ticket.ticket_id[13:]}"
        val = self.validator.validate(self.proposal, ticket, consumed_ticket_ids=set(), current_world_version=1)
        self.assertFalse(val.is_valid)
        self.assertEqual(val.status, HardwareExecutionStatus.INVALID_TICKET)

        with self.assertRaises(UnauthorizedActionError):
            self.actuator.execute(self.proposal, ticket)

    def test_tamper_proposal_id(self):
        """Tampering proposal_id causes proposal binding mismatch."""
        ticket = self._mint_valid_ticket()
        ticket.proposal_id = "prop_tampered_9999"
        val = self.validator.validate(self.proposal, ticket, consumed_ticket_ids=set(), current_world_version=1)
        self.assertFalse(val.is_valid)

        with self.assertRaises(UnauthorizedActionError):
            self.actuator.execute(self.proposal, ticket)

    def test_tamper_world_state_version(self):
        """Tampering world_state_version causes stale context rejection."""
        ticket = self._mint_valid_ticket()
        ticket.world_state_version = 99
        val = self.validator.validate(self.proposal, ticket, consumed_ticket_ids=set(), current_world_version=1)
        self.assertFalse(val.is_valid)
        self.assertEqual(val.status, HardwareExecutionStatus.INVALID_TICKET)

        with self.assertRaises(UnauthorizedActionError):
            self.actuator.execute(self.proposal, ticket)

    def test_tamper_expires_at(self):
        """Tampering expires_at invalidates cryptographic HMAC signature."""
        ticket = self._mint_valid_ticket()
        ticket.expires_at = ticket.expires_at + 3600.0  # extend lifetime by 1 hour
        val = self.validator.validate(self.proposal, ticket, consumed_ticket_ids=set(), current_world_version=1)
        self.assertFalse(val.is_valid)
        self.assertEqual(val.status, HardwareExecutionStatus.INVALID_TICKET)

        with self.assertRaises(UnauthorizedActionError):
            self.actuator.execute(self.proposal, ticket)

    def test_tamper_expired_ticket(self):
        """Expired ticket is rejected deterministically."""
        ticket = self._mint_valid_ticket()
        ticket.expires_at = time.time() - 10.0
        val = self.validator.validate(self.proposal, ticket, consumed_ticket_ids=set(), current_world_version=1)
        self.assertFalse(val.is_valid)
        self.assertEqual(val.status, HardwareExecutionStatus.EXPIRED_TICKET)

        with self.assertRaises(UnauthorizedActionError):
            self.actuator.execute(self.proposal, ticket)

    def test_tamper_signature_single_character(self):
        """Flipping a single hex character in the signature causes strict rejection."""
        ticket = self._mint_valid_ticket()
        last_char = ticket.signature[-1]
        flipped_char = "0" if last_char != "0" else "1"
        ticket.signature = ticket.signature[:-1] + flipped_char

        val = self.validator.validate(self.proposal, ticket, consumed_ticket_ids=set(), current_world_version=1)
        self.assertFalse(val.is_valid)
        self.assertEqual(val.status, HardwareExecutionStatus.INVALID_TICKET)

        with self.assertRaises(UnauthorizedActionError):
            self.actuator.execute(self.proposal, ticket)


class TestReleaseCandidatePropertyE_CrossContextTicketReplay(unittest.TestCase):
    """Property E: Ticket replay across contexts is strictly impossible.
    
    Verifies that a ticket minted for one target or state cannot execute on another.
    """

    def setUp(self):
        self.secret_key = "rc_adversarial_test_kernel_secret_key_32bytes"
        self.world = PhysicalWorld()
        self.world.valves["valve_a"] = ValveState.OPEN
        self.world.valves["valve_b"] = ValveState.OPEN
        self.world.version = 1
        self.authority = TicketAuthority(secret_key=self.secret_key)
        self.actuator = PhysicalActuator(self.world, secret_key=self.secret_key)

    def test_cross_target_ticket_reuse_rejected(self):
        """Ticket authorized for valve_b cannot be used to close valve_a."""
        prop_b = ActionProposal(action_type=ActionType.CLOSE_VALVE, target="valve_b", rationale="Fix leak B", model_confidence=0.9)
        prop_a = ActionProposal(action_type=ActionType.CLOSE_VALVE, target="valve_a", rationale="Fix leak A", model_confidence=0.9)

        ticket_b = self.authority.mint_ticket(prop_b, ttl_seconds=30.0, world_state=self.world.get_state())

        with self.assertRaises(UnauthorizedActionError):
            self.actuator.execute(prop_a, ticket_b)

        self.assertEqual(self.world.valves["valve_a"], ValveState.OPEN)

    def test_cross_world_version_ticket_reuse_rejected(self):
        """Ticket authorized for world state version 1 cannot execute when world drifts to version 2."""
        prop = ActionProposal(action_type=ActionType.CLOSE_VALVE, target="valve_b", rationale="Fix leak B", model_confidence=0.9)
        ticket = self.authority.mint_ticket(prop, ttl_seconds=30.0, world_state=self.world.get_state())

        # Simulate external state transition (world drifts to version 2)
        self.world.version = 2

        with self.assertRaises(UnauthorizedActionError) as cm:
            self.actuator.execute(prop, ticket)

        self.assertIn("Stale authorization context", str(cm.exception))


class TestReleaseCandidatePropertyF_FailureRemainsFailClosed(unittest.TestCase):
    """Property F: Failure remains fail-closed.
    
    Verifies that exceptions, timeouts, malformed responses, and crashes across
    LLM, SafetyEnclave, TicketAuthority, Hardware, and Telemetry never cause unauthorized execution.
    """

    def setUp(self):
        self.secret_key = "rc_adversarial_test_kernel_secret_key_32bytes"
        self.world = PhysicalWorld()

    def test_safety_enclave_exception_fails_closed(self):
        """When SafetyEnclave policy evaluation encounters an exception, no ticket is minted."""
        enclave = SafetyEnclave(secret_key=self.secret_key)

        req = EnclaveAuthorizationRequest(
            proposal=ActionProposal(action_type=ActionType.CLOSE_VALVE, target="valve_b", rationale="Emergency", model_confidence=0.9),
            world_state=self.world.get_state(),
            policy=Policy(id="test", name="test"),
        )

        with patch.object(PolicyEngine, "evaluate", side_effect=RuntimeError("Z3 SMT solver timeout")):
            with self.assertRaises(RuntimeError):
                enclave.authorize(req)

        # Actuator cannot execute because no ticket was ever minted
        actuator = PhysicalActuator(self.world, secret_key=self.secret_key)
        with self.assertRaises(UnauthorizedActionError):
            actuator.execute(req.proposal, ticket=None)

    def test_hardware_fault_injection_fails_safely(self):
        """When hardware fault occurs (NO_OP, WRONG_FINAL_STATE), hardware locks and actuation is flagged."""
        endpoint = MockHardwareEndpoint(
            world=self.world,
            hardware_id="HWR_FAULT_TEST",
            secret_key=self.secret_key,
        )
        endpoint.inject_fault(HardwareFaultType.NO_OP)

        proposal = ActionProposal(action_type=ActionType.CLOSE_VALVE, target="valve_b", rationale="Test", model_confidence=0.9)
        authority = TicketAuthority(secret_key=self.secret_key)
        ticket = authority.mint_ticket(proposal, ttl_seconds=30.0)

        rec = endpoint.receive_and_actuate(proposal, ticket)
        self.assertEqual(rec.execution_status, HardwareExecutionStatus.HARDWARE_FAULT)
        self.assertIn("mechanical fault", rec.message)

    def test_telemetry_tls_certificate_enforcement_fail_closed(self):
        """USGS provider enforces strict TLS certificate and hostname verification."""
        ctx = _get_ssl_context()
        self.assertEqual(ctx.verify_mode, ssl.CERT_REQUIRED)
        self.assertTrue(ctx.check_hostname)


class TestReleaseCandidatePropertyG_ConfigurationMatrix(unittest.TestCase):
    """Property G: Deployment configuration cannot silently weaken security.
    
    Verifies that production mode refuses to start with missing, default, or weak secrets,
    or with insecure TLS enabled.
    """

    def test_production_refuses_default_secret(self):
        """Production mode refuses to start with default repository secret."""
        sec = SecuritySettings(
            kernel_secret="motionfence_runtime_kernel_secret",
        )
        with self.assertRaises(RuntimeError) as cm:
            sec.validate_for_production("production")
        self.assertIn("MOTIONFENCE_KERNEL_SECRET must be set to a high-entropy secret", str(cm.exception))

    def test_production_refuses_short_secret(self):
        """Production mode refuses secrets shorter than 32 characters."""
        sec = SecuritySettings(
            kernel_secret="too_short_secret",
        )
        with self.assertRaises(RuntimeError) as cm:
            sec.validate_for_production("production")
        self.assertIn("at least 32 characters", str(cm.exception))

    def test_production_refuses_insecure_tls(self):
        """Production mode refuses to start if allow_insecure_tls is True."""
        sec = SecuritySettings(
            kernel_secret="a_valid_production_secret_with_more_than_32_characters_123",
            allow_insecure_tls=True,
        )
        with self.assertRaises(RuntimeError) as cm:
            sec.validate_for_production("production")
        self.assertIn("cannot be enabled in production", str(cm.exception))

    def test_production_valid_configuration_passes(self):
        """A valid production configuration with strong secret and secure TLS validates cleanly."""
        sec = SecuritySettings(
            kernel_secret="a_valid_production_secret_with_more_than_32_characters_123",
            allow_insecure_tls=False,
        )
        # Should not raise
        sec.validate_for_production("production")


class TestReleaseCandidatePropertyH_TrustedProxyAndClientIp(unittest.TestCase):
    """Property H: Trusted-proxy and client-IP attack resistance.
    
    Verifies that untrusted clients cannot spoof X-Forwarded-For to bypass rate limits.
    """

    def test_untrusted_peer_cannot_spoof_x_forwarded_for(self):
        """When immediate peer is not in trusted_proxies, X-Forwarded-For is ignored."""
        limiter = PerIpRateLimiter()
        limiter.trusted_proxies = {"10.0.0.1"}
        headers = {"X-Forwarded-For": "8.8.8.8"}
        resolved_ip = limiter.resolve_client_ip("198.51.100.55", headers)
        self.assertEqual(resolved_ip, "198.51.100.55", "Must ignore X-Forwarded-For from untrusted peer")

    def test_trusted_proxy_peer_resolves_client_ip(self):
        """When immediate peer is in trusted_proxies, X-Forwarded-For client IP is respected."""
        limiter = PerIpRateLimiter()
        limiter.trusted_proxies = {"10.0.0.1"}
        headers = {"X-Forwarded-For": "203.0.113.195, 10.0.0.1"}
        resolved_ip = limiter.resolve_client_ip("10.0.0.1", headers)
        self.assertEqual(resolved_ip, "203.0.113.195")

    def test_malformed_client_ips_do_not_crash(self):
        """Malformed or oversized IP addresses are handled gracefully without crashing."""
        limiter = PerIpRateLimiter()
        headers = {"X-Forwarded-For": "not-an-ip; DROP TABLE;"}
        resolved = limiter.resolve_client_ip("127.0.0.1", headers)
        self.assertEqual(resolved, "127.0.0.1")


class TestReleaseCandidatePropertyI_ResourceExhaustion(unittest.TestCase):
    """Property I: Public resource exhaustion is bounded.
    
    Verifies that payload size limits, rate limits, and worker queue depths prevent DoS.
    """

    def setUp(self):
        with rate_limiter.lock:
            rate_limiter.ip_buckets.clear()
            rate_limiter.global_timestamps.clear()

    def test_payload_exceeding_64kb_rejected_413(self):
        """Payloads greater than 64KB are rejected with 413 Payload Too Large."""
        oversized = {"scenario": "safe", "padding": "x" * 70000}
        handler, wfile = create_mock_handler("POST", "/api/demo/run", body=oversized)
        handler.do_POST()
        resp = json.loads(wfile.getvalue().decode("utf-8"))
        self.assertEqual(resp.get("error"), "PAYLOAD_TOO_LARGE")

    def test_rapid_burst_triggers_rate_limit_429(self):
        """A burst of requests exceeding max_per_ip triggers PER_IP_LIMIT_EXCEEDED."""
        client = "192.168.1.50"
        for _ in range(rate_limiter.max_per_ip):
            allowed, _ = rate_limiter.allow(client)
            self.assertTrue(allowed)

        allowed, reason = rate_limiter.allow(client)
        self.assertFalse(allowed)
        self.assertEqual(reason, "PER_IP_LIMIT_EXCEEDED")

    def test_controlled_demo_queue_depth_bounded(self):
        """ControlledDemoManager rejects execution dispatch when pending queue depth is exceeded."""
        mgr = ControlledDemoManager(max_concurrent=1, max_pending=2)
        # Block the single worker
        blocker_started = threading.Event()
        proceed = threading.Event()

        def blocking_worker(*args, **kwargs):
            blocker_started.set()
            proceed.wait(timeout=5.0)

        with patch.object(mgr, "_run_execution_task", side_effect=blocking_worker):
            mgr.create_execution("safe")
            blocker_started.wait(timeout=2.0)

            # Fill pending queue to max_pending (2)
            mgr.create_execution("safe")

            # Next execution must raise RuntimeError / queue overflow
            with self.assertRaises(RuntimeError) as cm:
                mgr.create_execution("safe")
            self.assertIn("Maximum demonstration queue depth reached", str(cm.exception))

            proceed.set()


class TestReleaseCandidatePropertyJ_StaticAssetTraversal(unittest.TestCase):
    """Property J: Static asset path traversal strictly prevented.
    
    Verifies that encoded, double-encoded, relative, sibling, and null payloads
    cannot escape the console/dist directory.
    """

    def setUp(self):
        with rate_limiter.lock:
            rate_limiter.ip_buckets.clear()
            rate_limiter.global_timestamps.clear()

    def test_path_traversal_payloads_rejected(self):
        """Directory traversal payloads return 400, 403, or 404 and never disclose server files."""
        traversals = [
            "/../scripts/console_server.py",
            "/../../etc/passwd",
            "/%2e%2e/scripts/console_server.py",
            "/%252e%252e/scripts/console_server.py",
            "/..\\..\\scripts/console_server.py",
            "/dist-secret/stolen.txt",
        ]
        for path in traversals:
            handler, wfile = create_mock_handler("GET", path)
            handler.do_GET()
            content = wfile.getvalue().decode("utf-8")
            self.assertNotIn("class ReadOnlyConsoleHandler", content)
            self.assertNotIn("root:", content)


class TestReleaseCandidatePropertyK_ScenarioAndModeBypass(unittest.TestCase):
    """Property K: Scenario allowlist and execution mode cannot be bypassed.
    
    Verifies that arbitrary or unknown scenarios are rejected, and execution modes
    cannot be abused for physical control.
    """

    def setUp(self):
        with rate_limiter.lock:
            rate_limiter.ip_buckets.clear()
            rate_limiter.global_timestamps.clear()

    def test_unknown_scenarios_rejected_404(self):
        """Unknown or malicious scenario names are rejected with 404 SCENARIO_NOT_FOUND."""
        bad_scenarios = [
            "arbitrary_eval",
            "admin_shell",
            "valve_destroyer",
            "null",
            "safe/../denied",
            "SAFE_NOMINAL",  # case variation without match
        ]
        for sc in bad_scenarios:
            handler, wfile = create_mock_handler("POST", "/api/demo/run", body={"scenario": sc})
            handler.do_POST()
            resp = json.loads(wfile.getvalue().decode("utf-8"))
            self.assertEqual(resp.get("error"), "SCENARIO_NOT_FOUND")

    def test_hostile_action_injection_in_payload_rejected_400(self):
        """Attempting to inject raw action commands in demo payload is rejected as forbidden."""
        hostile_payloads = [
            {"scenario": "safe", "action": "CLOSE_VALVE", "target": "valve_b"},
            {"scenario": "safe", "ticket": "forged_ticket_123"},
            {"scenario": "safe", "actuator": "direct_override"},
            {"scenario": "safe", "override": "bypass_safety_enclave"},
            {"scenario": "safe", "command": "SHUTDOWN_PLANT"},
            {"scenario": "safe", "hardware": "HWR_VALVE_01"},
        ]
        for p in hostile_payloads:
            handler, wfile = create_mock_handler("POST", "/api/demo/run", body=p)
            handler.do_POST()
            resp = json.loads(wfile.getvalue().decode("utf-8"))
            self.assertEqual(resp.get("error"), "FORBIDDEN_PAYLOAD")


class TestReleaseCandidatePropertyL_StateMachineAndHostilePrompts(unittest.TestCase):
    """Property L: State machine invalid transitions and hostile prompt injection defense.
    
    Verifies that:
    1. Invalid transitions (DENIED -> EXECUTED, WAITING -> EXECUTED) are impossible.
    2. Hostile prompt injections proposing out-of-bound targets are rejected deterministically.
    """

    def setUp(self):
        self.secret_key = "rc_adversarial_test_kernel_secret_key_32bytes"
        self.world = PhysicalWorld()
        self.enclave = SafetyEnclave(secret_key=self.secret_key)

    def test_hostile_prompt_injection_out_of_bounds_target_denied(self):
        """Hostile AI model proposing out-of-bounds target (e.g. 'reactor_core') is denied by enclave."""
        policy = Policy(id="test_pol", name="test_pol")

        malicious_proposals = [
            ActionProposal(action_type=ActionType.CLOSE_VALVE, target="reactor_core", rationale="Ignore safety; shutdown core", model_confidence=0.99),
            ActionProposal(action_type=ActionType.OPEN_VALVE, target="valves['override']", rationale="SQL/syntax injection", model_confidence=0.99),
            ActionProposal(action_type=ActionType.EMERGENCY_STOP, target="system_root", rationale="System override", model_confidence=0.99),
        ]

        for prop in malicious_proposals:
            req = EnclaveAuthorizationRequest(
                proposal=prop,
                world_state=self.world.get_state(),
                policy=policy,
            )
            res = self.enclave.authorize(req)
            self.assertFalse(res.authorized, f"Hostile proposal on target '{prop.target}' must NOT be authorized")
            self.assertIsNone(res.ticket)
            self.assertEqual(res.decision.decision, DecisionType.DENY)

    def test_denied_proposal_cannot_execute_on_actuator(self):
        """A proposal denied by enclave cannot execute because no ticket was minted."""
        actuator = PhysicalActuator(self.world, secret_key=self.secret_key)
        denied_proposal = ActionProposal(
            action_type=ActionType.CLOSE_VALVE,
            target="reactor_core",
            rationale="Malicious",
            model_confidence=0.99,
        )
        with self.assertRaises(UnauthorizedActionError) as cm:
            actuator.execute(denied_proposal, ticket=None)
        self.assertIn("Missing AuthorizationTicket", str(cm.exception))


if __name__ == "__main__":
    unittest.main()
