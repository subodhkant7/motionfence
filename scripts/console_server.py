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
from typing import Any, Dict, Optional
from urllib.parse import urlparse

# Ensure motionfence package is on sys.path
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

FIXTURES_DIR = os.path.abspath(
    os.path.join(os.path.dirname(__file__), "..", "motionfence", "fixtures", "judge_demo")
)
DIST_DIR = os.path.abspath(
    os.path.join(os.path.dirname(__file__), "..", "console", "dist")
)


class ReadOnlyConsoleHandler(BaseHTTPRequestHandler):
    """Strictly read-only HTTP handler serving canonical MotionFence records."""

    server_version = "MotionFenceReadOnlyConsole/1.0.0"

    def _set_headers(self, status_code: int = 200, content_type: str = "application/json") -> None:
        self.send_response(status_code)
        self.send_header("Content-Type", content_type)
        allowed_origin = os.getenv("MOTIONFENCE_CORS_ORIGIN", "*")
        self.send_header("Access-Control-Allow-Origin", allowed_origin)
        self.send_header("Access-Control-Allow-Methods", "GET, HEAD, OPTIONS")
        self.send_header("Access-Control-Allow-Headers", "Content-Type, Authorization")
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
        self._reject_mutation("POST")

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
        parsed_url = urlparse(self.path)
        path = parsed_url.path.rstrip("/")

        if not path:
            path = "/"

        # Health endpoint at /health or /api/health
        if path in ("/health", "/api/health"):
            self._handle_health(is_head=is_head)
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
        """Harden production health endpoint reporting real available capabilities."""
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
            "execution_modes": exec_modes,
            "model_provider": "nebius" if has_nebius else "offline_fixture",
            "model": settings.nebius.model if has_nebius else "nvidia/nemotron-3-super-120b-a12b",
            "telemetry_provider": "usgs",
            "evidence_provider": "tavily" if has_tavily else "offline_fixture",
            "physical_backends": backends,
            "safety_runtime": "deterministic",
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
        ]
        self.wfile.write(json.dumps(scenarios, indent=2).encode("utf-8"))

    def _handle_single_scenario(self, scenario_id: str, is_head: bool = False) -> None:
        mapping = {
            "scenario_a": "scenario_a.json",
            "scenario_b": "scenario_b_denied.json",
            "scenario_c": "scenario_b.json",
            "scenario_d": "scenario_c.json",
            "scenario_a_safe_execution": "scenario_a.json",
            "scenario_b_denied": "scenario_b_denied.json",
            "scenario_b_toctou_block": "scenario_b.json",
            "scenario_c_actuator_failure_recovery": "scenario_c.json",
            "scenario_safe": "scenario_live_safe.json",
            "scenario_denied": "scenario_b_denied.json",
            "scenario_toctou": "scenario_live_toctou.json",
            "scenario_recovery": "scenario_live_recovery.json",
        }
        filename = mapping.get(scenario_id)
        if not filename:
            # Check if it matches any decision ID in scenario files
            for fn in ["scenario_a.json", "scenario_b_denied.json", "scenario_b.json", "scenario_c.json"]:
                data = self._load_fixture(fn)
                if data and data.get("decision_record", {}).get("decision_id") == scenario_id:
                    filename = fn
                    break

        if not filename:
            self._set_headers(HTTPStatus.NOT_FOUND)
            if not is_head:
                self.wfile.write(json.dumps({"error": f"Scenario '{scenario_id}' not found."}).encode("utf-8"))
            return

        data = self._load_fixture(filename)
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
