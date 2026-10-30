"""Mutation checks for the backend contract consumed by the presentation."""
import json
from pathlib import Path

import pytest

from motionfence.runtime.controlled_demo import StageOutcome, evaluate_stage_outcome
from motionfence.runtime.live_demo import LiveDemoRecord, make_digital_twin_snapshot
from motionfence.simulation.world import PhysicalWorld

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
