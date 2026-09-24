"""Typed domain models for MotionFence Decision Records, Audit Chains, and Replay."""

from enum import Enum
import time
from typing import Any, Dict, List, Optional
import uuid
from pydantic import BaseModel, Field, ConfigDict

from motionfence.models.actions import ActionProposal, ExecutionResult
from motionfence.models.world import WorldState
from motionfence.runtime.verification import VerificationResult


class DecisionCategory(str, Enum):
    """Categorical outcome of a MotionFence authorization lifecycle."""
    ALLOW = "ALLOW"
    DENY = "DENY"
    NEED_MORE_EVIDENCE = "NEED_MORE_EVIDENCE"
    EXECUTION_FAILED = "EXECUTION_FAILED"
    VERIFICATION_FAILED = "VERIFICATION_FAILED"


class ExecutionMode(str, Enum):
    """Mode of operation under which the decision was evaluated."""
    LIVE = "LIVE"
    REPLAY = "REPLAY"
    FIXTURE = "FIXTURE"


class SourceMode(str, Enum):
    """Provenance origin of external evidence and models."""
    LIVE_MODEL_RESPONSE = "LIVE_MODEL_RESPONSE"
    LIVE_TAVILY_RESPONSE = "LIVE_TAVILY_RESPONSE"
    LOCAL_FIXTURE = "LOCAL_FIXTURE"
    LOCAL_CACHE_REPLAY = "LOCAL_CACHE_REPLAY"


class DecisionRecord(BaseModel):
    """Immutable, cryptographically hash-linked audit record of a physical authorization decision.
    
    SECURITY INVARIANTS:
    1. Once finalized, ordinary runtime code cannot modify the record.
    2. Contains complete provenance needed for 100% offline deterministic replay.
    3. Contains ZERO credentials, tokens, or private secrets.
    """
    model_config = ConfigDict(extra="ignore")

    # Identifiers & Provenance
    decision_id: str = Field(default_factory=lambda: f"dec_{uuid.uuid4().hex[:12]}")
    sequence_number: int = Field(default=0, ge=0, description="Monotonically increasing chain sequence number.")
    created_at: float = Field(default_factory=time.time)
    finalized_at: Optional[float] = Field(default=None)
    is_finalized: bool = Field(default=False)

    # Cryptographic Hash-Link Chain
    record_hash: Optional[str] = Field(default=None, description="SHA-256 canonical hash of this finalized record.")
    previous_record_hash: Optional[str] = Field(default=None, description="SHA-256 hash of the preceding record in the chain.")

    # Core Decision Context
    intent: str = Field(..., description="Original human operator intent.")
    world_state_snapshot: WorldState = Field(..., description="Ground-truth world state at time of evaluation.")

    # Evidence & Knowledge Provenance References
    sensor_evidence_ids: List[str] = Field(default_factory=list, description="IDs of physical sensor observations.")
    knowledge_evidence_ids: List[str] = Field(default_factory=list, description="IDs of referenced KnowledgeEvidence.")
    source_assessment_ids: List[str] = Field(default_factory=list, description="IDs of SourceTrustAssessments.")
    claim_support_certificate_ids: List[str] = Field(default_factory=list, description="IDs of ClaimSupportCertificates.")
    candidate_constraint_ids: List[str] = Field(default_factory=list, description="IDs of evaluated candidate constraints.")
    active_constraint_ids: List[str] = Field(default_factory=list, description="IDs of admissible active constraints.")

    # Action & Policy Verdict
    action_proposal: Optional[ActionProposal] = Field(default=None, description="Unprivileged model-proposed action.")
    policy_decision: DecisionCategory = Field(..., description="Categorical outcome of the policy evaluation.")
    policy_reasons: List[str] = Field(default_factory=list, description="Deterministic reasons cited for verdict.")

    # Actuation & Verification Tracking
    authorization_ticket_id: Optional[str] = Field(default=None, description="Minted HMAC ticket ID if authorized, else None.")
    execution_result: Optional[ExecutionResult] = Field(default=None, description="Actuator outcome if executed.")
    verification_result: Optional[VerificationResult] = Field(default=None, description="Postcondition verification outcome.")

    # Versions & Metadata
    runtime_version: str = Field(default="2.4.0", description="Semantic version of MotionFence runtime.")
    policy_version: str = Field(default="1.0.0", description="Version of the active policy specification.")
    schema_version: str = Field(default="1.0.0", description="Schema version of this DecisionRecord.")
    provider_metadata: Dict[str, Any] = Field(
        default_factory=dict,
        description="Model provider, model name, execution_mode, source_mode (zero secrets).",
    )

    # Standalone Snapshots for Complete Offline Replay
    snapshots: Dict[str, Any] = Field(
        default_factory=dict,
        description="Serialized snapshots of evidence, constraints, certificates for offline replay.",
    )

    # Phase 2F: State-Bound Authorization & TOCTOU Revalidation Fields
    authorization_context_hash: Optional[str] = Field(
        default=None,
        description="SHA-256 hash of the deterministic authorization context at ticket issuance."
    )
    ticket_world_state_version: Optional[int] = Field(
        default=None,
        description="World state version at ticket issuance time."
    )
    ticket_world_state_hash: Optional[str] = Field(
        default=None,
        description="SHA-256 hash of canonical world state at ticket issuance."
    )
    revalidation_status: Optional[str] = Field(
        default=None,
        description="Execution-time revalidation outcome (VALID, STALE, WORLD_STATE_CHANGED, etc.)."
    )
    revalidation_reasons: List[str] = Field(
        default_factory=list,
        description="Human-readable reasons from execution-time revalidation."
    )
    execution_context_version: Optional[int] = Field(
        default=None,
        description="World state version at execution time (may differ from issuance)."
    )
    execution_context_hash: Optional[str] = Field(
        default=None,
        description="SHA-256 hash of world state at execution time."
    )

    # Phase 2G: Active Evidence Acquisition Tracking
    evidence_action_ids: List[str] = Field(
        default_factory=list,
        description="IDs of executed information-gathering actions.",
    )
    evidence_acquisition_iterations: int = Field(
        default=0,
        ge=0,
        description="Number of information-gathering iterations executed.",
    )
    evidence_budget: int = Field(
        default=3,
        ge=0,
        description="Maximum permitted information-gathering iterations per cycle.",
    )
    predicted_information_gain: Optional[str] = Field(
        default=None,
        description="Predicted information gain level from planner (LOW, MEDIUM, HIGH).",
    )
    observed_information_gain: Optional[str] = Field(
        default=None,
        description="Observed empirical information gain level (HIGH, MEDIUM, LOW, ZERO, NEGATIVE).",
    )

    # Phase 2I: Fault Containment, Quarantine & Autonomous Recovery Tracking
    failure_ids: List[str] = Field(
        default_factory=list,
        description="IDs of classified failure events that triggered containment.",
    )
    recovery_plan_ids: List[str] = Field(
        default_factory=list,
        description="IDs of executed autonomous recovery plans.",
    )
    quarantine_record_ids: List[str] = Field(
        default_factory=list,
        description="IDs of quarantine records created or updated during this cycle.",
    )
    recovery_iterations: int = Field(
        default=0,
        ge=0,
        description="Number of autonomous recovery iterations executed.",
    )
    recovery_outcome: Optional[str] = Field(
        default=None,
        description="Terminal recovery outcome (SUCCESS, FAILED, BUDGET_EXHAUSTED, QUARANTINED).",
    )

    def mark_finalized(self, record_hash: str, previous_record_hash: Optional[str]) -> None:
        """Mark record as finalized with computed cryptographic hashes."""
        if self.is_finalized:
            raise ValueError(f"DecisionRecord '{self.decision_id}' is already finalized and cannot be modified.")
        self.record_hash = record_hash
        self.previous_record_hash = previous_record_hash
        self.finalized_at = time.time()
        self.is_finalized = True


def format_decision_audit(record: DecisionRecord) -> str:
    """Format human-readable decision explanation matching Section 8 specification."""
    lines = [
        "MOTIONFENCE DECISION",
        "--------------------",
        "",
        "Intent:",
        record.intent,
        "",
        "Proposed action:",
    ]
    if record.action_proposal:
        lines.append(f"{record.action_proposal.action_type.value} {record.action_proposal.target}")
    else:
        lines.append("NONE")

    lines.extend(["", "Evidence:"])
    if record.snapshots.get("evidence"):
        for ev in record.snapshots["evidence"]:
            ev_id = ev.get("id", "unknown")
            conf = ev.get("confidence", 0.0)
            lines.append(f"{ev_id:<16} {conf:.2f}")
    elif record.sensor_evidence_ids:
        for ev_id in record.sensor_evidence_ids:
            lines.append(f"{ev_id:<16}")
    else:
        lines.append("NONE")

    lines.extend(["", "Knowledge:"])
    if record.knowledge_evidence_ids:
        for k_id in record.knowledge_evidence_ids:
            lines.append(k_id)
    else:
        lines.append("NONE")

    lines.extend(["", "Constraint:"])
    if record.snapshots.get("active_constraints"):
        for cst in record.snapshots["active_constraints"]:
            lines.append(cst.get("claim_text") or cst.get("description", "No description"))
    elif record.active_constraint_ids:
        lines.append(f"{len(record.active_constraint_ids)} active constraint(s)")
    else:
        lines.append("NONE")

    lines.extend(["", "Grounding:"])
    if record.snapshots.get("certificates"):
        certs = record.snapshots["certificates"]
        st = certs[0].get("support_type", "UNKNOWN")
        ss = certs[0].get("support_status", "UNKNOWN")
        lines.append(f"{st} / {ss}")
    elif record.claim_support_certificate_ids:
        lines.append(f"CERTIFICATES: {', '.join(record.claim_support_certificate_ids)}")
    else:
        lines.append("NOT EVALUATED")

    lines.extend(["", "Source trust:"])
    if record.snapshots.get("source_assessments"):
        ass = record.snapshots["source_assessments"]
        lines.append(ass[0].get("source_category", "UNKNOWN"))
    else:
        lines.append("NOT ASSESSED")

    lines.extend(["", "Applicability:"])
    if record.snapshots.get("active_constraints"):
        cst = record.snapshots["active_constraints"][0]
        lines.append(cst.get("applicability", "DIRECT"))
    else:
        lines.append("DIRECT")

    lines.extend(["", "Policy:", record.policy_decision.value, "", "Reason:"])
    if record.policy_reasons:
        for r in record.policy_reasons:
            lines.append(r)
    else:
        lines.append("Nominal policy conditions satisfied.")

    lines.extend(["", "Authorization ticket:"])
    lines.append(record.authorization_ticket_id if record.authorization_ticket_id else "NOT CREATED")

    lines.extend(["", "World mutation:"])
    if record.execution_result and record.execution_result.success:
        lines.append("APPLIED")
    else:
        lines.append("NONE")

    lines.extend(["", "Final verification:"])
    if record.verification_result:
        lines.append("VERIFIED" if record.verification_result.is_verified else "FAILED")
    else:
        lines.append("NOT APPLICABLE")

    if record.evidence_acquisition_iterations > 0:
        lines.extend([
            "",
            "Evidence acquisition:",
            f"Iterations: {record.evidence_acquisition_iterations} / Budget: {record.evidence_budget}",
            f"Actions: {', '.join(record.evidence_action_ids) if record.evidence_action_ids else 'NONE'}",
            f"Predicted gain: {record.predicted_information_gain or 'N/A'}",
            f"Observed gain: {record.observed_information_gain or 'N/A'}",
        ])

    return "\n".join(lines)
