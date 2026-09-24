"""Physical actuator execution layer with cryptographic/ticket-gated authority enforcement."""

from typing import Optional
import time
import hmac
import hashlib

from motionfence.models.actions import (
    ActionProposal,
    ActionType,
    AuthorizationTicket,
    ExecutionResult,
)
from motionfence.models.world import ValveState
from motionfence.simulation.world import PhysicalWorld
from motionfence.simulation.exceptions import UnauthorizedActionError


class PhysicalActuator:
    """Hardware abstraction interface controlling simulated valves and physical plant.
    
    SECURITY INVARIANT:
    Direct execution without an authenticated, unconsumed AuthorizationTicket
    is mathematically and architecturally prohibited.
    """

    def __init__(self, world: PhysicalWorld, secret_key: str = "motionfence_runtime_kernel_secret") -> None:
        self.world = world
        self.secret_key = secret_key.encode("utf-8")

    def execute(
        self,
        proposal: ActionProposal,
        ticket: Optional[AuthorizationTicket],
    ) -> ExecutionResult:
        """Execute physical actuation strictly conditioned on a valid AuthorizationTicket."""
        v_before = self.world.version

        # Invariant 1: Ticket presence
        if ticket is None:
            raise UnauthorizedActionError(
                f"Execution rejected for proposal '{proposal.id}': Missing AuthorizationTicket. "
                "An ActionProposal possesses zero execution authority."
            )

        # Invariant 2: Ticket replay prevention
        if ticket.consumed:
            raise UnauthorizedActionError(
                f"Execution rejected: Ticket '{ticket.ticket_id}' has already been consumed."
            )

        # Invariant 3: Ticket proposal binding
        if ticket.proposal_id != proposal.id:
            raise UnauthorizedActionError(
                f"Execution rejected: Ticket proposal ID '{ticket.proposal_id}' does not match "
                f"proposal ID '{proposal.id}'."
            )

        # Invariant 4: Action and target alignment
        if ticket.action_type != proposal.action_type or ticket.target != proposal.target:
            raise UnauthorizedActionError(
                f"Execution rejected: Ticket authorization ({ticket.action_type.value} on {ticket.target}) "
                f"does not match requested action ({proposal.action_type.value} on {proposal.target})."
            )

        # Invariant 5: Ticket expiration
        if time.time() > ticket.expires_at:
            raise UnauthorizedActionError(
                f"Execution rejected: AuthorizationTicket '{ticket.ticket_id}' has expired."
            )

        # Invariant 6: Cryptographic / HMAC signature check
        expected_sig = self._compute_ticket_signature(
            ticket.ticket_id, ticket.proposal_id, ticket.action_type, ticket.target, ticket.expires_at
        )
        if not hmac.compare_digest(ticket.signature, expected_sig):
            raise UnauthorizedActionError(
                f"Execution rejected: Invalid ticket signature on ticket '{ticket.ticket_id}'."
            )

        # Ticket is valid - consume it immediately to prevent replay
        ticket.consumed = True

        # Check for simulated physical fault / mechanical jam
        if proposal.target in self.world.jammed_valves:
            # Physical failure: command was dispatched to actuator, but valve physically failed
            return ExecutionResult(
                success=False,
                action_id=proposal.id,
                ticket_id=ticket.ticket_id,
                executed_action=proposal.action_type,
                target=proposal.target,
                message=f"Mechanical failure: Actuator for {proposal.target} is jammed; valve did not seat.",
                state_version_before=v_before,
                state_version_after=self.world.version,
                timestamp=time.time(),
            )

        # Perform physical state transition
        if proposal.action_type == ActionType.CLOSE_VALVE:
            if proposal.target in self.world.valves:
                self.world.valves[proposal.target] = ValveState.CLOSED
                # If this valve is the leak line, closing it stops the leak
                if proposal.target == self.world.leak_target:
                    self.world.leak.active = False
                    self.world.leak.flow_rate_lpm = 0.0
                    self.world.leak.severity = 0.0
                self.world.version += 1
                self.world.last_updated = time.time()
                return ExecutionResult(
                    success=True,
                    action_id=proposal.id,
                    ticket_id=ticket.ticket_id,
                    executed_action=proposal.action_type,
                    target=proposal.target,
                    message=f"Valve {proposal.target} successfully closed.",
                    state_version_before=v_before,
                    state_version_after=self.world.version,
                    timestamp=time.time(),
                )
            else:
                return ExecutionResult(
                    success=False,
                    action_id=proposal.id,
                    ticket_id=ticket.ticket_id,
                    executed_action=proposal.action_type,
                    target=proposal.target,
                    message=f"Unknown valve target '{proposal.target}'.",
                    state_version_before=v_before,
                    state_version_after=self.world.version,
                    timestamp=time.time(),
                )

        elif proposal.action_type == ActionType.OPEN_VALVE:
            if proposal.target in self.world.valves:
                self.world.valves[proposal.target] = ValveState.OPEN
                if proposal.target == self.world.leak_target:
                    self.world.leak.active = True
                    self.world.leak.flow_rate_lpm = 14.2
                    self.world.leak.severity = 0.85
                self.world.version += 1
                self.world.last_updated = time.time()
                return ExecutionResult(
                    success=True,
                    action_id=proposal.id,
                    ticket_id=ticket.ticket_id,
                    executed_action=proposal.action_type,
                    target=proposal.target,
                    message=f"Valve {proposal.target} opened.",
                    state_version_before=v_before,
                    state_version_after=self.world.version,
                    timestamp=time.time(),
                )

        # Passive actions (INSPECT, GATHER_EVIDENCE) do not mutate valve state
        return ExecutionResult(
            success=True,
            action_id=proposal.id,
            ticket_id=ticket.ticket_id,
            executed_action=proposal.action_type,
            target=proposal.target,
            message=f"Observation/passive action '{proposal.action_type.value}' executed.",
            state_version_before=v_before,
            state_version_after=self.world.version,
            timestamp=time.time(),
        )

    def execute_raw_proposal(self, proposal: ActionProposal) -> ExecutionResult:
        """Direct call attempt by an unapproved proposal - strictly throws UnauthorizedActionError."""
        raise UnauthorizedActionError(
            f"SECURITY VIOLATION: Attempted direct execution of raw ActionProposal '{proposal.id}' "
            "without passing through MotionFence Policy Authorization."
        )

    def _compute_ticket_signature(
        self, ticket_id: str, proposal_id: str, action_type: ActionType, target: str, expires_at: float
    ) -> str:
        payload = f"{ticket_id}:{proposal_id}:{action_type.value}:{target}:{expires_at:.3f}".encode("utf-8")
        return hmac.new(self.secret_key, payload, hashlib.sha256).hexdigest()
