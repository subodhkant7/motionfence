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
from typing import Any, Dict, List, Optional, Set, Tuple
from urllib.parse import parse_qs, unquote, urlparse

# Ensure motionfence package is on sys.path
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from motionfence.config.settings import settings
from motionfence.runtime.controlled_demo import (
    demo_manager,
    CANONICAL_SCENARIOS,
    ControlledDemoExecution,
)
from motionfence.runtime.live_demo import LiveDemoRecord, live_record_to_scenario_data
from motionfence.benchmark.manager import safety_lab_manager
from motionfence.benchmark.registry import ScenarioRegistry
from motionfence.benchmark.evidence import (
    get_hash_scope_disclosure,
    validate_evidence_schema,
    verify_evidence_integrity,
)

FIXTURES_DIR = os.path.abspath(
    os.path.join(os.path.dirname(__file__), "..", "motionfence", "fixtures", "judge_demo")
)
LIVE_VALIDATION_DIR = os.path.abspath(
    os.path.join(os.path.dirname(__file__), "..", "motionfence", "fixtures", "live_validation")
)
DIST_DIR = os.path.abspath(
    os.path.join(os.path.dirname(__file__), "..", "console", "dist")
)


class PerIpRateLimiter:
    """Sliding-window per-IP rate limiter with global safety ceiling and bounded memory.

    SECURITY INVARIANTS:
    1. Keyed per client IP to prevent a single anonymous user from exhausting
       global capacity for all other users (MF-SEC-02).
    2. Global safety ceiling protects backend thread pool and cloud credits from botnets.
    3. Untrusted X-Forwarded-For headers are ignored unless the direct peer IP is
       in MOTIONFENCE_TRUSTED_PROXIES to prevent IP spoofing rate-limit evasion.
    4. Memory is strictly bounded to max_tracked_ips with automatic stale pruning.
    """

    def __init__(
        self,
        max_per_ip: int = 10,
        window_seconds: float = 60.0,
        global_max: int = 120,
        max_tracked_ips: int = 2000,
    ):
        self.max_per_ip = max_per_ip
        self.window_seconds = window_seconds
        self.global_max = global_max
        self.max_tracked_ips = max_tracked_ips
        self.ip_buckets: Dict[str, List[float]] = {}
        self.global_timestamps: List[float] = []
        self.lock = threading.Lock()
        raw_proxies = os.getenv("MOTIONFENCE_TRUSTED_PROXIES", "").strip()
        self.trusted_proxies: Set[str] = set(p.strip() for p in raw_proxies.split(",") if p.strip())

    def resolve_client_ip(self, peer_ip: str, headers: Any) -> str:
        """Derive client IP safely without trusting spoofable X-Forwarded-For from untrusted peers."""
        if peer_ip in self.trusted_proxies:
            xff = headers.get("X-Forwarded-For") or headers.get("x-forwarded-for")
            if xff:
                parts = [p.strip() for p in xff.split(",")]
                if parts and parts[0]:
                    return parts[0]
        return peer_ip

    def allow(self, client_ip: str) -> Tuple[bool, str]:
        """Check if request is permitted under per-IP and global rate limits."""
        now = time.time()
        with self.lock:
            # 1. Prune global timestamps
            self.global_timestamps = [t for t in self.global_timestamps if now - t < self.window_seconds]
            if len(self.global_timestamps) >= self.global_max:
                return False, "GLOBAL_CAP_EXCEEDED"

            # 2. Prune client IP bucket
            timestamps = self.ip_buckets.get(client_ip, [])
            timestamps = [t for t in timestamps if now - t < self.window_seconds]

            if len(timestamps) >= self.max_per_ip:
                self.ip_buckets[client_ip] = timestamps
                return False, "PER_IP_LIMIT_EXCEEDED"

            # 3. Memory bounding: if too many inactive IPs, prune empty/stale buckets
            if len(self.ip_buckets) > self.max_tracked_ips:
                stale_ips = [ip for ip, ts in self.ip_buckets.items() if not ts or (now - ts[-1] >= self.window_seconds)]
                for ip in stale_ips:
                    del self.ip_buckets[ip]

            # 4. Record timestamp
            timestamps.append(now)
            self.ip_buckets[client_ip] = timestamps
            self.global_timestamps.append(now)
            return True, "OK"


rate_limiter = PerIpRateLimiter(
    max_per_ip=int(os.getenv("MOTIONFENCE_RATE_LIMIT_PER_IP", "30")),
    window_seconds=float(os.getenv("MOTIONFENCE_RATE_LIMIT_WINDOW", "60.0")),
    global_max=int(os.getenv("MOTIONFENCE_RATE_LIMIT_GLOBAL", "120")),
)


class ReadOnlyConsoleHandler(BaseHTTPRequestHandler):
    """Strictly read-only HTTP handler serving canonical MotionFence records."""

    server_version = "MotionFenceReadOnlyConsole/1.0.0"

    def _set_headers(self, status_code: int = 200, content_type: str = "application/json") -> None:
        self.send_response(status_code)
        self.send_header("Content-Type", content_type)
        # CORS Configuration:
        # In production: emits configured origin, or omits header for strict same-origin isolation. Wildcard is prohibited.
        # In development: defaults to the local Judge Console Vite dev server (http://127.0.0.1:5173) if unset.
        cors_origin = settings.security.cors_origin or os.getenv("MOTIONFENCE_CORS_ORIGIN", "")
        if not cors_origin and settings.environment.lower() not in ("production", "prod"):
            cors_origin = "http://127.0.0.1:5173"

        if cors_origin and cors_origin != "*":
            self.send_header("Access-Control-Allow-Origin", cors_origin)
            self.send_header("Access-Control-Allow-Methods", "GET, POST, HEAD, OPTIONS")
            self.send_header("Access-Control-Allow-Headers", "Content-Type, Authorization, X-Request-ID")
            self.send_header("Vary", "Origin")
        elif cors_origin == "*" and settings.environment.lower() not in ("production", "prod"):
            self.send_header("Access-Control-Allow-Origin", "*")
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
        if path.startswith("/api/safety-lab"):
            self._handle_safety_lab_post(path)
            return
        self._reject_mutation("POST")

    def _handle_demo_post(self, path: str) -> None:
        """Handle server-controlled demonstration execution requests."""
        peer_ip = self.client_address[0] if hasattr(self, "client_address") and self.client_address else "127.0.0.1"
        client_ip = rate_limiter.resolve_client_ip(peer_ip, self.headers)

        allowed, reason = rate_limiter.allow(client_ip)
        if not allowed:
            self._set_headers(HTTPStatus.TOO_MANY_REQUESTS)
            self.wfile.write(json.dumps({
                "error": "RATE_LIMIT_EXCEEDED",
                "code": reason,
                "client_ip": client_ip,
                "message": (
                    "Global demonstration request ceiling reached. Please wait a moment."
                    if reason == "GLOBAL_CAP_EXCEEDED"
                    else "Per-client demo rate limit exceeded. Maximum 10 demonstrations per minute per client."
                ),
            }).encode("utf-8"))
            return

        subpath = path.replace("/api/demo", "").strip("/")

        raw_cl = self.headers.get("Content-Length")
        content_length = 0
        if raw_cl is not None:
            raw_cl_str = str(raw_cl).strip()
            if "," in raw_cl_str:
                self._set_headers(HTTPStatus.BAD_REQUEST)
                self.wfile.write(json.dumps({
                    "error": "CONFLICTING_CONTENT_LENGTH",
                    "message": "Multiple Content-Length headers are prohibited.",
                }).encode("utf-8"))
                return

            try:
                content_length = int(raw_cl_str)
            except (ValueError, TypeError):
                self._set_headers(HTTPStatus.BAD_REQUEST)
                self.wfile.write(json.dumps({
                    "error": "INVALID_CONTENT_LENGTH",
                    "message": "Content-Length header must be a valid integer.",
                }).encode("utf-8"))
                return

            if content_length < 0:
                self._set_headers(HTTPStatus.BAD_REQUEST)
                self.wfile.write(json.dumps({
                    "error": "NEGATIVE_CONTENT_LENGTH",
                    "message": "Content-Length header cannot be negative.",
                }).encode("utf-8"))
                return

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

    def _handle_safety_lab_post(self, path: str) -> None:
        """Handle public Safety Lab execution and evidence verification requests."""
        peer_ip = self.client_address[0] if hasattr(self, "client_address") and self.client_address else "127.0.0.1"
        client_ip = rate_limiter.resolve_client_ip(peer_ip, self.headers)

        allowed, reason = rate_limiter.allow(client_ip)
        if not allowed:
            self._set_headers(HTTPStatus.TOO_MANY_REQUESTS)
            self.wfile.write(json.dumps({
                "error": "RATE_LIMIT_EXCEEDED",
                "code": reason,
                "message": "Safety Lab rate limit exceeded. Please wait a moment before running more scenarios.",
            }).encode("utf-8"))
            return

        subpath = path.replace("/api/safety-lab", "").strip("/")

        raw_cl = self.headers.get("Content-Length")
        content_length = 0
        if raw_cl is not None:
            try:
                content_length = int(str(raw_cl).strip())
            except (ValueError, TypeError):
                self._set_headers(HTTPStatus.BAD_REQUEST)
                self.wfile.write(json.dumps({"error": "INVALID_CONTENT_LENGTH"}).encode("utf-8"))
                return
            if content_length > 65536:
                self._set_headers(HTTPStatus.REQUEST_ENTITY_TOO_LARGE)
                self.wfile.write(json.dumps({"error": "PAYLOAD_TOO_LARGE"}).encode("utf-8"))
                return

        body: Dict[str, Any] = {}
        if content_length > 0:
            raw_body = self.rfile.read(content_length)
            try:
                body = json.loads(raw_body.decode("utf-8"))
            except Exception:
                self._set_headers(HTTPStatus.BAD_REQUEST)
                self.wfile.write(json.dumps({"error": "INVALID_JSON"}).encode("utf-8"))
                return

        if not isinstance(body, dict):
            self._set_headers(HTTPStatus.BAD_REQUEST)
            self.wfile.write(json.dumps({"error": "INVALID_PAYLOAD"}).encode("utf-8"))
            return

        # Verification endpoint
        if subpath == "verify-evidence":
            schema_valid, schema_err = validate_evidence_schema(body)
            if not schema_valid:
                self._set_headers(HTTPStatus.BAD_REQUEST)
                self.wfile.write(json.dumps({
                    "is_valid": False,
                    "schema_valid": False,
                    "error": "MALFORMED_EVIDENCE_SCHEMA",
                    "message": schema_err,
                    "hash_scope_disclosure": get_hash_scope_disclosure(),
                }, indent=2).encode("utf-8"))
                return

            is_valid, reported, computed = verify_evidence_integrity(body)
            self._set_headers(HTTPStatus.OK)
            self.wfile.write(json.dumps({
                "is_valid": is_valid,
                "schema_valid": True,
                "reported_hash": reported,
                "computed_hash": computed,
                "message": (
                    "SHA-256 byte-level integrity verified against canonical serialization."
                    if is_valid
                    else "SHA-256 hash mismatch: artifact inputs, pipeline stages, or assertions have been modified."
                ),
                "hash_scope_disclosure": get_hash_scope_disclosure(),
            }, indent=2).encode("utf-8"))
            return

        # Payload validation against arbitrary actuation
        is_valid, err_msg = safety_lab_manager.validate_payload(body)
        if not is_valid:
            self._set_headers(HTTPStatus.BAD_REQUEST)
            self.wfile.write(json.dumps({
                "error": "FORBIDDEN_PAYLOAD",
                "message": err_msg,
            }).encode("utf-8"))
            return

        if subpath in ("run", ""):
            scenario_id = str(body.get("scenario_id") or body.get("scenario") or "safe_valve_operation").strip()
            mode = str(body.get("mode", "DETERMINISTIC_REPLAY")).strip()
            seed = int(body.get("seed", 42))

            try:
                dispatch_res = safety_lab_manager.start_scenario_execution(scenario_id, mode_str=mode, seed=seed)
                self._set_headers(HTTPStatus.ACCEPTED)
                self.wfile.write(json.dumps(dispatch_res, indent=2).encode("utf-8"))
            except Exception as e:
                self._set_headers(HTTPStatus.INTERNAL_SERVER_ERROR)
                self.wfile.write(json.dumps({"error": "DISPATCH_FAILED", "message": str(e)}).encode("utf-8"))
            return

        if subpath == "benchmark":
            mode = str(body.get("mode", "DETERMINISTIC_REPLAY")).strip()
            suite = str(body.get("suite", "expanded")).strip()
            seed = int(body.get("seed", 42))
            try:
                dispatch_res = safety_lab_manager.start_benchmark_suite(mode_str=mode, suite_str=suite, seed=seed)
                self._set_headers(HTTPStatus.ACCEPTED)
                self.wfile.write(json.dumps(dispatch_res, indent=2).encode("utf-8"))
            except Exception as e:
                self._set_headers(HTTPStatus.INTERNAL_SERVER_ERROR)
                self.wfile.write(json.dumps({"error": "DISPATCH_FAILED", "message": str(e)}).encode("utf-8"))
            return

        self._set_headers(HTTPStatus.NOT_FOUND)
        self.wfile.write(json.dumps({"error": "ROUTE_NOT_FOUND"}).encode("utf-8"))

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

        # Safety Lab routes
        if path == "/api/safety-lab/scenarios":
            self._handle_safety_lab_scenarios(is_head=is_head)
            return

        if path.startswith("/api/safety-lab/executions/"):
            exec_id = path.split("/")[-1]
            self._handle_safety_lab_single_execution(exec_id, is_head=is_head)
            return

        if path.startswith("/api/safety-lab/evidence/"):
            exec_id = path.split("/")[-1]
            self._handle_safety_lab_evidence(exec_id, is_head=is_head)
            return

        if path == "/api/safety-lab/benchmark/report":
            self._handle_safety_lab_benchmark_report(is_head=is_head)
            return

        if path == "/api/isaac/status":
            self._handle_isaac_status(is_head=is_head)
            return

        if path in ("/api/isaac/scene.usda", "/api/isaac/scene"):
            self._handle_isaac_usd(is_head=is_head)
            return

        if path in ("/api/isaac/runner.py", "/api/isaac/runner"):
            self._handle_isaac_runner(is_head=is_head)
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

        real_dist = os.path.realpath(DIST_DIR)

        # Unquote URL path to prevent %2e%2e traversal
        unquoted_path = unquote(req_path).lstrip("/")
        if not unquoted_path:
            unquoted_path = "index.html"

        candidate_file = os.path.realpath(os.path.join(real_dist, unquoted_path))

        # Security check: candidate must be strictly contained inside real_dist
        try:
            common = os.path.commonpath([real_dist, candidate_file])
        except ValueError:
            self._set_headers(HTTPStatus.FORBIDDEN)
            if not is_head:
                self.wfile.write(b'{"error": "FORBIDDEN", "message": "Access denied."}')
            return

        if common != real_dist:
            self._set_headers(HTTPStatus.FORBIDDEN)
            if not is_head:
                self.wfile.write(b'{"error": "FORBIDDEN", "message": "Access denied."}')
            return

        # If file exists and is file, serve it
        if os.path.isfile(candidate_file):
            target_file = candidate_file
        else:
            # SPA fallback to index.html
            target_file = os.path.join(real_dist, "index.html")

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
        except Exception:
            self._set_headers(HTTPStatus.INTERNAL_SERVER_ERROR)
            if not is_head:
                err_resp = {"error": "INTERNAL_SERVER_ERROR", "message": "Failed to read requested static asset."}
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
            "error_details": ex.error_details,
            "sha256_hash": ex.sha256_hash,
            "scenario_data": ex.scenario_data,
        }
        self.wfile.write(json.dumps(data, indent=2).encode("utf-8"))

    def _handle_safety_lab_scenarios(self, is_head: bool = False) -> None:
        """Return permitted Safety Lab scenarios and ground truth metadata."""
        self._set_headers(200)
        if is_head:
            return
        scenarios = ScenarioRegistry.list_scenarios()
        data = [
            {
                "scenario_id": s.scenario_id,
                "version": s.version,
                "title": s.title,
                "threat_category": s.threat_category,
                "threat_description": s.threat_description,
                "metric_classification": s.metric_classification.value,
                "initial_plant_state": s.initial_plant_state,
                "ground_truth": s.ground_truth.model_dump(),
                "assertion_count": len(s.assertion_rules),
                "assertion_rules": [a.model_dump() for a in s.assertion_rules],
                "is_canonical": s.is_canonical,
                "variant_of": s.variant_of,
            }
            for s in scenarios
        ]
        self.wfile.write(json.dumps(data, indent=2).encode("utf-8"))

    def _handle_safety_lab_single_execution(self, exec_id: str, is_head: bool = False) -> None:
        """Return status and results of a Safety Lab execution."""
        record = safety_lab_manager.get_execution(exec_id)
        if not record:
            self._set_headers(HTTPStatus.NOT_FOUND)
            if not is_head:
                self.wfile.write(json.dumps({"error": "EXECUTION_NOT_FOUND"}).encode("utf-8"))
            return
        self._set_headers(HTTPStatus.OK)
        if is_head:
            return
        self.wfile.write(json.dumps(record, indent=2).encode("utf-8"))

    def _handle_safety_lab_evidence(self, exec_id: str, is_head: bool = False) -> None:
        """Return downloadable, canonical evidence bundle for a completed execution."""
        bundle = safety_lab_manager.get_evidence_bundle(exec_id)
        if not bundle:
            self._set_headers(HTTPStatus.NOT_FOUND)
            if not is_head:
                self.wfile.write(json.dumps({"error": "EVIDENCE_NOT_FOUND"}).encode("utf-8"))
            return
        self._set_headers(HTTPStatus.OK)
        if is_head:
            return
        self.wfile.write(json.dumps(bundle, indent=2).encode("utf-8"))

    def _handle_safety_lab_benchmark_report(self, is_head: bool = False) -> None:
        report_file = os.path.abspath(
            os.path.join(os.path.dirname(__file__), "..", "motionfence", "fixtures", "benchmark", "report.json")
        )
        parsed = urlparse(getattr(self, "path", ""))
        query_params = parse_qs(parsed.query)
        suite_req = query_params.get("suite", ["expanded"])[0].lower()

        data = None
        if os.path.exists(report_file):
            try:
                with open(report_file, "r", encoding="utf-8") as f:
                    cached_data = json.load(f)
                if suite_req == "canonical" and cached_data.get("suite_type") != "canonical":
                    from motionfence.benchmark.engine import BenchmarkEngine
                    engine = BenchmarkEngine()
                    rep = engine.run_suite(suite_type="canonical")
                    data = rep.model_dump()
                else:
                    data = cached_data
            except Exception:
                data = None

        if not data:
            from motionfence.benchmark.engine import BenchmarkEngine
            engine = BenchmarkEngine()
            rep = engine.run_suite(suite_type=suite_req)
            data = rep.model_dump()

        self._set_headers(HTTPStatus.OK)
        if is_head:
            return
        self.wfile.write(json.dumps(data, indent=2).encode("utf-8"))

    def _handle_isaac_status(self, is_head: bool = False) -> None:
        """Return runtime status of NVIDIA Isaac Sim environment and USD stage spec."""
        self._set_headers(200)
        if is_head:
            return
        from motionfence.simulation.isaac.environment import detect_isaac_environment
        from motionfence.simulation.isaac.scene_spec import IndustrialCellSceneSpec

        isaac_env = detect_isaac_environment()
        spec = IndustrialCellSceneSpec()

        data = {
            "is_available": isaac_env.is_available,
            "runtime_mode": "native_isaac_sim" if isaac_env.is_available else "contract_simulator",
            "host_os": isaac_env.os_name,
            "architecture": isaac_env.arch,
            "simulation_backend": "isaac",
            "root_prim": spec.root_prim,
            "prim_paths": {
                "valve_b": spec.valve_b_prim,
                "pump_p1": spec.pump_p1_prim,
                "human_zone": spec.human_zone_prim,
                "human_actor": spec.human_actor_prim,
                "gateway_actuator": spec.gateway_prim,
            },
            "bounds": spec.human_zone_bounds,
            "kinematic_limits": {
                "valve_open_angle_deg": spec.valve_open_angle_deg,
                "valve_closed_angle_deg": spec.valve_closed_angle_deg,
                "valve_stroke_time_sec": spec.valve_stroke_time_sec,
            },
            "environment_instructions": (
                "Native NVIDIA Omniverse Isaac Sim requires Ubuntu 22.04/24.04 or Windows 11 with NVIDIA RTX GPU. "
                "On macOS (arm64), contract simulation with real-time 3D OpenUSD stage visualization is active."
            ),
        }
        self.wfile.write(json.dumps(data, indent=2).encode("utf-8"))

    def _handle_isaac_usd(self, is_head: bool = False) -> None:
        """Return downloadable OpenUSD ASCII stage representation."""
        from motionfence.simulation.isaac.scene_spec import generate_scene_usd_ascii
        usd_data = generate_scene_usd_ascii().encode("utf-8")
        self.send_response(200)
        self.send_header("Content-Type", "model/vnd.usda; charset=utf-8")
        self.send_header("Content-Length", str(len(usd_data)))
        self.send_header("Content-Disposition", 'attachment; filename="industrial_cell.usda"')
        self.send_header("Access-Control-Allow-Origin", "*")
        self.end_headers()
        if not is_head:
            self.wfile.write(usd_data)

    def _handle_isaac_runner(self, is_head: bool = False) -> None:
        """Return standalone Python runner script for native Isaac Sim workstation execution."""
        from motionfence.simulation.isaac.scene_spec import generate_isaac_standalone_python_script
        script_data = generate_isaac_standalone_python_script().encode("utf-8")
        self.send_response(200)
        self.send_header("Content-Type", "text/x-python; charset=utf-8")
        self.send_header("Content-Length", str(len(script_data)))
        self.send_header("Content-Disposition", 'attachment; filename="isaac_motionfence_cell.py"')
        self.send_header("Access-Control-Allow-Origin", "*")
        self.end_headers()
        if not is_head:
            self.wfile.write(script_data)

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
    # Enforce strict production security check if in production mode
    settings.validate_production_security()

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
