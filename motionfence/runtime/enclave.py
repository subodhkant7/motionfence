"""Deterministic Safety Enclave for MotionFence runtime authorization.

SECURITY ARCHITECTURE:
Untrusted World + Untrusted Model + Untrusted Knowledge
          ↓
   MotionFence Core
          ↓
   SAFETY ENCLAVE
          ↓
 Authorization Decision
          ↓
   Ticket Authority

SECURITY INVARIANTS:
1. Zero LLM calls.
2. Zero Tavily calls / web retrieval.
3. The enclave is the final authority before physical mutation.
4. Only the Safety Enclave can cause an AuthorizationTicket to be minted.
5. No parallel authorization path exists.
6. Phase 2F: Tickets are bound to a deterministic authorization context.
"""

from typing import Any, Dict, List, Optional
import time
from pydantic import BaseModel, Field

from motionfence.models.actions import ActionProposal, AuthorizationTicket
from motionfence.models.world import WorldState
from motionfence.evidence.models import Evidence
from motionfence.policy.models import Policy, PolicyDecision, DecisionType
from motionfence.policy.engine import PolicyEngine
from motionfence.constraints.models import CandidateConstraint
from motionfence.runtime.ticket import TicketAuthority
from motionfence.runtime.events import EventBus
from motionfence.models.events import EventType
from motionfence.runtime.revalidation import (
    AuthorizationContext,
    build_authorization_context,
    compute_authorization_context_hash,
)


class EnclaveAuthorizationRequest(BaseModel):
    """Strictly typed, validated input bundle for the Safety Enclave."""
    proposal: ActionProposal
    world_state: WorldState
    evidence: List[Evidence]
    policy: Policy
    active_constraints: List[CandidateConstraint] = Field(default_factory=list)


class EnclaveAuthorizationResult(BaseModel):
    """Deterministic verdict and optional ticket issued by the Safety Enclave."""
    authorized: bool
    decision: PolicyDecision
    ticket: Optional[AuthorizationTicket] = None
    authorization_context: Optional[AuthorizationContext] = None
    enclave_reasons: List[str] = Field(default_factory=list)
    timestamp: float = Field(default_factory=time.time)

    @property
    def is_authorized(self) -> bool:
        return self.authorized and self.ticket is not None


class SafetyEnclave:
    """Isolated deterministic authorization enclave.
    
    The Safety Enclave isolates the final physical authorization decision from
    perceptual models, retrieval agents, and external networks.

    Phase 2F: The enclave now builds and binds a deterministic AuthorizationContext
    to every minted ticket, enabling execution-time TOCTOU revalidation.
    """

    def __init__(
        self,
        secret_key: str = "motionfence_runtime_kernel_secret",
        event_bus: Optional[EventBus] = None,
    ) -> None:
        # Cryptographic ticket authority is private and strictly encapsulated
        self._ticket_authority = TicketAuthority(secret_key=secret_key)
        self.event_bus = event_bus

    def authorize(self, request: EnclaveAuthorizationRequest) -> EnclaveAuthorizationResult:
        """Evaluate deterministic safety policy and conditionally mint a state-bound AuthorizationTicket."""
        if self.event_bus:
            self.event_bus.emit(
                EventType.ENCLAVE_AUTHORIZATION_REQUESTED,
                f"Safety Enclave evaluating proposal '{request.proposal.id}' for target '{request.proposal.target}'.",
                payload={"proposal_id": request.proposal.id, "target": request.proposal.target},
            )

        # 1. Deterministic evaluation via PolicyEngine (Zero LLMs)
        decision = PolicyEngine.evaluate(
            proposal=request.proposal,
            world_state=request.world_state,
            evidence=request.evidence,
            policy=request.policy,
            active_constraints=request.active_constraints,
        )

        reasons = [r.details if hasattr(r, "details") and r.details else f"{r.constraint}: {r.status}" for r in decision.reasons]

        # 2. Hard Enclave Decision: Only ALLOW verdict permits ticket issuance
        if decision.is_allowed:
            # Phase 2F: Build authorization context and bind to ticket
            policy_version = getattr(request.policy, "version", "1.0.0")
            auth_context = build_authorization_context(
                proposal=request.proposal,
                world_state=request.world_state,
                policy_version=policy_version,
                active_constraints=request.active_constraints,
                evidence=request.evidence,
            )

            ticket = self._ticket_authority.mint_ticket(
                proposal=request.proposal,
                world_state=request.world_state,
                policy_version=policy_version,
                active_constraints=request.active_constraints,
                evidence=request.evidence,
            )

            if self.event_bus:
                self.event_bus.emit(
                    EventType.ENCLAVE_AUTHORIZATION_GRANTED,
                    f"Safety Enclave GRANTED authorization. Minted state-bound ticket '{ticket.ticket_id}'.",
                    payload={
                        "proposal_id": request.proposal.id,
                        "ticket_id": ticket.ticket_id,
                        "world_state_version": auth_context.world_state_version,
                        "authorization_context_hash": ticket.authorization_context_hash[:16],
                    },
                )
            return EnclaveAuthorizationResult(
                authorized=True,
                decision=decision,
                ticket=ticket,
                authorization_context=auth_context,
                enclave_reasons=reasons,
            )
        else:
            if self.event_bus:
                self.event_bus.emit(
                    EventType.ENCLAVE_AUTHORIZATION_DENIED,
                    f"Safety Enclave DENIED authorization: verdict={decision.decision.value}.",
                    payload={"proposal_id": request.proposal.id, "verdict": decision.decision.value, "reasons": reasons},
                )
            return EnclaveAuthorizationResult(
                authorized=False,
                decision=decision,
                ticket=None,
                authorization_context=None,
                enclave_reasons=reasons,
            )
