"""MotionFence Safety Lab Execution Manager.

Provides thread-safe management, dispatching, in-memory caching,
and evidence retrieval for Safety Lab scenario and benchmark runs.

SECURITY INVARIANTS:
1. ONLY PREDEFINED CANONICAL SCENARIOS: Only registered scenarios can be executed.
2. ZERO ARBITRARY ACTUATION: Any payload attempting to supply action, target,
   commands, or policy overrides is strictly rejected.
3. ISOLATED SYNTHETIC STATE: Runs execute in isolated synthetic environments;
   real hardware endpoints are never accessed.
4. BOUNDED HISTORY & RATE LIMITS: In-memory cache is strictly bounded to prevent DoS.
"""

from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor
import copy
from datetime import datetime, timezone
import json
import logging
import threading
import time
from typing import Any, Dict, List, Optional, Tuple
import uuid

from motionfence.benchmark.engine import BenchmarkEngine
from motionfence.benchmark.evidence import canonicalize_json, compute_evidence_hash, verify_evidence_integrity
from motionfence.benchmark.models import (
    BenchmarkExecutionMode,
    BenchmarkReport,
    ScenarioDefinition,
    ScenarioExecutionResult,
)
from motionfence.benchmark.registry import ScenarioRegistry

logger = logging.getLogger("motionfence.benchmark.manager")

FORBIDDEN_FIELDS = {
    "action", "target", "command", "commands", "override", "overrides",
    "hardware", "actuate", "actuator", "patch", "ticket", "policy_override",
    "force_execute", "shell", "eval", "exec",
}


class SafetyLabManager:
    """Manages execution, caching, and evidence retrieval for the public Safety Lab."""

    def __init__(self, max_concurrent: int = 4, max_history: int = 50):
        self._max_concurrent = max_concurrent
        self._max_history = max_history
        self._executor = ThreadPoolExecutor(max_workers=max_concurrent, thread_name_prefix="safetylab-worker")
        self._lock = threading.Lock()
        self._executions: Dict[str, Dict[str, Any]] = {}
        self._benchmark_reports: Dict[str, BenchmarkReport] = {}
        self._engine = BenchmarkEngine()

    def validate_payload(self, payload: Dict[str, Any]) -> Tuple[bool, Optional[str]]:
        """Strict server-side validation rejecting arbitrary actuator commands."""
        if not isinstance(payload, dict):
            return False, "Payload must be a JSON object."

        for key in FORBIDDEN_FIELDS:
            if key in payload:
                return False, f"Forbidden field '{key}' detected. Public users cannot submit arbitrary actions, targets, or policy commands."

        scenario_id = payload.get("scenario_id") or payload.get("scenario")
        if scenario_id and not ScenarioRegistry.validate_scenario_id(scenario_id):
            return False, f"Scenario '{scenario_id}' is not permitted. Permitted scenarios: {[s.scenario_id for s in ScenarioRegistry.list_scenarios()]}"

        return True, None

    def start_scenario_execution(
        self,
        scenario_id: str,
        mode_str: str = "DETERMINISTIC_REPLAY",
        seed: int = 42,
    ) -> Dict[str, Any]:
        """Start execution of a single scenario."""
        sc_def = ScenarioRegistry.get_scenario(scenario_id)
        if not sc_def:
            raise ValueError(f"Unknown scenario: {scenario_id}")

        mode = BenchmarkExecutionMode.DETERMINISTIC_REPLAY
        if mode_str.upper() in ("LIVE_INFERENCE", "LIVE"):
            # Enforce live inference guardrails: only nominal safe scenario is allowed live, others replay
            mode = BenchmarkExecutionMode.LIVE_INFERENCE if scenario_id == "safe_valve_operation" else BenchmarkExecutionMode.DETERMINISTIC_REPLAY

        exec_id = f"lab_exec_{uuid.uuid4().hex[:12]}"
        created_at = time.time()

        record: Dict[str, Any] = {
            "execution_id": exec_id,
            "type": "SINGLE_SCENARIO",
            "scenario_id": scenario_id,
            "scenario_title": sc_def.title,
            "execution_mode": mode.value,
            "status": "RUNNING",
            "created_at": created_at,
            "completed_at": None,
            "duration_ms": None,
            "result": None,
            "error": None,
            "sha256_hash": None,
        }

        with self._lock:
            if len(self._executions) >= self._max_history:
                oldest_id = next(iter(self._executions))
                del self._executions[oldest_id]
            self._executions[exec_id] = record

        # Execute scenario
        def _task():
            try:
                res = self._engine.run_scenario(sc_def, mode=mode)
                res_dict = res.model_dump()
                res_dict["execution_id"] = exec_id
                with self._lock:
                    record["status"] = "COMPLETED"
                    record["completed_at"] = time.time()
                    record["duration_ms"] = res.duration_ms
                    record["result"] = res_dict
                    record["sha256_hash"] = res.sha256_hash
            except Exception as e:
                logger.exception("Safety lab scenario execution failed: %s", e)
                with self._lock:
                    record["status"] = "FAILED"
                    record["completed_at"] = time.time()
                    record["error"] = "Execution encountered internal fault fail-closed."

        self._executor.submit(_task)
        return {
            "execution_id": exec_id,
            "status": "QUEUED",
            "scenario_id": scenario_id,
            "execution_mode": mode.value,
            "poll_url": f"/api/safety-lab/executions/{exec_id}",
        }

    def start_benchmark_suite(
        self,
        mode_str: str = "DETERMINISTIC_REPLAY",
        suite_str: str = "expanded",
        seed: int = 42,
    ) -> Dict[str, Any]:
        """Start full benchmark suite run."""
        mode = BenchmarkExecutionMode.DETERMINISTIC_REPLAY
        suite = "canonical" if str(suite_str).lower() == "canonical" else "expanded"
        exec_id = f"lab_suite_{uuid.uuid4().hex[:12]}"
        created_at = time.time()

        record: Dict[str, Any] = {
            "execution_id": exec_id,
            "type": "BENCHMARK_SUITE",
            "suite_type": suite,
            "execution_mode": mode.value,
            "status": "RUNNING",
            "created_at": created_at,
            "completed_at": None,
            "duration_ms": None,
            "report": None,
            "error": None,
            "sha256_hash": None,
        }

        with self._lock:
            if len(self._executions) >= self._max_history:
                oldest_id = next(iter(self._executions))
                del self._executions[oldest_id]
            self._executions[exec_id] = record

        def _task():
            try:
                report = self._engine.run_suite(mode=mode, suite_type=suite)
                with self._lock:
                    record["status"] = "COMPLETED"
                    record["completed_at"] = time.time()
                    record["report"] = report.model_dump()
                    record["sha256_hash"] = report.sha256_hash
                    self._benchmark_reports[exec_id] = report
            except Exception as e:
                logger.exception("Safety lab benchmark suite execution failed: %s", e)
                with self._lock:
                    record["status"] = "FAILED"
                    record["completed_at"] = time.time()
                    record["error"] = "Benchmark execution encountered internal fault fail-closed."

        self._executor.submit(_task)
        return {
            "execution_id": exec_id,
            "status": "QUEUED",
            "suite_type": suite,
            "execution_mode": mode.value,
            "poll_url": f"/api/safety-lab/executions/{exec_id}",
        }

    def get_execution(self, exec_id: str) -> Optional[Dict[str, Any]]:
        with self._lock:
            ex = self._executions.get(exec_id)
            if not ex:
                for item in self._executions.values():
                    if item.get("result", {}).get("execution_id") == exec_id:
                        return copy.deepcopy(item)
                return None
            return copy.deepcopy(ex)

    def get_evidence_bundle(self, exec_id: str) -> Optional[Dict[str, Any]]:
        with self._lock:
            ex = self._executions.get(exec_id)
            if not ex:
                for item in self._executions.values():
                    res = item.get("result", {})
                    if res.get("execution_id") == exec_id or res.get("evidence_bundle_id") == exec_id:
                        ex = item
                        break
            if not ex:
                return None
            if "evidence_bundle" in ex:
                return copy.deepcopy(ex["evidence_bundle"])
            if ex.get("type") == "SINGLE_SCENARIO" and ex.get("result"):
                res = ex["result"]
                evidence_bundle = {
                    "bundle_id": res.get("evidence_bundle_id", f"evb_{exec_id}"),
                    "run_id": exec_id,
                    "scenario_id": res["scenario_id"],
                    "scenario_version": res.get("scenario_version", "1.0.0"),
                    "benchmark_version": "1.0.0",
                    "execution_mode": res.get("execution_mode", "DETERMINISTIC_REPLAY"),
                    "created_at_utc": datetime.now(timezone.utc).isoformat(),
                    "sanitized_initial_state": res.get("initial_state_summary", {}),
                    "sanitized_final_state": res.get("final_state_summary", {}),
                    "ordered_events": res.get("events", [])[:20],
                    "proposal": res.get("proposal_summary"),
                    "policy_verdict": {
                        "decision": res.get("policy_decision"),
                        "reasons": res.get("policy_reason_codes", []),
                    },
                    "authorization": {
                        "status": res.get("authorization_status"),
                        "ticket_minted": res.get("ticket_minted"),
                        "ticket_id": res.get("ticket_id"),
                        "revalidation_status": res.get("revalidation_status"),
                    },
                    "execution": {
                        "status": res.get("execution_status"),
                        "mutation_occurred": res.get("mutation_occurred"),
                    },
                    "verification": {
                        "status": res.get("verification_status"),
                        "discrepancies": res.get("verification_discrepancies", []),
                    },
                    "assertions": res.get("assertions", []),
                    "timing": {
                        "duration_ms": res.get("duration_ms", 0.0),
                        "simulation_ms": res.get("simulation_duration_ms", 0.0),
                        "backend_ms": res.get("backend_duration_ms", 0.0),
                    },
                    "final_classification": "PASS" if res.get("passed") else "FAIL",
                }
                computed_hash = compute_evidence_hash(evidence_bundle)
                evidence_bundle["sha256_hash"] = computed_hash
                ex["evidence_bundle"] = evidence_bundle
                return copy.deepcopy(evidence_bundle)
            elif ex.get("type") == "BENCHMARK_SUITE" and ex.get("report"):
                return copy.deepcopy(ex["report"])
            return None


safety_lab_manager = SafetyLabManager()
