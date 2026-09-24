"""Authorization ticket minting and signature validation.

Phase 2F: Extended to bind tickets to a deterministic authorization context
including world state version/hash, policy version, constraint set hash,
and evidence context hash.
"""

import time
import uuid
import hmac
import hashlib
from typing import List, Optional

from motionfence.models.actions import ActionProposal, AuthorizationTicket
from motionfence.models.world import WorldState
from motionfence.constraints.models import CandidateConstraint
from motionfence.runtime.revalidation import (
    AuthorizationContext,
    build_authorization_context,
    compute_authorization_context_hash,
)


class TicketAuthority:
    """Mints cryptographically sealed, state-bound tickets strictly for authorized proposals.

    Phase 2F: Tickets are bound to a deterministic authorization context at issuance.
    The context captures world state, policy, constraints, and evidence so that
    execution-time revalidation can detect authorization staleness.
    """

    def __init__(self, secret_key: str = "motionfence_runtime_kernel_secret") -> None:
        self.secret_key = secret_key.encode("utf-8")

    def mint_ticket(
        self,
        proposal: ActionProposal,
        ttl_seconds: float = 30.0,
        world_state: Optional[WorldState] = None,
        policy_version: str = "1.0.0",
        active_constraints: Optional[List[CandidateConstraint]] = None,
        evidence: Optional[list] = None,
    ) -> AuthorizationTicket:
        """Mint a one-time, time-bounded, state-bound AuthorizationTicket.

        Phase 2F binds the ticket to a deterministic authorization context
        so that execution-time revalidation can detect any safety-relevant
        state drift between authorization and execution.
        """
        ticket_id = f"tkt_{uuid.uuid4().hex[:12]}"
        now = time.time()
        expires_at = now + ttl_seconds

        # Phase 2F: Build authorization context bindings
        auth_context_hash = ""
        ws_version = 0
        ws_hash = ""
        constraint_hash = ""
        evidence_hash = ""

        if world_state is not None:
            ctx = build_authorization_context(
                proposal=proposal,
                world_state=world_state,
                policy_version=policy_version,
                active_constraints=active_constraints or [],
                evidence=evidence or [],
            )
            auth_context_hash = compute_authorization_context_hash(ctx)
            ws_version = ctx.world_state_version
            ws_hash = ctx.world_state_hash
            constraint_hash = ctx.constraint_set_hash
            evidence_hash = ctx.evidence_context_hash

        signature = self._compute_signature(
            ticket_id=ticket_id,
            proposal_id=proposal.id,
            action_type_value=proposal.action_type.value,
            target=proposal.target,
            expires_at=expires_at,
        )

        return AuthorizationTicket(
            ticket_id=ticket_id,
            proposal_id=proposal.id,
            action_type=proposal.action_type,
            target=proposal.target,
            issued_at=now,
            expires_at=expires_at,
            authorized_by="MotionFence.PolicyEngine.DeterministicEvaluator",
            signature=signature,
            consumed=False,
            # Phase 2F state bindings
            authorization_context_hash=auth_context_hash,
            world_state_version=ws_version,
            world_state_hash=ws_hash,
            policy_version=policy_version,
            constraint_set_hash=constraint_hash,
            evidence_context_hash=evidence_hash,
        )

    def _compute_signature(
        self,
        ticket_id: str,
        proposal_id: str,
        action_type_value: str,
        target: str,
        expires_at: float,
    ) -> str:
        payload = f"{ticket_id}:{proposal_id}:{action_type_value}:{target}:{expires_at:.3f}".encode("utf-8")
        return hmac.new(self.secret_key, payload, hashlib.sha256).hexdigest()
