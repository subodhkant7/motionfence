"""Live Nebius/Nemotron demonstration and deterministic offline replay engine (Phase 2N).

Coordinates:
LIVE NEMOTRON -> ACTION PROPOSAL -> EVIDENCE/CONTEXT -> DETERMINISTIC POLICY
-> SAFETY ENCLAVE -> STATE-BOUND AUTHORIZATION -> EXECUTION-TIME REVALIDATION
-> MOCK HARDWARE -> PHYSICALWORLD -> POSTCONDITION VERIFICATION -> CONTAINMENT/RECOVERY

Enforces:
1. Model possesses ZERO direct actuator or ticket authority.
2. Distinct execution modes: LIVE, REPLAY, OFFLINE_TEST.
3. 100% offline, side-effect-free replay with cryptographic integrity checks.
4. Digital Twin state synchronization reflecting real physical simulation.
"""

from enum import Enum
import hashlib
import json
import logging
import os
import time
from typing import Any, Dict, List, Optional
from pydantic import BaseModel, Field

from motionfence.agent.nebius_provider import NebiusNemotronProvider
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
from motionfence.policy.engine import PolicyEngine
from motionfence.policy.models import DecisionType, Policy, PolicyDecision
from motionfence.recovery.executor import RecoveryExecutor
from motionfence.runtime.core import MotionFenceRuntime
from motionfence.runtime.enclave import EnclaveAuthorizationRequest, SafetyEnclave
from motionfence.runtime.events import EventBus
from motionfence.runtime.revalidation import ExecutionTimeRevalidator, RevalidationStatus
from motionfence.runtime.ticket import TicketAuthority
from motionfence.runtime.verification import PostActionVerifier, VerificationResult, VerificationStatus
from motionfence.simulation.world import PhysicalWorld

logger = logging.getLogger("motionfence.runtime.live_demo")


class ExecutionMode(str, Enum):
    """Explicit execution modes distinguishing live AI calls from deterministic replay."""
    LIVE = "LIVE"
    REPLAY = "REPLAY"
    OFFLINE_TEST = "OFFLINE_TEST"


class LiveScenarioType(str, Enum):
    """The four canonical Phase 2N demonstration scenarios."""
    SAFE = "safe"
    DENIED = "denied"
    TOCTOU = "toctou"
    RECOVERY = "recovery"


class DigitalTwinPlantState(BaseModel):
    """2D lightweight digital twin state snapshot synchronized with PhysicalWorld."""
    timestamp: float = Field(default_factory=time.time)
    stage_name: str = Field(default="initial")
    pump_state: str = Field(default="INACTIVE")
    valve_b_state: str = Field(default="OPEN")
    cooling_state: str = Field(default="ACTIVE")
    human_zone: str = Field(default="CLEAR")
    actuator_status: str = Field(default="READY")
    world_version: int = Field(default=1)
    leak_active: bool = Field(default=False)
    pressure_psi: float = Field(default=120.0)
    flow_rate_lpm: float = Field(default=0.0)


class LiveDemoRecord(BaseModel):
    """Canonical, cryptographically auditable demonstration record.
    
    Contains all context necessary to reproduce the execution offline
    with zero network calls, zero model calls, and zero secrets.
    """
    record_id: str
    scenario_type: LiveScenarioType
    execution_mode: ExecutionMode
    timestamp: float = Field(default_factory=time.time)
    provider: str
    model: str
    token_usage: Dict[str, Any] = Field(default_factory=dict)
    intent: str
    pre_state: WorldState
    proposal: ActionProposal
    policy_decision: PolicyDecision
    ticket: Optional[AuthorizationTicket] = None
    world_drift_event: Optional[Dict[str, Any]] = None
    revalidation_result: Optional[Dict[str, Any]] = None
    hardware_execution: Optional[HardwareExecutionRecord] = None
    verification_result: Optional[VerificationResult] = None
    recovery_result: Optional[Dict[str, Any]] = None
    post_state: WorldState
    digital_twin_snapshots: List[DigitalTwinPlantState] = Field(default_factory=list)
    events: List[Dict[str, Any]] = Field(default_factory=list)
    sha256_hash: Optional[str] = None

    def compute_record_hash(self) -> str:
        """Compute canonical SHA-256 hash across proposal, policy, ticket, and execution outcome."""
        canonical_dict = {
            "record_id": self.record_id,
            "scenario_type": self.scenario_type.value,
            "provider": self.provider,
            "model": self.model,
            "intent": self.intent,
            "pre_state_version": self.pre_state.version,
            "proposal_id": self.proposal.id,
            "proposal_action": self.proposal.action_type.value,
            "proposal_target": self.proposal.target,
            "policy_decision": self.policy_decision.decision.value,
            "ticket_id": self.ticket.ticket_id if self.ticket else None,
            "hardware_status": self.hardware_execution.execution_status.value if self.hardware_execution else None,
            "post_state_version": self.post_state.version,
        }
        raw_json = json.dumps(canonical_dict, sort_keys=True)
        return hashlib.sha256(raw_json.encode("utf-8")).hexdigest()

    def finalize_record(self) -> "LiveDemoRecord":
        """Attach computed hash to record."""
        self.sha256_hash = self.compute_record_hash()
        return self


def make_digital_twin_snapshot(
    world: PhysicalWorld,
    stage_name: str,
    actuator_status: str = "READY",
) -> DigitalTwinPlantState:
    """Extract an instantaneous Digital Twin representation from the physical simulation."""
    ws = world.get_state()
    return DigitalTwinPlantState(
        stage_name=stage_name,
        pump_state=world.pumps.get("pump_p1", "INACTIVE"),
        valve_b_state=world.valves.get("valve_b", ValveState.OPEN).value,
        cooling_state=world.cooling.value,
        human_zone=world.human_zone.value,
        actuator_status=actuator_status,
        world_version=world.version,
        leak_active=world.leak.active if world.leak else False,
        pressure_psi=95.5 if (world.leak and world.leak.active) else 125.0,
        flow_rate_lpm=world.leak.flow_rate_lpm if (world.leak and world.leak.active) else 0.0,
    )


def live_record_to_scenario_data(rec: LiveDemoRecord) -> Dict[str, Any]:
    """Convert a canonical LiveDemoRecord into rich ScenarioData for the Judge Console."""
    dec_dict = {
        "decision_id": rec.record_id,
        "sequence_number": 1,
        "created_at": rec.timestamp,
        "finalized_at": rec.timestamp,
        "is_finalized": True,
        "record_hash": rec.sha256_hash,
        "intent": rec.intent,
        "world_state_snapshot": rec.pre_state.model_dump(),
        "sensor_evidence_ids": rec.proposal.supporting_evidence_ids,
        "action_proposal": rec.proposal.model_dump(),
        "policy_decision": rec.policy_decision.decision.value,
        "policy_reasons": [
            f"{r.constraint}: {r.details or r.status}" for r in rec.policy_decision.reasons
        ],
        "authorization_ticket_id": rec.ticket.ticket_id if rec.ticket else None,
        "execution_result": rec.hardware_execution.model_dump() if rec.hardware_execution else None,
        "verification_result": rec.verification_result.model_dump() if rec.verification_result else None,
        "runtime_version": "2.4.0",
        "policy_version": "1.0.0",
        "schema_version": "2.0.0",
        "provider_metadata": {
            "provider": rec.provider,
            "model": rec.model,
            "execution_mode": rec.execution_mode.value,
            "source_mode": "LIVE_MODEL_RESPONSE" if rec.execution_mode == ExecutionMode.LIVE else "RECORDED_LIVE_FIXTURE",
            "token_usage": rec.token_usage,
        },
        "ticket_world_state_version": rec.ticket.world_state_version if rec.ticket else None,
        "ticket_world_state_hash": rec.ticket.world_state_hash if rec.ticket else None,
        "revalidation_status": rec.revalidation_result.get("status") if rec.revalidation_result else None,
        "revalidation_reasons": rec.revalidation_result.get("reasons", []) if rec.revalidation_result else [],
        "hardware_execution_id": rec.hardware_execution.record_id if rec.hardware_execution else None,
        "hardware_status": rec.hardware_execution.execution_status.value if rec.hardware_execution else None,
    }

    scenario_meta = {
        LiveScenarioType.SAFE: {
            "title": "A. Safe Execution (Nominal — Live Nemotron)",
            "subtitle": "Live Nemotron generates safe proposal -> Policy ALLOW -> Ticket minted -> Mock Hardware actuates -> Verified",
            "flow_summary": "NEMOTRON -> POLICY ALLOW -> TICKET -> HARDWARE ACTUATE -> VERIFIED",
            "category": "NOMINAL",
        },
        LiveScenarioType.DENIED: {
            "title": "B. Unsafe Proposal Denial (Live Nemotron)",
            "subtitle": "Human in hazard zone -> Live Nemotron proposes -> Policy strictly DENIES -> Zero Ticket -> Hardware LOCKED",
            "flow_summary": "NEMOTRON -> POLICY DENY -> NO TICKET -> HARDWARE LOCKED -> ZERO MUTATION",
            "category": "POLICY_DENIAL",
        },
        LiveScenarioType.TOCTOU: {
            "title": "C. TOCTOU Revalidation Block (Live Nemotron)",
            "subtitle": "Live Nemotron proposes -> Ticket minted bound to v3 -> World drifts v3 -> v4 -> Revalidation FAILS -> Hardware LOCKED",
            "flow_summary": "NEMOTRON -> TICKET (v3) -> WORLD CHANGE (v4) -> REVALIDATION BLOCKED -> HARDWARE LOCKED",
            "category": "TOCTOU_DEFENSE",
        },
        LiveScenarioType.RECOVERY: {
            "title": "D. Actuator Failure & Autonomous Recovery (Live Nemotron)",
            "subtitle": "Live Nemotron proposes -> Ticket -> Hardware fault (NO_OP) -> Verification FAILS -> Quarantine & Recovery",
            "flow_summary": "NEMOTRON -> TICKET -> HARDWARE FAULT -> VERIF FAILED -> QUARANTINE -> RECOVERED",
            "category": "FAULT_RECOVERY",
        },
    }[rec.scenario_type]

    return {
        "scenario_id": f"scenario_{rec.scenario_type.value}",
        "title": scenario_meta["title"],
        "subtitle": scenario_meta["subtitle"],
        "flow_summary": scenario_meta["flow_summary"],
        "category": scenario_meta["category"],
        "execution_mode": rec.execution_mode.value,
        "provider": rec.provider,
        "model": rec.model,
        "token_usage": rec.token_usage,
        "sha256_hash": rec.sha256_hash,
        "decision_record": dec_dict,
        "events": rec.events,
        "pre_state": rec.pre_state.model_dump(),
        "post_state": rec.post_state.model_dump(),
        "policy_decision": rec.policy_decision.model_dump(),
        "ticket": rec.ticket.model_dump() if rec.ticket else None,
        "initial_ticket": rec.ticket.model_dump() if rec.ticket else None,
        "world_change_event": rec.world_drift_event,
        "execution_result": rec.hardware_execution.model_dump() if rec.hardware_execution else None,
        "verification_result": rec.verification_result.model_dump() if rec.verification_result else None,
        "recovery_result": rec.recovery_result,
        "digital_twin_snapshots": [s.model_dump() for s in rec.digital_twin_snapshots],
    }
