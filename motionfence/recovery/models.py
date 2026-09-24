"""Structured domain models for failure classification, component quarantine, and autonomous recovery."""

from enum import Enum
from typing import Any, Dict, List, Optional
import time
import uuid
from pydantic import BaseModel, Field

from motionfence.models.actions import ActionProposal, ActionType, AuthorizationTicket, ExecutionResult
from motionfence.policy.models import PolicyDecision
from motionfence.runtime.verification import VerificationResult
from motionfence.evidence.models import Evidence


class FailureClass(str, Enum):
    """Deterministic failure taxonomy for physical actions, sensors, and environmental state."""
    ACTUATOR_NO_OP = "ACTUATOR_NO_OP"                # Command acknowledged but physical state unchanged
    ACTUATOR_PARTIAL = "ACTUATOR_PARTIAL"            # Mechanical motion stalled mid-stroke (e.g. TRANSITIONING)
    ACTUATOR_DELAY = "ACTUATOR_DELAY"                # Motion lagged beyond latency deadline
    ACTUATOR_WRONG_STATE = "ACTUATOR_WRONG_STATE"    # Physical actuator seated into incorrect/opposite state
    SENSOR_FAILURE = "SENSOR_FAILURE"                # Hardware dropout, flatline, or stuck transducer
    SENSOR_STALE = "SENSOR_STALE"                    # Telemetry expired beyond freshness window
    SENSOR_CONTRADICTION = "SENSOR_CONTRADICTION"    # Divergent readings across independent channels
    KNOWLEDGE_FAILURE = "KNOWLEDGE_FAILURE"          # Guidance conflict or expired safety manual
    POLICY_FAILURE = "POLICY_FAILURE"                # Policy engine evaluated unexpected violation
    VERIFICATION_FAILURE = "VERIFICATION_FAILURE"    # Generic postcondition invariant mismatch
    ENVIRONMENT_DRIFT = "ENVIRONMENT_DRIFT"          # Physical world mutated between check and execution (TOCTOU)
    UNKNOWN_FAILURE = "UNKNOWN_FAILURE"              # Unrecognized disturbance


class ComponentType(str, Enum):
    """Classification of monitored plant components."""
    ACTUATOR = "actuator"
    SENSOR = "sensor"
    KNOWLEDGE_SOURCE = "knowledge_source"
    ZONE = "zone"
    CONTROLLER = "controller"


class QuarantineStatus(str, Enum):
    """Deterministic component health and quarantine status."""
    HEALTHY = "HEALTHY"                              # Component operating nominally
    SUSPECT = "SUSPECT"                              # Initial failure detected; monitored and restricted
    RECOVERY_REQUIRED = "RECOVERY_REQUIRED"          # Multiple failures; requires active diagnostic verification
    QUARANTINED = "QUARANTINED"                      # Consequential capabilities disabled; isolated
    RECERTIFICATION_REQUIRED = "RECERTIFICATION_REQUIRED"  # Requires formal evidence recertification


class RecoveryStrategy(str, Enum):
    """Catalog of autonomous recovery and mitigation strategies."""
    GATHER_ALTERNATE_EVIDENCE = "GATHER_ALTERNATE_EVIDENCE"
    RESAMPLE_SENSOR = "RESAMPLE_SENSOR"
    INSPECT_TARGET = "INSPECT_TARGET"
    WAIT_FOR_STABILITY = "WAIT_FOR_STABILITY"
    TRY_ALTERNATE_ALLOWED_PATH = "TRY_ALTERNATE_ALLOWED_PATH"
    ABORT_AND_QUARANTINE = "ABORT_AND_QUARANTINE"


class RiskLevel(str, Enum):
    """Risk assessment for proposed recovery plans."""
    LOW = "LOW"
    MEDIUM = "MEDIUM"
    HIGH = "HIGH"
    CRITICAL = "CRITICAL"


class RecoveryOutcome(str, Enum):
    """Terminal outcome of an autonomous recovery cycle."""
    SUCCESS = "SUCCESS"                    # Failure contained, alternative/fresh authorization verified
    PARTIAL = "PARTIAL"                    # Intermediate progress, further cycles needed
    FAILED = "FAILED"                      # Recovery failed, system held in safe refusal
    BUDGET_EXHAUSTED = "BUDGET_EXHAUSTED"  # Max recovery attempts reached, component quarantined
    QUARANTINED = "QUARANTINED"            # Component permanently quarantined for human inspection


class FailureRecord(BaseModel):
    """Deterministic record of an observed physical or perceptual failure."""
    failure_id: str = Field(default_factory=lambda: f"fail_{uuid.uuid4().hex[:10]}")
    failure_class: FailureClass = Field(..., description="Taxonomic classification of the failure.")
    target_component: str = Field(..., description="Identifier of the failing component or actuator.")
    component_type: ComponentType = Field(..., description="Class of the failing component.")
    timestamp: float = Field(default_factory=time.time)
    details: str = Field(default="", description="Human-readable explanation of failure signature.")
    evidence_ids: List[str] = Field(default_factory=list, description="IDs of evidence demonstrating the failure.")
    proposal_id: Optional[str] = Field(default=None, description="ActionProposal ID that failed, if applicable.")
    ticket_id: Optional[str] = Field(default=None, description="AuthorizationTicket ID, if applicable.")
    execution_result: Optional[ExecutionResult] = Field(default=None)
    verification_result: Optional[VerificationResult] = Field(default=None)
    revalidation_status: Optional[str] = Field(default=None)


class QuarantineRecord(BaseModel):
    """Audit record and operational state of a quarantined plant component."""
    record_id: str = Field(default_factory=lambda: f"qr_{uuid.uuid4().hex[:10]}")
    component_id: str = Field(..., description="Target component identifier.")
    component_type: ComponentType = Field(..., description="Category of component.")
    status: QuarantineStatus = Field(default=QuarantineStatus.HEALTHY)
    reason: str = Field(default="", description="Justification for quarantine status.")
    evidence: List[str] = Field(default_factory=list, description="Supporting evidence references.")
    failure_count: int = Field(default=0, ge=0, description="Total lifetime observed failures.")
    consecutive_failures: int = Field(default=0, ge=0, description="Consecutive failure streak.")
    first_failure_at: Optional[float] = None
    last_failure_at: Optional[float] = None
    quarantined_at: Optional[float] = None
    affected_capabilities: List[str] = Field(default_factory=list, description="Blocked action types/capabilities.")
    remaining_capabilities: List[str] = Field(default_factory=list, description="Allowed safe action types.")
    created_at: float = Field(default_factory=time.time)
    updated_at: float = Field(default_factory=time.time)

    @property
    def is_quarantined(self) -> bool:
        return self.status == QuarantineStatus.QUARANTINED

    @property
    def is_suspect(self) -> bool:
        return self.status in (QuarantineStatus.SUSPECT, QuarantineStatus.RECOVERY_REQUIRED)


class RecoveryStep(BaseModel):
    """A bounded, non-consequential step within a recovery plan."""
    step_id: str = Field(default_factory=lambda: f"rstep_{uuid.uuid4().hex[:8]}")
    action_type: ActionType = Field(..., description="Informational action type.")
    target: str = Field(..., description="Target sensor, camera, or instrument.")
    parameters: Dict[str, Any] = Field(default_factory=dict)
    description: str = Field(default="")
    expected_gain: str = Field(default="MEDIUM")
    is_consequential: bool = Field(default=False, description="Must strictly remain False in recovery plans.")


class RecoveryPlan(BaseModel):
    """Structured, machine-readable recovery procedure generated autonomously."""
    plan_id: str = Field(default_factory=lambda: f"rplan_{uuid.uuid4().hex[:10]}")
    failure_id: str = Field(..., description="Associated FailureRecord ID.")
    strategy: RecoveryStrategy = Field(..., description="High-level recovery strategy.")
    steps: List[RecoveryStep] = Field(default_factory=list, description="Ordered diagnostic/informational steps.")
    required_evidence: List[str] = Field(default_factory=list, description="Expected empirical evidence outputs.")
    expected_information_gain: float = Field(default=0.5, ge=0.0, le=1.0)
    risk_level: RiskLevel = Field(default=RiskLevel.LOW)
    rationale: str = Field(default="")
    suggested_alternate_proposal: Optional[ActionProposal] = Field(
        default=None,
        description="Optional alternate consequential action (e.g. Valve A) requiring completely fresh authorization.",
    )
    created_at: float = Field(default_factory=time.time)


class ContainmentActionReport(BaseModel):
    """Audit report generated immediately when containment policies trigger."""
    containment_id: str = Field(default_factory=lambda: f"cont_{uuid.uuid4().hex[:10]}")
    failure_id: str
    target_component: str
    ticket_invalidated: bool = False
    invalidated_ticket_id: Optional[str] = None
    component_status: QuarantineStatus
    frozen_actions: List[str] = Field(default_factory=list)
    allowed_actions: List[str] = Field(default_factory=list)
    timestamp: float = Field(default_factory=time.time)
    message: str = ""


class RecoveryExecutionResult(BaseModel):
    """Complete audit record of an autonomous recovery lifecycle run."""
    run_id: str = Field(default_factory=lambda: f"rec_{uuid.uuid4().hex[:10]}")
    failure_record: FailureRecord
    recovery_plan: RecoveryPlan
    outcome: RecoveryOutcome
    iterations_used: int = 0
    max_iterations_allowed: int = 3
    executed_steps: List[Dict[str, Any]] = Field(default_factory=list)
    new_evidence_gathered: List[Evidence] = Field(default_factory=list)
    quarantine_records: Dict[str, QuarantineRecord] = Field(default_factory=dict)
    fresh_authorization_required: bool = True
    fresh_policy_decision: Optional[PolicyDecision] = None
    fresh_ticket: Optional[AuthorizationTicket] = None
    retry_execution_result: Optional[ExecutionResult] = None
    retry_verification_result: Optional[VerificationResult] = None
    unsafe_retries: int = 0
    duration_seconds: float = 0.0
    message: str = ""
