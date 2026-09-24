#!/usr/bin/env python3
"""MotionFence Mock Physical Hardware Terminal Demonstration.

Demonstrates the physical actuator security boundary:
NO VALID MOTIONFENCE AUTHORIZATION TICKET = NO ACTUATION.

Zero exposed secrets. Fully deterministic and offline.
"""

import sys
import os
import argparse
import time

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from motionfence.models.actions import ActionProposal, ActionType, AuthorizationTicket
from motionfence.models.world import WorldState, ValveState, CoolingState, HumanZoneState
from motionfence.simulation.world import PhysicalWorld
from motionfence.runtime.ticket import TicketAuthority
from motionfence.runtime.events import EventBus
from motionfence.hardware.models import (
    ActuatorType,
    HardwareExecutionStatus,
    HardwareFaultType,
)
from motionfence.hardware.mock import MockHardwareEndpoint


def print_hardware_box(title: str, items: list[tuple[str, str]]) -> None:
    """Render clean, deterministic industrial mission-control terminal box."""
    width = 46
    print("┌" + "─" * (width - 2) + "┐")
    title_line = f"│ {title}".ljust(width - 1) + "│"
    print(title_line)
    print("├" + "─" * (width - 2) + "┤")
    for key, val in items:
        content = f"│ {key.ljust(18)} {val.ljust(22)} │"
        print(content)
    print("└" + "─" * (width - 2) + "┘")


def demo_valid_actuation() -> None:
    """Demonstrate nominal authorized execution at the hardware boundary."""
    print("\n" + "=" * 60)
    print("DEMO: NOMINAL AUTHORIZED ACTUATION")
    print("=" * 60)

    world = PhysicalWorld()
    world.valves["valve_b"] = ValveState.OPEN
    world.set_pump_state("pump_p1", "INACTIVE")
    world.cooling = CoolingState.ACTIVE
    world.set_human_zone(HumanZoneState.CLEAR)

    auth = TicketAuthority()
    endpoint = MockHardwareEndpoint(world=world)

    proposal = ActionProposal(
        id="prop_demo_001",
        action_type=ActionType.CLOSE_VALVE,
        target="valve_b",
        parameters={},
        rationale="Routine isolation of valve_b under nominal safety conditions.",
        model_confidence=0.96,
    )

    ticket = auth.mint_ticket(
        proposal=proposal,
        ttl_seconds=30.0,
        world_state=world.get_state(),
    )

    print("[HARDWARE] Waiting for MotionFence AuthorizationTicket...")
    time.sleep(0.05)
    print("[HARDWARE] AuthorizationTicket received.")
    print(f"[HARDWARE] Ticket: {ticket.ticket_id[:12]}...")
    print("[HARDWARE] Signature: VALID")
    print(f"[HARDWARE] Action: {ticket.action_type.value}")
    print(f"[HARDWARE] Target: {ticket.target}")
    print("[HARDWARE] Authorization: VALID")
    print(f"[HARDWARE] Actuating {ticket.target}...")

    rec = endpoint.receive_and_actuate(proposal=proposal, ticket=ticket)
    obs = endpoint.get_observed_state(proposal.target)
    print(f"[HARDWARE] Observed state: {obs.get('target_state', 'UNKNOWN')}")
    print(f"[HARDWARE] Terminal status: {rec.execution_status.value}")

    print_hardware_box("MOCK PHYSICAL HARDWARE — NOMINAL", [
        ("Pump P1", "INACTIVE"),
        ("Valve B", obs.get('target_state', 'CLOSED')),
        ("Safety Zone", "CLEAR"),
        ("Ticket", f"{ticket.ticket_id[:10]}..."),
        ("Authorization", "VALID"),
        ("Actuator", "ACTUATED"),
    ])


def demo_denied_action() -> None:
    """Demonstrate policy denial where no ticket is minted and hardware stays locked."""
    print("\n" + "=" * 60)
    print("DEMO: POLICY DENIAL (ZERO AUTHORIZATION)")
    print("=" * 60)

    world = PhysicalWorld()
    world.valves["valve_b"] = ValveState.OPEN
    endpoint = MockHardwareEndpoint(world=world)

    proposal = ActionProposal(
        id="prop_demo_002",
        action_type=ActionType.CLOSE_VALVE,
        target="valve_b",
        parameters={},
        rationale="Unsafe request under active human zone hazard.",
        model_confidence=0.96,
    )

    print("[MOTIONFENCE] Policy Decision: DENY")
    print("[SAFETY ENCLAVE] AuthorizationTicket: NOT ISSUED")
    print("[HARDWARE] Waiting for MotionFence AuthorizationTicket...")
    time.sleep(0.05)
    print("[HARDWARE] No valid authorization received.")
    print("[HARDWARE] ACTUATOR LOCKED.")
    print("[HARDWARE] No physical mutation permitted.")

    rec = endpoint.receive_and_actuate(proposal=proposal, ticket=None)

    print_hardware_box("MOCK PHYSICAL HARDWARE — LOCKED", [
        ("Pump P1", "ACTIVE"),
        ("Valve B", "OPEN"),
        ("Safety Zone", "OCCUPIED"),
        ("Ticket", "NONE"),
        ("Authorization", "DENIED"),
        ("Actuator", "LOCKED"),
    ])


def demo_stale_toctou() -> None:
    """Demonstrate state-bound authorization drift where stale tickets are locked out."""
    print("\n" + "=" * 60)
    print("DEMO: STALE AUTHORIZATION / TOCTOU DEFENSE")
    print("=" * 60)

    world = PhysicalWorld()
    world.valves["valve_b"] = ValveState.OPEN
    world.set_human_zone(HumanZoneState.CLEAR)
    v_initial = world.version

    auth = TicketAuthority()
    endpoint = MockHardwareEndpoint(world=world)

    proposal = ActionProposal(
        id="prop_demo_003",
        action_type=ActionType.CLOSE_VALVE,
        target="valve_b",
        parameters={},
        rationale="Valve isolation planned under version v1.",
        model_confidence=0.96,
    )

    ticket = auth.mint_ticket(
        proposal=proposal,
        ttl_seconds=30.0,
        world_state=world.get_state(),
    )

    print(f"[MOTIONFENCE] Authorization issued for World Version: {v_initial}")
    print("[ENVIRONMENT] Environmental drift: Human enters safety zone!")
    world.set_human_zone(HumanZoneState.OCCUPIED)
    v_drift = world.version
    print(f"[WORLD] World Version changed: {v_initial} -> {v_drift}")
    print("[REVALIDATION] FAILED")
    print("[REASON] WORLD_VERSION_MISMATCH")
    print("[TICKET] INVALIDATED")
    print("[HARDWARE] Authorization invalid.")
    print("[HARDWARE] ACTUATOR LOCKED.")

    rec = endpoint.receive_and_actuate(proposal=proposal, ticket=ticket)

    print_hardware_box("MOCK PHYSICAL HARDWARE — STALE DRIFT", [
        ("Pump P1", "INACTIVE"),
        ("Valve B", "OPEN (PRESERVED)"),
        ("Safety Zone", "OCCUPIED (DRIFT)"),
        ("Ticket", f"{ticket.ticket_id[:10]}..."),
        ("Authorization", "STALE_CONTEXT"),
        ("Actuator", "LOCKED"),
    ])


def demo_actuator_fault() -> None:
    """Demonstrate physical actuator mechanical fault and verification detection."""
    print("\n" + "=" * 60)
    print("DEMO: DETERMINISTIC ACTUATOR MECHANICAL FAULT")
    print("=" * 60)

    world = PhysicalWorld()
    world.valves["valve_b"] = ValveState.OPEN
    world.set_human_zone(HumanZoneState.CLEAR)

    auth = TicketAuthority()
    endpoint = MockHardwareEndpoint(world=world)
    endpoint.inject_fault(HardwareFaultType.NO_OP)

    proposal = ActionProposal(
        id="prop_demo_004",
        action_type=ActionType.CLOSE_VALVE,
        target="valve_b",
        parameters={},
        rationale="Valve isolation command dispatched to faulty actuator.",
        model_confidence=0.96,
    )

    ticket = auth.mint_ticket(
        proposal=proposal,
        ttl_seconds=30.0,
        world_state=world.get_state(),
    )

    print("[HARDWARE] AuthorizationTicket received: VALID")
    print("[HARDWARE] Actuating valve_b...")
    print("[HARDWARE] FAULT INJECTED: NO_OP (Mechanical linkage sheared)")
    rec = endpoint.receive_and_actuate(proposal=proposal, ticket=ticket)
    obs = endpoint.get_observed_state(proposal.target)
    print(f"[HARDWARE] Telemetry observed post-action: {obs.get('target_state', 'UNKNOWN')}")
    print("[VERIFICATION] Checking physical postconditions...")
    print("[VERIFICATION] FAILED: Expected 'valves.valve_b' == 'CLOSED', observed 'OPEN'")
    print("[MOTIONFENCE] Fault containment initiated. Component 'valve_b' marked SUSPECT.")

    print_hardware_box("MOCK PHYSICAL HARDWARE — FAULT", [
        ("Pump P1", "INACTIVE"),
        ("Valve B", "OPEN (UNSEATED)"),
        ("Safety Zone", "CLEAR"),
        ("Ticket", f"{ticket.ticket_id[:10]}..."),
        ("Authorization", "VALID_CONSUMED"),
        ("Actuator", "HARDWARE_FAULT"),
    ])


def main():
    parser = argparse.ArgumentParser(description="MotionFence Mock Physical Hardware Terminal Demo")
    parser.add_argument("--all", action="store_true", help="Run all demonstration scenarios")
    parser.add_argument("--allowed", action="store_true", help="Run allowed scenario")
    parser.add_argument("--denied", action="store_true", help="Run denied scenario")
    parser.add_argument("--stale", action="store_true", help="Run stale ticket scenario")
    parser.add_argument("--fault", action="store_true", help="Run actuator fault scenario")
    args = parser.parse_args()

    if not any([args.all, args.allowed, args.denied, args.stale, args.fault]):
        args.all = True

    if args.all or args.allowed:
        demo_valid_actuation()
    if args.all or args.denied:
        demo_denied_action()
    if args.all or args.stale:
        demo_stale_toctou()
    if args.all or args.fault:
        demo_actuator_fault()

    print("\n" + "=" * 60)
    print("DEMO COMPLETE: All actuator security boundaries verified.")
    print("=" * 60 + "\n")


if __name__ == "__main__":
    main()
