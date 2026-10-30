"""Tests for the post-action verification gate."""

import pytest

from motionfence.runtime.verification import PostActionVerifier, VerificationStatus
from motionfence.models.actions import ActionProposal, ActionType, ExecutionResult
from motionfence.models.world import WorldState, ValveState, CoolingState, LeakState


@pytest.fixture
def proposal() -> ActionProposal:
    return ActionProposal(
        action_type=ActionType.CLOSE_VALVE,
        target="valve_b",
        rationale="Close leaking valve.",
        model_confidence=0.95,
    )


def test_successful_postcondition_verification(proposal: ActionProposal):
    """When actual post-state satisfies all postconditions, verification succeeds."""
    pre_state = WorldState(
        valves={"valve_a": ValveState.OPEN, "valve_b": ValveState.OPEN},
        cooling=CoolingState.ACTIVE,
        leak=LeakState(active=True, target="valve_b"),
    )
    post_state = WorldState(
        valves={"valve_a": ValveState.OPEN, "valve_b": ValveState.CLOSED},
        cooling=CoolingState.ACTIVE,
        leak=LeakState(active=False, target="valve_b"),
    )
    execution = ExecutionResult(
        success=True,
        action_id=proposal.id,
        executed_action=proposal.action_type,
        target=proposal.target,
        message="Closed successfully.",
        state_version_before=1,
        state_version_after=2,
    )

    result = PostActionVerifier.verify(proposal, execution, pre_state, post_state)
    assert result.status == VerificationStatus.VERIFIED
    assert result.is_verified
    assert len(result.discrepancies) == 0


def test_failed_postcondition_when_valve_remains_open(proposal: ActionProposal):
    """If valve remained OPEN despite execution, verification must fail."""
    pre_state = WorldState(
        valves={"valve_b": ValveState.OPEN},
        cooling=CoolingState.ACTIVE,
    )
    # The world did NOT change to CLOSED (e.g. valve stuck)
    post_state = WorldState(
        valves={"valve_b": ValveState.OPEN},
        cooling=CoolingState.ACTIVE,
    )
    execution = ExecutionResult(
        success=True,  # Signal was sent
        action_id=proposal.id,
        executed_action=proposal.action_type,
        target=proposal.target,
        message="Signal sent.",
        state_version_before=1,
        state_version_after=2,
    )

    result = PostActionVerifier.verify(proposal, execution, pre_state, post_state)
    assert result.status == VerificationStatus.VERIFICATION_FAILED
    assert not result.is_verified
    assert any("valves.valve_b" in d for d in result.discrepancies)


def test_failed_postcondition_when_actuator_fails(proposal: ActionProposal):
    """When actuator reports failure, verification must reflect failure."""
    pre_state = WorldState(valves={"valve_b": ValveState.OPEN})
    post_state = WorldState(valves={"valve_b": ValveState.OPEN})

    execution = ExecutionResult(
        success=False,
        action_id=proposal.id,
        executed_action=proposal.action_type,
        target=proposal.target,
        message="Actuator jammed.",
        state_version_before=1,
        state_version_after=1,
    )

    result = PostActionVerifier.verify(proposal, execution, pre_state, post_state)
    assert result.status == VerificationStatus.VERIFICATION_FAILED
    assert any("jammed" in d for d in result.discrepancies)


def test_failed_postcondition_when_cooling_invariant_compromised(proposal: ActionProposal):
    """If cooling becomes inactive after actuation, verification must fail."""
    pre_state = WorldState(
        valves={"valve_b": ValveState.OPEN},
        cooling=CoolingState.ACTIVE,
    )
    post_state = WorldState(
        valves={"valve_b": ValveState.CLOSED},
        cooling=CoolingState.INACTIVE,  # Invariant violated!
    )
    execution = ExecutionResult(
        success=True,
        action_id=proposal.id,
        executed_action=proposal.action_type,
        target=proposal.target,
        message="Closed.",
        state_version_before=1,
        state_version_after=2,
    )

    result = PostActionVerifier.verify(proposal, execution, pre_state, post_state)
    assert result.status == VerificationStatus.VERIFICATION_FAILED
    assert any("cooling" in d for d in result.discrepancies)


@pytest.mark.parametrize('path, value', [
    ('invented.field', None), ('cooling.state', None), ('model_dump', None),
    ('valves.valve_b', 'OPEN'), ('cooling', 'INACTIVE'), ('leak.active', True),
])
def test_custom_postconditions_cannot_use_missing_paths_or_override_invariants(proposal, path, value):
    pre = WorldState(valves={'valve_b': ValveState.OPEN}, leak=LeakState(active=True, target='valve_b'))
    post = WorldState(valves={'valve_b': ValveState.CLOSED}, leak=LeakState(active=False, target='valve_b'))
    execution = ExecutionResult(success=True, action_id=proposal.id, executed_action=proposal.action_type,
                                target=proposal.target, message='closed', state_version_before=1, state_version_after=2)
    result = PostActionVerifier.verify(proposal, execution, pre, post, {path: value})
    assert result.status == VerificationStatus.VERIFICATION_FAILED
    assert result.discrepancies


def test_resolvable_custom_scalar_structured_and_null_values_remain_supported(proposal):
    pre = WorldState(valves={'valve_b': ValveState.OPEN})
    post = WorldState(valves={'valve_b': ValveState.CLOSED}, external_observations={'custom': {'nullable': None, 'values': [1, True]}})
    execution = ExecutionResult(success=True, action_id=proposal.id, executed_action=proposal.action_type,
                                target=proposal.target, message='closed', state_version_before=1, state_version_after=2)
    result = PostActionVerifier.verify(proposal, execution, pre, post, {
        'external_observations.custom': {'nullable': None, 'values': [1, True]},
        'external_observations.custom.nullable': None, 'valves.valve_b': 'CLOSED',
    })
    assert result.status == VerificationStatus.VERIFIED
    assert not result.discrepancies
