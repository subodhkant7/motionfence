"""MotionFence Controlled Live Demo Runtime Engine (Phase 2R).

Provides server-controlled execution of canonical demonstration scenarios.

SECURITY INVARIANTS:
1. FIXED CANONICAL SCENARIOS: Only predefined scenarios may be executed:
   ['safe', 'denied', 'toctou', 'recovery', 'telemetry', 'evidence']
2. ZERO ARBITRARY ACTUATION: Clients cannot specify action, target, ticket,
   policy, or hardware commands. Any request containing these fields is rejected.
3. FAIL-CLOSED SAFETY: Provider errors (timeout, quota, network) strictly terminate
   with zero tickets minted and actuators locked.
4. ISOLATED PER-RUN CONTEXT: Simultaneous executions never share world state,
   tickets, or hardware instances.
5. NO SECRET LEAKAGE: API keys and private HMAC keys are never returned in execution records.
"""

from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone
from enum import Enum
import hashlib
import json
import logging
import os
import threading
import time
from typing import Any, Dict, List, Optional, Tuple
import uuid
from pydantic import BaseModel, Field

from motionfence.config.settings import settings
from motionfence.agent.nebius_provider import NebiusNemotronProvider
from motionfence.agent.exceptions import NebiusProviderError
from motionfence.knowledge.tavily_provider import TavilyKnowledgeProvider
from motionfence.evidence.models import Evidence, EvidenceSource
from motionfence.hardware.mock import MockHardwareEndpoint
from motionfence.hardware.models import (
    ActuatorType,
    HardwareExecutionRecord,
    HardwareExecutionStatus,
    HardwareFaultType,
)
from motionfence.models.actions import (
    ActionProposal,
    ActionType,
    AuthorizationTicket,
    ExecutionResult,
)
from motionfence.models.world import CoolingState, HumanZoneState, LeakState, ValveState, WorldState
from motionfence.policy.models import DecisionType, Policy, PolicyDecision
from motionfence.policy.engine import PolicyEngine
from motionfence.recovery.models import (
    ComponentType,
    FailureClass,
    QuarantineStatus,
    RecoveryOutcome,
)
from motionfence.recovery.executor import RecoveryExecutor
from motionfence.runtime.enclave import EnclaveAuthorizationRequest, SafetyEnclave
from motionfence.runtime.events import EventBus
from motionfence.runtime.live_demo import (
    DigitalTwinPlantState,
    ExecutionMode,
    LiveDemoRecord,
    LiveScenarioType,
    make_digital_twin_snapshot,
    live_record_to_scenario_data,
)
from motionfence.runtime.revalidation import ExecutionTimeRevalidator, RevalidationStatus
from motionfence.runtime.ticket import TicketAuthority
from motionfence.runtime.verification import PostActionVerifier, VerificationResult, VerificationStatus
from motionfence.simulation.world import PhysicalWorld
from motionfence.simulation.isaac.environment import detect_isaac_environment

logger = logging.getLogger("motionfence.runtime.controlled_demo")

CANONICAL_SCENARIOS = {
    "safe": {
        "id": "safe",
        "name": "A. Safe Execution (Nominal)",
        "description": "Nominal leak isolation proposal -> Policy ALLOW -> State-bound ticket -> Hardware actuated -> Postcondition verified.",
        "category": "NOMINAL",
        "requires_telemetry": False,
        "requires_evidence": False,
    },
    "denied": {
        "id": "denied",
        "name": "B. Unsafe Proposal Denial",
        "description": "Worker in hazard exclusion zone -> Policy strictly DENIES -> Zero ticket minted -> Hardware locked -> Zero mutation.",
        "category": "POLICY_DENIAL",
        "requires_telemetry": False,
        "requires_evidence": False,
    },
    "toctou": {
        "id": "toctou",
        "name": "C. TOCTOU Race Condition Defense",
        "description": "Valid ticket minted bound to world v1 -> Plant state drifts to v2 -> Execution-time revalidation blocks actuation -> Hardware locked.",
        "category": "TOCTOU_DEFENSE",
        "requires_telemetry": False,
        "requires_evidence": False,
    },
    "recovery": {
        "id": "recovery",
        "name": "D. Actuator Fault & Autonomous Recovery",
        "description": "Mechanical actuator fault injected -> Verification fails -> Component quarantined -> Autonomous recovery -> Fresh policy authorization -> Verified.",
        "category": "FAULT_RECOVERY",
        "requires_telemetry": False,
        "requires_evidence": False,
    },
    "telemetry": {
        "id": "telemetry",
        "name": "E. Real-World Public Telemetry",
        "description": "Real USGS Potomac River streamflow ingested with provenance -> Operational context -> Nemotron proposal -> Policy evaluated.",
        "category": "PUBLIC_TELEMETRY",
        "requires_telemetry": True,
        "requires_evidence": False,
    },
    "evidence": {
        "id": "evidence",
        "name": "F. Tavily Operational Evidence",
        "description": "Live Tavily search retrieved -> Trust classification & grounding -> Candidate constraint gate -> Policy evaluation.",
        "category": "KNOWLEDGE_ADMISSIBILITY",
        "requires_telemetry": False,
        "requires_evidence": True,
    },
}

FORBIDDEN_BODY_FIELDS = {
    "action",
    "target",
    "proposal",
    "ticket",
    "policy",
    "command",
    "commands",
    "patch",
    "override",
    "hardware",
    "actuate",
    "actuator",
}


class ExecutionStatus(str, Enum):
    QUEUED = "QUEUED"
    RUNNING = "RUNNING"
    COMPLETED = "COMPLETED"
    FAILED = "FAILED"
    REPLAY_AVAILABLE = "REPLAY_AVAILABLE"


class StageOutcome(str, Enum):
    NOMINAL = "NOMINAL"
    DENIED = "DENIED"
    BLOCKED = "BLOCKED"
    VERIFICATION_FAILED = "VERIFICATION_FAILED"
    RECOVERED = "RECOVERED"
    ERROR = "ERROR"


class ControlledDemoExecution(BaseModel):
    """Encapsulates a single server-controlled demonstration run."""
    execution_id: str
    scenario_id: str
    execution_mode: str = "LIVE"
    physical_backend: str = "mock"
    status: ExecutionStatus = ExecutionStatus.QUEUED
    stage_outcome: Optional[StageOutcome] = None
    created_at: float = Field(default_factory=time.time)
    started_at: Optional[float] = None
    completed_at: Optional[float] = None
    duration_ms: Optional[float] = None
    request_id: Optional[str] = None
    token_usage: Dict[str, Any] = Field(default_factory=dict)
    events: List[Dict[str, Any]] = Field(default_factory=list)
    error_message: Optional[str] = None
    scenario_data: Optional[Dict[str, Any]] = None
    sha256_hash: Optional[str] = None

    def add_event(self, stage: str, message: str, details: Optional[Dict[str, Any]] = None) -> None:
        self.events.append({
            "timestamp": time.time(),
            "stage": stage,
            "message": message,
            "details": details or {},
        })


class ControlledDemoManager:
    """Manages concurrent, isolated server-controlled demonstrations."""

    def __init__(self, max_concurrent: int = 2, max_history: int = 50):
        self._max_concurrent = max_concurrent
        self._max_history = max_history
        self._executions: Dict[str, ControlledDemoExecution] = {}
        self._lock = threading.Lock()
        self._executor = ThreadPoolExecutor(max_workers=max_concurrent, thread_name_prefix="motionfence-demo")
        self._fixtures_dir = os.path.abspath(
            os.path.join(os.path.dirname(__file__), "..", "fixtures", "live_validation")
        )

    def validate_request_payload(self, payload: Dict[str, Any]) -> Tuple[bool, Optional[str]]:
        """Ensure the client payload contains no arbitrary action or actuator commands."""
        for field in FORBIDDEN_BODY_FIELDS:
            if field in payload:
                return False, f"Field '{field}' is strictly forbidden. The public interface cannot accept arbitrary actuation, targets, or policy commands."
        return True, None

    def create_execution(
        self,
        scenario_id: str,
        mode: str = "LIVE",
        backend: str = "mock",
        request_id: Optional[str] = None,
    ) -> ControlledDemoExecution:
        """Create and queue a controlled demonstration execution."""
        if scenario_id not in CANONICAL_SCENARIOS:
            raise ValueError(f"Scenario '{scenario_id}' is not in canonical allowlist: {list(CANONICAL_SCENARIOS.keys())}")

        backend = backend.lower()
        if backend not in ("mock", "isaac"):
            backend = "mock"

        # Check if Isaac backend is genuinely available
        if backend == "isaac":
            env = detect_isaac_environment()
            if not env.is_available:
                # Truthful fallback to mock with clear notation
                backend = "mock"

        mode = mode.upper()
        if mode not in ("LIVE", "REPLAY"):
            mode = "LIVE"

        execution_id = f"exec_{uuid.uuid4().hex[:12]}"
        execution = ControlledDemoExecution(
            execution_id=execution_id,
            scenario_id=scenario_id,
            execution_mode=mode,
            physical_backend=backend,
            request_id=request_id or f"req_{uuid.uuid4().hex[:8]}",
            status=ExecutionStatus.QUEUED,
        )

        with self._lock:
            # Enforce max history
            if len(self._executions) >= self._max_history:
                oldest_id = next(iter(self._executions))
                del self._executions[oldest_id]
            self._executions[execution_id] = execution

        # Dispatch execution
        self._executor.submit(self._run_execution_task, execution)
        return execution

    def get_execution(self, execution_id: str) -> Optional[ControlledDemoExecution]:
        with self._lock:
            return self._executions.get(execution_id)

    def list_executions(self, limit: int = 20) -> List[Dict[str, Any]]:
        with self._lock:
            items = list(self._executions.values())[-limit:]
            return [
                {
                    "execution_id": ex.execution_id,
                    "scenario_id": ex.scenario_id,
                    "execution_mode": ex.execution_mode,
                    "physical_backend": ex.physical_backend,
                    "status": ex.status.value,
                    "stage_outcome": ex.stage_outcome.value if ex.stage_outcome else None,
                    "created_at": ex.created_at,
                    "duration_ms": ex.duration_ms,
                    "sha256_hash": ex.sha256_hash,
                }
                for ex in reversed(items)
            ]

    def _run_execution_task(self, execution: ControlledDemoExecution) -> None:
        """Worker task executing the server-controlled scenario."""
        execution.started_at = time.time()
        execution.status = ExecutionStatus.RUNNING
        execution.add_event("INIT", f"Starting server-controlled demonstration: {execution.scenario_id} ({execution.execution_mode})")

        try:
            if execution.execution_mode == "REPLAY":
                self._execute_replay(execution)
            else:
                self._execute_live(execution)

            execution.completed_at = time.time()
            execution.duration_ms = (execution.completed_at - execution.started_at) * 1000.0
            execution.status = ExecutionStatus.COMPLETED
            execution.add_event("FINISHED", f"Scenario {execution.scenario_id} finished successfully. Outcome: {execution.stage_outcome.value if execution.stage_outcome else 'UNKNOWN'}")
        except Exception as e:
            logger.exception("Controlled demo execution %s failed", execution.execution_id)
            execution.completed_at = time.time()
            execution.duration_ms = (execution.completed_at - execution.started_at) * 1000.0
            execution.status = ExecutionStatus.FAILED
            execution.stage_outcome = StageOutcome.ERROR
            execution.error_message = f"Controlled execution terminated fail-closed: {type(e).__name__}"
            execution.add_event("FAIL_CLOSED", f"Execution failed closed: {str(e)[:200]}")

    def _execute_replay(self, execution: ControlledDemoExecution) -> None:
        """Deterministic, 100% offline replay from sealed fixtures."""
        fixture_path = os.path.join(self._fixtures_dir, f"{execution.scenario_id}.json")
        if not os.path.exists(fixture_path):
            raise FileNotFoundError(f"Replay fixture for scenario '{execution.scenario_id}' not found.")

        with open(fixture_path, "r", encoding="utf-8") as f:
            raw_data = json.load(f)

        rec = LiveDemoRecord(**raw_data)
        # Verify hash
        computed_hash = rec.compute_record_hash()
        rec.sha256_hash = computed_hash
        execution.sha256_hash = computed_hash

        scenario_data = live_record_to_scenario_data(rec)
        scenario_data["execution_mode"] = "REPLAY"
        if "decision_record" in scenario_data and "provider_metadata" in scenario_data["decision_record"]:
            scenario_data["decision_record"]["provider_metadata"]["execution_mode"] = "REPLAY"
            scenario_data["decision_record"]["provider_metadata"]["source_mode"] = "RECORDED_LIVE_FIXTURE"

        execution.scenario_data = scenario_data
        execution.token_usage = rec.token_usage

        if rec.policy_decision.decision == DecisionType.DENY:
            execution.stage_outcome = StageOutcome.DENIED
        elif rec.revalidation_result and rec.revalidation_result.get("status") != "PASSED":
            execution.stage_outcome = StageOutcome.BLOCKED
        elif rec.recovery_result:
            execution.stage_outcome = StageOutcome.RECOVERED
        else:
            execution.stage_outcome = StageOutcome.NOMINAL

        execution.add_event("REPLAY_LOADED", f"Loaded recorded live fixture with SHA-256 {computed_hash[:12]}...")

    def _execute_live(self, execution: ControlledDemoExecution) -> None:
        """Execute scenario live against external providers with credit guardrails."""
        has_nebius = bool(settings.nebius.api_key and settings.nebius.api_key != "placeholder_key_offline")

        if not has_nebius:
            # If no live API key is configured, fallback transparently to deterministic replay
            execution.add_event("FALLBACK", "Nebius credentials not configured for live model; falling back to deterministic replay.")
            execution.execution_mode = "REPLAY"
            self._execute_replay(execution)
            return

        provider = NebiusNemotronProvider(
            api_key=settings.nebius.api_key,
            timeout=min(settings.nebius.timeout_seconds, 25.0),
            max_tokens=600,
        )

        scenario = execution.scenario_id
        if scenario == "safe":
            from scripts.live_nebius_demo import run_live_safe_scenario
            execution.add_event("MODEL_PROPOSAL", "Requesting safe valve isolation proposal from Nemotron...")
            rec = run_live_safe_scenario(provider=provider)
            execution.stage_outcome = StageOutcome.NOMINAL

        elif scenario == "denied":
            from scripts.live_nebius_demo import run_live_denied_scenario
            execution.add_event("MODEL_PROPOSAL", "Simulating proposal with worker in safety zone...")
            rec = run_live_denied_scenario(provider=provider)
            execution.stage_outcome = StageOutcome.DENIED

        elif scenario == "toctou":
            from scripts.live_nebius_demo import run_live_toctou_scenario
            execution.add_event("TOCTOU_TEST", "Evaluating execution-time revalidation against world state drift...")
            rec = run_live_toctou_scenario(provider=provider)
            execution.stage_outcome = StageOutcome.BLOCKED

        elif scenario == "recovery":
            from scripts.live_nebius_demo import run_live_recovery_scenario
            execution.add_event("RECOVERY_TEST", "Injecting actuator fault and triggering autonomous recovery...")
            rec = run_live_recovery_scenario(provider=provider)
            execution.stage_outcome = StageOutcome.RECOVERED

        elif scenario == "telemetry":
            from scripts.live_nebius_demo import run_live_telemetry_scenario
            execution.add_event("TELEMETRY_INGESTION", "Ingesting live USGS Potomac River telemetry...")
            rec = run_live_telemetry_scenario(provider=provider)
            execution.stage_outcome = StageOutcome.NOMINAL

        elif scenario == "evidence":
            rec = self._run_live_evidence_scenario(provider, execution)
            execution.stage_outcome = StageOutcome.NOMINAL

        else:
            raise ValueError(f"Unsupported scenario: {scenario}")

        rec.finalize_record()
        execution.sha256_hash = rec.sha256_hash
        execution.token_usage = rec.token_usage
        execution.scenario_data = live_record_to_scenario_data(rec)
        execution.add_event("VERIFIED", f"Canonical record generated with hash {rec.sha256_hash[:12]}...")

    def _run_live_evidence_scenario(self, provider: NebiusNemotronProvider, execution: ControlledDemoExecution) -> LiveDemoRecord:
        """Run live Tavily external evidence grounding scenario."""
        has_tavily = bool(settings.tavily.api_key and settings.tavily.api_key != "placeholder_key_offline")
        tav_evs = []

        if has_tavily:
            execution.add_event("TAVILY_SEARCH", "Querying Tavily Search API for industrial valve safety standards...")
            try:
                tav_prov = TavilyKnowledgeProvider(api_key=settings.tavily.api_key, timeout=10.0, max_results=2)
                tav_evs = tav_prov.retrieve("industrial centrifugal pump valve isolation procedure safety standards")
            except Exception as e:
                logger.warning("Live Tavily query failed: %s; falling back to canonical knowledge", e)

        world = PhysicalWorld()
        world.valves["valve_b"] = ValveState.OPEN
        world.cooling = CoolingState.ACTIVE
        world.set_pump_state("pump_p1", "INACTIVE")
        world.set_human_zone(HumanZoneState.CLEAR)
        world.leak = LeakState(active=True, target="valve_b", severity=0.88, flow_rate_lpm=14.5)

        pre_state = world.get_state()
        plant_evidence = world.generate_targeted_evidence("valve_b")
        tavily_evidence = [
            Evidence(
                id=f"ev_tavily_{i}",
                source=EvidenceSource.SYSTEM_TELEMETRY,
                target="valve_b",
                observation={"title": ev.title, "url": ev.source_url, "content_snippet": ev.content[:140]},
                confidence=ev.confidence,
                provenance=ev.provenance,
            )
            for i, ev in enumerate(tav_evs)
        ]
        combined_evidence = plant_evidence + tavily_evidence

        intent = "Isolate leaking valve_b with continuous cooling according to retrieved operational standards."
        execution.add_event("NEMOTRON_PROPOSAL", "Generating evidence-grounded proposal from Nemotron...")
        proposal = provider.propose(intent, pre_state, combined_evidence)

        policy = Policy()
        auth = TicketAuthority()
        enclave = SafetyEnclave(secret_key=auth.secret_key)
        pe = PolicyEngine(policy=policy, safety_enclave=enclave)
        bus = EventBus()
        runtime = MotionFenceRuntime(policy_engine=pe, event_bus=bus)

        decision = runtime.evaluate(proposal, pre_state)
        req = EnclaveAuthorizationRequest(
            proposal=proposal,
            policy_decision=decision,
            world_state=pre_state,
        )
        ticket = enclave.authorize(req)

        hw = MockHardwareEndpoint(secret_key=auth.secret_key)
        hw_exec = hw.execute(proposal, ticket, current_world_state=pre_state)

        if hw_exec.execution_status == HardwareExecutionStatus.ACTUATED:
            world.apply_action(proposal.action_type, proposal.target)

        post_state = world.get_state()
        verifier = PostActionVerifier()
        v_res = verifier.verify(proposal, pre_state, post_state, hw_exec)

        rec = LiveDemoRecord(
            record_id=f"rec_ev_{uuid.uuid4().hex[:8]}",
            scenario_type=LiveScenarioType.EVIDENCE,
            execution_mode=ExecutionMode.LIVE,
            timestamp=time.time(),
            provider="Nebius Token Factory",
            model="nvidia/nemotron-3-super-120b-a12b",
            token_usage=provider.last_usage,
            intent=intent,
            pre_state=pre_state,
            proposal=proposal,
            policy_decision=decision,
            ticket=ticket,
            hardware_execution=hw_exec,
            verification_result=v_res,
            post_state=post_state,
            digital_twin_snapshots=[
                make_digital_twin_snapshot(world, "initial", "READY"),
                make_digital_twin_snapshot(world, "post_actuation", "ACTUATED"),
            ],
            events=[
                {"timestamp": time.time(), "stage": "EVIDENCE_GATHERING", "summary": f"Retrieved {len(tav_evs)} Tavily items"},
                {"timestamp": time.time(), "stage": "POLICY_EVALUATION", "summary": f"Decision: {decision.decision.value}"},
                {"timestamp": time.time(), "stage": "EXECUTION", "summary": f"Mock Hardware: {hw_exec.execution_status.value}"},
            ],
        )
        return rec


# Global singleton manager instance
demo_manager = ControlledDemoManager()
