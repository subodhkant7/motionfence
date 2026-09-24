"""Typed models and enumerations for adversarial physical environment testing."""

from enum import Enum
from typing import Any, Dict, List, Optional, Set
import time
import uuid
from pydantic import BaseModel, Field

from motionfence.models.actions import ActionProposal, ActionType, ExecutionResult
from motionfence.models.world import WorldState, ValveState, CoolingState, HumanZoneState
from motionfence.policy.models import DecisionType, PolicyDecision
from motionfence.runtime.verification import VerificationStatus, VerificationResult


class FaultCategory(str, Enum):
    """Broad categories of physical and informational faults."""
    HUMAN = "HUMAN"
    EQUIPMENT = "EQUIPMENT"
    SENSOR = "SENSOR"
    PERCEPTION = "PERCEPTION"
    KNOWLEDGE = "KNOWLEDGE"
    TIMING = "TIMING"
    ACTUATOR = "ACTUATOR"


class FaultType(str, Enum):
    """Specific typed fault types in the adversarial taxonomy."""
    # Human faults
    HUMAN_ENTERS_ZONE = "HUMAN_ENTERS_ZONE"
    HUMAN_LEAVES_ZONE = "HUMAN_LEAVES_ZONE"
    HUMAN_MOVEMENT_DURING_EXECUTION = "HUMAN_MOVEMENT_DURING_EXECUTION"

    # Equipment faults
    PUMP_STARTS_UNEXPECTEDLY = "PUMP_STARTS_UNEXPECTEDLY"
    PUMP_STOPS_UNEXPECTEDLY = "PUMP_STOPS_UNEXPECTEDLY"
    VALVE_JAM = "VALVE_JAM"
    VALVE_PARTIAL_MOVE = "VALVE_PARTIAL_MOVE"
    COOLING_DEGRADES = "COOLING_DEGRADES"

    # Sensor faults
    SENSOR_NOISE = "SENSOR_NOISE"
    SENSOR_STUCK = "SENSOR_STUCK"
    SENSOR_DROPOUT = "SENSOR_DROPOUT"
    SENSOR_BIAS = "SENSOR_BIAS"
    SENSOR_CONTRADICTION = "SENSOR_CONTRADICTION"

    # Perception faults
    TARGET_OCCLUDED = "TARGET_OCCLUDED"
    TARGET_AMBIGUITY_INCREASES = "TARGET_AMBIGUITY_INCREASES"
    OBJECT_APPEARANCE_CHANGE = "OBJECT_APPEARANCE_CHANGE"
    VIEWPOINT_LOSS = "VIEWPOINT_LOSS"

    # Knowledge faults
    KNOWLEDGE_STALE = "KNOWLEDGE_STALE"
    KNOWLEDGE_CONFLICT = "KNOWLEDGE_CONFLICT"
    SOURCE_DISAPPEARS = "SOURCE_DISAPPEARS"
    SOURCE_CONTENT_CHANGES = "SOURCE_CONTENT_CHANGES"

    # Timing faults
    STATE_CHANGE_AFTER_OBSERVATION = "STATE_CHANGE_AFTER_OBSERVATION"
    STATE_CHANGE_AFTER_POLICY = "STATE_CHANGE_AFTER_POLICY"
    STATE_CHANGE_AFTER_TICKET = "STATE_CHANGE_AFTER_TICKET"
    STATE_CHANGE_BEFORE_EXECUTION = "STATE_CHANGE_BEFORE_EXECUTION"

    # Actuator faults
    ACTUATOR_NO_OP = "ACTUATOR_NO_OP"
    ACTUATOR_PARTIAL = "ACTUATOR_PARTIAL"
    ACTUATOR_DELAY = "ACTUATOR_DELAY"
    ACTUATOR_WRONG_STATE = "ACTUATOR_WRONG_STATE"
    ACTUATOR_JAM = "ACTUATOR_JAM"


class FaultSeverity(str, Enum):
    """Categorical severity rating of injected physical/environmental disturbances."""
    LOW = "LOW"
    MEDIUM = "MEDIUM"
    HIGH = "HIGH"
    CRITICAL = "CRITICAL"


class FaultTiming(str, Enum):
    """Discrete lifecycle points where faults are scheduled to execute."""
    AFTER_OBSERVATION = "AFTER_OBSERVATION"          # t=0.5: between sensor sampling and proposal
    AFTER_PROPOSAL = "AFTER_PROPOSAL"                # t=1.5: between proposal and policy check
    AFTER_POLICY = "AFTER_POLICY"                    # t=2.5: between policy decision and enclave ticket
    AFTER_TICKET = "AFTER_TICKET"                    # t=3.5: immediately after ticket is issued
    BEFORE_EXECUTION = "BEFORE_EXECUTION"            # t=4.5: immediately before revalidation & execution (TOCTOU window)
    DURING_EXECUTION = "DURING_EXECUTION"            # t=5.0: while actuator is firing (solenoid jamming, partial move)
    AFTER_EXECUTION = "AFTER_EXECUTION"              # t=5.5: between actuator completion and verification
    DURING_EVIDENCE_ACQUISITION = "DURING_EVIDENCE_ACQUISITION"  # during active evidence gathering loop


class ScenarioOutcome(str, Enum):
    """Granular classification of adversarial scenario execution outcomes."""
    SAFE_ALLOW = "SAFE_ALLOW"                        # Action permitted under benign/safe conditions & verified
    SAFE_DENY = "SAFE_DENY"                          # Unsafe/inadmissible condition correctly blocked by policy
    SAFE_NEED_MORE_EVIDENCE = "SAFE_NEED_MORE_EVIDENCE"  # Insufficient or contradictory evidence properly deferred
    SAFE_REVALIDATION_BLOCK = "SAFE_REVALIDATION_BLOCK"  # State/policy drift during TOCTOU caught by revalidation gate
    EXECUTION_FAILURE = "EXECUTION_FAILURE"          # Actuator refused execution (missing/stale/corrupted ticket)
    VERIFICATION_FAILURE = "VERIFICATION_FAILURE"    # Actuator commanded, but physical state failed postconditions
    UNSAFE_ALLOW = "UNSAFE_ALLOW"                    # CRITICAL: Policy allowed action in an unsafe modeled state!
    UNEXPECTED_MUTATION = "UNEXPECTED_MUTATION"      # Physical state mutated without authorization
    BUDGET_EXHAUSTION = "BUDGET_EXHAUSTION"          # Active evidence loop halted safely after budget exhausted


class AdversarialFault(BaseModel):
    """Definition of an individual typed fault disturbance."""
    fault_id: str = Field(default_factory=lambda: f"flt_{uuid.uuid4().hex[:8]}")
    fault_type: FaultType
    category: FaultCategory
    severity: FaultSeverity = FaultSeverity.MEDIUM
    timing: FaultTiming = FaultTiming.BEFORE_EXECUTION
    target: str = Field(default="", description="Target equipment, sensor, or subsystem.")
    parameters: Dict[str, Any] = Field(default_factory=dict, description="Fault-specific tuning values.")
    description: str = Field(default="", description="Human-readable explanation of disturbance.")


class ScheduledFault(BaseModel):
    """A fault bound to a deterministic execution schedule within a scenario."""
    schedule_id: str = Field(default_factory=lambda: f"sch_{uuid.uuid4().hex[:8]}")
    fault: AdversarialFault
    timing: FaultTiming
    step_offset: int = 0
    executed: bool = False
    execution_timestamp: Optional[float] = None
    applied_mutation: Optional[str] = None


class AdversarialScenario(BaseModel):
    """Complete specification of an adversarial physical environment scenario."""
    scenario_id: str
    description: str
    initial_world_state: Optional[Dict[str, Any]] = None
    initial_evidence: List[Dict[str, Any]] = Field(default_factory=list)
    initial_knowledge: List[Dict[str, Any]] = Field(default_factory=list)
    initial_policy_modifications: Dict[str, Any] = Field(default_factory=dict)
    fault_schedule: List[ScheduledFault] = Field(default_factory=list)
    seed: int = 42
    expected_safety_properties: List[str] = Field(default_factory=list)
    expected_outcome: Optional[ScenarioOutcome] = None
    tags: List[str] = Field(default_factory=list)
    created_at: float = Field(default_factory=time.time)


class ScenarioExecutionResult(BaseModel):
    """Detailed result of running an adversarial scenario through MotionFence."""
    scenario_id: str
    outcome: ScenarioOutcome
    baseline_decision: Optional[DecisionType] = None
    adversarial_decision: Optional[DecisionType] = None
    revalidation_status: Optional[str] = None
    execution_success: Optional[bool] = None
    verification_status: Optional[VerificationStatus] = None
    faults_scheduled: int = 0
    faults_applied: List[str] = Field(default_factory=list)
    unsafe_allow: bool = False
    false_denial: bool = False
    counterexample_id: Optional[str] = None
    message: str = ""
    duration_seconds: float = 0.0
    pre_state_version: int = 1
    post_state_version: int = 1
    timestamp: float = Field(default_factory=time.time)


class AdversarialCounterexample(BaseModel):
    """Reproducible machine-readable counterexample of an invariant or safety failure."""
    counterexample_id: str = Field(default_factory=lambda: f"cx_{uuid.uuid4().hex[:10]}")
    scenario_id: str
    faults: List[str] = Field(default_factory=list)
    decision: Optional[str] = None
    expected: Optional[str] = None
    unsafe: bool = False
    seed: int = 42
    generator_version: str = "0.7.0"
    runtime_version: str = "0.7.0"
    policy_version: str = "2026.1"
    details: Dict[str, Any] = Field(default_factory=dict)
    shrunk: bool = False
    minimal_fault_count: int = 0
    created_at: float = Field(default_factory=time.time)


class AdversarialEvaluationReport(BaseModel):
    """Aggregate evaluation report across an adversarial corpus or fuzzing run."""
    report_id: str = Field(default_factory=lambda: f"adv_rep_{uuid.uuid4().hex[:8]}")
    run_timestamp: float = Field(default_factory=time.time)
    seed: int = 42
    total_scenarios: int = 0
    safe_allows: int = 0
    safe_denials: int = 0
    safe_need_more_evidence: int = 0
    revalidation_blocks: int = 0
    verification_failures: int = 0
    unsafe_allows: int = 0
    false_denials: int = 0
    evidence_budget_exhaustions: int = 0
    unexpected_mutations: int = 0
    counterexamples: List[AdversarialCounterexample] = Field(default_factory=list)
    minimal_counterexamples: List[AdversarialCounterexample] = Field(default_factory=list)
    coverage_by_fault_type: Dict[str, int] = Field(default_factory=dict)
    coverage_by_fault_timing: Dict[str, int] = Field(default_factory=dict)
    execution_time_seconds: float = 0.0
