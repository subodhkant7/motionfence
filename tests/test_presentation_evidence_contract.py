"""Mutation checks for the backend contract consumed by the presentation."""
import json
from pathlib import Path

import pytest

from motionfence.runtime.controlled_demo import StageOutcome, evaluate_stage_outcome
from motionfence.runtime.live_demo import LiveDemoRecord, make_digital_twin_snapshot
from motionfence.simulation.world import PhysicalWorld
from motionfence.models.world import ValveState

FIXTURES = Path(__file__).parents[1] / 'motionfence' / 'fixtures' / 'live_validation'


def record(name):
    return LiveDemoRecord(**json.loads((FIXTURES / f'{name}.json').read_text()))


def test_scenario_name_never_authorizes_an_outcome():
    assert evaluate_stage_outcome(record('safe'), 'denied') == StageOutcome.NOMINAL
    assert evaluate_stage_outcome(record('denied'), 'safe') == StageOutcome.DENIED


def test_closed_recovery_snapshot_is_not_final_verification():
    rec = record('recovery')
    assert rec.post_state.valves['valve_b'] == 'CLOSED'
    assert evaluate_stage_outcome(rec) == StageOutcome.UNVERIFIED
    rec.recovery_result['outcome'] = 'FAILED'
    assert evaluate_stage_outcome(rec) == StageOutcome.VERIFICATION_FAILED


def recovery_with_proof():
    rec = record('recovery')
    safe = record('safe')
    rec.recovery_result['fresh_ticket'] = safe.ticket.model_dump()
    rec.recovery_result['fresh_ticket'].update(issued_at=rec.verification_result.timestamp + 0.1, expires_at=rec.verification_result.timestamp + 30)
    rec.recovery_result['retry_execution_result'] = safe.hardware_execution.model_dump(mode='json')
    rec.recovery_result['retry_execution_result']['timestamp'] = rec.verification_result.timestamp + 0.2
    final = safe.verification_result.model_dump(mode='json')
    final['timestamp'] = rec.verification_result.timestamp + 1
    rec.recovery_result['retry_verification_result'] = final
    return rec


def test_explicit_correlated_final_recovery_proof_can_pass():
    assert evaluate_stage_outcome(recovery_with_proof()) == StageOutcome.RECOVERED


@pytest.mark.parametrize('missing', ['timestamp', 'action_occurred', 'expected_postconditions', 'discrepancies'])
def test_missing_final_verification_fact_fails_closed(missing):
    rec = recovery_with_proof()
    del rec.recovery_result['retry_verification_result'][missing]
    assert evaluate_stage_outcome(rec) == StageOutcome.UNVERIFIED


@pytest.mark.parametrize('mutation', ['old_verification', 'no_fresh_ticket', 'no_execution', 'wrong_target', 'contradictory_readback'])
def test_mutating_one_recovery_fact_removes_success(mutation):
    rec = recovery_with_proof()
    final = rec.recovery_result['retry_verification_result']
    if mutation == 'old_verification':
        final['timestamp'] = rec.verification_result.timestamp
    elif mutation == 'no_fresh_ticket':
        del rec.recovery_result['fresh_ticket']
    elif mutation == 'no_execution':
        del rec.recovery_result['retry_execution_result']
    elif mutation == 'wrong_target':
        final['target'] = 'valve_a'
    else:
        final['observed_postconditions']['valves.valve_b'] = 'OPEN'
    assert evaluate_stage_outcome(rec) in (StageOutcome.UNVERIFIED, StageOutcome.VERIFICATION_FAILED)


def test_telemetry_route_cannot_bypass_verification():
    rec = record('telemetry')
    rec.verification_result = None
    assert evaluate_stage_outcome(rec) == StageOutcome.UNVERIFIED


def test_new_twin_pressure_is_a_recorded_sensor_reading():
    world = PhysicalWorld()
    snapshot = make_digital_twin_snapshot(world, 'test')
    reading = world.get_state().observations.get('pressure_main')
    assert snapshot.pressure_psi == (reading.reading.get('pressure_psi') if reading else None)


@pytest.mark.parametrize('mutation', ['wrong_action', 'wrong_target', 'premature_verification', 'expired_ticket', 'failed_policy_rule'])
def test_primary_evidence_correlation_mutations_fail_closed(mutation):
    rec = record('safe')
    if mutation == 'wrong_action':
        rec.verification_result.action_id = 'different-action'
    elif mutation == 'wrong_target':
        rec.verification_result.target = 'valve_a'
    elif mutation == 'premature_verification':
        rec.verification_result.timestamp = rec.hardware_execution.timestamp - 1
    elif mutation == 'expired_ticket':
        rec.ticket.expires_at = rec.ticket.issued_at
    else:
        rec.policy_decision.reasons[0].status = 'failed'
    assert evaluate_stage_outcome(rec) == StageOutcome.UNVERIFIED


@pytest.mark.parametrize('mutation', [
    'missing_valve', 'cooling_only', 'unsupported_null', 'extra_unknown_null',
    'wrong_target', 'wrong_valve_key', 'contradictory_world', 'explicit_failure',
    'missing_cooling', 'missing_leak', 'unresolvable_path', 'missing_action_id',
])
def test_p1_incomplete_valve_verification_never_proves_nominal(mutation):
    from motionfence.runtime.controlled_demo import _recorded_verification_passed
    rec = record('safe')
    verification = rec.verification_result
    expected, observed = verification.expected_postconditions, verification.observed_postconditions
    if mutation == 'missing_valve':
        del expected['valves.valve_b']
        del observed['valves.valve_b']
    elif mutation == 'cooling_only':
        verification.expected_postconditions = {'cooling': 'ACTIVE'}
        verification.observed_postconditions = {'cooling': 'ACTIVE'}
    elif mutation == 'unsupported_null':
        verification.expected_postconditions = {'invented.field': None}
        verification.observed_postconditions = {'invented.field': None}
    elif mutation == 'extra_unknown_null':
        expected['invented.field'] = observed['invented.field'] = None
    elif mutation == 'wrong_target':
        verification.target = 'valve_a'
    elif mutation == 'wrong_valve_key':
        expected['valves.valve_a'] = expected.pop('valves.valve_b')
        observed['valves.valve_a'] = observed.pop('valves.valve_b')
        rec.post_state.valves['valve_a'] = ValveState.CLOSED
    elif mutation == 'contradictory_world':
        rec.post_state.valves['valve_b'] = ValveState.OPEN
    elif mutation == 'explicit_failure':
        verification.status = 'VERIFICATION_FAILED'
    elif mutation == 'missing_action_id':
        rec.proposal.id = rec.ticket.proposal_id = verification.action_id = ''
    elif mutation == 'missing_cooling':
        del expected['cooling']
        del observed['cooling']
    elif mutation == 'missing_leak':
        del expected['leak.active']
        del observed['leak.active']
    else:
        expected['cooling.state'] = observed['cooling.state'] = None
    assert not _recorded_verification_passed(verification, rec)
    assert evaluate_stage_outcome(rec) not in (StageOutcome.NOMINAL, StageOutcome.RECOVERED)


def test_p1_complete_closure_and_legitimate_custom_paths_pass():
    rec = record('safe')
    rec.post_state.external_observations['custom'] = {'constructor': 'OEM', 'nullable': None, 'values': [1, True]}
    custom = {
        'observations.pressure_main.reading.pressure_psi': rec.post_state.observations['pressure_main'].reading['pressure_psi'],
        'external_observations.custom': {'constructor': 'OEM', 'nullable': None, 'values': [1, True]},
        'external_observations.custom.nullable': None,
        'external_observations.custom.constructor': 'OEM',
    }
    rec.verification_result.expected_postconditions.update(custom)
    rec.verification_result.observed_postconditions.update(custom)
    assert evaluate_stage_outcome(rec) == StageOutcome.NOMINAL
    rec.post_state.external_observations['custom']['values'][0] = 2
    assert evaluate_stage_outcome(rec) == StageOutcome.UNVERIFIED


def test_p1_open_valve_requires_the_open_target_state():
    from motionfence.models.actions import ActionType
    rec = record('safe')
    rec.proposal.action_type = rec.ticket.action_type = ActionType.OPEN_VALVE
    rec.hardware_execution.requested_action = 'OPEN_VALVE'
    rec.post_state.valves['valve_b'] = ValveState.OPEN
    rec.verification_result.expected_postconditions['valves.valve_b'] = 'OPEN'
    rec.verification_result.observed_postconditions['valves.valve_b'] = 'OPEN'
    assert evaluate_stage_outcome(rec) == StageOutcome.NOMINAL
    del rec.verification_result.expected_postconditions['valves.valve_b']
    del rec.verification_result.observed_postconditions['valves.valve_b']
    assert evaluate_stage_outcome(rec) == StageOutcome.UNVERIFIED


@pytest.mark.parametrize('proof', ['cooling_only', 'unknown_null', 'wrong_target_valve'])
def test_p1_recovery_requires_its_own_target_valve_postcondition(proof):
    rec = recovery_with_proof()
    final = rec.recovery_result['retry_verification_result']
    if proof == 'cooling_only':
        final['expected_postconditions'] = {'cooling': 'ACTIVE'}
        final['observed_postconditions'] = {'cooling': 'ACTIVE'}
    elif proof == 'unknown_null':
        final['expected_postconditions'] = {'invented.field': None}
        final['observed_postconditions'] = {'invented.field': None}
    else:
        final['expected_postconditions'] = {'valves.valve_a': 'OPEN', 'cooling': 'ACTIVE'}
        final['observed_postconditions'] = {'valves.valve_a': 'OPEN', 'cooling': 'ACTIVE'}
    assert evaluate_stage_outcome(rec) != StageOutcome.RECOVERED
