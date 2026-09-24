"""State-bound authorization context and execution-time revalidation.

Phase 2F introduces TOCTOU defense by binding AuthorizationTickets to a
deterministic authorization context (world state version, world state hash,
policy version, constraint set hash, evidence context hash) and requiring
execution-time revalidation before any physical actuation.

SECURITY INVARIANTS:
1. No model or network call is made during revalidation.
2. Revalidation is purely deterministic and locally decidable.
3. Any safety-relevant state drift invalidates the ticket.
4. Revalidation cannot mutate WorldState or mint new tickets.
5. Stale tickets cannot silently preserve authorization.
"""

from enum import Enum
from typing import Any, Dict, List, Optional
import hashlib
import json
import time
import uuid
from pydantic import BaseModel, Field

from motionfence.models.world import WorldState
from motionfence.models.actions import ActionProposal, ActionType
from motionfence.constraints.models import CandidateConstraint
from motionfence.audit.serialization import canonical_json_dump


# ---------------------------------------------------------------------------
# Revalidation status enumeration
# ---------------------------------------------------------------------------

class RevalidationStatus(str, Enum):
    """Possible outcomes of execution-time ticket revalidation."""
    VALID = "VALID"
    STALE = "STALE"
    WORLD_STATE_CHANGED = "WORLD_STATE_CHANGED"
    EVIDENCE_CHANGED = "EVIDENCE_CHANGED"
    POLICY_CHANGED = "POLICY_CHANGED"
    CONSTRAINT_CHANGED = "CONSTRAINT_CHANGED"
    TICKET_EXPIRED = "TICKET_EXPIRED"
    TARGET_MISMATCH = "TARGET_MISMATCH"
    ACTION_MISMATCH = "ACTION_MISMATCH"
    CONTEXT_MISMATCH = "CONTEXT_MISMATCH"


# ---------------------------------------------------------------------------
# Authorization context
# ---------------------------------------------------------------------------

class AuthorizationContext(BaseModel):
    """Deterministic snapshot of the full authorization environment at ticket issuance.

    Every field exists because a change in that field could invalidate the
    safety basis of the original ALLOW decision:

    - world_state_version: Monotonic version detects ANY state mutation.
    - world_state_hash: Cryptographic integrity of the specific state snapshot.
    - policy_version: Policy rule changes may alter the ALLOW/DENY outcome.
    - constraint_set_hash: Active constraint set changes may introduce new prohibitions.
    - evidence_context_hash: Evidence changes may contradict the target identity.
    - action_type / target: Prevents post-authorization action/target tampering.
    - proposal_id: Binds context to the specific evaluated proposal.
    """
    context_id: str = Field(default_factory=lambda: f"ctx_{uuid.uuid4().hex[:12]}")
    proposal_id: str = Field(..., description="ID of the authorized ActionProposal.")
    action_type: ActionType = Field(..., description="Authorized action type.")
    target: str = Field(..., description="Authorized target.")
    world_state_version: int = Field(..., description="Monotonic world state version at authorization.")
    world_state_hash: str = Field(..., description="SHA-256 of canonical world state at authorization.")
    policy_version: str = Field(..., description="Policy version string at authorization.")
    constraint_set_hash: str = Field(..., description="SHA-256 of canonical active constraint set.")
    evidence_context_hash: str = Field(..., description="SHA-256 of canonical safety-relevant evidence.")
    created_at: float = Field(default_factory=time.time)


class AuthorizationRevalidationResult(BaseModel):
    """Typed result of execution-time ticket revalidation.

    Exposes expected vs. observed context for audit and replay
    without exposing secrets.
    """
    status: RevalidationStatus = Field(..., description="Revalidation outcome.")
    reasons: List[str] = Field(default_factory=list, description="Human-readable explanation of failure.")
    expected_context_hash: str = Field(default="", description="Context hash from ticket issuance.")
    observed_context_hash: str = Field(default="", description="Context hash at execution time.")
    expected_world_version: int = Field(default=0, description="World version at ticket issuance.")
    observed_world_version: int = Field(default=0, description="World version at execution time.")
    timestamp: float = Field(default_factory=time.time)


# ---------------------------------------------------------------------------
# Hashing utilities
# ---------------------------------------------------------------------------

def compute_world_state_hash(world_state: WorldState) -> str:
    """Compute deterministic SHA-256 hash of safety-relevant world state fields.

    Uses canonical JSON serialization with sorted keys and normalized floats.
    The hash changes when any safety-relevant physical state changes.
    """
    safety_fields = {
        "valves": {k: v.value for k, v in sorted(world_state.valves.items())},
        "cooling": world_state.cooling.value,
        "human_zone": world_state.human_zone.value,
        "pumps": {k: v for k, v in sorted(world_state.pumps.items())},
        "leak_active": world_state.leak.active,
        "leak_target": world_state.leak.target,
        "version": world_state.version,
    }
    canonical = canonical_json_dump(safety_fields)
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


def compute_constraint_set_hash(constraints: List[CandidateConstraint]) -> str:
    """Compute deterministic SHA-256 hash of the active constraint set.

    Sorted by constraint_id for deterministic ordering.
    """
    if not constraints:
        return hashlib.sha256(b"EMPTY_CONSTRAINT_SET").hexdigest()

    items = []
    for c in sorted(constraints, key=lambda x: x.constraint_id):
        items.append({
            "constraint_id": c.constraint_id,
            "constraint_type": c.constraint_type.value,
            "action": c.action.value if c.action else "NONE",
            "target": c.target,
            "status": c.status.value,
            "claim_text": c.claim_text,
        })
    canonical = canonical_json_dump(items)
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


def compute_evidence_context_hash(evidence: list) -> str:
    """Compute deterministic SHA-256 hash of safety-relevant evidence.

    Uses evidence IDs, sources, targets, and confidence values.
    """
    if not evidence:
        return hashlib.sha256(b"EMPTY_EVIDENCE_SET").hexdigest()

    items = []
    for e in sorted(evidence, key=lambda x: getattr(x, "id", "")):
        items.append({
            "id": getattr(e, "id", ""),
            "source": getattr(e, "source", "").value if hasattr(getattr(e, "source", ""), "value") else str(getattr(e, "source", "")),
            "target": getattr(e, "target", ""),
            "confidence": round(getattr(e, "confidence", 0.0), 6),
        })
    canonical = canonical_json_dump(items)
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


def compute_authorization_context_hash(context: AuthorizationContext) -> str:
    """Compute deterministic SHA-256 hash of the full authorization context."""
    fields = {
        "proposal_id": context.proposal_id,
        "action_type": context.action_type.value,
        "target": context.target,
        "world_state_version": context.world_state_version,
        "world_state_hash": context.world_state_hash,
        "policy_version": context.policy_version,
        "constraint_set_hash": context.constraint_set_hash,
        "evidence_context_hash": context.evidence_context_hash,
    }
    canonical = canonical_json_dump(fields)
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


# ---------------------------------------------------------------------------
# Context builder
# ---------------------------------------------------------------------------

def build_authorization_context(
    proposal: ActionProposal,
    world_state: WorldState,
    policy_version: str,
    active_constraints: List[CandidateConstraint],
    evidence: list,
) -> AuthorizationContext:
    """Construct an AuthorizationContext capturing the full deterministic authorization environment."""
    return AuthorizationContext(
        proposal_id=proposal.id,
        action_type=proposal.action_type,
        target=proposal.target,
        world_state_version=world_state.version,
        world_state_hash=compute_world_state_hash(world_state),
        policy_version=policy_version,
        constraint_set_hash=compute_constraint_set_hash(active_constraints),
        evidence_context_hash=compute_evidence_context_hash(evidence),
    )


# ---------------------------------------------------------------------------
# Execution-time revalidation engine
# ---------------------------------------------------------------------------

class ExecutionTimeRevalidator:
    """Deterministic, locally-decidable execution-time ticket revalidation.

    SECURITY INVARIANTS:
    1. Makes ZERO model calls (no Nemotron, no Tavily, no LLM).
    2. Makes ZERO network calls.
    3. Cannot mutate WorldState.
    4. Cannot mint new AuthorizationTickets.
    5. Cannot silently refresh stale authorization.
    """

    @staticmethod
    def revalidate(
        authorization_context: AuthorizationContext,
        current_world_state: WorldState,
        current_policy_version: str,
        current_constraints: List[CandidateConstraint],
        current_evidence: list,
        ticket_expires_at: float,
        proposal_action_type: ActionType,
        proposal_target: str,
    ) -> AuthorizationRevalidationResult:
        """Perform deterministic execution-time revalidation.

        Only returns VALID if the authorization context remains identical.
        Any safety-relevant drift produces an immediate rejection.
        """
        now = time.time()
        reasons: List[str] = []

        # 1. Ticket expiration check
        if now > ticket_expires_at:
            return AuthorizationRevalidationResult(
                status=RevalidationStatus.TICKET_EXPIRED,
                reasons=["Authorization ticket has expired."],
                expected_world_version=authorization_context.world_state_version,
                observed_world_version=current_world_state.version,
            )

        # 2. Action type mismatch (post-authorization tampering)
        if proposal_action_type != authorization_context.action_type:
            reasons.append(
                f"Action type mismatch: authorized={authorization_context.action_type.value}, "
                f"requested={proposal_action_type.value}"
            )
            return AuthorizationRevalidationResult(
                status=RevalidationStatus.ACTION_MISMATCH,
                reasons=reasons,
                expected_world_version=authorization_context.world_state_version,
                observed_world_version=current_world_state.version,
            )

        # 3. Target mismatch (post-authorization tampering)
        if proposal_target != authorization_context.target:
            reasons.append(
                f"Target mismatch: authorized={authorization_context.target}, "
                f"requested={proposal_target}"
            )
            return AuthorizationRevalidationResult(
                status=RevalidationStatus.TARGET_MISMATCH,
                reasons=reasons,
                expected_world_version=authorization_context.world_state_version,
                observed_world_version=current_world_state.version,
            )

        # 4. World state version drift
        if current_world_state.version != authorization_context.world_state_version:
            reasons.append(
                f"World state version drift: authorized_version={authorization_context.world_state_version}, "
                f"current_version={current_world_state.version}"
            )
            return AuthorizationRevalidationResult(
                status=RevalidationStatus.WORLD_STATE_CHANGED,
                reasons=reasons,
                expected_world_version=authorization_context.world_state_version,
                observed_world_version=current_world_state.version,
            )

        # 5. World state hash integrity
        current_ws_hash = compute_world_state_hash(current_world_state)
        if current_ws_hash != authorization_context.world_state_hash:
            reasons.append(
                f"World state hash mismatch: expected={authorization_context.world_state_hash[:16]}..., "
                f"observed={current_ws_hash[:16]}..."
            )
            return AuthorizationRevalidationResult(
                status=RevalidationStatus.WORLD_STATE_CHANGED,
                reasons=reasons,
                expected_context_hash=authorization_context.world_state_hash,
                observed_context_hash=current_ws_hash,
                expected_world_version=authorization_context.world_state_version,
                observed_world_version=current_world_state.version,
            )

        # 6. Policy version drift
        if current_policy_version != authorization_context.policy_version:
            reasons.append(
                f"Policy version drift: authorized={authorization_context.policy_version}, "
                f"current={current_policy_version}"
            )
            return AuthorizationRevalidationResult(
                status=RevalidationStatus.POLICY_CHANGED,
                reasons=reasons,
                expected_world_version=authorization_context.world_state_version,
                observed_world_version=current_world_state.version,
            )

        # 7. Constraint set drift
        current_constraint_hash = compute_constraint_set_hash(current_constraints)
        if current_constraint_hash != authorization_context.constraint_set_hash:
            reasons.append(
                f"Constraint set hash drift: expected={authorization_context.constraint_set_hash[:16]}..., "
                f"observed={current_constraint_hash[:16]}..."
            )
            return AuthorizationRevalidationResult(
                status=RevalidationStatus.CONSTRAINT_CHANGED,
                reasons=reasons,
                expected_context_hash=authorization_context.constraint_set_hash,
                observed_context_hash=current_constraint_hash,
                expected_world_version=authorization_context.world_state_version,
                observed_world_version=current_world_state.version,
            )

        # 8. Evidence context drift
        current_evidence_hash = compute_evidence_context_hash(current_evidence)
        if current_evidence_hash != authorization_context.evidence_context_hash:
            reasons.append(
                f"Evidence context hash drift: expected={authorization_context.evidence_context_hash[:16]}..., "
                f"observed={current_evidence_hash[:16]}..."
            )
            return AuthorizationRevalidationResult(
                status=RevalidationStatus.EVIDENCE_CHANGED,
                reasons=reasons,
                expected_context_hash=authorization_context.evidence_context_hash,
                observed_context_hash=current_evidence_hash,
                expected_world_version=authorization_context.world_state_version,
                observed_world_version=current_world_state.version,
            )

        # 9. Full authorization context hash verification
        expected_ctx_hash = compute_authorization_context_hash(authorization_context)
        rebuilt_ctx = AuthorizationContext(
            context_id=authorization_context.context_id,
            proposal_id=authorization_context.proposal_id,
            action_type=proposal_action_type,
            target=proposal_target,
            world_state_version=current_world_state.version,
            world_state_hash=current_ws_hash,
            policy_version=current_policy_version,
            constraint_set_hash=current_constraint_hash,
            evidence_context_hash=current_evidence_hash,
            created_at=authorization_context.created_at,
        )
        observed_ctx_hash = compute_authorization_context_hash(rebuilt_ctx)

        if expected_ctx_hash != observed_ctx_hash:
            reasons.append(
                f"Full context hash mismatch: expected={expected_ctx_hash[:16]}..., "
                f"observed={observed_ctx_hash[:16]}..."
            )
            return AuthorizationRevalidationResult(
                status=RevalidationStatus.CONTEXT_MISMATCH,
                reasons=reasons,
                expected_context_hash=expected_ctx_hash,
                observed_context_hash=observed_ctx_hash,
                expected_world_version=authorization_context.world_state_version,
                observed_world_version=current_world_state.version,
            )

        # ALL checks passed
        return AuthorizationRevalidationResult(
            status=RevalidationStatus.VALID,
            reasons=["Authorization context remains valid. All bindings match."],
            expected_context_hash=expected_ctx_hash,
            observed_context_hash=observed_ctx_hash,
            expected_world_version=authorization_context.world_state_version,
            observed_world_version=current_world_state.version,
        )
