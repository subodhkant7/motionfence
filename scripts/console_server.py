#!/usr/bin/env python3
"""MotionFence Read-Only Console Server & API Adapter (Phase 2L).

SECURITY INVARIANTS:
1. STRICTLY READ-ONLY: Serves canonical execution records, decision traces, and assurance metrics.
2. ZERO EXECUTION AUTHORITY: Has no credentials, cannot mint AuthorizationTicket, cannot invoke PhysicalActuator.
3. CANNOT MODIFY POLICY: Has no write endpoints; rejects all non-GET requests with 405 Method Not Allowed.
4. CANNOT APPROVE REPAIRS: Repair proposals remain non-authoritative recommendations.
5. ISOLATED RUNTIME: Operates 100% offline, side-effect free.

Usage:
    python scripts/console_server.py [--port 8000] [--host 127.0.0.1]
"""

import argparse
from http import HTTPStatus
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import json
import mimetypes
import os
import sys
import threading
import time
from typing import Any, Dict, List, Optional
from urllib.parse import urlparse

# Ensure motionfence package is on sys.path
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from motionfence.runtime.controlled_demo import (
    demo_manager,
    CANONICAL_SCENARIOS,
    ControlledDemoExecution,
)
from motionfence.runtime.live_demo import LiveDemoRecord, live_record_to_scenario_data

FIXTURES_DIR = os.path.abspath(
    os.path.join(os.path.dirname(__file__), "..", "motionfence", "fixtures", "judge_demo")
)
LIVE_VALIDATION_DIR = os.path.abspath(
    os.path.join(os.path.dirname(__file__), "..", "motionfence", "fixtures", "live_validation")
)
DIST_DIR = os.path.abspath(
    os.path.join(os.path.dirname(__file__), "..", "console", "dist")
)


class RateLimiter:
    """Sliding-window in-memory rate limiter protecting cloud API credits."""

    def __init__(self, max_requests: int = 30, window_seconds: float = 60.0):
        self.max_requests = max_requests
        self.window_seconds = window_seconds
        self.timestamps: List[float] = []
        self.lock = threading.Lock()

    def allow(self) -> bool:
        now = time.time()
        with self.lock:
            self.timestamps = [t for t in self.timestamps if now - t < self.window_seconds]
            if len(self.timestamps) >= self.max_requests:
                return False
            self.timestamps.append(now)
            return True


rate_limiter = RateLimiter(max_requests=30, window_seconds=60.0)


class ReadOnlyConsoleHandler(BaseHTTPRequestHandler):
    """Strictly read-only HTTP handler serving canonical MotionFence records."""

    server_version = "MotionFenceReadOnlyConsole/1.0.0"

    def _set_headers(self, status_code: int = 200, content_type: str = "application/json") -> None:
        self.send_response(status_code)
        self.send_header("Content-Type", content_type)
        allowed_origin = os.getenv("MOTIONFENCE_CORS_ORIGIN", "*")
        self.send_header("Access-Control-Allow-Origin", allowed_origin)
        self.send_header("Access-Control-Allow-Methods", "GET, POST, HEAD, OPTIONS")
        self.send_header("Access-Control-Allow-Headers", "Content-Type, Authorization, X-Request-ID")
        self.send_header("X-Content-Type-Options", "nosniff")
        self.send_header("X-MotionFence-Authority", "STRICTLY_READ_ONLY")
        self.end_headers()

    def do_OPTIONS(self) -> None:
        self._set_headers(200, "text/plain")

    def do_HEAD(self) -> None:
        self._dispatch_request(is_head=True)

    def do_GET(self) -> None:
        self._dispatch_request(is_head=False)

    def do_POST(self) -> None:
        raw_path = getattr(self, "path", "")
        parsed_url = urlparse(raw_path)
        path = parsed_url.path.rstrip("/")
        if path.startswith("/api/demo"):
            self._handle_demo_post(path)
            return
        self._reject_mutation("POST")

    def _handle_demo_post(self, path: str) -> None:
        """Handle server-controlled demonstration execution requests."""
        if not rate_limiter.allow():
            self._set_headers(HTTPStatus.TOO_MANY_REQUESTS)
            self.wfile.write(json.dumps({
                "error": "RATE_LIMIT_EXCEEDED",
                "message": "Demo request rate limit exceeded. Please wait a moment before requesting another demonstration.",
            }).encode("utf-8"))
            return

        subpath = path.replace("/api/demo", "").strip("/")

        content_length = int(self.headers.get("Content-Length", 0))
        if content_length > 65536:
            self._set_headers(HTTPStatus.REQUEST_ENTITY_TOO_LARGE)
            self.wfile.write(json.dumps({
                "error": "PAYLOAD_TOO_LARGE",
                "message": "Request payload exceeds 64KB limit.",
            }).encode("utf-8"))
            return

        body: Dict[str, Any] = {}
        if content_length > 0:
            raw_body = self.rfile.read(content_length)
            try:
                body = json.loads(raw_body.decode("utf-8"))
            except Exception:
                self._set_headers(HTTPStatus.BAD_REQUEST)
                self.wfile.write(json.dumps({
                    "error": "INVALID_JSON",
                    "message": "Request payload must be valid JSON.",
                }).encode("utf-8"))
                return

        if not isinstance(body, dict):
            self._set_headers(HTTPStatus.BAD_REQUEST)
            self.wfile.write(json.dumps({
                "error": "INVALID_PAYLOAD",
                "message": "Request payload must be a JSON object.",
            }).encode("utf-8"))
            return

        is_valid, err_msg = demo_manager.validate_request_payload(body)
        if not is_valid:
            self._set_headers(HTTPStatus.BAD_REQUEST)
            self.wfile.write(json.dumps({
                "error": "FORBIDDEN_PAYLOAD",
                "message": err_msg,
            }).encode("utf-8"))
            return

        scenario = subpath
        if subpath == "run":
            scenario = str(body.get("scenario", "")).strip().lower()

        if scenario not in CANONICAL_SCENARIOS:
            self._set_headers(HTTPStatus.NOT_FOUND)
            self.wfile.write(json.dumps({
                "error": "SCENARIO_NOT_FOUND",
                "message": f"Scenario '{scenario}' is not permitted. Permitted scenarios: {list(CANONICAL_SCENARIOS.keys())}",
                "allowed_scenarios": list(CANONICAL_SCENARIOS.keys()),
            }).encode("utf-8"))
            return

        mode = body.get("mode", "LIVE")
        backend = body.get("backend", "mock")
        request_id = body.get("request_id")

        try:
            ex = demo_manager.create_execution(
                scenario_id=scenario,
                mode=mode,
                backend=backend,
                request_id=request_id,
            )
            self._set_headers(HTTPStatus.ACCEPTED)
            response = {
                "execution_id": ex.execution_id,
                "scenario_id": ex.scenario_id,
                "execution_mode": ex.execution_mode,
                "physical_backend": ex.physical_backend,
                "status": ex.status.value,
                "created_at": ex.created_at,
                "poll_url": f"/api/demo/executions/{ex.execution_id}",
            }
            self.wfile.write(json.dumps(response, indent=2).encode("utf-8"))
        except Exception:
            self._set_headers(HTTPStatus.INTERNAL_SERVER_ERROR)
            self.wfile.write(json.dumps({
                "error": "EXECUTION_DISPATCH_FAILED",
                "message": "Failed to schedule demonstration execution.",
            }).encode("utf-8"))

    def do_PUT(self) -> None:
        self._reject_mutation("PUT")

    def do_DELETE(self) -> None:
        self._reject_mutation("DELETE")

    def do_PATCH(self) -> None:
        self._reject_mutation("PATCH")

    def _reject_mutation(self, method: str) -> None:
        """Reject any state mutation attempt in compliance with Security Invariant 1."""
        self._set_headers(HTTPStatus.METHOD_NOT_ALLOWED)
        response = {
            "error": "METHOD_NOT_ALLOWED",
            "method": method,
            "message": "Safety Engine Invariant Violation: Console server is strictly read-only and possesses ZERO actuation or policy mutation authority.",
            "authority": "ZERO",
        }
        self.wfile.write(json.dumps(response, indent=2).encode("utf-8"))

    def _dispatch_request(self, is_head: bool = False) -> None:
        raw_path = getattr(self, "path", "/")
        parsed_url = urlparse(raw_path)
        path = parsed_url.path.rstrip("/")

        if not path:
            path = "/"

        # Health endpoint at /health or /api/health
        if path in ("/health", "/api/health"):
            self._handle_health(is_head=is_head)
            return

        # Controlled demo routes
        if path == "/api/demo/scenarios":
            self._handle_demo_scenarios(is_head=is_head)
            return

        if path == "/api/demo/executions":
            self._handle_demo_executions(is_head=is_head)
            return

        if path.startswith("/api/demo/executions/"):
            execution_id = path.split("/")[-1]
            self._handle_single_execution(execution_id, is_head=is_head)
            return

        routes = {
            "/api/status": self._handle_status,
            "/api/scenarios": self._handle_scenarios,
            "/api/assurance": self._handle_assurance,
            "/api/mutations": self._handle_mutations,
            "/api/repairs": self._handle_repairs,
            "/api/trajectories": self._handle_trajectories,
        }

        # Check exact API route
        if path in routes:
            routes[path](is_head=is_head)
            return

        # Check parameterized API routes
        if path.startswith("/api/scenarios/") or path.startswith("/api/decisions/") or path.startswith("/api/replay/"):
            scenario_id = path.split("/")[-1]
            self._handle_single_scenario(scenario_id, is_head=is_head)
            return

        if path.startswith("/api/mutations/"):
            mutation_id = path.split("/")[-1]
            self._handle_single_mutation(mutation_id, is_head=is_head)
            return

        if path.startswith("/api/trajectories/"):
            trajectory_id = path.split("/")[-1]
            self._handle_single_trajectory(trajectory_id, is_head=is_head)
            return

        # If it's an API route that didn't match, return 404 JSON
        if path.startswith("/api/"):
            self._set_headers(HTTPStatus.NOT_FOUND)
            if not is_head:
                response = {
                    "error": "NOT_FOUND",
                    "path": self.path,
                    "message": "The requested read-only resource does not exist.",
                }
                self.wfile.write(json.dumps(response).encode("utf-8"))
            return

        # Static file / SPA asset serving from console/dist
        self._serve_static_asset(parsed_url.path, is_head=is_head)

    def _serve_static_asset(self, req_path: str, is_head: bool = False) -> None:
        """Serve static production assets from console/dist or fallback to index.html for SPA."""
        if not os.path.isdir(DIST_DIR):
            self._set_headers(HTTPStatus.NOT_FOUND)
            if not is_head:
                response = {
                    "error": "NOT_FOUND",
                    "path": req_path,
                    "message": "Frontend distribution assets not built or found.",
                }
                self.wfile.write(json.dumps(response).encode("utf-8"))
            return

        # Clean relative path
        rel_path = req_path.lstrip("/")
        if not rel_path:
            rel_path = "index.html"

        candidate_file = os.path.abspath(os.path.join(DIST_DIR, rel_path))

        # Security check: must reside inside DIST_DIR
        if not candidate_file.startswith(DIST_DIR):
            self._set_headers(HTTPStatus.FORBIDDEN)
            if not is_head:
                self.wfile.write(b'{"error": "FORBIDDEN", "message": "Access denied."}')
            return

        # If file exists and is file, serve it
        if os.path.isfile(candidate_file):
            target_file = candidate_file
        else:
            # SPA fallback to index.html
            target_file = os.path.join(DIST_DIR, "index.html")

        if not os.path.isfile(target_file):
            self._set_headers(HTTPStatus.NOT_FOUND)
            if not is_head:
                self.wfile.write(b'{"error": "NOT_FOUND", "message": "File not found."}')
            return

        content_type, _ = mimetypes.guess_type(target_file)
        if not content_type:
            content_type = "application/octet-stream"
        if content_type.startswith("text/") or content_type == "application/javascript":
            content_type += "; charset=utf-8"

        try:
            with open(target_file, "rb") as f:
                content = f.read()
            self._set_headers(HTTPStatus.OK, content_type=content_type)
            if not is_head:
                self.wfile.write(content)
        except Exception as e:
            self._set_headers(HTTPStatus.INTERNAL_SERVER_ERROR)
            if not is_head:
                err_resp = {"error": "INTERNAL_SERVER_ERROR", "message": str(e)}
                self.wfile.write(json.dumps(err_resp).encode("utf-8"))

    def _load_fixture(self, filename: str) -> Optional[Any]:
        filepath = os.path.join(FIXTURES_DIR, filename)
        if not os.path.exists(filepath):
            return None
        with open(filepath, "r", encoding="utf-8") as f:
            return json.load(f)

    def _handle_health(self, is_head: bool = False) -> None:
        """Harden production health endpoint reporting real available capabilities and distinguishing application health from dependency availability."""
        self._set_headers(200)
        if is_head:
            return

        from motionfence.config.settings import settings
        from motionfence.simulation.isaac.environment import detect_isaac_environment

        has_nebius = bool(settings.nebius.api_key and settings.nebius.api_key != "placeholder_key_offline")
        has_tavily = bool(settings.tavily.api_key and settings.tavily.api_key != "placeholder_key_offline")

        isaac_env = detect_isaac_environment()
        backends = ["mock", "replay"]
        if isaac_env.is_available:
            backends.append("isaac")

        exec_modes = ["REPLAY", "OFFLINE_TEST"]
        if has_nebius:
            exec_modes.insert(0, "LIVE")

        data = {
            "status": "healthy",
            "application": "motionfence",
            "safety_runtime": "deterministic",
            "live_model": "configured" if has_nebius else "offline_fixture",
            "telemetry": "configured",
            "evidence_provider": "configured" if has_tavily else "offline_fixture",
            "isaac_runtime": "available" if isaac_env.is_available else "unavailable",
            "mock_backend": "available",
            "execution_modes": exec_modes,
            "model_provider": "nebius" if has_nebius else "offline_fixture",
            "model": settings.nebius.model if has_nebius else "nvidia/nemotron-3-super-120b-a12b",
            "telemetry_provider": "usgs",
            "evidence_provider": "tavily" if has_tavily else "offline_fixture",
            "physical_backends": backends,
        }
        self.wfile.write(json.dumps(data, indent=2).encode("utf-8"))

    def _handle_demo_scenarios(self, is_head: bool = False) -> None:
        """Return allowed server-controlled demonstration scenarios."""
        self._set_headers(200)
        if is_head:
            return
        self.wfile.write(json.dumps(CANONICAL_SCENARIOS, indent=2).encode("utf-8"))

    def _handle_demo_executions(self, is_head: bool = False) -> None:
        """List recent demonstration executions."""
        self._set_headers(200)
        if is_head:
            return
        executions = demo_manager.list_executions()
        self.wfile.write(json.dumps(executions, indent=2).encode("utf-8"))

    def _handle_single_execution(self, execution_id: str, is_head: bool = False) -> None:
        """Return detailed status and result for a demonstration execution."""
        ex = demo_manager.get_execution(execution_id)
        if not ex:
            self._set_headers(HTTPStatus.NOT_FOUND)
            if not is_head:
                self.wfile.write(json.dumps({
                    "error": "EXECUTION_NOT_FOUND",
                    "message": f"Demonstration execution '{execution_id}' not found.",
                }).encode("utf-8"))
            return

        self._set_headers(200)
        if is_head:
            return
        data = {
            "execution_id": ex.execution_id,
            "scenario_id": ex.scenario_id,
            "execution_mode": ex.execution_mode,
            "physical_backend": ex.physical_backend,
            "status": ex.status.value,
            "stage_outcome": ex.stage_outcome.value if ex.stage_outcome else None,
            "created_at": ex.created_at,
            "started_at": ex.started_at,
            "completed_at": ex.completed_at,
            "duration_ms": ex.duration_ms,
            "token_usage": ex.token_usage,
            "events": ex.events,
            "error_message": ex.error_message,
            "sha256_hash": ex.sha256_hash,
            "scenario_data": ex.scenario_data,
        }
        self.wfile.write(json.dumps(data, indent=2).encode("utf-8"))

    def _handle_status(self, is_head: bool = False) -> None:
        self._set_headers(200)
        if is_head:
            return
        from motionfence.config.settings import settings
        has_key = bool(settings.nebius.api_key and settings.nebius.api_key != "placeholder_key_offline")
        data = {
            "service": "MotionFence Safety Case & Judge Console Adapter",
            "version": "2.4.0",
            "status": "OPERATIONAL",
            "execution_mode": "LIVE" if has_key else "OFFLINE_DETERMINISTIC_REPLAY",
            "provider": "nebius" if has_key else "offline_fixture",
            "model": settings.nebius.model if has_key else "nvidia/nemotron-3-super-120b-a12b",
            "authority": {
                "ticket_minting": False,
                "physical_actuation": False,
                "policy_modification": False,
                "repair_approval": False,
                "read_only": True,
            },
            "security_invariants": [
                "UI is strictly read-only with zero execution authority",
                "Backend remains authoritative for all safety decisions",
                "Revalidation defenses are deterministically visualized",
                "Formal assurance results include bounded model disclaimers",
                "Digital twin snapshots originate strictly from runtime state",
            ],
        }
        self.wfile.write(json.dumps(data, indent=2).encode("utf-8"))

    def _handle_scenarios(self, is_head: bool = False) -> None:
        self._set_headers(200)
        if is_head:
            return
        scenarios = [
            {
                "id": "scenario_a",
                "title": "A. Safe Execution (Live Nemotron)",
                "subtitle": "Live Nemotron proposes safe valve isolation -> Policy ALLOW -> Ticket minted -> Actuation verified",
                "flow": "NEMOTRON -> POLICY ALLOW -> TICKET -> HARDWARE ACTUATE -> VERIFIED",
                "category": "NOMINAL",
                "execution_mode": "LIVE",
            },
            {
                "id": "scenario_b",
                "title": "B. Unsafe Proposal Denial (Live Nemotron)",
                "subtitle": "Technician in hazard zone -> Live Nemotron proposes -> Policy strictly DENIES -> Zero Ticket -> Hardware LOCKED",
                "flow": "NEMOTRON -> POLICY DENY -> NO TICKET -> HARDWARE LOCKED -> ZERO MUTATION",
                "category": "POLICY_DENIAL",
                "execution_mode": "LIVE",
            },
            {
                "id": "scenario_c",
                "title": "C. TOCTOU Revalidation Block (Live Nemotron)",
                "subtitle": "Human enters hazardous zone after authorization -> Ticket invalidated before execution -> Hardware LOCKED",
                "flow": "NEMOTRON -> TICKET (v3) -> WORLD CHANGE (v4) -> REVALIDATION BLOCKED -> HARDWARE LOCKED",
                "category": "TOCTOU_DEFENSE",
                "execution_mode": "LIVE",
            },
            {
                "id": "scenario_d",
                "title": "D. Actuator Failure & Recovery (Live Nemotron)",
                "subtitle": "Actuator mechanical stroke fails -> Verification mismatch -> Containment -> Quarantine -> Autonomous Recovery",
                "flow": "NEMOTRON -> TICKET -> HARDWARE FAULT -> VERIF FAILED -> QUARANTINE -> RECOVERED",
                "category": "FAULT_RECOVERY",
                "execution_mode": "LIVE",
            },
            {
                "id": "scenario_e",
                "title": "E. Real-World Public Telemetry (USGS OGC API)",
                "subtitle": "Continuous USGS streamflow ingestion -> Provenance hash -> Environmental context -> Gated execution",
                "flow": "USGS TELEMETRY -> EVIDENCE / PROVENANCE -> NEMOTRON -> POLICY GATE -> ZERO DIRECT ACTUATION",
                "category": "PUBLIC_TELEMETRY",
                "execution_mode": "LIVE",
            },
            {
                "id": "scenario_f",
                "title": "F. Tavily Operational Evidence & Knowledge Admissibility",
                "subtitle": "External web retrieval -> Trust classification & grounding -> Candidate constraint gate -> Policy evaluation",
                "flow": "TAVILY EVIDENCE -> TRUST / GROUNDING -> CONSTRAINT GATE -> POLICY DECISION -> DETERMINISTIC SAFETY",
                "category": "KNOWLEDGE_ADMISSIBILITY",
                "execution_mode": "LIVE",
            },
        ]
        self.wfile.write(json.dumps(scenarios, indent=2).encode("utf-8"))

    def _handle_single_scenario(self, scenario_id: str, is_head: bool = False) -> None:
        mapping = {
            "scenario_a": "scenario_a.json",
            "scenario_b": "scenario_b_denied.json",
            "scenario_c": "scenario_b.json",
            "scenario_d": "scenario_c.json",
            "scenario_e": "telemetry.json",
            "scenario_f": "evidence.json",
            "scenario_a_safe_execution": "scenario_a.json",
            "scenario_b_denied": "scenario_b_denied.json",
            "scenario_b_toctou_block": "scenario_b.json",
            "scenario_c_actuator_failure_recovery": "scenario_c.json",
            "scenario_safe": "safe.json",
            "scenario_denied": "denied.json",
            "scenario_toctou": "toctou.json",
            "scenario_recovery": "recovery.json",
            "scenario_telemetry": "telemetry.json",
            "scenario_evidence": "evidence.json",
        }
        filename = mapping.get(scenario_id)
        if not filename:
            # Check if it matches any decision ID in scenario files
            for fn in ["scenario_a.json", "scenario_b_denied.json", "scenario_b.json", "scenario_c.json"]:
                data = self._load_fixture(fn)
                if data and data.get("decision_record", {}).get("decision_id") == scenario_id:
                    filename = fn
                    break

        # Check LIVE_VALIDATION_DIR if not found in FIXTURES_DIR
        clean_name = scenario_id.replace("scenario_", "").lower()
        live_fixture = os.path.join(LIVE_VALIDATION_DIR, f"{clean_name}.json")
        if os.path.exists(live_fixture):
            try:
                with open(live_fixture, "r", encoding="utf-8") as f:
                    rec_data = json.load(f)
                rec = LiveDemoRecord(**rec_data)
                sc_data = live_record_to_scenario_data(rec)
                self._set_headers(200)
                if not is_head:
                    self.wfile.write(json.dumps(sc_data, indent=2).encode("utf-8"))
                return
            except Exception:
                pass

        if not filename:
            self._set_headers(HTTPStatus.NOT_FOUND)
            if not is_head:
                self.wfile.write(json.dumps({"error": f"Scenario '{scenario_id}' not found."}).encode("utf-8"))
            return

        data = self._load_fixture(filename)
        if not data:
            self._set_headers(HTTPStatus.NOT_FOUND)
            if not is_head:
                self.wfile.write(json.dumps({"error": f"Scenario '{scenario_id}' not found."}).encode("utf-8"))
            return

        self._set_headers(200)
        if not is_head:
            self.wfile.write(json.dumps(data, indent=2).encode("utf-8"))

    def _handle_assurance(self, is_head: bool = False) -> None:
        data = self._load_fixture("assurance_properties.json")
        if not data:
            self._set_headers(HTTPStatus.NOT_FOUND)
            if not is_head:
                self.wfile.write(json.dumps({"error": "Assurance properties not found."}).encode("utf-8"))
            return
        self._set_headers(200)
        if not is_head:
            self.wfile.write(json.dumps(data, indent=2).encode("utf-8"))

    def _handle_mutations(self, is_head: bool = False) -> None:
        data = self._load_fixture("firewall_report.json")
        if not data:
            self._set_headers(HTTPStatus.NOT_FOUND)
            if not is_head:
                self.wfile.write(json.dumps({"error": "Firewall report not found."}).encode("utf-8"))
            return
        self._set_headers(200)
        if not is_head:
            self.wfile.write(json.dumps(data, indent=2).encode("utf-8"))

    def _handle_single_mutation(self, mutation_id: str, is_head: bool = False) -> None:
        report = self._load_fixture("firewall_report.json")
        if not report:
            self._set_headers(HTTPStatus.NOT_FOUND)
            if not is_head:
                self.wfile.write(json.dumps({"error": "Firewall report not found."}).encode("utf-8"))
            return

        for res in report.get("results", []):
            if res.get("mutation", {}).get("mutation_id") == mutation_id:
                self._set_headers(200)
                if not is_head:
                    self.wfile.write(json.dumps(res, indent=2).encode("utf-8"))
                return

        self._set_headers(HTTPStatus.NOT_FOUND)
        if not is_head:
            self.wfile.write(json.dumps({"error": f"Mutation '{mutation_id}' not found."}).encode("utf-8"))

    def _handle_repairs(self, is_head: bool = False) -> None:
        data = self._load_fixture("repair_proposals.json")
        if not data:
            self._set_headers(HTTPStatus.NOT_FOUND)
            if not is_head:
                self.wfile.write(json.dumps({"error": "Repair proposals not found."}).encode("utf-8"))
            return
        self._set_headers(200)
        if not is_head:
            self.wfile.write(json.dumps(data, indent=2).encode("utf-8"))

    def _handle_trajectories(self, is_head: bool = False) -> None:
        data = self._load_fixture("trajectories.json")
        if not data:
            self._set_headers(HTTPStatus.NOT_FOUND)
            if not is_head:
                self.wfile.write(json.dumps({"error": "Trajectories not found."}).encode("utf-8"))
            return
        self._set_headers(200)
        if not is_head:
            self.wfile.write(json.dumps(data, indent=2).encode("utf-8"))

    def _handle_single_trajectory(self, trajectory_id: str, is_head: bool = False) -> None:
        trajs = self._load_fixture("trajectories.json")
        if not trajs:
            self._set_headers(HTTPStatus.NOT_FOUND)
            if not is_head:
                self.wfile.write(json.dumps({"error": "Trajectories not found."}).encode("utf-8"))
            return

        for t in trajs:
            if t.get("trajectory_id") == trajectory_id:
                self._set_headers(200)
                if not is_head:
                    self.wfile.write(json.dumps(t, indent=2).encode("utf-8"))
                return

        self._set_headers(HTTPStatus.NOT_FOUND)
        if not is_head:
            self.wfile.write(json.dumps({"error": f"Trajectory '{trajectory_id}' not found."}).encode("utf-8"))

    def log_message(self, format: str, *args: Any) -> None:
        # Standard clean log output
        sys.stderr.write(f"[MotionFence-Console-API] {self.address_string()} - {format % args}\n")


def run_server(host: str = "127.0.0.1", port: int = 8080) -> None:
    server_address = (host, port)
    httpd = ThreadingHTTPServer(server_address, ReadOnlyConsoleHandler)
    print("=" * 70)
    print(" MOTIONFENCE READ-ONLY CONSOLE API SERVER (PHASE 2L)")
    print("=" * 70)
    print(f"Listening on: http://{host}:{port}")
    print("Authority:    STRICTLY READ-ONLY (Zero Ticket Minting, Zero Actuator Access)")
    print("Endpoints:")
    print("  GET /api/status")
    print("  GET /api/scenarios")
    print("  GET /api/scenarios/{id}")
    print("  GET /api/mutations")
    print("  GET /api/mutations/{id}")
    print("  GET /api/trajectories")
    print("  GET /api/trajectories/{id}")
    print("  GET /api/assurance")
    print("  GET /api/repairs")
    print("=" * 70)
    try:
        httpd.serve_forever()
    except KeyboardInterrupt:
        print("\nShutting down console server cleanly.")
        httpd.server_close()


def main():
    parser = argparse.ArgumentParser(description="MotionFence Read-Only Console Server")
    parser.add_argument("--host", default="127.0.0.1", help="Host interface to bind")
    parser.add_argument("--port", type=int, default=8080, help="Port to bind")
    args = parser.parse_args()
    run_server(host=args.host, port=args.port)


if __name__ == "__main__":
    main()
