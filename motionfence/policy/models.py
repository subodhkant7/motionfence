"""Policy definition and deterministic decision evaluation models."""

from enum import Enum
from typing import Any, Dict, List, Optional
import time
from pydantic import BaseModel, Field

from motionfence.models.actions import ActionType
from motionfence.evidence.models import EvidenceSource, ContradictionSeverity


class DecisionType(str, Enum):
    """The triad of deterministic policy authorization verdicts."""
    ALLOW = "ALLOW"
    DENY = "DENY"
    NEED_MORE_EVIDENCE = "NEED_MORE_EVIDENCE"


class PolicyReason(BaseModel):
    """Structured, machine-readable explanation for an evaluated constraint."""
    constraint: str = Field(..., description="Name of the evaluated policy constraint.")
    observed: Any = Field(..., description="Observed parameter, measurement, or state value.")
    required: Any = Field(..., description="Required threshold or invariant condition.")
    status: str = Field(..., description="Evaluation outcome: 'passed', 'failed', or 'requires_evidence'.")
    details: str = Field(default="", description="Human-readable context.")


class PolicyDecision(BaseModel):
    """Immutable verdict produced exclusively by the deterministic Policy Engine."""
    decision: DecisionType = Field(..., description="Authorization verdict (ALLOW / DENY / NEED_MORE_EVIDENCE).")
    proposal_id: str = Field(..., description="ID of the evaluated action proposal.")
    target: str = Field(..., description="Target entity or actuator.")
    reasons: List[PolicyReason] = Field(
        default_factory=list,
        description="Structured rationale for each evaluated constraint."
    )
    contradiction_severity: ContradictionSeverity = Field(
        default=ContradictionSeverity.NONE,
        description="Observed contradiction severity level during evaluation."
    )
    timestamp: float = Field(default_factory=time.time)

    @property
    def is_allowed(self) -> bool:
        return self.decision == DecisionType.ALLOW

    @property
    def is_denied(self) -> bool:
        return self.decision == DecisionType.DENY

    @property
    def needs_evidence(self) -> bool:
        return self.decision == DecisionType.NEED_MORE_EVIDENCE


class Policy(BaseModel):
    """Declarative safety policy defining invariants, bounds, and requirements."""
    id: str = Field(default="policy_leak_isolation")
    name: str = Field(default="Leak Isolation and Safety Policy")
    objective: str = Field(
        default="Isolate leaking line while maintaining active cooling and guaranteeing human safety."
    )
    min_target_confidence: float = Field(
        default=0.90,
        ge=0.0,
        le=1.0,
        description="Minimum confidence score required for target entity identification."
    )
    require_human_zone_clear: bool = Field(
        default=True,
        description="Safety invariant: human safety zone must be strictly CLEAR."
    )
    require_cooling_active: bool = Field(
        default=True,
        description="Operational invariant: cooling system must remain ACTIVE."
    )
    prohibited_actions: List[ActionType] = Field(
        default_factory=lambda: [ActionType.ADJUST_COOLING],
        description="Action types explicitly forbidden under this policy."
    )
    allowed_actuator_targets: List[str] = Field(
        default_factory=lambda: ["valve_a", "valve_b"],
        description="Actuator targets permissible for manipulation under this policy."
    )
    max_tolerated_contradiction: ContradictionSeverity = Field(
        default=ContradictionSeverity.NONE,
        description="Maximum contradiction severity tolerated before denying or requesting evidence."
    )
    required_evidence_sources: List[EvidenceSource] = Field(
        default_factory=list,
        description="List of specific sensor sources that must supply evidence before ALLOW."
    )
    expected_postconditions: Dict[str, Any] = Field(
        default_factory=dict,
        description="Expected post-actuation physical world invariants."
    )
    active_constraints: List[Any] = Field(
        default_factory=list,
        description="Active knowledge-derived constraints governing policy authorization."
    )
