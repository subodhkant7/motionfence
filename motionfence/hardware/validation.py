"""Cryptographic and semantic AuthorizationTicket validation at the hardware boundary.

SECURITY INVARIANTS:
1. Uses real HMAC-SHA256 signature verification matching TicketAuthority.
2. Checks action binding, target binding, expiration, and anti-replay.
3. Does NOT duplicate SafetyEnclave policy evaluation — validates authorization integrity only.
4. Never exposes the HMAC secret key.
"""

from typing import Optional, Set
import time
import hmac
import hashlib

from motionfence.models.actions import ActionProposal, ActionType, AuthorizationTicket
from motionfence.hardware.models import (
    HardwareExecutionStatus,
    HardwareTicketValidationResult,
)


class HardwareTicketValidator:
    """Validates presented AuthorizationTickets at the physical actuator boundary."""

    def __init__(self, secret_key: str = "motionfence_runtime_kernel_secret") -> None:
        self._secret_key = secret_key.encode("utf-8")

    def validate(
        self,
        proposal: ActionProposal,
        ticket: Optional[AuthorizationTicket],
        consumed_ticket_ids: Set[str],
        current_world_version: Optional[int] = None,
    ) -> HardwareTicketValidationResult:
        """Validate presented AuthorizationTicket against proposal and hardware boundary rules."""
        reasons = []

        # 1. Ticket presence
        if ticket is None:
            return HardwareTicketValidationResult(
                is_valid=False,
                status=HardwareExecutionStatus.LOCKED,
                reasons=["No AuthorizationTicket presented. Unprivileged proposal cannot actuate."],
            )

        # 2. Replay check (ticket marked consumed or present in hardware consumed registry)
        if ticket.consumed or ticket.ticket_id in consumed_ticket_ids:
            return HardwareTicketValidationResult(
                is_valid=False,
                status=HardwareExecutionStatus.REPLAYED_TICKET,
                single_use_valid=False,
                reasons=[f"Ticket '{ticket.ticket_id}' has already been consumed. Replay rejected."],
            )

        # 3. Action alignment check
        if ticket.action_type != proposal.action_type:
            return HardwareTicketValidationResult(
                is_valid=False,
                status=HardwareExecutionStatus.ACTION_MISMATCH,
                action_valid=False,
                reasons=[
                    f"Action mismatch: Ticket authorizes '{ticket.action_type.value}', "
                    f"but requested action is '{proposal.action_type.value}'."
                ],
            )

        # 4. Target alignment check
        if ticket.target != proposal.target:
            return HardwareTicketValidationResult(
                is_valid=False,
                status=HardwareExecutionStatus.TARGET_MISMATCH,
                target_valid=False,
                action_valid=True,
                reasons=[
                    f"Target mismatch: Ticket authorizes target '{ticket.target}', "
                    f"but requested target is '{proposal.target}'."
                ],
            )

        # 5. Expiration check
        now = time.time()
        if now > ticket.expires_at:
            return HardwareTicketValidationResult(
                is_valid=False,
                status=HardwareExecutionStatus.EXPIRED_TICKET,
                expiry_valid=False,
                target_valid=True,
                action_valid=True,
                single_use_valid=True,
                reasons=[
                    f"Ticket '{ticket.ticket_id}' expired at {ticket.expires_at:.3f} (current time: {now:.3f})."
                ],
            )

        # 6. Cryptographic HMAC signature check
        expected_sig = self._compute_ticket_signature(
            ticket_id=ticket.ticket_id,
            proposal_id=ticket.proposal_id,
            action_type_value=ticket.action_type.value,
            target=ticket.target,
            expires_at=ticket.expires_at,
        )
        if not hmac.compare_digest(ticket.signature, expected_sig):
            return HardwareTicketValidationResult(
                is_valid=False,
                status=HardwareExecutionStatus.INVALID_TICKET,
                signature_valid=False,
                expiry_valid=True,
                target_valid=True,
                action_valid=True,
                single_use_valid=True,
                reasons=[f"Invalid cryptographic signature on ticket '{ticket.ticket_id}'."],
            )

        # 7. World state version drift (State-Bound Authorization check)
        if (
            current_world_version is not None
            and ticket.world_state_version > 0
            and current_world_version != ticket.world_state_version
        ):
            return HardwareTicketValidationResult(
                is_valid=False,
                status=HardwareExecutionStatus.INVALID_TICKET,
                signature_valid=True,
                expiry_valid=True,
                target_valid=True,
                action_valid=True,
                single_use_valid=True,
                context_valid=False,
                reasons=[
                    f"Stale authorization context: Ticket issued for world version {ticket.world_state_version}, "
                    f"but current world version is {current_world_version}."
                ],
            )

        # All checks passed
        return HardwareTicketValidationResult(
            is_valid=True,
            status=HardwareExecutionStatus.WAITING,
            signature_valid=True,
            expiry_valid=True,
            target_valid=True,
            action_valid=True,
            single_use_valid=True,
            context_valid=True,
            reasons=["All hardware-boundary validation checks satisfied."],
        )

    def verify_ticket(self, ticket: AuthorizationTicket) -> tuple[bool, str]:
        """Direct cryptographic HMAC verification of ticket signature."""
        action_val = ticket.action_type.value if hasattr(ticket.action_type, "value") else str(ticket.action_type)
        expected_sig = self._compute_ticket_signature(
            ticket_id=ticket.ticket_id,
            proposal_id=ticket.proposal_id,
            action_type_value=action_val,
            target=ticket.target,
            expires_at=ticket.expires_at,
        )
        if hmac.compare_digest(ticket.signature, expected_sig):
            return True, "Valid signature"
        return False, "Invalid cryptographic HMAC signature."

    def _compute_ticket_signature(
        self,
        ticket_id: str,
        proposal_id: str,
        action_type_value: str,
        target: str,
        expires_at: float,
    ) -> str:
        """Compute expected HMAC-SHA256 matching TicketAuthority and PhysicalActuator."""
        payload = f"{ticket_id}:{proposal_id}:{action_type_value}:{target}:{expires_at:.3f}".encode("utf-8")
        return hmac.new(self._secret_key, payload, hashlib.sha256).hexdigest()
