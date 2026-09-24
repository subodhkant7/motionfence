"""Tests for stateful physical simulator dynamics and state transitions."""

import pytest

from motionfence.simulation.world import PhysicalWorld
from motionfence.simulation.actuator import PhysicalActuator
from motionfence.runtime.ticket import TicketAuthority
from motionfence.models.actions import ActionProposal, ActionType
from motionfence.models.world import ValveState, HumanZoneState
from motionfence.simulation.exceptions import UnauthorizedActionError


@pytest.fixture
def world() -> PhysicalWorld:
    return PhysicalWorld(leak_target="valve_b", leak_severity=0.85)


@pytest.fixture
def actuator(world: PhysicalWorld) -> PhysicalActuator:
    return PhysicalActuator(world)


@pytest.fixture
def ticket_auth() -> TicketAuthority:
    return TicketAuthority()


def test_valid_close_action_mutates_state(world: PhysicalWorld, actuator: PhysicalActuator, ticket_auth: TicketAuthority):
    """An authorized close action must physically transition the valve from OPEN to CLOSED."""
    assert world.valves["valve_b"] == ValveState.OPEN
    assert world.leak.active is True

    proposal = ActionProposal(
        action_type=ActionType.CLOSE_VALVE,
        target="valve_b",
        rationale="Authorized isolation.",
        model_confidence=0.95,
    )
    ticket = ticket_auth.mint_ticket(proposal)

    result = actuator.execute(proposal, ticket)
    assert result.success is True
    assert world.valves["valve_b"] == ValveState.CLOSED
    assert world.leak.active is False
    assert world.leak.flow_rate_lpm == 0.0


def test_valid_open_action_mutates_state(world: PhysicalWorld, actuator: PhysicalActuator, ticket_auth: TicketAuthority):
    """An authorized open action must transition the valve to OPEN."""
    world.valves["valve_a"] = ValveState.CLOSED

    proposal = ActionProposal(
        action_type=ActionType.OPEN_VALVE,
        target="valve_a",
        rationale="Re-opening valve A.",
        model_confidence=0.95,
    )
    ticket = ticket_auth.mint_ticket(proposal)

    result = actuator.execute(proposal, ticket)
    assert result.success is True
    assert world.valves["valve_a"] == ValveState.OPEN


def test_denied_or_missing_ticket_does_not_mutate_state(world: PhysicalWorld, actuator: PhysicalActuator):
    """An action attempted without an authorization ticket cannot mutate world state."""
    v_before = world.version
    proposal = ActionProposal(
        action_type=ActionType.CLOSE_VALVE,
        target="valve_b",
        rationale="Unauthorized attempt.",
        model_confidence=0.99,
    )

    with pytest.raises(UnauthorizedActionError):
        actuator.execute(proposal, ticket=None)

    # World state must remain unchanged
    assert world.valves["valve_b"] == ValveState.OPEN
    assert world.leak.active is True
    assert world.version == v_before


def test_mechanical_jam_leaves_incorrect_state(world: PhysicalWorld, actuator: PhysicalActuator, ticket_auth: TicketAuthority):
    """When a valve experiences mechanical failure, execution fails and state does not change."""
    world.inject_valve_jam("valve_b")
    v_before = world.version

    proposal = ActionProposal(
        action_type=ActionType.CLOSE_VALVE,
        target="valve_b",
        rationale="Authorized close on jammed valve.",
        model_confidence=0.95,
    )
    ticket = ticket_auth.mint_ticket(proposal)

    result = actuator.execute(proposal, ticket)
    assert result.success is False
    assert "jammed" in result.message
    # State must not have updated to CLOSED
    assert world.valves["valve_b"] == ValveState.OPEN
    assert world.version == v_before


def test_environment_changes_human_zone(world: PhysicalWorld):
    """Stateful environment correctly reflects dynamic physical events."""
    assert world.human_zone == HumanZoneState.CLEAR
    state1 = world.get_state()
    assert not state1.is_human_present()

    world.set_human_zone(HumanZoneState.OCCUPIED)
    state2 = world.get_state()
    assert state2.is_human_present()
    assert state2.human_zone == HumanZoneState.OCCUPIED
    assert state2.version > state1.version
