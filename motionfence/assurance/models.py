"""Domain models for bounded assurance, formal verification, and adversarial evaluation."""

from enum import Enum
from typing import Any, Dict, List, Optional
import time
import uuid
from pydantic import BaseModel, Field

from motionfence.models.world import WorldState, ValveState, CoolingState, HumanZoneState, LeakState


class FindingStatus(str, Enum):
    """Evaluation status of an assurance property."""
    SATISFIED = "SATISFIED"
    VIOLATED = "VIOLATED"
    UNKNOWN = "UNKNOWN"
    NOT_APPLICABLE = "NOT_APPLICABLE"


class FindingSeverity(str, Enum):
    """Severity classification for assurance findings."""
    INFO = "INFO"
    LOW = "LOW"
    MEDIUM = "MEDIUM"
    HIGH = "HIGH"
    CRITICAL = "CRITICAL"


class AssuranceScope(str, Enum):
    """Categorical scope of the property check."""
    STATIC_INVARIANT = "STATIC_INVARIANT"
    BOUNDED_TRANSITION = "BOUNDED_TRANSITION"
    TEMPORAL_SAFETY = "TEMPORAL_SAFETY"
    ADVERSARIAL_EVAL = "ADVERSARIAL_EVAL"


class AssuranceFinding(BaseModel):
    """Machine-checkable evidence result for an assurance check."""
    finding_id: str = Field(default_factory=lambda: f"fnd_{uuid.uuid4().hex[:10]}")
    property_id: str
    property_name: str
    status: FindingStatus
    severity: FindingSeverity
    scope: str
    observed_state: Optional[Dict[str, Any]] = None
    counterexample: Optional[Dict[str, Any]] = None
    explanation: str
    created_at: float = Field(default_factory=time.time)


class FormalState(BaseModel):
    """Smallest bounded formal representation of the physical plant state."""
    valves: Dict[str, str] = Field(default_factory=lambda: {"valve_a": "OPEN", "valve_b": "OPEN"})
    pumps: Dict[str, str] = Field(default_factory=lambda: {"pump_p1": "INACTIVE"})
    cooling: str = "ACTIVE"
    human_zone: str = "CLEAR"
    leak_active: bool = False
    leak_target: Optional[str] = None
    leak_severity: float = 0.0

    @classmethod
    def from_world_state(cls, world: WorldState) -> "FormalState":
        """Deterministic conversion from runtime WorldState to bounded FormalState."""
        return cls(
            valves={k: v.value for k, v in world.valves.items()},
            pumps=dict(world.pumps),
            cooling=world.cooling.value,
            human_zone=world.human_zone.value,
            leak_active=world.leak.active,
            leak_target=world.leak.target,
            leak_severity=world.leak.severity,
        )

    def to_world_state(self, version: int = 1, timestamp: float = 0.0) -> WorldState:
        """Deterministic conversion from FormalState to WorldState snapshot."""
        valves_enum = {k: ValveState(v) for k, v in self.valves.items()}
        cooling_enum = CoolingState(self.cooling)
        human_enum = HumanZoneState(self.human_zone)
        leak_model = LeakState(
            active=self.leak_active,
            target=self.leak_target,
            severity=self.leak_severity,
        )
        return WorldState(
            valves=valves_enum,
            cooling=cooling_enum,
            leak=leak_model,
            human_zone=human_enum,
            pumps=dict(self.pumps),
            observations={},
            version=version,
            timestamp=timestamp if timestamp > 0.0 else time.time(),
        )


class AdversarialOutcomeCategory(str, Enum):
    """Categorical classification of adversarial evaluation outcomes."""
    SAFE_ALLOW = "SAFE_ALLOW"
    SAFE_DENY = "SAFE_DENY"
    SAFE_NEED_MORE_EVIDENCE = "SAFE_NEED_MORE_EVIDENCE"
    FALSE_ALLOW = "FALSE_ALLOW"                # Critical safety hazard
    FALSE_DENY = "FALSE_DENY"                  # Operational over-conservatism
    EXECUTION_FAILURE = "EXECUTION_FAILURE"
    VERIFICATION_FAILURE = "VERIFICATION_FAILURE"


class AdversarialCaseResult(BaseModel):
    """Audit record for a single adversarial evaluation instance."""
    case_id: str = Field(default_factory=lambda: f"adv_{uuid.uuid4().hex[:10]}")
    category: AdversarialOutcomeCategory
    is_safe: bool
    input_parameters: Dict[str, Any]
    observed_verdict: str
    reasons: List[str]
    notes: Optional[str] = None
    minimized: bool = False


class AssuranceReport(BaseModel):
    """Aggregated machine-readable report summarizing assurance and adversarial evaluations."""
    report_id: str = Field(default_factory=lambda: f"rep_{uuid.uuid4().hex[:10]}")
    created_at: float = Field(default_factory=time.time)
    runtime_version: str = "0.4.0"
    policy_version: str = "2026.1"
    generator_version: str = "1.0.0"
    seed: Optional[int] = None
    properties_checked: int = 0
    properties_satisfied: int = 0
    properties_violated: int = 0
    unknown_properties: int = 0
    findings: List[AssuranceFinding] = Field(default_factory=list)
    counterexamples: List[Dict[str, Any]] = Field(default_factory=list)
    adversarial_cases: int = 0
    unsafe_authorizations_discovered: int = 0
    adversarial_outcomes: Dict[str, int] = Field(default_factory=dict)
    execution_time_seconds: float = 0.0

    def summary_text(self) -> str:
        """Concise, transparent human-readable summary without inflated claims."""
        lines = [
            "======================================================================",
            " MOTIONFENCE BOUNDED ASSURANCE & ADVERSARIAL EVALUATION REPORT",
            "======================================================================",
            f"Report ID:        {self.report_id}",
            f"Runtime Version:  {self.runtime_version} | Policy Version: {self.policy_version}",
            f"Execution Time:   {self.execution_time_seconds:.3f}s | Seed: {self.seed}",
            "----------------------------------------------------------------------",
            "BOUNDED PROPERTIES CHECKED (Z3 SMT Solver & Static Evaluators):",
            f"  Total Checked:    {self.properties_checked}",
            f"  Satisfied:        {self.properties_satisfied}",
            f"  Violated:         {self.properties_violated}",
            f"  Unknown:          {self.unknown_properties}",
            "----------------------------------------------------------------------",
            "ADVERSARIAL EVALUATION (Property-Based Fuzzing & Boundary Search):",
            f"  Cases Generated:  {self.adversarial_cases}",
            f"  Unsafe ALLOWs:    {self.unsafe_authorizations_discovered}",
            f"  Outcome Breakdown:{self.adversarial_outcomes}",
            "----------------------------------------------------------------------",
            "ASSURANCE BOUNDARY NOTE:",
            "  * BOUNDED PROPERTY SATISFIED ≠ REAL-WORLD SAFETY PROVEN.",
            "  * Results apply strictly to the modeled state variables, bounded",
            "    transitions, and deterministic policy specifications.",
            "======================================================================",
        ]
        return "\n".join(lines)
