"""Authorization ticket minting and signature validation."""

import time
import uuid
import hmac
import hashlib

from motionfence.models.actions import ActionProposal, AuthorizationTicket


class TicketAuthority:
    """Mints cryptographically sealed tickets strictly for authorized proposals."""

    def __init__(self, secret_key: str = "motionfence_runtime_kernel_secret") -> None:
        self.secret_key = secret_key.encode("utf-8")

    def mint_ticket(
        self,
        proposal: ActionProposal,
        ttl_seconds: float = 30.0,
    ) -> AuthorizationTicket:
        """Mint a one-time, time-bounded AuthorizationTicket for an approved proposal."""
        ticket_id = f"tkt_{uuid.uuid4().hex[:12]}"
        now = time.time()
        expires_at = now + ttl_seconds

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
