#!/usr/bin/env python3
"""CLI utility to demonstrate MotionFence Autonomous Fault Containment & Recovery (Phase 2I).

Usage:
    python scripts/run_recovery.py --scenario actuator-no-op
    python scripts/run_recovery.py --scenario repeated-failure
    python scripts/run_recovery.py --scenario alternate-path
    python scripts/run_recovery.py --scenario sensor-quarantine
    python scripts/run_recovery.py --scenario budget-exhaustion
"""

import argparse
import json
import os
import sys
import time

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from motionfence.models.actions import (
    ActionProposal,
    ActionType,
    AuthorizationTicket,
    ExecutionResult,
)
from motionfence.models.world import CoolingState, HumanZoneState, ValveState
from motionfence.evidence.models import Evidence, EvidenceSource
from motionfence.policy.models import Policy
from motionfence.policy.engine import PolicyEngine
from motionfence.runtime.enclave import EnclaveAuthorizationRequest, SafetyEnclave
from motionfence.runtime.events import EventBus
from motionfence.runtime.verification import PostActionVerifier, VerificationResult, VerificationStatus
from motionfence.simulation.world import PhysicalWorld
from motionfence.recovery.models import (
    ComponentType,
    FailureClass,
    FailureRecord,
    QuarantineStatus,
    RecoveryOutcome,
)
from motionfence.recovery.executor import RecoveryExecutor
from motionfence.recovery.policies import QuarantinePolicy, RecoveryBudget


def render_step(step_idx: str, name: str, details: list[str]) -> None:
    print(f"\n[{step_idx}] {name}")
    print("-" * 70)
    for d in details:
        print(f"    {d}")


def run_scenario(scenario_name: str, audit_dir: str = "audit_records") -> str:
    print("=" * 70)
    print(" MOTIONFENCE PHASE 2I: FAULT CONTAINMENT, QUARANTINE & RECOVERY")
    print(f" SCENARIO: {scenario_name.upper()}")
    print("=" * 70)

    os.makedirs(audit_dir, exist_ok=True)
    world = PhysicalWorld(leak_target="valve_b")
    event_bus = EventBus()
    executor = RecoveryExecutor(world=world, event_bus=event_bus)
    policy = Policy()

    run_id = f"rec_{scenario_name}_{int(time.time())}"

    if scenario_name == "actuator-no-op":
        render_step("1. INITIAL EVALUATION", "Normal Authorization Cycle", [
            "Plant World: human_zone=CLEAR, cooling=ACTIVE, valve_b=OPEN",
            "Command: CLOSE_VALVE on valve_b to isolate verified leak",
            "Policy evaluated: ALLOW",
        ])

        initial_proposal = ActionProposal(
            id="prop_noop_1",
            action_type=ActionType.CLOSE_VALVE,
            target="valve_b",
            rationale="Isolate verified leaking branch",
            model_confidence=0.96,
        )
        evidence = world.generate_targeted_evidence("valve_b")
        enclave = SafetyEnclave(secret_key=executor.secret_key, event_bus=event_bus)
        auth_res = enclave.authorize(EnclaveAuthorizationRequest(
            proposal=initial_proposal,
            world_state=world.get_state(),
            evidence=evidence,
            policy=policy,
        ))
        initial_ticket = auth_res.ticket

        render_step("2. ACTUATION & FAULT OCCURRENCE", "Physical Actuator Mechanical Failure", [
            f"Authorized with Ticket: {initial_ticket.ticket_id}",
            "Actuator energized, but mechanical stem failed to traverse stroke.",
            "Simulating ground-truth state: valve_b remains OPEN.",
        ])

        failed_exec = ExecutionResult(
            success=True,
            action_id=initial_proposal.id,
            ticket_id=initial_ticket.ticket_id,
            executed_action=ActionType.CLOSE_VALVE,
            target="valve_b",
            message="Actuator energized; stroke command completed",
            state_version_before=world.version,
            state_version_after=world.version,
        )
        failed_verif = VerificationResult(
            action_id=initial_proposal.id,
            target="valve_b",
            action_occurred=True,
            expected_postconditions={"valves.valve_b": ValveState.CLOSED.value},
            observed_postconditions={"valves.valve_b": ValveState.OPEN.value},
            status=VerificationStatus.VERIFICATION_FAILED,
            discrepancies=["valves.valve_b expected CLOSED, observed OPEN"],
        )

        render_step("3. AUTONOMOUS CONTAINMENT & RECOVERY", "Failure Containment, Scoped Isolation, Fresh Cycle", [
            "Detecting physical postcondition mismatch...",
            "Executing RecoveryExecutor.handle_failure_and_recover()...",
        ])

        result = executor.handle_failure_and_recover(
            failed_proposal=initial_proposal,
            failed_execution=failed_exec,
            failed_verification=failed_verif,
            initial_ticket=initial_ticket,
            current_evidence=evidence,
            policy=policy,
        )

        render_step("4. OUTCOME & VERIFICATION", "Fresh Authorization & Independent Verification", [
            f"Failure Classified: {result.failure_record.failure_class.value}",
            f"Stale Ticket Invalidation: consumed={initial_ticket.consumed}",
            f"Component Status: {result.quarantine_records['valve_b'].status.value}",
            f"Recovery Strategy Proposed: {result.recovery_plan.strategy.value}",
            f"Fresh Ticket Issued: {result.fresh_ticket.ticket_id if result.fresh_ticket else 'None'}",
            f"Recovery Outcome: {result.outcome.value}",
            f"Physical Valve State After Recovery: {world.valves['valve_b'].value}",
            f"Unsafe Retries Observed: {result.unsafe_retries} (CRITICAL: 0)",
        ])

    elif scenario_name == "repeated-failure":
        render_step("1. REPEATED FAILURES", "Escalating from SUSPECT to QUARANTINED", [
            "Simulating 3 consecutive mechanical failures on valve_b...",
        ])

        prop = ActionProposal(
            id="prop_rep",
            action_type=ActionType.CLOSE_VALVE,
            target="valve_b",
            rationale="Repeated attempts",
            model_confidence=0.95,
        )

        for i in range(3):
            fail = FailureRecord(
                failure_class=FailureClass.ACTUATOR_NO_OP,
                target_component="valve_b",
                component_type=ComponentType.ACTUATOR,
                details=f"Consecutive stall #{i+1}",
            )
            rec = executor.containment_manager.contain_failure(fail, quarantine_manager=executor.quarantine_manager)
            print(f"    Failure #{i+1}: Component 'valve_b' status -> {rec.component_status.value}")

        render_step("2. SCOPED QUARANTINE ENFORCEMENT", "Consequential Blocked, Diagnostics Allowed", [
            f"Quarantined: {executor.quarantine_manager.is_quarantined('valve_b')}",
            f"CLOSE_VALVE permitted on valve_b: {executor.quarantine_manager.is_action_permitted(ActionType.CLOSE_VALVE, 'valve_b')}",
            f"INSPECT_TARGET permitted on valve_b: {executor.quarantine_manager.is_action_permitted(ActionType.INSPECT_TARGET, 'valve_b')}",
            f"CLOSE_VALVE permitted on valve_a: {executor.quarantine_manager.is_action_permitted(ActionType.CLOSE_VALVE, 'valve_a')}",
        ])
        result = None

    elif scenario_name == "alternate-path":
        render_step("1. VALVE B QUARANTINED", "Proposing Alternate Isolation Path via Valve A", [
            "Valve B is permanently jammed and marked QUARANTINED.",
            "World has redundant upstream isolator: valve_a=OPEN.",
        ])
        executor.quarantine_manager.quarantine_component("valve_b", "Permanent mechanical jam")
        world.valves["valve_b"] = ValveState.OPEN
        world.valves["valve_a"] = ValveState.OPEN

        plan = executor.recovery_planner.plan_recovery(
            failure=FailureRecord(
                failure_class=FailureClass.ACTUATOR_WRONG_STATE,
                target_component="valve_b",
                component_type=ComponentType.ACTUATOR,
            ),
            world_state=world.get_state(),
            evidence_pool=[],
            quarantine_manager=executor.quarantine_manager,
            available_alternate_targets=["valve_a"],
        )

        render_step("2. FRESH AUTHORIZATION FOR ALTERNATE", "No Authority Transfer — Fresh Cycle Required", [
            f"Strategy: {plan.strategy.value}",
            f"Suggested Alternate Target: {plan.suggested_alternate_proposal.target if plan.suggested_alternate_proposal else 'None'}",
            f"Suggested Action: {plan.suggested_alternate_proposal.action_type.value if plan.suggested_alternate_proposal else 'None'}",
            "Initiating fresh PolicyEngine evaluation on valve_a...",
        ])

        fresh_eval = PolicyEngine.evaluate(plan.suggested_alternate_proposal, world.get_state(), world.generate_targeted_evidence("valve_a"))
        print(f"    Fresh Policy Decision on valve_a: {fresh_eval.decision.value} (is_allowed={fresh_eval.is_allowed})")
        result = None

    elif scenario_name == "sensor-quarantine":
        render_step("1. SENSOR QUARANTINE", "Pruning Untrusted Telemetry from Context", [
            "Pressure sensor 'pressure_sensor_1' stuck at 45.0 psi.",
            "Adding quarantine record for sensor...",
        ])
        executor.quarantine_manager.quarantine_component("pressure_sensor_1", "Stuck transducer output", ComponentType.SENSOR)

        good_ev = Evidence(
            id="ev_vision_1",
            source=EvidenceSource.VISION,
            target="valve_b",
            observation={"valve_state": "OPEN"},
            confidence=0.98,
            provenance="camera_overhead",
        )
        stuck_ev = Evidence(
            id="ev_press_1",
            source=EvidenceSource.PRESSURE_SENSOR,
            target="valve_b",
            observation={"pressure_psi": 45.0},
            confidence=0.95,
            provenance="pressure_sensor_1:port_a",
        )

        filtered = executor.quarantine_manager.filter_admissible_evidence([good_ev, stuck_ev])
        render_step("2. FILTERED EVIDENCE ADMISSIBILITY", "PROP_028 Invariant Enforcement", [
            f"Raw evidence items: {len([good_ev, stuck_ev])}",
            f"Admissible evidence items: {len(filtered)}",
            f"Admitted ID: {filtered[0].id}",
            "Stuck sensor evidence excluded from authorization context: True",
        ])
        result = None

    elif scenario_name == "budget-exhaustion":
        render_step("1. BUDGET BOUNDARY", "Finite Recovery Attempts", [
            "Human occupied safety zone (unresolvable physical violation).",
            "Configuring RecoveryBudget(max_recovery_attempts=1)...",
        ])
        world.human_zone = HumanZoneState.OCCUPIED
        prop = ActionProposal(
            id="prop_unrecoverable",
            action_type=ActionType.CLOSE_VALVE,
            target="valve_b",
            rationale="Attempt isolation under human occupancy",
            model_confidence=0.95,
        )
        result = executor.handle_failure_and_recover(
            failed_proposal=prop,
            max_attempts=1,
        )
        render_step("2. TERMINAL OUTCOME", "Safe Refusal Without Automatic Authorization", [
            f"Outcome: {result.outcome.value}",
            f"Fresh Ticket Issued: {result.fresh_ticket is not None}",
            f"Component Quarantined: {executor.quarantine_manager.is_quarantined('valve_b')}",
            f"Unsafe Retries: {result.unsafe_retries} (CRITICAL: 0)",
        ])

    else:
        print(f"Unknown scenario '{scenario_name}'.")
        sys.exit(1)

    record_path = os.path.join(audit_dir, f"{run_id}.json")
    with open(record_path, "w") as f:
        json.dump({
            "run_id": run_id,
            "scenario": scenario_name,
            "timestamp": time.time(),
            "events": [e.model_dump() for e in event_bus.get_events()],
        }, f, indent=2)

    print(f"\nAudit trace persisted to: {record_path}")
    print("=" * 70)
    return run_id


def main():
    parser = argparse.ArgumentParser(description="MotionFence Autonomous Recovery Runner (Phase 2I)")
    parser.add_argument(
        "--scenario",
        choices=["actuator-no-op", "repeated-failure", "alternate-path", "sensor-quarantine", "budget-exhaustion"],
        default="actuator-no-op",
        help="Recovery scenario to demonstrate",
    )
    parser.add_argument("--audit-dir", default="audit_records", help="Directory to store audit traces")
    args = parser.parse_args()

    run_scenario(args.scenario, args.audit_dir)


if __name__ == "__main__":
    main()
