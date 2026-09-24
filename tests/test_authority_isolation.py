"""Security Invariant Tests: Proving that unapproved AI proposals cannot mutate WorldState."""

import time
import pytest

from motionfence.simulation.world import PhysicalWorld
from motionfence.simulation.actuator import PhysicalActuator
from motionfence.runtime.ticket import TicketAuthority
from motionfence.models.actions import ActionProposal, ActionType, AuthorizationTicket
from motionfence.models.world import ValveState
from motionfence.simulation.exceptions import UnauthorizedActionError


@pytest.fixture
def world() -> PhysicalWorld:
    return PhysicalWorld(leak_target="valve_b")


@pytest.fixture
def actuator(world: PhysicalWorld) -> PhysicalActuator:
    return PhysicalActuator(world)


@pytest.fixture
def ticket_auth() -> TicketAuthority:
    return TicketAuthority()


def test_unapproved_proposal_cannot_directly_execute(world: PhysicalWorld, actuator: PhysicalActuator):
    """Direct execution of an ActionProposal without runtime policy authorization is strictly blocked."""
    v_initial = world.version
    proposal = ActionProposal(
        action_type=ActionType.CLOSE_VALVE,
        target="valve_b",
        rationale="AI direct actuator bypass attempt.",
        model_confidence=0.99,
    )

    with pytest.raises(UnauthorizedActionError) as exc_info:
        actuator.execute_raw_proposal(proposal)

    assert "SECURITY VIOLATION" in str(exc_info.value)
    assert world.version == v_initial
    assert world.valves["valve_b"] == ValveState.OPEN


def test_actuator_rejects_missing_ticket(world: PhysicalWorld, actuator: PhysicalActuator):
    """Actuator call with ticket=None must raise UnauthorizedActionError and cause zero mutation."""
    v_initial = world.version
    proposal = ActionProposal(
        action_type=ActionType.CLOSE_VALVE,
        target="valve_b",
        rationale="Calling actuator with missing ticket.",
        model_confidence=0.95,
    )

    with pytest.raises(UnauthorizedActionError) as exc_info:
        actuator.execute(proposal, ticket=None)

    assert "Missing AuthorizationTicket" in str(exc_info.value)
    assert world.version == v_initial
    assert world.valves["valve_b"] == ValveState.OPEN


def test_actuator_rejects_forged_ticket_signature(
    world: PhysicalWorld, actuator: PhysicalActuator, ticket_auth: TicketAuthority
):
    """A maliciously fabricated or forged ticket signature must be rejected."""
    v_initial = world.version
    proposal = ActionProposal(
        action_type=ActionType.CLOSE_VALVE,
        target="valve_b",
        rationale="Forged authorization test.",
        model_confidence=0.95,
    )

    forged_ticket = AuthorizationTicket(
        ticket_id="tkt_forged_12345",
        proposal_id=proposal.id,
        action_type=proposal.action_type,
        target=proposal.target,
        expires_at=time.time() + 60.0,
        authorized_by="AdversarialAgent",
        signature="invalid_signature_hash_000000000000",
        consumed=False,
    )

    with pytest.raises(UnauthorizedActionError) as exc_info:
        actuator.execute(proposal, ticket=forged_ticket)

    assert "Invalid ticket signature" in str(exc_info.value)
    assert world.version == v_initial
    assert world.valves["valve_b"] == ValveState.OPEN


def test_actuator_rejects_replayed_ticket(
    world: PhysicalWorld, actuator: PhysicalActuator, ticket_auth: TicketAuthority
):
    """A ticket that has already been consumed cannot be replayed."""
    proposal = ActionProposal(
        action_type=ActionType.CLOSE_VALVE,
        target="valve_b",
        rationale="Replay attack test.",
        model_confidence=0.95,
    )
    ticket = ticket_auth.mint_ticket(proposal)

    # First execution succeeds
    res1 = actuator.execute(proposal, ticket)
    assert res1.success is True
    assert ticket.consumed is True
    v_after_first = world.version

    # Replay attempt with same ticket
    with pytest.raises(UnauthorizedActionError) as exc_info:
        actuator.execute(proposal, ticket)

    assert "already been consumed" in str(exc_info.value)
    assert world.version == v_after_first


def test_actuator_rejects_expired_ticket(
    world: PhysicalWorld, actuator: PhysicalActuator, ticket_auth: TicketAuthority
):
    """An expired authorization ticket must be rejected."""
    proposal = ActionProposal(
        action_type=ActionType.CLOSE_VALVE,
        target="valve_b",
        rationale="Expired ticket test.",
        model_confidence=0.95,
    )
    # Mint ticket with negative TTL (already expired)
    ticket = ticket_auth.mint_ticket(proposal, ttl_seconds=-5.0)

    with pytest.raises(UnauthorizedActionError) as exc_info:
        actuator.execute(proposal, ticket)

    assert "expired" in str(exc_info.value)
    assert world.valves["valve_b"] == ValveState.OPEN


def test_actuator_rejects_target_tampering(
    world: PhysicalWorld, actuator: PhysicalActuator, ticket_auth: TicketAuthority
):
    """A ticket authorized for Valve A cannot be used to actuate Valve B."""
    proposal_a = ActionProposal(
        action_type=ActionType.CLOSE_VALVE,
        target="valve_a",
        rationale="Authorized for Valve A.",
        model_confidence=0.95,
    )
    ticket_a = ticket_auth.mint_ticket(proposal_a)

    # Malicious proposal attempting to use Ticket A to close Valve B
    proposal_b = ActionProposal(
        id=proposal_a.id,  # Spoofing proposal ID
        action_type=ActionType.CLOSE_VALVE,
        target="valve_b",  # Different target!
        rationale="Unauthorized target switch.",
        model_confidence=0.95,
    )

    with pytest.raises(UnauthorizedActionError) as exc_info:
        actuator.execute(proposal_b, ticket_a)

    assert "does not match" in str(exc_info.value)
    assert world.valves["valve_b"] == ValveState.OPEN


def test_actuator_rejects_action_type_tampering(
    world: PhysicalWorld, actuator: PhysicalActuator, ticket_auth: TicketAuthority
):
    """A ticket authorized for INSPECT cannot be used to CLOSE_VALVE."""
    proposal_inspect = ActionProposal(
        action_type=ActionType.INSPECT,
        target="valve_b",
        rationale="Authorized only for inspection.",
        model_confidence=0.95,
    )
    ticket_inspect = ticket_auth.mint_ticket(proposal_inspect)

    proposal_close = ActionProposal(
        id=proposal_inspect.id,
        action_type=ActionType.CLOSE_VALVE,  # Escalated action!
        target="valve_b",
        rationale="Privilege escalation.",
        model_confidence=0.95,
    )

    with pytest.raises(UnauthorizedActionError) as exc_info:
        actuator.execute(proposal_close, ticket_inspect)

    assert "does not match" in str(exc_info.value)
    assert world.valves["valve_b"] == ValveState.OPEN
