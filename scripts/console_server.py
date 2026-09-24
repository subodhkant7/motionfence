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
import os
import sys
from typing import Any, Dict, Optional
from urllib.parse import urlparse

FIXTURES_DIR = os.path.abspath(
    os.path.join(os.path.dirname(__file__), "..", "motionfence", "fixtures", "judge_demo")
)


class ReadOnlyConsoleHandler(BaseHTTPRequestHandler):
    """Strictly read-only HTTP handler serving canonical MotionFence records."""

    server_version = "MotionFenceReadOnlyConsole/1.0.0"

    def _set_headers(self, status_code: int = 200, content_type: str = "application/json") -> None:
        self.send_response(status_code)
        self.send_header("Content-Type", content_type)
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Access-Control-Allow-Methods", "GET, OPTIONS")
        self.send_header("Access-Control-Allow-Headers", "Content-Type, Authorization")
        self.send_header("X-Content-Type-Options", "nosniff")
        self.send_header("X-MotionFence-Authority", "STRICTLY_READ_ONLY")
        self.end_headers()

    def do_OPTIONS(self) -> None:
        self._set_headers(200, "text/plain")

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

    def do_GET(self) -> None:
        parsed_url = urlparse(self.path)
        path = parsed_url.path.rstrip("/")

        if not path:
            path = "/api/status"

        routes = {
            "/api/status": self._handle_status,
            "/api/scenarios": self._handle_scenarios,
            "/api/assurance": self._handle_assurance,
            "/api/mutations": self._handle_mutations,
            "/api/repairs": self._handle_repairs,
            "/api/trajectories": self._handle_trajectories,
        }

        # Check exact route
        if path in routes:
            routes[path]()
            return

        # Check parameterized routes
        if path.startswith("/api/scenarios/") or path.startswith("/api/decisions/") or path.startswith("/api/replay/"):
            scenario_id = path.split("/")[-1]
            self._handle_single_scenario(scenario_id)
            return

        if path.startswith("/api/mutations/"):
            mutation_id = path.split("/")[-1]
            self._handle_single_mutation(mutation_id)
            return

        if path.startswith("/api/trajectories/"):
            trajectory_id = path.split("/")[-1]
            self._handle_single_trajectory(trajectory_id)
            return

        # Unknown route
        self._set_headers(HTTPStatus.NOT_FOUND)
        response = {
            "error": "NOT_FOUND",
            "path": self.path,
            "message": "The requested read-only resource does not exist.",
        }
        self.wfile.write(json.dumps(response).encode("utf-8"))

    def _load_fixture(self, filename: str) -> Optional[Any]:
        filepath = os.path.join(FIXTURES_DIR, filename)
        if not os.path.exists(filepath):
            return None
        with open(filepath, "r", encoding="utf-8") as f:
            return json.load(f)

    def _handle_status(self) -> None:
        self._set_headers(200)
        data = {
            "service": "MotionFence Safety Case & Judge Console Adapter",
            "version": "2.4.0",
            "status": "OPERATIONAL",
            "execution_mode": "OFFLINE_DETERMINISTIC_REPLAY",
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
            ],
        }
        self.wfile.write(json.dumps(data, indent=2).encode("utf-8"))

    def _handle_scenarios(self) -> None:
        self._set_headers(200)
        scenarios = [
            {
                "id": "scenario_a",
                "title": "A. Safe Execution (Nominal)",
                "subtitle": "Agent proposes an allowed action; verified through complete safety lifecycle",
                "flow": "PROPOSE -> POLICY ALLOW -> AUTHORIZE -> REVALIDATE (PASS) -> EXECUTE -> VERIFIED",
                "category": "NOMINAL",
            },
            {
                "id": "scenario_b",
                "title": "B. TOCTOU Revalidation Block",
                "subtitle": "Human enters hazardous zone after authorization; ticket invalidated before execution",
                "flow": "PROPOSE -> POLICY ALLOW -> AUTHORIZE -> WORLD CHANGE -> REVALIDATE (BLOCKED) -> ABORT",
                "category": "TOCTOU_DEFENSE",
            },
            {
                "id": "scenario_c",
                "title": "C. Actuator Failure & Autonomous Recovery",
                "subtitle": "Actuator stroke fails; verification mismatch triggers quarantine, fresh auth, and recovery",
                "flow": "AUTH -> EXECUTE -> VERIF FAILED -> INVALIDATE -> CONTAIN/QUARANTINE -> FRESH AUTH -> VERIFIED",
                "category": "FAULT_RECOVERY",
            },
        ]
        self.wfile.write(json.dumps(scenarios, indent=2).encode("utf-8"))

    def _handle_single_scenario(self, scenario_id: str) -> None:
        mapping = {
            "scenario_a": "scenario_a.json",
            "scenario_b": "scenario_b.json",
            "scenario_c": "scenario_c.json",
            "scenario_a_safe_execution": "scenario_a.json",
            "scenario_b_toctou_block": "scenario_b.json",
            "scenario_c_actuator_failure_recovery": "scenario_c.json",
        }
        filename = mapping.get(scenario_id)
        if not filename:
            # Check if it matches any decision ID in scenario files
            for fn in ["scenario_a.json", "scenario_b.json"]:
                data = self._load_fixture(fn)
                if data and data.get("decision_record", {}).get("decision_id") == scenario_id:
                    filename = fn
                    break

        if not filename:
            self._set_headers(HTTPStatus.NOT_FOUND)
            self.wfile.write(json.dumps({"error": f"Scenario '{scenario_id}' not found."}).encode("utf-8"))
            return

        data = self._load_fixture(filename)
        self._set_headers(200)
        self.wfile.write(json.dumps(data, indent=2).encode("utf-8"))

    def _handle_assurance(self) -> None:
        data = self._load_fixture("assurance_properties.json")
        if not data:
            self._set_headers(HTTPStatus.NOT_FOUND)
            self.wfile.write(json.dumps({"error": "Assurance properties not found."}).encode("utf-8"))
            return
        self._set_headers(200)
        self.wfile.write(json.dumps(data, indent=2).encode("utf-8"))

    def _handle_mutations(self) -> None:
        data = self._load_fixture("firewall_report.json")
        if not data:
            self._set_headers(HTTPStatus.NOT_FOUND)
            self.wfile.write(json.dumps({"error": "Firewall report not found."}).encode("utf-8"))
            return
        self._set_headers(200)
        self.wfile.write(json.dumps(data, indent=2).encode("utf-8"))

    def _handle_single_mutation(self, mutation_id: str) -> None:
        report = self._load_fixture("firewall_report.json")
        if not report:
            self._set_headers(HTTPStatus.NOT_FOUND)
            self.wfile.write(json.dumps({"error": "Firewall report not found."}).encode("utf-8"))
            return

        for res in report.get("results", []):
            if res.get("mutation", {}).get("mutation_id") == mutation_id:
                self._set_headers(200)
                self.wfile.write(json.dumps(res, indent=2).encode("utf-8"))
                return

        self._set_headers(HTTPStatus.NOT_FOUND)
        self.wfile.write(json.dumps({"error": f"Mutation '{mutation_id}' not found."}).encode("utf-8"))

    def _handle_repairs(self) -> None:
        data = self._load_fixture("repair_proposals.json")
        if not data:
            self._set_headers(HTTPStatus.NOT_FOUND)
            self.wfile.write(json.dumps({"error": "Repair proposals not found."}).encode("utf-8"))
            return
        self._set_headers(200)
        self.wfile.write(json.dumps(data, indent=2).encode("utf-8"))

    def _handle_trajectories(self) -> None:
        data = self._load_fixture("trajectories.json")
        if not data:
            self._set_headers(HTTPStatus.NOT_FOUND)
            self.wfile.write(json.dumps({"error": "Trajectories not found."}).encode("utf-8"))
            return
        self._set_headers(200)
        self.wfile.write(json.dumps(data, indent=2).encode("utf-8"))

    def _handle_single_trajectory(self, trajectory_id: str) -> None:
        trajs = self._load_fixture("trajectories.json")
        if not trajs:
            self._set_headers(HTTPStatus.NOT_FOUND)
            self.wfile.write(json.dumps({"error": "Trajectories not found."}).encode("utf-8"))
            return

        for t in trajs:
            if t.get("trajectory_id") == trajectory_id:
                self._set_headers(200)
                self.wfile.write(json.dumps(t, indent=2).encode("utf-8"))
                return

        self._set_headers(HTTPStatus.NOT_FOUND)
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
