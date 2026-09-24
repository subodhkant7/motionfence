"""Structured models for candidate, admissible, and active operational constraints."""

from enum import Enum
from typing import Any, Dict, List, Optional
import time
import uuid
from pydantic import BaseModel, Field

from motionfence.models.actions import ActionType
from motionfence.knowledge.trust import (
    SourceTrustAssessment,
    EvidenceRole,
    CorroborationStatus,
)


class ConstraintType(str, Enum):
    """Classification of operational constraint extracted from knowledge."""
    PROHIBITION = "PROHIBITION"        # Hard negative rule (e.g., must not close valve while pump running)
    REQUIREMENT = "REQUIREMENT"        # Mandatory condition (e.g., cooling must remain active)
    PRECONDITION = "PRECONDITION"      # Prerequisite step (e.g., visual inspection before servicing)
    POSTCONDITION = "POSTCONDITION"    # Desired post-state invariant
    INFORMATIONAL = "INFORMATIONAL"    # Non-binding procedure or routine checklist


class ConstraintStatus(str, Enum):
    """Lifecycle and qualification status of a candidate constraint."""
    CANDIDATE = "CANDIDATE"                    # Newly extracted from knowledge; unvalidated
    STRUCTURALLY_VALID = "STRUCTURALLY_VALID"  # Correctly formed schema and references real evidence
    VALIDATED = "VALIDATED"                    # Backwards-compatibility alias for STRUCTURALLY_VALID
    ADMISSIBLE = "ADMISSIBLE"                  # Passed institutional authority, evidence-role, and applicability checks
    ACTIVE = "ACTIVE"                          # Authoritative in policy evaluation; gates physical actuation
    REJECTED = "REJECTED"                      # Failed structural validation, missing evidence, or inadmissible
    CONFLICTED = "CONFLICTED"                  # Mutual contradiction with another source or policy
    STALE = "STALE"                            # Sourced from outdated / expired documentation


class Applicability(str, Enum):
    """Relevance and context alignment of operational knowledge to target plant equipment."""
    DIRECT = "DIRECT"      # Explicitly matches target equipment ID and plant context
    PARTIAL = "PARTIAL"    # Generic guidance for equipment class without plant-specific model
    UNKNOWN = "UNKNOWN"    # Context cannot be verified from document
    MISMATCH = "MISMATCH"  # Refers to a different equipment family, plant profile, or operating mode


class PlantContext(BaseModel):
    """Operational plant metadata against which knowledge applicability is verified."""
    plant_profile: str = Field(default="industrial_fluid_plant", description="Facility classification.")
    equipment_type: str = Field(default="centrifugal_pump", description="Primary equipment class.")
    equipment_model: Optional[str] = Field(default="P100-A", description="Specific equipment model designation.")
    equipment_id: str = Field(default="pump_p1", description="Identifier of the monitored physical unit.")
    operating_mode: str = Field(default="nominal", description="Current operating regime.")
    authorized_targets: List[str] = Field(
        default_factory=lambda: ["valve_a", "valve_b", "pump_p1"],
        description="Physical components within plant control boundary."
    )


class CandidateConstraint(BaseModel):
    """Structured, machine-readable operational rule extracted from knowledge evidence.
    
    SECURITY INVARIANT:
    A CandidateConstraint is unprivileged data until deterministically validated,
    admissibility-checked, and explicitly promoted to ACTIVE.
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
    confidence: float = Field(default=1.0, ge=0.0, le=1.0, description="Model extraction confidence score.")
    created_at: float = Field(default_factory=time.time)
    status: ConstraintStatus = Field(default=ConstraintStatus.CANDIDATE)
    description: str = Field(default="", description="Human-readable rule text.")
    claim_text: Optional[str] = Field(default=None, description="Exact operational claim quote from text.")
    extraction_rationale: Optional[str] = Field(default=None, description="Model or parser rationale.")
    
    # Phase 2B: Evidence Trust & Admissibility Properties
    evidence_role: Optional[EvidenceRole] = Field(default=None, description="Assigned role of supporting evidence.")
    source_trust: Optional[SourceTrustAssessment] = Field(default=None, description="Formal source assessment.")
    applicability: Applicability = Field(default=Applicability.DIRECT, description="Context applicability.")
    corroboration: CorroborationStatus = Field(default=CorroborationStatus.SINGLE_SOURCE, description="Multi-source status.")
    admissibility_notes: List[str] = Field(default_factory=list, description="Audit notes on admissibility.")
    validation_notes: List[str] = Field(default_factory=list, description="Audit notes from validator.")

    @property
    def is_active(self) -> bool:
        return self.status == ConstraintStatus.ACTIVE

    @property
    def is_admissible(self) -> bool:
        return self.status in (ConstraintStatus.ADMISSIBLE, ConstraintStatus.ACTIVE)

    @property
    def is_prohibition(self) -> bool:
        return self.constraint_type == ConstraintType.PROHIBITION


class ConflictCategory(str, Enum):
    """Categorization of operational contradictions."""
    SOURCE_CONFLICT = "SOURCE_CONFLICT"              # Disagreement between multiple knowledge sources
    POLICY_CONFLICT = "POLICY_CONFLICT"              # Constraint contradicts base safety policy
    APPLICABILITY_CONFLICT = "APPLICABILITY_CONFLICT"# Guidance applies to different models or conflicting operating modes
    FRESHNESS_CONFLICT = "FRESHNESS_CONFLICT"        # Superseded guidance contradicts current standard


class ConstraintConflictReport(BaseModel):
    """Structured assessment of mutual incompatibility between constraints."""
    conflict: bool = Field(default=False)
    constraint_a_id: str = Field(..., description="First conflicting constraint ID.")
    constraint_b_id: str = Field(..., description="Second conflicting constraint ID.")
    conflict_category: ConflictCategory = Field(default=ConflictCategory.SOURCE_CONFLICT, description="Type of contradiction.")
    severity: str = Field(default="HIGH", description="Severity level ('LOW', 'MEDIUM', 'HIGH').")
    details: str = Field(default="", description="Explanation of the contradiction.")
    timestamp: float = Field(default_factory=time.time)
