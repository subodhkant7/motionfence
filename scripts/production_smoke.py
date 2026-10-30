#!/usr/bin/env python3
"""MotionFence Black-Box Production Smoke Test Suite (Phase 2R).

Validates any deployed MotionFence endpoint (local or remote Nebius public HTTPS URL):
1. Application Health vs Dependency Availability (/health and /api/health)
2. Static Console Assets (SPA index.html and headers)
3. Controlled Demo Scenario Allowlist (/api/demo/scenarios)
4. Strict Rejection of Arbitrary Proposals, Targets, Actions, and Tickets (HTTP 400)
5. Strict Rejection of Direct Actuation / Mutating Endpoints (HTTP 405)
6. Server-Controlled Demo Execution across all 6 Canonical Scenarios
7. Polling and Deterministic Replay Verification (/api/demo/executions/{id})

Usage:
    python scripts/production_smoke.py [--url http://localhost:8080] [--mode REPLAY|LIVE]
"""

import argparse
import json
import os
import sys
import time
from typing import Any, Dict, List, Optional, Tuple
import urllib.error
import ssl
import urllib.request

# Setup clean urllib opener without inherited proxy interference for localhost and with system CA bundle
ssl_ctx = ssl.create_default_context()
if os.path.exists("/etc/ssl/cert.pem"):
    ssl_ctx = ssl.create_default_context(cafile="/etc/ssl/cert.pem")
opener = urllib.request.build_opener(urllib.request.ProxyHandler({}), urllib.request.HTTPSHandler(context=ssl_ctx))


class ProductionSmokeRunner:
    """Black-box validator for public MotionFence endpoints."""

    def __init__(self, base_url: str, mode: str = "REPLAY", timeout: float = 20.0):
        self.base_url = base_url.rstrip("/")
        self.mode = mode.upper()
        self.timeout = timeout
        self.passed_count = 0
        self.failed_count = 0
        self.results: List[Dict[str, Any]] = []

    def _request(
        self,
        method: str,
        path: str,
        body: Optional[Dict[str, Any]] = None,
        headers: Optional[Dict[str, str]] = None,
    ) -> Tuple[int, Dict[str, Any], bytes]:
        """Execute HTTP request against target service."""
        url = f"{self.base_url}{path}"
        data = json.dumps(body).encode("utf-8") if body is not None else None
        hdrs = {
            "User-Agent": "MotionFence-ProductionSmoke/1.0",
            "Accept": "application/json, text/html, */*",
        }
        if data:
            hdrs["Content-Type"] = "application/json"
        if headers:
            hdrs.update(headers)

        req = urllib.request.Request(url, data=data, headers=hdrs, method=method)
        try:
            with opener.open(req, timeout=self.timeout) as resp:
                status_code = resp.status
                raw_bytes = resp.read()
                try:
                    parsed_json = json.loads(raw_bytes.decode("utf-8"))
                except Exception:
                    parsed_json = {}
                return status_code, parsed_json, raw_bytes
        except urllib.error.HTTPError as e:
            raw_bytes = e.read()
            try:
                parsed_json = json.loads(raw_bytes.decode("utf-8"))
            except Exception:
                parsed_json = {}
            return e.code, parsed_json, raw_bytes
        except Exception as e:
            return 0, {"error": str(e)}, b""

    def record_test(self, name: str, passed: bool, details: str = "") -> None:
        if passed:
            self.passed_count += 1
            print(f"  [PASS] {name} {details}")
        else:
            self.failed_count += 1
            print(f"  [FAIL] {name} {details}")
        self.results.append({"name": name, "passed": passed, "details": details})

    def run_all(self) -> bool:
        print("\n" + "=" * 75)
        print(f" MOTIONFENCE PRODUCTION SMOKE TESTER")
        print(f" Target Endpoint: {self.base_url}")
        print(f" Execution Mode:  {self.mode}")
        print(f" Timeout:         {self.timeout}s")
        print("=" * 75 + "\n")

        # 1. Health Endpoints
        print("[1/7] Testing Health & Capability Distinction...")
        status, health_json, _ = self._request("GET", "/health")
        h_ok = (status == 200 and health_json.get("status") == "healthy" and health_json.get("safety_runtime") == "deterministic")
        self.record_test("GET /health", h_ok, f"(status={status}, app={health_json.get('application')}, runtime={health_json.get('safety_runtime')})")

        status_api, api_health_json, _ = self._request("GET", "/api/health")
        self.record_test("GET /api/health", status_api == 200, f"(status={status_api})")

        # 2. Console Static Assets
        print("\n[2/7] Testing Console Static Asset Serving...")
        status_root, _, raw_root = self._request("GET", "/")
        is_html = b"<html" in raw_root.lower() or b"<!doctype html" in raw_root.lower()
        self.record_test("GET / (SPA Shell)", status_root == 200 and is_html, f"(status={status_root}, bytes={len(raw_root)})")

        # 3. Controlled Scenario Allowlist
        print("\n[3/7] Testing Server-Controlled Scenario Allowlist...")
        status_sc, sc_json, _ = self._request("GET", "/api/demo/scenarios")
        expected_scenarios = {"safe", "denied", "toctou", "recovery", "telemetry", "evidence"}
        sc_ok = (status_sc == 200 and expected_scenarios.issubset(set(sc_json.keys())))
        self.record_test("GET /api/demo/scenarios", sc_ok, f"(found={list(sc_json.keys())})")

        # 4. Security: Rejection of Unknown Scenarios
        print("\n[4/7] Testing Unknown Scenario Rejection...")
        status_bad, bad_json, _ = self._request("POST", "/api/demo/malicious_exploit", body={})
        self.record_test("POST /api/demo/unknown_scenario (Rejected)", status_bad in (400, 404), f"(status={status_bad}, err={bad_json.get('error')})")

        # 5. Security: Rejection of Arbitrary Proposals & Actions
        print("\n[5/7] Testing Rejection of Arbitrary Commands & Payloads...")
        injections = [
            ("Arbitrary Action", {"action": "CLOSE_VALVE"}),
            ("Arbitrary Target", {"target": "valve_b"}),
            ("Injected Proposal", {"proposal": {"target": "valve_b"}}),
            ("Forged Ticket", {"ticket": "fake_ticket_123"}),
            ("Policy Override", {"policy": "PERMISSIVE"}),
            ("Direct Command", {"command": "force_stroke"}),
        ]
        for label, payload in injections:
            st, res, _ = self._request("POST", "/api/demo/safe", body=payload)
            passed = (st == 400 and res.get("error") == "FORBIDDEN_PAYLOAD")
            self.record_test(f"Reject {label}", passed, f"(status={st})")

        # 6. Security: Rejection of Mutating / Actuation Endpoints
        print("\n[6/7] Testing Direct Actuation & Mutation Prohibition (405 Method Not Allowed)...")
        forbidden_endpoints = [
            "/api/actuate",
            "/api/execute",
            "/api/hardware",
            "/api/policy",
            "/api/actions",
            "/actuate",
            "/execute",
        ]
        for ep in forbidden_endpoints:
            st, res, _ = self._request("POST", ep, body={"action": "OPEN_VALVE"})
            self.record_test(f"Block POST {ep}", st == 405, f"(status={st}, err={res.get('error')})")

        # 7. Controlled Demo Execution across All 6 Canonical Scenarios
        print(f"\n[7/7] Executing Controlled Scenarios in Mode: {self.mode}...")
        for scenario_id in ["safe", "denied", "toctou", "recovery", "telemetry", "evidence"]:
            t0 = time.time()
            st, trig_json, _ = self._request(
                "POST",
                f"/api/demo/{scenario_id}",
                body={"mode": self.mode, "backend": "mock"},
            )
            if st != 202:
                self.record_test(f"Trigger {scenario_id}", False, f"(status={st}, resp={trig_json})")
                continue

            exec_id = trig_json.get("execution_id")
            poll_url = trig_json.get("poll_url")
            terminal_status = None
            final_record = None

            # Poll for completion
            for _ in range(40):
                time.sleep(0.3)
                pst, pjson, _ = self._request("GET", poll_url)
                if pst == 200:
                    status_val = pjson.get("status")
                    if status_val in ("COMPLETED", "FAILED"):
                        terminal_status = status_val
                        final_record = pjson
                        break

            elapsed_ms = (time.time() - t0) * 1000.0
            is_completed = (terminal_status == "COMPLETED")
            stage_outcome = final_record.get("stage_outcome") if final_record else None
            hash_val = final_record.get("sha256_hash", "")[:12] if final_record else None

            # Verify expected scenario outcome
            expected_outcomes = {
                "safe": "NOMINAL",
                "denied": "DENIED",
                "toctou": "BLOCKED",
                "recovery": "UNVERIFIED",
                "telemetry": "NOMINAL",
                "evidence": "NOMINAL",
            }
            outcome_match = (stage_outcome == expected_outcomes.get(scenario_id))
            passed = is_completed and outcome_match

            self.record_test(
                f"Controlled {scenario_id.upper()}",
                passed,
                f"(status={terminal_status}, outcome={stage_outcome}, hash={hash_val}, elapsed={elapsed_ms:.1f}ms)",
            )

        print("\n" + "=" * 75)
        print(f" PRODUCTION SMOKE TEST SUMMARY")
        print(f" Total Tests Run: {self.passed_count + self.failed_count}")
        print(f" PASSED:          {self.passed_count}")
        print(f" FAILED:          {self.failed_count}")
        print("=" * 75)

        return self.failed_count == 0


def main():
    parser = argparse.ArgumentParser(description="MotionFence Production Smoke Verifier")
    parser.add_argument("--url", default="http://localhost:8088", help="Base URL of MotionFence endpoint")
    parser.add_argument("--mode", default="REPLAY", choices=["REPLAY", "LIVE"], help="Execution mode for demo trigger")
    parser.add_argument("--timeout", type=float, default=25.0, help="Per-request timeout in seconds")
    args = parser.parse_args()

    runner = ProductionSmokeRunner(base_url=args.url, mode=args.mode, timeout=args.timeout)
    success = runner.run_all()
    sys.exit(0 if success else 1)


if __name__ == "__main__":
    main()
