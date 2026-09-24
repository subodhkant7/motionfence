"""Interactive terminal demonstration of MotionFence authorization and safety invariants.

Supports demonstrating:
1. Ambiguous target inspection and verified closure
2. Human safety zone incursion (DENY)
3. Multi-sensor contradiction detection (DENY)
"""

import argparse
import os
import sys
import time

from motionfence.config.settings import settings
from motionfence.runtime.core import MotionFenceRuntime
from motionfence.simulation.world import PhysicalWorld
from motionfence.models.world import HumanZoneState, ValveState
from motionfence.agent.provider import LocalDeterministicProvider
from motionfence.agent.nebius_provider import NebiusNemotronProvider


def run_scenario_leak_isolation(runtime: MotionFenceRuntime, world: PhysicalWorld) -> None:
    """Scenario 1: Industrial Leak Isolation with Ambiguity Resolution."""
    print("\n" + "=" * 70)
    print(" SCENARIO 1: LEAK ISOLATION WITH AMBIGUITY RESOLUTION")
    print("=" * 70)

    intent = "Isolate the leaking line while keeping cooling active."
    print(f"[1] Human intent received:\n    \"{intent}\"")

    init_state = world.get_state()
    print(f"\n[2] Initial Physical World State (v{init_state.version}):")
    print(f"    - Valve A:      {init_state.valves['valve_a'].value}")
    print(f"    - Valve B:      {init_state.valves['valve_b'].value}")
    print(f"    - Cooling:      {init_state.cooling.value}")
    print(f"    - Leak:         ACTIVE on {init_state.leak.target} ({init_state.leak.flow_rate_lpm:.1f} LPM)")
    print(f"    - Human Zone:   {init_state.human_zone.value}")

    # Pass 1: Ambiguous evidence
    ambiguous_evidence = world.generate_initial_ambiguous_evidence()
    print(f"\n[3] Ambient Observations Recorded (Wide-Angle / Ambiguous):")
    for ev in ambiguous_evidence:
        print(f"    - [{ev.source.value.upper()}] id={ev.id} target={ev.target} conf={ev.confidence:.2f}")

    print(f"\n[4] Querying proposal provider ({getattr(runtime.proposal_provider, 'provider_name', 'deterministic')})...")
    cycle_1 = runtime.run_cycle(
        intent=intent,
        initial_evidence=ambiguous_evidence,
        gather_additional_evidence_on_request=False,
    )
    p1 = cycle_1.proposal
    d1 = cycle_1.policy_decision

    print(f"\n[5] Model Proposal (Pass 1):")
    print(f"    Action:     {p1.action_type.value}")
    print(f"    Target:     {p1.target}")
    print(f"    Confidence: {p1.model_confidence:.2f}")
    print(f"    Rationale:  {p1.rationale}")

    print(f"\n[6] Deterministic Policy Evaluation (Pass 1):")
    print(f"    Verdict:    {d1.decision.value}")
    for reason in d1.reasons:
        marker = "✓" if reason.status == "passed" else "✗"
        print(f"    [{marker}] {reason.constraint}: observed={reason.observed}, required={reason.required}")

    print(f"\n>>> POLICY RESULT: Actuator execution BLOCKED (Verdict: {d1.decision.value}).")

    # Pass 2: Targeted Evidence
    print(f"\n[7] Initiating Targeted Inspection on '{p1.target}'...")
    targeted_evidence = world.generate_targeted_evidence(p1.target)
    for ev in targeted_evidence:
        print(f"    - [{ev.source.value.upper()}] id={ev.id} target={ev.target} conf={ev.confidence:.2f}")

    combined_evidence = list(ambiguous_evidence) + list(targeted_evidence)

    print(f"\n[8] Re-evaluating proposal with multi-modal evidence pool...")
    cycle_2 = runtime.run_cycle(
        intent=intent,
        initial_evidence=combined_evidence,
        gather_additional_evidence_on_request=False,
    )
    d2 = cycle_2.policy_decision
    tkt = cycle_2.ticket
    exec_res = cycle_2.execution_result
    verif = cycle_2.verification_result

    print(f"\n[9] Deterministic Policy Evaluation (Pass 2):")
    print(f"    Verdict:    {d2.decision.value}")
    for reason in d2.reasons:
        marker = "✓" if reason.status == "passed" else "✗"
        print(f"    [{marker}] {reason.constraint}: observed={reason.observed}, required={reason.required}")

    print(f"\n[10] Authorization Ticket Minted:")
    print(f"    Ticket ID:  {tkt.ticket_id}")
    print(f"    Signed By:  {tkt.authorized_by}")
    print(f"    Expires In: {round(tkt.expires_at - time.time(), 1)}s")

    print(f"\n[11] Physical Actuator Execution:")
    print(f"    Status:     {'SUCCESS' if exec_res.success else 'FAILED'}")
    print(f"    Transition: World state v{exec_res.state_version_before} -> v{exec_res.state_version_after}")

    post_state = world.get_state()
    print(f"\n[12] Post-Action Verification:")
    for postcond, val in verif.expected_postconditions.items():
        obs = verif.observed_postconditions.get(postcond)
        status = "PASS" if obs == val else "FAIL"
        print(f"    - {postcond} == {val}: {status} (observed={obs})")

    print(f"\n>>> FINAL OUTCOME: {verif.status.value}")


def run_scenario_human_incursion(runtime: MotionFenceRuntime, world: PhysicalWorld) -> None:
    """Scenario 2: Human incursion into safety exclusion zone."""
    print("\n" + "=" * 70)
    print(" SCENARIO 2: HUMAN SAFETY ZONE INCURSION (HARD INVARIANT TEST)")
    print("=" * 70)

    # Re-open valve and simulate human entry
    world.valves["valve_b"] = ValveState.OPEN
    world.leak.active = True
    world.leak.flow_rate_lpm = 14.2
    world.set_human_zone(HumanZoneState.OCCUPIED)

    intent = "Emergency: Isolate leaking valve B immediately!"
    print(f"[1] Human intent: \"{intent}\"")
    print(f"[2] Physical Environment: Human Zone is OCCUPIED!")

    targeted_evidence = world.generate_targeted_evidence("valve_b")
    cycle = runtime.run_cycle(intent=intent, initial_evidence=targeted_evidence)

    print(f"\n[3] Model Proposed: {cycle.proposal.action_type.value} on {cycle.proposal.target} (conf={cycle.proposal.model_confidence:.2f})")
    print(f"[4] Policy Verdict: {cycle.policy_decision.decision.value}")
    for reason in cycle.policy_decision.reasons:
        if reason.constraint == "human_safety_zone":
            print(f"    -> Safety Constraint: {reason.constraint} = {reason.observed} (required: {reason.required})")

    print(f"[5] Ticket Minted:   {cycle.ticket}")
    print(f"[6] Valve B State:   {world.valves['valve_b'].value} (MUST REMAIN OPEN - NO MUTATION)")
    assert cycle.policy_decision.is_denied
    assert cycle.ticket is None
    assert world.valves["valve_b"] == ValveState.OPEN
    print("\n>>> INVARIANT VERIFIED: Actuation strictly blocked while human is in safety zone.")


def run_scenario_sensor_contradiction(runtime: MotionFenceRuntime, world: PhysicalWorld) -> None:
    """Scenario 3: Contradictory sensor observations."""
    print("\n" + "=" * 70)
    print(" SCENARIO 3: MULTI-SENSOR CONTRADICTION DETECTION")
    print("=" * 70)

    world.set_human_zone(HumanZoneState.CLEAR)
    contradictory_evidence = world.generate_contradictory_evidence("valve_b")
    print("[1] Recorded Contradictory Telemetry:")
    for ev in contradictory_evidence:
        print(f"    - [{ev.source.value.upper()}] obs={ev.observation} conf={ev.confidence:.2f}")

    intent = "Isolate leaking line."
    cycle = runtime.run_cycle(intent=intent, initial_evidence=contradictory_evidence)

    print(f"\n[2] Policy Verdict: {cycle.policy_decision.decision.value}")
    for reason in cycle.policy_decision.reasons:
        if reason.constraint == "contradiction_check":
            print(f"    -> Contradiction Constraint: {reason.details}")

    print(f"[3] Ticket Minted:   {cycle.ticket}")
    print(f"[4] Actuation:       BLOCKED (Contradiction severity prevents execution)")
    assert cycle.ticket is None
    print("\n>>> INVARIANT VERIFIED: High-severity sensor contradictions block actuation.")


def main() -> int:
    parser = argparse.ArgumentParser(description="MotionFence Physical AI Runtime Demonstration.")
    parser.add_argument(
        "--provider",
        choices=["local", "nebius"],
        default="nebius" if os.getenv("NEBIUS_API_KEY") else "local",
        help="Proposal provider (defaults to 'nebius' if NEBIUS_API_KEY is set, else 'local').",
    )
    args = parser.parse_args()

    print("=" * 70)
    print(" MOTIONFENCE: PHYSICAL AI RUNTIME AUTHORIZATION LAYER")
    print(f" Provider: {args.provider.upper()}")
    print("=" * 70)

    world = PhysicalWorld(leak_target="valve_b", leak_severity=0.85)

    if args.provider == "nebius":
        api_key = os.getenv("NEBIUS_API_KEY")
        if not api_key:
            print("ERROR: NEBIUS_API_KEY is not set. Run with --provider local or export NEBIUS_API_KEY.")
            return 1
        provider = NebiusNemotronProvider(api_key=api_key)
    else:
        provider = LocalDeterministicProvider()

    runtime = MotionFenceRuntime(world=world, proposal_provider=provider)

    run_scenario_leak_isolation(runtime, world)
    run_scenario_human_incursion(runtime, world)
    run_scenario_sensor_contradiction(runtime, world)

    print("\n" + "=" * 70)
    print(" ALL SCENARIOS COMPLETED SUCCESSFULLY")
    print("=" * 70)
    return 0


if __name__ == "__main__":
    sys.exit(main())
