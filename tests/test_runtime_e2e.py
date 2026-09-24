"""End-to-end tests for the complete MotionFence runtime control loop."""

from motionfence.runtime.core import MotionFenceRuntime
from motionfence.simulation.world import PhysicalWorld
from motionfence.models.world import HumanZoneState, ValveState
from motionfence.models.events import EventType


def test_full_cycle_end_to_end_with_evidence_gathering():
    """End-to-end test of the complete Observe-Propose-Policy-Act-Verify loop."""
    world = PhysicalWorld(leak_target="valve_b")
    runtime = MotionFenceRuntime(world=world)

    # Run cycle with automatic additional evidence gathering on request
    result = runtime.run_cycle(
        intent="Isolate the leaking line while keeping cooling active.",
        gather_additional_evidence_on_request=True,
    )

    assert result.is_success
    assert result.policy_decision is not None
    assert result.policy_decision.is_allowed
    assert result.ticket is not None
    assert result.execution_result is not None
    assert result.execution_result.success is True
    assert result.verification_result is not None
    assert result.verification_result.is_verified

    # Physical world state must have transitioned
    assert world.valves["valve_b"] == ValveState.CLOSED
    assert world.leak.active is False

    # Event stream audit
    event_types = [e.event_type for e in result.events]
    assert EventType.INTENT_RECEIVED in event_types
    assert EventType.OBSERVATION_RECORDED in event_types
    assert EventType.ACTION_PROPOSED in event_types
    assert EventType.POLICY_EVALUATED in event_types
    assert EventType.MORE_EVIDENCE_REQUIRED in event_types
    assert EventType.ACTION_AUTHORIZED in event_types
    assert EventType.ACTION_EXECUTED in event_types
    assert EventType.POSTCONDITION_VERIFIED in event_types


def test_full_cycle_blocks_when_human_in_zone():
    """Runtime must abort actuation immediately when a human is in the exclusion zone."""
    world = PhysicalWorld(leak_target="valve_b")
    world.set_human_zone(HumanZoneState.OCCUPIED)
    runtime = MotionFenceRuntime(world=world)

    result = runtime.run_cycle(
        intent="Isolate leaking line.",
        gather_additional_evidence_on_request=False,
    )

    assert not result.is_success
    assert result.policy_decision.is_denied
    assert result.ticket is None
    assert result.execution_result is None
    assert result.verification_result is None

    # Valve must remain untouched
    assert world.valves["valve_b"] == ValveState.OPEN
    assert world.leak.active is True

    event_types = [e.event_type for e in result.events]
    assert EventType.ACTION_DENIED in event_types
    assert EventType.ACTION_AUTHORIZED not in event_types
    assert EventType.ACTION_EXECUTED not in event_types
