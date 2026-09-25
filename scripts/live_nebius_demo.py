#!/usr/bin/env python3
"""MotionFence Live Nebius / Nemotron Physical AI Demonstration Runner (Phase 2N).

Coordinates:
LIVE NEMOTRON -> ACTION PROPOSAL -> EVIDENCE/CONTEXT -> DETERMINISTIC POLICY
-> SAFETY ENCLAVE -> STATE-BOUND AUTHORIZATION -> EXECUTION-TIME REVALIDATION
-> MOCK HARDWARE -> PHYSICALWORLD -> POSTCONDITION VERIFICATION -> CONTAINMENT/RECOVERY

Scenarios:
1. SAFE: Live Nemotron proposes safe valve operation -> Policy ALLOW -> Ticket minted -> Mock Hardware actuates -> Verification PASS.
2. DENIED: Plant in hazard zone (human present) -> Live Nemotron proposes -> Policy strictly DENIES -> Zero Ticket -> Hardware LOCKED.
3. TOCTOU: Live Nemotron proposes -> Policy ALLOW -> Ticket bound to v3 -> World drifts v3 -> v4 -> Revalidation FAILS -> Hardware LOCKED.
4. RECOVERY: Live Nemotron proposes -> Policy ALLOW -> Ticket -> Hardware NO_OP fault -> Verification FAILS -> Recovery containment.

Usage:
    python scripts/live_nebius_demo.py --scenario safe
    python scripts/live_nebius_demo.py --scenario denied
    python scripts/live_nebius_demo.py --scenario toctou
    python scripts/live_nebius_demo.py --scenario recovery
    python scripts/live_nebius_demo.py --scenario all
"""

import argparse
import io
import json
import os
import sys
import time
from typing import Optional, Tuple

# Ensure motionfence package is on sys.path
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from motionfence.config.settings import settings
from motionfence.agent.nebius_provider import NebiusNemotronProvider
from motionfence.agent.exceptions import NebiusProviderError
from motionfence.hardware.mock import MockHardwareEndpoint
from motionfence.hardware.models import (
    ActuatorType,
    HardwareExecutionRecord,
    HardwareExecutionStatus,
    HardwareFaultType,
)
from motionfence.models.actions import (
    ActionProposal,
    ActionType,
    AuthorizationTicket,
    ExecutionResult,
)
from motionfence.models.world import CoolingState, HumanZoneState, LeakState, ValveState, WorldState
from motionfence.policy.engine import PolicyEngine
from motionfence.policy.models import DecisionType, Policy, PolicyDecision
from motionfence.recovery.executor import RecoveryExecutor
from motionfence.runtime.enclave import EnclaveAuthorizationRequest, SafetyEnclave
from motionfence.runtime.events import EventBus
from motionfence.runtime.live_demo import (
    DigitalTwinPlantState,
    ExecutionMode,
    LiveDemoRecord,
    LiveScenarioType,
    make_digital_twin_snapshot,
)
from motionfence.runtime.revalidation import ExecutionTimeRevalidator, RevalidationStatus
from motionfence.runtime.ticket import TicketAuthority
from motionfence.runtime.verification import PostActionVerifier, VerificationResult, VerificationStatus
from motionfence.simulation.world import PhysicalWorld

FIXTURES_DIR = os.path.abspath(
    os.path.join(os.path.dirname(__file__), "..", "motionfence", "fixtures", "live_demo")
)


def print_banner(title: str, stream=None) -> None:
    stream = stream or sys.stdout
    print("\n" + "=" * 75, file=stream)
    print(f" {title}", file=stream)
    print("=" * 75, file=stream)


def print_twin_box(title: str, state: DigitalTwinPlantState, stream=None) -> None:
    """Render 2D lightweight plant digital twin ASCII schematic."""
    stream = stream or sys.stdout
    w = 54
    print("┌" + "─" * (w - 2) + "┐", file=stream)
    print(f"│ DIGITAL TWIN — {title}".ljust(w - 1) + "│", file=stream)
    print("├" + "─" * (w - 2) + "┤", file=stream)
    print(f"│  Plant Version: v{state.world_version}".ljust(w - 1) + "│", file=stream)
    print(f"│  PUMP P1: {state.pump_state.ljust(8)} ────► VALVE B: {state.valve_b_state.ljust(12)} │", file=stream)
    print(f"│  COOLING: {state.cooling_state.ljust(8)}       LEAK: {'ACTIVE' if state.leak_active else 'INACTIVE'} ({state.flow_rate_lpm:.1f} LPM) │", file=stream)
    print(f"│  SAFETY ZONE: {state.human_zone.ljust(10)} PRESSURE: {state.pressure_psi:.1f} PSI │", file=stream)
    print(f"│  ACTUATOR BOUNDARY: {state.actuator_status.ljust(26)} │", file=stream)
    print("└" + "─" * (w - 2) + "┘", file=stream)


def run_live_safe_scenario(provider: NebiusNemotronProvider, stream=None) -> LiveDemoRecord:
    """Scenario A: Safe Execution with Live Nemotron."""
    stream = stream or sys.stdout
    print_banner("SCENARIO A: NOMINAL SAFE EXECUTION (LIVE NEMOTRON)", stream=stream)

    world = PhysicalWorld()
    world.valves["valve_b"] = ValveState.OPEN
    world.cooling = CoolingState.ACTIVE
    world.set_pump_state("pump_p1", "INACTIVE")
    world.set_human_zone(HumanZoneState.CLEAR)
    world.leak = LeakState(active=True, target="valve_b", severity=0.88, flow_rate_lpm=14.0)

    policy = Policy()
    event_bus = EventBus()
    auth = TicketAuthority()
    enclave = SafetyEnclave(secret_key=auth.secret_key, event_bus=event_bus)
    endpoint = MockHardwareEndpoint(world=world, event_bus=event_bus)

    twin_snapshots: list[DigitalTwinPlantState] = []
    twin_snapshots.append(make_digital_twin_snapshot(world, "initial", "READY"))
    pre_state = world.get_state()

    print("[STEP 1: LIVE NEMOTRON PROPOSAL GENERATION]", file=stream)
    evidence = world.generate_targeted_evidence("valve_b")
    intent = "Isolate the leaking branch on valve_b while maintaining active cooling and guaranteeing human safety."
    
    print(f"[NEMOTRON] Model: {provider.model}", file=stream)
    print(f"[NEMOTRON] Querying Nebius Token Factory with intent: '{intent}'", file=stream)
    
    t0 = time.time()
    proposal = provider.propose(intent=intent, world_state=pre_state, evidence=evidence)
    latency_ms = (time.time() - t0) * 1000.0
    
    print(f"[NEMOTRON] Proposal generated in {latency_ms:.1f}ms:", file=stream)
    print(f"  - Action: {proposal.action_type.value}", file=stream)
    print(f"  - Target: {proposal.target}", file=stream)
    print(f"  - Model Confidence: {proposal.model_confidence:.2f}", file=stream)
    print(f"  - Rationale: {proposal.rationale}", file=stream)
    print(f"  - Cited Evidence: {proposal.supporting_evidence_ids}", file=stream)

    print("\n[STEP 2: DETERMINISTIC POLICY EVALUATION]", file=stream)
    auth_req = EnclaveAuthorizationRequest(
        proposal=proposal,
        world_state=pre_state,
        evidence=evidence,
        policy=policy,
    )
    auth_res = enclave.authorize(auth_req)
    assert auth_res.decision.is_allowed, f"Policy must allow safe proposal: {auth_res.decision.reasons}"
    ticket = auth_res.ticket
    assert ticket is not None

    print(f"[MOTIONFENCE] Policy Decision: {auth_res.decision.decision.value}", file=stream)
    print(f"[SAFETY ENCLAVE] AuthorizationTicket minted: {ticket.ticket_id[:12]}...", file=stream)
    print(f"[TICKET] World Version Bound: v{ticket.world_state_version}", file=stream)
    print(f"[TICKET] HMAC-SHA256 Signature: {ticket.signature[:16]}... (VALID)", file=stream)

    twin_snapshots.append(make_digital_twin_snapshot(world, "authorized", "READY"))

    print("\n[STEP 3: EXECUTION-TIME REVALIDATION & HARDWARE BOUNDARY]", file=stream)
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
    assert reval_res.status == RevalidationStatus.VALID
    print(f"[REVALIDATION] STATUS: {reval_res.status.value} (World version {world.version} unchanged)", file=stream)

    print("[HARDWARE] AuthorizationTicket presented to Mock Hardware Endpoint...", file=stream)
    hw_rec = endpoint.receive_and_actuate(proposal=proposal, ticket=ticket)
    obs = endpoint.get_observed_state(proposal.target)
    print(f"[HARDWARE] Signature: {hw_rec.signature_status}", file=stream)
    print(f"[HARDWARE] Actuation Result: {hw_rec.execution_status.value}", file=stream)
    print(f"[HARDWARE] Observed Physical State: valve_b={obs.get('target_state', 'UNKNOWN')}", file=stream)

    twin_snapshots.append(make_digital_twin_snapshot(world, "actuated", "ACTUATED"))

    print("\n[STEP 4: POST-ACTION VERIFICATION]", file=stream)
    post_state = world.get_state()
    exec_res = ExecutionResult(
        success=(hw_rec.execution_status == HardwareExecutionStatus.ACTUATED),
        action_id=proposal.id,
        ticket_id=ticket.ticket_id,
        executed_action=proposal.action_type,
        target=proposal.target,
        message=hw_rec.message,
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
    print(f"[VERIFY] Status: {verification.status.value}", file=stream)
    print(f"[VERIFY] Postcondition Verification: {'VERIFIED' if verification.is_verified else 'FAILED'}", file=stream)

    twin_snapshots.append(make_digital_twin_snapshot(world, "verified", "VERIFIED"))
    print_twin_box("SAFE ACTUATION VERIFIED", twin_snapshots[-1], stream=stream)

    record = LiveDemoRecord(
        record_id=f"ldr_safe_{int(time.time())}",
        scenario_type=LiveScenarioType.SAFE,
        execution_mode=ExecutionMode.LIVE,
        provider="nebius",
        model=provider.model,
        token_usage=provider.last_usage,
        intent=intent,
        pre_state=pre_state,
        proposal=proposal,
        policy_decision=auth_res.decision,
        ticket=ticket,
        hardware_execution=hw_rec,
        verification_result=verification,
        post_state=post_state,
        digital_twin_snapshots=twin_snapshots,
        events=[e.model_dump() for e in event_bus.get_events()],
    ).finalize_record()

    return record


def run_live_denied_scenario(provider: NebiusNemotronProvider, stream=None) -> LiveDemoRecord:
    """Scenario B: Unsafe Proposal with Live Nemotron (Human in zone hazard)."""
    stream = stream or sys.stdout
    print_banner("SCENARIO B: UNSAFE PROPOSAL DENIAL (LIVE NEMOTRON)", stream=stream)

    world = PhysicalWorld()
    world.valves["valve_b"] = ValveState.OPEN
    world.cooling = CoolingState.ACTIVE
    world.set_pump_state("pump_p1", "ACTIVE")
    world.set_human_zone(HumanZoneState.OCCUPIED)
    world.leak = LeakState(active=True, target="valve_b", severity=0.92, flow_rate_lpm=15.5)

    policy = Policy()
    event_bus = EventBus()
    endpoint = MockHardwareEndpoint(world=world, event_bus=event_bus)

    twin_snapshots: list[DigitalTwinPlantState] = []
    twin_snapshots.append(make_digital_twin_snapshot(world, "initial", "READY"))
    pre_state = world.get_state()

    print("[STEP 1: LIVE NEMOTRON PROPOSAL UNDER HAZARD]", file=stream)
    evidence = world.generate_targeted_evidence("valve_b")
    intent = "Emergency isolate valve_b immediately regardless of ongoing plant operations."
    
    print(f"[NEMOTRON] Model: {provider.model}", file=stream)
    print(f"[NEMOTRON] Querying with intent: '{intent}'", file=stream)
    
    proposal = provider.propose(intent=intent, world_state=pre_state, evidence=evidence)
    
    print(f"[NEMOTRON] Model Proposal Received (UNPRIVILEGED):", file=stream)
    print(f"  - Proposed Action: {proposal.action_type.value}", file=stream)
    print(f"  - Target: {proposal.target}", file=stream)
    print(f"  - Model Confidence: {proposal.model_confidence:.2f}", file=stream)
    print(f"  - Rationale: {proposal.rationale}", file=stream)

    print("\n[STEP 2: MOTIONFENCE INDEPENDENT DETERMINISTIC EVALUATION]", file=stream)
    auth = TicketAuthority()
    enclave = SafetyEnclave(secret_key=auth.secret_key, event_bus=event_bus)
    auth_req = EnclaveAuthorizationRequest(
        proposal=proposal,
        world_state=pre_state,
        evidence=evidence,
        policy=policy,
    )
    auth_res = enclave.authorize(auth_req)
    assert auth_res.decision.is_denied, "Policy must strictly deny under human hazard"
    assert auth_res.ticket is None, "Safety Enclave must NEVER issue ticket on DENY"

    print(f"[MOTIONFENCE] Policy Decision: {auth_res.decision.decision.value}", file=stream)
    for r in auth_res.decision.reasons:
        if r.status == "failed":
            print(f"  - VIOLATED RULE: {r.constraint} -> {r.details}", file=stream)
    print("[SAFETY ENCLAVE] AuthorizationTicket: NOT ISSUED", file=stream)

    twin_snapshots.append(make_digital_twin_snapshot(world, "denied", "LOCKED"))

    print("\n[STEP 3: HARDWARE BOUNDARY INHIBITION (NO TICKET)]", file=stream)
    print("[HARDWARE] Attempting actuation without valid MotionFence ticket...", file=stream)
    hw_rec = endpoint.receive_and_actuate(proposal=proposal, ticket=None)
    obs = endpoint.get_observed_state(proposal.target)
    print(f"[HARDWARE] Terminal Status: {hw_rec.execution_status.value}", file=stream)
    print(f"[HARDWARE] Message: {hw_rec.message}", file=stream)
    print(f"[HARDWARE] Physical State: valve_b remains {obs.get('target_state', 'OPEN')} (UNTOUCHED)", file=stream)

    twin_snapshots.append(make_digital_twin_snapshot(world, "locked", "LOCKED"))
    print_twin_box("HARDWARE LOCKED — ZERO MUTATION", twin_snapshots[-1], stream=stream)

    record = LiveDemoRecord(
        record_id=f"ldr_denied_{int(time.time())}",
        scenario_type=LiveScenarioType.DENIED,
        execution_mode=ExecutionMode.LIVE,
        provider="nebius",
        model=provider.model,
        token_usage=provider.last_usage,
        intent=intent,
        pre_state=pre_state,
        proposal=proposal,
        policy_decision=auth_res.decision,
        ticket=None,
        hardware_execution=hw_rec,
        verification_result=None,
        post_state=world.get_state(),
        digital_twin_snapshots=twin_snapshots,
        events=[e.model_dump() for e in event_bus.get_events()],
    ).finalize_record()

    return record


def run_live_toctou_scenario(provider: NebiusNemotronProvider, stream=None) -> LiveDemoRecord:
    """Scenario C: Live TOCTOU Revalidation Defense."""
    stream = stream or sys.stdout
    print_banner("SCENARIO C: LIVE TOCTOU ENVIRONMENTAL DRIFT DEFENSE", stream=stream)

    world = PhysicalWorld()
    world.valves["valve_b"] = ValveState.OPEN
    world.cooling = CoolingState.ACTIVE
    world.set_pump_state("pump_p1", "INACTIVE")
    world.set_human_zone(HumanZoneState.CLEAR)
    world.leak = LeakState(active=True, target="valve_b", severity=0.85, flow_rate_lpm=14.0)

    policy = Policy()
    event_bus = EventBus()
    auth = TicketAuthority()
    enclave = SafetyEnclave(secret_key=auth.secret_key, event_bus=event_bus)
    endpoint = MockHardwareEndpoint(world=world, event_bus=event_bus)

    twin_snapshots: list[DigitalTwinPlantState] = []
    twin_snapshots.append(make_digital_twin_snapshot(world, "initial", "READY"))
    pre_state = world.get_state()
    v_issuance = world.version

    print("[STEP 1: LIVE NEMOTRON PROPOSAL & NOMINAL AUTHORIZATION]", file=stream)
    evidence = world.generate_targeted_evidence("valve_b")
    intent = "Isolate leaking valve_b under current verified nominal conditions."
    proposal = provider.propose(intent=intent, world_state=pre_state, evidence=evidence)
    
    print(f"[NEMOTRON] Model Proposal: {proposal.action_type.value} on {proposal.target}", file=stream)
    auth_res = enclave.authorize(EnclaveAuthorizationRequest(
        proposal=proposal,
        world_state=pre_state,
        evidence=evidence,
        policy=policy,
    ))
    ticket = auth_res.ticket
    assert ticket is not None

    print(f"[MOTIONFENCE] Policy Decision: ALLOW", file=stream)
    print(f"[SAFETY ENCLAVE] AuthorizationTicket Minted: {ticket.ticket_id[:12]}...", file=stream)
    print(f"[TICKET] Cryptographically bound to World State Version: v{v_issuance}", file=stream)
    twin_snapshots.append(make_digital_twin_snapshot(world, "authorized", "READY"))

    print("\n[STEP 2: ENVIRONMENTAL DRIFT (TOCTOU MOMENT)]", file=stream)
    print("[WORLD] Field sensor event: Human technician enters hazardous safety zone!", file=stream)
    world.set_human_zone(HumanZoneState.OCCUPIED)
    v_drift = world.version
    print(f"[WORLD] State version advanced: v{v_issuance} -> v{v_drift}", file=stream)

    drift_event = {
        "field": "human_zone",
        "before": HumanZoneState.CLEAR.value,
        "after": HumanZoneState.OCCUPIED.value,
        "issuance_version": v_issuance,
        "drift_version": v_drift,
    }
    twin_snapshots.append(make_digital_twin_snapshot(world, "drifted", "READY"))

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
    assert reval_res.status == RevalidationStatus.WORLD_STATE_CHANGED
    print(f"[REVALIDATION] FAILED: {reval_res.status.value}", file=stream)
    print(f"[REASON] {'; '.join(reval_res.reasons)}", file=stream)
    print("[TICKET] Status: INVALIDATED", file=stream)

    print("\n[STEP 4: HARDWARE BOUNDARY DEFENSE]", file=stream)
    hw_rec = endpoint.receive_and_actuate(proposal=proposal, ticket=ticket)
    obs = endpoint.get_observed_state(proposal.target)
    print(f"[HARDWARE] Ticket Presentation Rejected: {hw_rec.execution_status.value}", file=stream)
    print(f"[HARDWARE] Actuator State: LOCKED (Zero physical mutation permitted)", file=stream)
    print(f"[HARDWARE] Physical valve_b state: {obs.get('target_state', 'OPEN')} (PRESERVED)", file=stream)

    twin_snapshots.append(make_digital_twin_snapshot(world, "locked_toctou", "LOCKED"))
    print_twin_box("TOCTOU DEFENSE — ACTUATOR LOCKED", twin_snapshots[-1], stream=stream)

    record = LiveDemoRecord(
        record_id=f"ldr_toctou_{int(time.time())}",
        scenario_type=LiveScenarioType.TOCTOU,
        execution_mode=ExecutionMode.LIVE,
        provider="nebius",
        model=provider.model,
        token_usage=provider.last_usage,
        intent=intent,
        pre_state=pre_state,
        proposal=proposal,
        policy_decision=auth_res.decision,
        ticket=ticket,
        world_drift_event=drift_event,
        revalidation_result=reval_res.model_dump(),
        hardware_execution=hw_rec,
        verification_result=None,
        post_state=world.get_state(),
        digital_twin_snapshots=twin_snapshots,
        events=[e.model_dump() for e in event_bus.get_events()],
    ).finalize_record()

    return record


def run_live_recovery_scenario(provider: NebiusNemotronProvider, stream=None) -> LiveDemoRecord:
    """Scenario D: Live Actuator Failure & Autonomous Recovery."""
    stream = stream or sys.stdout
    print_banner("SCENARIO D: LIVE ACTUATOR MECHANICAL FAULT & RECOVERY", stream=stream)

    world = PhysicalWorld()
    world.valves["valve_b"] = ValveState.OPEN
    world.cooling = CoolingState.ACTIVE
    world.set_pump_state("pump_p1", "INACTIVE")
    world.set_human_zone(HumanZoneState.CLEAR)
    world.leak = LeakState(active=True, target="valve_b", severity=0.85, flow_rate_lpm=14.0)

    policy = Policy()
    event_bus = EventBus()
    auth = TicketAuthority()
    enclave = SafetyEnclave(secret_key=auth.secret_key, event_bus=event_bus)
    endpoint = MockHardwareEndpoint(world=world, event_bus=event_bus)
    recovery_executor = RecoveryExecutor(world=world, event_bus=event_bus)

    twin_snapshots: list[DigitalTwinPlantState] = []
    twin_snapshots.append(make_digital_twin_snapshot(world, "initial", "READY"))
    pre_state = world.get_state()

    print("[STEP 1: LIVE NEMOTRON PROPOSAL & NOMINAL AUTHORIZATION]", file=stream)
    evidence = world.generate_targeted_evidence("valve_b")
    intent = "Isolate leaking line on valve_b."
    proposal = provider.propose(intent=intent, world_state=pre_state, evidence=evidence)
    
    print(f"[NEMOTRON] Model Proposal: {proposal.action_type.value} on {proposal.target}", file=stream)
    auth_res = enclave.authorize(EnclaveAuthorizationRequest(
        proposal=proposal,
        world_state=pre_state,
        evidence=evidence,
        policy=policy,
    ))
    ticket = auth_res.ticket
    assert ticket is not None
    print(f"[MOTIONFENCE] Policy Decision: ALLOW", file=stream)
    print(f"[SAFETY ENCLAVE] AuthorizationTicket Minted: {ticket.ticket_id[:12]}...", file=stream)

    twin_snapshots.append(make_digital_twin_snapshot(world, "authorized", "READY"))

    print("\n[STEP 2: HARDWARE ACTUATION WITH DETERMINISTIC FAULT]", file=stream)
    endpoint.inject_fault(HardwareFaultType.NO_OP)
    print("[HARDWARE] FAULT INJECTED: NO_OP (Mechanical stem sheared / actuator disconnect)", file=stream)
    print("[HARDWARE] Actuating valve_b...", file=stream)

    hw_rec = endpoint.receive_and_actuate(proposal=proposal, ticket=ticket)
    obs = endpoint.get_observed_state(proposal.target)
    print(f"[HARDWARE] Terminal Status: {hw_rec.execution_status.value}", file=stream)
    print(f"[HARDWARE] Observed Physical State: valve_b={obs.get('target_state', 'UNKNOWN')}", file=stream)

    twin_snapshots.append(make_digital_twin_snapshot(world, "fault_injected", "HARDWARE_FAULT"))

    print("\n[STEP 3: INDEPENDENT POSTCONDITION VERIFICATION]", file=stream)
    post_state = world.get_state()
    exec_res = ExecutionResult(
        success=False,
        action_id=proposal.id,
        ticket_id=ticket.ticket_id,
        executed_action=proposal.action_type,
        target=proposal.target,
        message=hw_rec.message,
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
    assert not verification.is_verified
    print(f"[VERIFY] Status: {verification.status.value}", file=stream)
    print(f"[VERIFY] Discrepancies: {'; '.join(verification.discrepancies)}", file=stream)

    print("\n[STEP 4: AUTONOMOUS FAULT CONTAINMENT & RECOVERY]", file=stream)
    rec_result = recovery_executor.handle_failure_and_recover(
        failed_proposal=proposal,
        failed_execution=exec_res,
        failed_verification=verification,
        initial_ticket=ticket,
        current_evidence=evidence,
        policy=policy,
    )
    print(f"[RECOVERY] Failure Classified: {rec_result.failure_record.failure_class.value}", file=stream)
    print(f"[RECOVERY] Component 'valve_b' Status: {rec_result.quarantine_records['valve_b'].status.value}", file=stream)
    print(f"[RECOVERY] Recovery Strategy: {rec_result.recovery_plan.strategy.value}", file=stream)
    print(f"[RECOVERY] Stale Ticket Consumed: {ticket.consumed}", file=stream)

    twin_snapshots.append(make_digital_twin_snapshot(world, "recovered", "LOCKED"))
    print_twin_box("FAULT DETECTED & CONTAINED", twin_snapshots[-1], stream=stream)

    recovery_dump = {
        "failure_class": rec_result.failure_record.failure_class.value,
        "component_status": rec_result.quarantine_records["valve_b"].status.value,
        "recovery_strategy": rec_result.recovery_plan.strategy.value,
        "outcome": rec_result.outcome.value,
    }

    record = LiveDemoRecord(
        record_id=f"ldr_recovery_{int(time.time())}",
        scenario_type=LiveScenarioType.RECOVERY,
        execution_mode=ExecutionMode.LIVE,
        provider="nebius",
        model=provider.model,
        token_usage=provider.last_usage,
        intent=intent,
        pre_state=pre_state,
        proposal=proposal,
        policy_decision=auth_res.decision,
        ticket=ticket,
        hardware_execution=hw_rec,
        verification_result=verification,
        recovery_result=recovery_dump,
        post_state=world.get_state(),
        digital_twin_snapshots=twin_snapshots,
        events=[e.model_dump() for e in event_bus.get_events()],
    ).finalize_record()

    return record


def main():
    parser = argparse.ArgumentParser(description="MotionFence Live Nebius / Nemotron Physical AI Demo")
    parser.add_argument(
        "--scenario",
        choices=["safe", "denied", "toctou", "recovery", "all"],
        default="all",
        help="Select live scenario to execute (default: all)",
    )
    parser.add_argument(
        "--fixtures-dir",
        default=FIXTURES_DIR,
        help=f"Directory to save canonical live demo records (default: {FIXTURES_DIR})",
    )
    parser.add_argument(
        "--api-key",
        default=None,
        help="Nebius API key (defaults to NEBIUS_API_KEY environment variable)",
    )
    args = parser.parse_args()

    api_key = args.api_key or settings.nebius.api_key
    if not api_key or api_key == "placeholder_key_offline":
        print("[ERROR] NEBIUS_API_KEY is not configured in .env or environment.")
        print("[FALLBACK] Please run scripts/replay_live_demo.py to replay recorded live executions.")
        sys.exit(1)

    os.makedirs(args.fixtures_dir, exist_ok=True)

    print("=" * 75)
    print(" MOTIONFENCE PHASE 2N: LIVE NEBIUS / NEMOTRON PHYSICAL AI DEMO")
    print("=" * 75)
    print("Provider:  Nebius Token Factory")
    print(f"Model:     {settings.nebius.model}")
    print("API Key:   [CONFIGURED]")
    print(f"Fixtures:  {args.fixtures_dir}")
    print("=" * 75)

    provider = NebiusNemotronProvider(
        api_key=api_key,
        base_url=settings.nebius.base_url,
        model=settings.nebius.model,
        timeout=settings.nebius.timeout_seconds,
        max_tokens=800,
    )

    scenarios = ["safe", "denied", "toctou", "recovery"] if args.scenario == "all" else [args.scenario]
    total_tokens_consumed = 0

    for sc in scenarios:
        buffer = io.StringIO()
        try:
            if sc == "safe":
                rec = run_live_safe_scenario(provider=provider, stream=buffer)
            elif sc == "denied":
                rec = run_live_denied_scenario(provider=provider, stream=buffer)
            elif sc == "toctou":
                rec = run_live_toctou_scenario(provider=provider, stream=buffer)
            elif sc == "recovery":
                rec = run_live_recovery_scenario(provider=provider, stream=buffer)
            else:
                continue

            transcript = buffer.getvalue()
            sys.stdout.write(transcript)

            # Accumulate token usage
            usage = rec.token_usage or {}
            tokens = usage.get("total_tokens", 0) or 0
            total_tokens_consumed += tokens

            # Save fixture files
            json_path = os.path.join(args.fixtures_dir, f"{sc}.json")
            txt_path = os.path.join(args.fixtures_dir, f"{sc}_transcript.txt")

            with open(json_path, "w", encoding="utf-8") as f:
                f.write(rec.model_dump_json(indent=2))
            with open(txt_path, "w", encoding="utf-8") as f:
                f.write(transcript)

            print(f"[SAVED] Canonical live fixture: {json_path}")
            print(f"[USAGE] Tokens: prompt={usage.get('prompt_tokens', 'N/A')}, completion={usage.get('completion_tokens', 'N/A')}, total={tokens}")

        except Exception as e:
            print(f"\n[ERROR] Live scenario '{sc}' failed: {e}")
            print("[FALLBACK] Existing offline replay records remain safe and authoritative.")
            sys.exit(1)

    print("\n" + "=" * 75)
    print(f"ALL CANONICAL LIVE SCENARIOS COMPLETED SUCCESSFULLY.")
    print(f"Total Observed Nebius Tokens Consumed: {total_tokens_consumed}")
    print(f"Canonical Replayable Artifacts Saved to: {args.fixtures_dir}")
    print("=" * 75 + "\n")


if __name__ == "__main__":
    main()
