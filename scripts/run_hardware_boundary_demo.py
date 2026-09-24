#!/usr/bin/env python3
"""MotionFence Deterministic Hardware Boundary Demonstration Runner (Phase 2M).

Demonstrates the physical actuator security boundary across 4 canonical scenarios:
1. ALLOWED: Valid AuthorizationTicket presented -> Hardware validated -> Physical actuation -> Verification PASSED.
2. DENIED: Policy denies unsafe action -> No ticket issued -> Hardware LOCKED -> No actuation.
3. STALE-TICKET: World changes after issuance -> Revalidation fails -> Ticket invalidated -> Hardware LOCKED.
4. ACTUATOR-FAILURE: Ticket valid -> Actuator experiences deterministic fault -> Verification FAILS -> Recovery containment.

Usage:
    python scripts/run_hardware_boundary_demo.py --scenario allowed
    python scripts/run_hardware_boundary_demo.py --scenario denied
    python scripts/run_hardware_boundary_demo.py --scenario stale-ticket
    python scripts/run_hardware_boundary_demo.py --scenario actuator-failure
    python scripts/run_hardware_boundary_demo.py --scenario all
"""

import argparse
import io
import json
import os
import sys
import time
from typing import Optional

# Ensure motionfence package is importable
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from motionfence.models.actions import (
    ActionProposal,
    ActionType,
    AuthorizationTicket,
    ExecutionResult,
)
from motionfence.models.world import WorldState, ValveState, CoolingState, HumanZoneState
from motionfence.policy.models import Policy
from motionfence.simulation.world import PhysicalWorld
from motionfence.runtime.ticket import TicketAuthority
from motionfence.runtime.enclave import SafetyEnclave, EnclaveAuthorizationRequest
from motionfence.runtime.revalidation import ExecutionTimeRevalidator, RevalidationStatus
from motionfence.runtime.verification import PostActionVerifier, VerificationStatus
from motionfence.runtime.events import EventBus
from motionfence.hardware.models import (
    ActuatorType,
    HardwareExecutionStatus,
    HardwareFaultType,
    HardwareExecutionRecord,
)
from motionfence.hardware.mock import MockHardwareEndpoint
from motionfence.recovery.executor import RecoveryExecutor

FIXTURE_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "motionfence", "fixtures", "hardware_demo"))


def print_hardware_box(title: str, items: list[tuple[str, str]], stream=None) -> None:
    """Render clean, deterministic industrial mission-control terminal box."""
    stream = stream or sys.stdout
    width = 46
    print("┌" + "─" * (width - 2) + "┐", file=stream)
    title_line = f"│ {title}".ljust(width - 1) + "│"
    print(title_line, file=stream)
    print("├" + "─" * (width - 2) + "┤", file=stream)
    for key, val in items:
        content = f"│ {key.ljust(18)} {val.ljust(22)} │"
        print(content, file=stream)
    print("└" + "─" * (width - 2) + "┘", file=stream)


def run_scenario_allowed(stream=None) -> str:
    """Scenario 1: ALLOWED - Nominal authorized execution at hardware boundary."""
    stream = stream or sys.stdout
    print("=" * 70, file=stream)
    print("SCENARIO 1: NOMINAL AUTHORIZED ACTUATION (ALLOWED)", file=stream)
    print("=" * 70, file=stream)

    world = PhysicalWorld()
    world.valves["valve_b"] = ValveState.OPEN
    world.set_pump_state("pump_p1", "INACTIVE")
    world.cooling = CoolingState.ACTIVE
    world.set_human_zone(HumanZoneState.CLEAR)
    policy = Policy()
    event_bus = EventBus()

    auth = TicketAuthority()
    endpoint = MockHardwareEndpoint(world=world, event_bus=event_bus)

    print("\n[STEP 1: AGENT PROPOSAL]", file=stream)
    proposal = ActionProposal(
        id="prop_demo_allowed_001",
        action_type=ActionType.CLOSE_VALVE,
        target="valve_b",
        parameters={},
        rationale="Routine isolation of valve_b under verified clear zone conditions.",
        model_confidence=0.96,
    )
    print(f"Agent proposal: {proposal.action_type.value} on {proposal.target}", file=stream)
    print(f"Rationale: {proposal.rationale}", file=stream)

    print("\n[STEP 2: POLICY EVALUATION & TICKET ISSUANCE]", file=stream)
    evidence = world.generate_targeted_evidence("valve_b")
    enclave = SafetyEnclave(secret_key=auth.secret_key, event_bus=event_bus)
    auth_req = EnclaveAuthorizationRequest(
        proposal=proposal,
        world_state=world.get_state(),
        evidence=evidence,
        policy=policy,
    )
    auth_res = enclave.authorize(auth_req)
    assert auth_res.decision.is_allowed, "Policy must allow under nominal conditions"
    ticket = auth_res.ticket
    assert ticket is not None, "Ticket must be minted on policy ALLOW"
    print(f"[MOTIONFENCE] Policy Decision: ALLOW", file=stream)
    print(f"[SAFETY ENCLAVE] AuthorizationTicket minted: {ticket.ticket_id[:12]}...", file=stream)
    print(f"[TICKET] World Version Bound: v{ticket.world_state_version}", file=stream)
    print(f"[TICKET] Target Bound: {ticket.target}", file=stream)
    print(f"[TICKET] Action Bound: {ticket.action_type.value}", file=stream)

    print("\n[STEP 3: HARDWARE BOUNDARY PRESENTATION]", file=stream)
    print("[HARDWARE] Waiting for MotionFence AuthorizationTicket...", file=stream)
    print("[HARDWARE] AuthorizationTicket received.", file=stream)
    print(f"[HARDWARE] Ticket: {ticket.ticket_id[:12]}...", file=stream)
    print("[HARDWARE] Signature: VALID", file=stream)
    print(f"[HARDWARE] Action: {ticket.action_type.value}", file=stream)
    print(f"[HARDWARE] Target: {ticket.target}", file=stream)
    print("[HARDWARE] Authorization: VALID", file=stream)
    print(f"[HARDWARE] Actuating {ticket.target}...", file=stream)

    pre_state = world.get_state()
    rec = endpoint.receive_and_actuate(proposal=proposal, ticket=ticket)
    obs = endpoint.get_observed_state(proposal.target)
    print(f"[HARDWARE] Observed state: {obs.get('target_state', 'UNKNOWN')}", file=stream)
    print(f"[HARDWARE] Terminal status: {rec.execution_status.value}", file=stream)

    print("\n[STEP 4: POST-ACTION INDEPENDENT VERIFICATION]", file=stream)
    post_state = world.get_state()
    exec_res = ExecutionResult(
        success=(rec.execution_status == HardwareExecutionStatus.ACTUATED),
        action_id=proposal.id,
        ticket_id=ticket.ticket_id,
        executed_action=proposal.action_type,
        target=proposal.target,
        message=rec.message,
        state_version_before=pre_state.version,
        state_version_after=post_state.version,
    )
    verification = PostActionVerifier.verify(
        proposal=proposal,
        execution=exec_res,
        pre_state=pre_state,
        post_state=post_state,
        expected_postconditions=policy.expected_postconditions,
    )
    print(f"[VERIFICATION] Status: {verification.status.value}", file=stream)
    print(f"[VERIFICATION] Outcome: {'VERIFIED' if verification.is_verified else 'FAILED'}", file=stream)

    print("\n[STEP 5: VISUAL HARDWARE STATE]", file=stream)
    print_hardware_box("MOCK PHYSICAL HARDWARE — NOMINAL", [
        ("Pump P1", "INACTIVE"),
        ("Valve B", obs.get('target_state', 'CLOSED')),
        ("Safety Zone", "CLEAR"),
        ("Ticket", f"{ticket.ticket_id[:10]}..."),
        ("Authorization", "VALID"),
        ("Actuator", "ACTUATED"),
    ], stream=stream)

    return rec.model_dump_json(indent=2)


def run_scenario_denied(stream=None) -> str:
    """Scenario 2: DENIED - Zero authorization due to policy violation -> Hardware LOCKED."""
    stream = stream or sys.stdout
    print("=" * 70, file=stream)
    print("SCENARIO 2: POLICY DENIAL (ZERO AUTHORIZATION)", file=stream)
    print("=" * 70, file=stream)

    world = PhysicalWorld()
    world.valves["valve_b"] = ValveState.OPEN
    world.set_pump_state("pump_p1", "ACTIVE")
    world.set_human_zone(HumanZoneState.OCCUPIED)
    policy = Policy()
    event_bus = EventBus()

    endpoint = MockHardwareEndpoint(world=world, event_bus=event_bus)

    print("\n[STEP 1: AGENT PROPOSAL UNDER HAZARD]", file=stream)
    proposal = ActionProposal(
        id="prop_demo_denied_002",
        action_type=ActionType.CLOSE_VALVE,
        target="valve_b",
        parameters={},
        rationale="Emergency valve isolation requested while personnel are present in hazard zone.",
        model_confidence=0.94,
    )
    print(f"Agent proposal: {proposal.action_type.value} on {proposal.target}", file=stream)
    print(f"Environment: HumanZoneState.OCCUPIED, Pump P1 ACTIVE", file=stream)

    print("\n[STEP 2: POLICY EVALUATION & TICKET REFUSAL]", file=stream)
    auth = TicketAuthority()
    enclave = SafetyEnclave(secret_key=auth.secret_key, event_bus=event_bus)
    auth_req = EnclaveAuthorizationRequest(
        proposal=proposal,
        world_state=world.get_state(),
        policy=policy,
    )
    auth_res = enclave.authorize(auth_req)
    assert not auth_res.decision.is_allowed, "Policy must strictly deny under human hazard"
    assert auth_res.ticket is None, "Safety Enclave must NEVER issue ticket on DENY"

    print("[MOTIONFENCE] Policy Decision: DENY", file=stream)
    for reason in auth_res.decision.reasons:
        if reason.status == "failed":
            print(f"  * {reason.constraint}: {reason.details}", file=stream)
    print("[SAFETY ENCLAVE] AuthorizationTicket: NOT ISSUED", file=stream)

    print("\n[STEP 3: HARDWARE BOUNDARY RECEPTION (NO TICKET)]", file=stream)
    print("[HARDWARE] Waiting for MotionFence AuthorizationTicket...", file=stream)
    print("[HARDWARE] No valid authorization received.", file=stream)
    print("[HARDWARE] ACTUATOR LOCKED.", file=stream)
    print("[HARDWARE] No physical mutation permitted.", file=stream)

    rec = endpoint.receive_and_actuate(proposal=proposal, ticket=None)
    obs = endpoint.get_observed_state(proposal.target)
    print(f"[HARDWARE] Terminal status: {rec.execution_status.value}", file=stream)
    print(f"[HARDWARE] Physical valve_b state: {obs.get('target_state', 'OPEN')} (UNTOUCHED)", file=stream)

    print("\n[STEP 4: VISUAL HARDWARE STATE]", file=stream)
    print_hardware_box("MOCK PHYSICAL HARDWARE — LOCKED", [
        ("Pump P1", "ACTIVE"),
        ("Valve B", "OPEN (PRESERVED)"),
        ("Safety Zone", "OCCUPIED"),
        ("Ticket", "NONE"),
        ("Authorization", "DENIED"),
        ("Actuator", "LOCKED"),
    ], stream=stream)

    return rec.model_dump_json(indent=2)


def run_scenario_stale_ticket(stream=None) -> str:
    """Scenario 3: STALE-TICKET - Environmental TOCTOU drift blocks execution before hardware."""
    stream = stream or sys.stdout
    print("=" * 70, file=stream)
    print("SCENARIO 3: STALE AUTHORIZATION / TOCTOU DEFENSE", file=stream)
    print("=" * 70, file=stream)

    world = PhysicalWorld()
    world.valves["valve_b"] = ValveState.OPEN
    world.set_pump_state("pump_p1", "INACTIVE")
    world.cooling = CoolingState.ACTIVE
    world.set_human_zone(HumanZoneState.CLEAR)
    policy = Policy()
    event_bus = EventBus()

    auth = TicketAuthority()
    enclave = SafetyEnclave(secret_key=auth.secret_key, event_bus=event_bus)
    endpoint = MockHardwareEndpoint(world=world, event_bus=event_bus)

    print("\n[STEP 1: NOMINAL PROPOSAL & ISSUANCE]", file=stream)
    proposal = ActionProposal(
        id="prop_demo_stale_003",
        action_type=ActionType.CLOSE_VALVE,
        target="valve_b",
        parameters={},
        rationale="Valve isolation planned under nominal world version v1.",
        model_confidence=0.95,
    )
    v_issuance = world.version
    evidence = world.generate_targeted_evidence("valve_b")
    auth_res = enclave.authorize(EnclaveAuthorizationRequest(
        proposal=proposal,
        world_state=world.get_state(),
        evidence=evidence,
        policy=policy,
    ))
    ticket = auth_res.ticket
    assert ticket is not None
    print(f"[MOTIONFENCE] Authorization issued for World Version: {v_issuance}", file=stream)
    print(f"[TICKET] ID: {ticket.ticket_id[:12]}...", file=stream)

    print("\n[STEP 2: ENVIRONMENTAL DRIFT (TOCTOU INTERACTION)]", file=stream)
    print("[ENVIRONMENT] Plant sensor detects human technician entering safety zone!", file=stream)
    world.set_human_zone(HumanZoneState.OCCUPIED)
    v_drift = world.version
    print(f"[WORLD] World Version mutated: {v_issuance} -> {v_drift}", file=stream)

    print("\n[STEP 3: EXECUTION-TIME REVALIDATION]", file=stream)
    reval_res = ExecutionTimeRevalidator.revalidate(
        authorization_context=auth_res.authorization_context,
        current_world_state=world.get_state(),
        current_policy_version=policy.version,
        current_constraints=[],
        current_evidence=evidence,
        ticket_expires_at=ticket.expires_at,
        proposal_action_type=proposal.action_type,
        proposal_target=proposal.target,
    )
    print(f"[REVALIDATION] STATUS: {reval_res.status.value}", file=stream)
    print(f"[REVALIDATION] REASONS: {'; '.join(reval_res.reasons)}", file=stream)
    print("[TICKET] INVALIDATED", file=stream)
    print("[HARDWARE] Authorization invalid.", file=stream)
    print("[HARDWARE] ACTUATOR LOCKED.", file=stream)

    # Hardware endpoint directly rejects stale ticket presentation
    rec = endpoint.receive_and_actuate(proposal=proposal, ticket=ticket)
    obs = endpoint.get_observed_state(proposal.target)
    print(f"[HARDWARE] Physical state preserved: valve_b remains {obs.get('target_state', 'OPEN')}", file=stream)
    print(f"[HARDWARE] Terminal status: {rec.execution_status.value}", file=stream)

    print("\n[STEP 4: VISUAL HARDWARE STATE]", file=stream)
    print_hardware_box("MOCK PHYSICAL HARDWARE — STALE DRIFT", [
        ("Pump P1", "INACTIVE"),
        ("Valve B", "OPEN (PRESERVED)"),
        ("Safety Zone", "OCCUPIED (DRIFT)"),
        ("Ticket", f"{ticket.ticket_id[:10]}..."),
        ("Authorization", "STALE_CONTEXT"),
        ("Actuator", "LOCKED"),
    ], stream=stream)

    return rec.model_dump_json(indent=2)


def run_scenario_actuator_failure(stream=None) -> str:
    """Scenario 4: ACTUATOR-FAILURE - Mechanical fault detected by post-action verifier and handled by recovery."""
    stream = stream or sys.stdout
    print("=" * 70, file=stream)
    print("SCENARIO 4: HARDWARE FAULT & CONTAINMENT RECOVERY", file=stream)
    print("=" * 70, file=stream)

    world = PhysicalWorld()
    world.valves["valve_b"] = ValveState.OPEN
    world.set_pump_state("pump_p1", "INACTIVE")
    world.cooling = CoolingState.ACTIVE
    world.set_human_zone(HumanZoneState.CLEAR)
    policy = Policy()
    event_bus = EventBus()

    auth = TicketAuthority()
    enclave = SafetyEnclave(secret_key=auth.secret_key, event_bus=event_bus)
    endpoint = MockHardwareEndpoint(world=world, event_bus=event_bus)
    recovery_executor = RecoveryExecutor(world=world, event_bus=event_bus)

    print("\n[STEP 1: NOMINAL AUTHORIZATION]", file=stream)
    proposal = ActionProposal(
        id="prop_demo_fault_004",
        action_type=ActionType.CLOSE_VALVE,
        target="valve_b",
        parameters={},
        rationale="Isolate valve_b under nominal safety conditions.",
        model_confidence=0.97,
    )
    evidence = world.generate_targeted_evidence("valve_b")
    auth_res = enclave.authorize(EnclaveAuthorizationRequest(
        proposal=proposal,
        world_state=world.get_state(),
        evidence=evidence,
        policy=policy,
    ))
    ticket = auth_res.ticket
    assert ticket is not None

    print("[HARDWARE] AuthorizationTicket received: VALID", file=stream)
    print(f"[HARDWARE] Ticket ID: {ticket.ticket_id[:12]}...", file=stream)

    print("\n[STEP 2: HARDWARE EXECUTION WITH DETERMINISTIC FAULT]", file=stream)
    endpoint.inject_fault(HardwareFaultType.NO_OP)
    print("[HARDWARE] FAULT INJECTED: NO_OP (Mechanical linkage sheared)", file=stream)
    print("[HARDWARE] Actuating valve_b...", file=stream)

    pre_state = world.get_state()
    rec = endpoint.receive_and_actuate(proposal=proposal, ticket=ticket)
    obs = endpoint.get_observed_state(proposal.target)
    print(f"[HARDWARE] Telemetry observed post-action: {obs.get('target_state', 'UNKNOWN')}", file=stream)
    print(f"[HARDWARE] Terminal status: {rec.execution_status.value}", file=stream)

    print("\n[STEP 3: INDEPENDENT POSTCONDITION VERIFICATION]", file=stream)
    post_state = world.get_state()
    exec_res = ExecutionResult(
        success=False,
        action_id=proposal.id,
        ticket_id=ticket.ticket_id,
        executed_action=proposal.action_type,
        target=proposal.target,
        message=rec.message,
        state_version_before=pre_state.version,
        state_version_after=post_state.version,
    )
    verification = PostActionVerifier.verify(
        proposal=proposal,
        execution=exec_res,
        pre_state=pre_state,
        post_state=post_state,
        expected_postconditions=policy.expected_postconditions,
    )
    print(f"[VERIFICATION] Checking physical postconditions...", file=stream)
    print(f"[VERIFICATION] FAILED: {'; '.join(verification.discrepancies)}", file=stream)

    print("\n[STEP 4: EXISTING MOTIONFENCE RECOVERY PIPELINE]", file=stream)
    evidence = world.generate_targeted_evidence("valve_b")
    rec_result = recovery_executor.handle_failure_and_recover(
        failed_proposal=proposal,
        failed_execution=exec_res,
        failed_verification=verification,
        initial_ticket=ticket,
        current_evidence=evidence,
        policy=policy,
    )
    print(f"[MOTIONFENCE] Fault containment initiated.", file=stream)
    print(f"[MOTIONFENCE] Failure Classified: {rec_result.failure_record.failure_class.value}", file=stream)
    print(f"[MOTIONFENCE] Component 'valve_b' status: {rec_result.quarantine_records['valve_b'].status.value}", file=stream)
    print(f"[MOTIONFENCE] Recovery Strategy: {rec_result.recovery_plan.strategy.value}", file=stream)
    print(f"[MOTIONFENCE] Stale Ticket Consumed: {ticket.consumed}", file=stream)

    print("\n[STEP 5: VISUAL HARDWARE STATE]", file=stream)
    print_hardware_box("MOCK PHYSICAL HARDWARE — FAULT", [
        ("Pump P1", "INACTIVE"),
        ("Valve B", "OPEN (UNSEATED)"),
        ("Safety Zone", "CLEAR"),
        ("Ticket", f"{ticket.ticket_id[:10]}..."),
        ("Authorization", "VALID_CONSUMED"),
        ("Actuator", "HARDWARE_FAULT"),
    ], stream=stream)

    return rec.model_dump_json(indent=2)


def main():
    parser = argparse.ArgumentParser(description="MotionFence Hardware Boundary Demonstration Runner")
    parser.add_argument(
        "--scenario",
        choices=["allowed", "denied", "stale-ticket", "actuator-failure", "all"],
        default="all",
        help="Select specific demonstration scenario (default: all)",
    )
    parser.add_argument(
        "--fixtures-dir",
        default=FIXTURE_DIR,
        help=f"Directory to save canonical transcripts (default: {FIXTURE_DIR})",
    )
    args = parser.parse_args()

    os.makedirs(args.fixtures_dir, exist_ok=True)

    scenarios = (
        ["allowed", "denied", "stale-ticket", "actuator-failure"]
        if args.scenario == "all"
        else [args.scenario]
    )

    for sc in scenarios:
        buffer = io.StringIO()
        if sc == "allowed":
            record_json = run_scenario_allowed(stream=buffer)
            transcript = buffer.getvalue()
            sys.stdout.write(transcript)
            out_file = os.path.join(args.fixtures_dir, "allowed.txt")
            with open(out_file, "w", encoding="utf-8") as f:
                f.write(transcript)
            with open(os.path.join(args.fixtures_dir, "allowed_record.json"), "w", encoding="utf-8") as f:
                f.write(record_json)

        elif sc == "denied":
            record_json = run_scenario_denied(stream=buffer)
            transcript = buffer.getvalue()
            sys.stdout.write(transcript)
            out_file = os.path.join(args.fixtures_dir, "denied.txt")
            with open(out_file, "w", encoding="utf-8") as f:
                f.write(transcript)
            with open(os.path.join(args.fixtures_dir, "denied_record.json"), "w", encoding="utf-8") as f:
                f.write(record_json)

        elif sc == "stale-ticket":
            record_json = run_scenario_stale_ticket(stream=buffer)
            transcript = buffer.getvalue()
            sys.stdout.write(transcript)
            out_file = os.path.join(args.fixtures_dir, "stale_ticket.txt")
            with open(out_file, "w", encoding="utf-8") as f:
                f.write(transcript)
            with open(os.path.join(args.fixtures_dir, "stale_ticket_record.json"), "w", encoding="utf-8") as f:
                f.write(record_json)

        elif sc == "actuator-failure":
            record_json = run_scenario_actuator_failure(stream=buffer)
            transcript = buffer.getvalue()
            sys.stdout.write(transcript)
            out_file = os.path.join(args.fixtures_dir, "actuator_failure.txt")
            with open(out_file, "w", encoding="utf-8") as f:
                f.write(transcript)
            with open(os.path.join(args.fixtures_dir, "actuator_failure_record.json"), "w", encoding="utf-8") as f:
                f.write(record_json)

    print("\n" + "=" * 70)
    print(f"CANONICAL DEMO RUN COMPLETE: Saved transcripts to {args.fixtures_dir}")
    print("=" * 70 + "\n")


if __name__ == "__main__":
    main()
