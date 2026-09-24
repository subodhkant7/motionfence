"""Structured models for candidate and active operational constraints."""

from enum import Enum
from typing import Any, Dict, List, Optional
import time
import uuid
from pydantic import BaseModel, Field

from motionfence.models.actions import ActionType


class ConstraintType(str, Enum):
    """Classification of operational constraint extracted from knowledge."""
    PROHIBITION = "PROHIBITION"        # Hard negative rule (e.g., must not close valve while pump running)
    REQUIREMENT = "REQUIREMENT"        # Mandatory condition (e.g., cooling must remain active)
    PRECONDITION = "PRECONDITION"      # Prerequisite step (e.g., visual inspection before servicing)
    POSTCONDITION = "POSTCONDITION"    # Desired post-state invariant
    INFORMATIONAL = "INFORMATIONAL"    # Non-binding procedure or routine checklist


class ConstraintStatus(str, Enum):
    """Lifecycle and qualification status of a candidate constraint."""
    CANDIDATE = "CANDIDATE"      # Newly extracted from knowledge; unvalidated
    VALIDATED = "VALIDATED"      # Passed structural and provenance verification
    REJECTED = "REJECTED"        # Failed validation or missing evidence references
    ACTIVE = "ACTIVE"            # Promoted and authoritative in policy evaluation
    CONFLICTED = "CONFLICTED"    # Mutual contradiction with another source or policy
    STALE = "STALE"              # Sourced from outdated / expired documentation


class CandidateConstraint(BaseModel):
    """Structured, machine-readable operational rule extracted from knowledge evidence.
    
    SECURITY INVARIANT:
    A CandidateConstraint is unprivileged data until deterministically validated
    and explicitly promoted to ACTIVE.
    """
    constraint_id: str = Field(default_factory=lambda: f"cst_{uuid.uuid4().hex[:8]}")
    constraint_type: ConstraintType = Field(..., description="Classification of the constraint.")
    action: Optional[ActionType] = Field(default=None, description="Physical action governed by this rule.")
    target: str = Field(..., description="Target physical entity or subsystem (e.g. 'valve_b').")
    condition: Dict[str, Any] = Field(
        default_factory=dict,
        description="Physical state conditions under which constraint triggers (e.g. {'pump_p1': 'ACTIVE'})."
    )
    source_evidence_id: str = Field(..., description="ID of the KnowledgeEvidence source.")
    confidence: float = Field(default=1.0, ge=0.0, le=1.0, description="Extraction confidence score.")
    created_at: float = Field(default_factory=time.time)
    status: ConstraintStatus = Field(default=ConstraintStatus.CANDIDATE)
    description: str = Field(default="", description="Human-readable rule text.")
    validation_notes: List[str] = Field(default_factory=list, description="Audit notes from validator.")

    @property
    def is_active(self) -> bool:
        return self.status == ConstraintStatus.ACTIVE

    @property
    def is_prohibition(self) -> bool:
        return self.constraint_type == ConstraintType.PROHIBITION


class ConstraintConflictReport(BaseModel):
    """Structured assessment of mutual incompatibility between constraints."""
    conflict: bool = Field(default=False)
    constraint_a_id: str = Field(..., description="First conflicting constraint ID.")
    constraint_b_id: str = Field(..., description="Second conflicting constraint ID.")
    severity: str = Field(default="HIGH", description="Severity level ('LOW', 'MEDIUM', 'HIGH').")
    details: str = Field(default="", description="Explanation of the contradiction.")
    timestamp: float = Field(default_factory=time.time)
