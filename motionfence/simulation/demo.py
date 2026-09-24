"""Interactive terminal demonstration of the MotionFence runtime control loop."""

import sys
import time

from motionfence.runtime.core import MotionFenceRuntime
from motionfence.simulation.world import PhysicalWorld
from motionfence.simulation.actuator import PhysicalActuator
from motionfence.policy.models import Policy
from motionfence.models.actions import ActionProposal, ActionType
from motionfence.models.world import HumanZoneState, CoolingState
from motionfence.models.events import EventType


def run_demo() -> int:
    """Run an end-to-end demonstration of MotionFence authorization and verification."""
    print("=" * 70)
    print(" MOTIONFENCE: PHYSICAL AI RUNTIME AUTHORIZATION LAYER")
    print(" Scenario: Industrial Leak Isolation & Continuous Cooling Safety")
    print("=" * 70)

    # 1. Initialize physical world and runtime
    world = PhysicalWorld(leak_target="valve_b", leak_severity=0.85)
    runtime = MotionFenceRuntime(world=world)

    intent = "Isolate the leaking line while keeping cooling active."
    print(f"\n[1] Human intent received:")
    print(f"    \"{intent}\"")

    # Initial state summary
    init_state = world.get_state()
    print(f"\n[2] Initial Physical World State (v{init_state.version}):")
    print(f"    - Valve A:      {init_state.valves['valve_a'].value}")
    print(f"    - Valve B:      {init_state.valves['valve_b'].value}")
    print(f"    - Cooling:      {init_state.cooling.value}")
    print(f"    - Leak:         ACTIVE on {init_state.leak.target} ({init_state.leak.flow_rate_lpm:.1f} LPM)")
    print(f"    - Human Zone:   {init_state.human_zone.value}")

    # 2. First pass: Ambiguous evidence
    ambiguous_evidence = world.generate_initial_ambiguous_evidence()
    print(f"\n[3] Ambient Observations Recorded:")
    for ev in ambiguous_evidence:
        print(f"    - [{ev.source.value.upper()}] target={ev.target} conf={ev.confidence:.2f} ({ev.provenance})")

    # 3. Agent proposes action
    proposal_1 = runtime.proposal_provider.propose(
        intent=intent,
        world_state=init_state,
        evidence=ambiguous_evidence,
    )
    print(f"\n[4] Agent Proposes Physical Action:")
    print(f"    Action:     {proposal_1.action_type.value}")
    print(f"    Target:     {proposal_1.target}")
    print(f"    Confidence: {proposal_1.model_confidence:.2f}")
    print(f"    Rationale:  {proposal_1.rationale}")

    # 4. Policy evaluation 1
    decision_1 = runtime.policy.min_target_confidence
    cycle_1 = runtime.run_cycle(
        intent=intent,
        initial_evidence=ambiguous_evidence,
        gather_additional_evidence_on_request=False,
    )
    d1 = cycle_1.policy_decision

    print(f"\n[5] MotionFence Policy Evaluation (Pass 1):")
    print(f"    Verdict:    {d1.decision.value}")
    for reason in d1.reasons:
        status_marker = "✓" if reason.status == "passed" else "✗"
        print(f"    [{status_marker}] Constraint '{reason.constraint}': observed={reason.observed}, required={reason.required}")
        if reason.status != "passed":
            print(f"        -> Reason: {reason.details}")

    assert d1.needs_evidence, "Expected Pass 1 to require more evidence!"
    print(f"\n>>> RESULT: Actuator action BLOCKED. Direct execution denied without sufficient confidence.")

    # 5. Targeted evidence gathering
    print(f"\n[6] Runtime Initiates Targeted Inspection on '{proposal_1.target}'...")
    targeted_evidence = world.generate_targeted_evidence(proposal_1.target)
    for ev in targeted_evidence:
        print(f"    - [{ev.source.value.upper()}] target={ev.target} conf={ev.confidence:.2f} ({ev.provenance})")

    combined_evidence = list(ambiguous_evidence) + list(targeted_evidence)

    # 6. Pass 2: Re-evaluate with complete evidence
    cycle_2 = runtime.run_cycle(
        intent=intent,
        initial_evidence=combined_evidence,
        gather_additional_evidence_on_request=False,
    )
    d2 = cycle_2.policy_decision
    tkt = cycle_2.ticket
    exec_res = cycle_2.execution_result
    verif = cycle_2.verification_result

    print(f"\n[7] MotionFence Policy Evaluation (Pass 2):")
    print(f"    Verdict:    {d2.decision.value}")
    for reason in d2.reasons:
        status_marker = "✓" if reason.status == "passed" else "✗"
        print(f"    [{status_marker}] Constraint '{reason.constraint}': observed={reason.observed}, required={reason.required}")

    print(f"\n[8] Action Authorization:")
    print(f"    Ticket ID:  {tkt.ticket_id}")
    print(f"    Signed By:  {tkt.authorized_by}")
    print(f"    Signature:  {tkt.signature[:24]}...")

    print(f"\n[9] Physical Actuator Execution:")
    print(f"    Status:     {'SUCCESS' if exec_res.success else 'FAILED'}")
    print(f"    Details:    {exec_res.message}")
    print(f"    Transition: World state v{exec_res.state_version_before} -> v{exec_res.state_version_after}")

    # Post-action state
    post_state = world.get_state()
    print(f"\n[10] Post-Action World State (v{post_state.version}):")
    print(f"    - Valve A:      {post_state.valves['valve_a'].value}")
    print(f"    - Valve B:      {post_state.valves['valve_b'].value}")
    print(f"    - Cooling:      {post_state.cooling.value}")
    print(f"    - Leak:         {'ACTIVE' if post_state.leak.active else 'RESOLVED'} ({post_state.leak.flow_rate_lpm:.1f} LPM)")
    print(f"    - Human Zone:   {post_state.human_zone.value}")

    print(f"\n[11] Post-Action Verification:")
    for postcond, val in verif.expected_postconditions.items():
        obs = verif.observed_postconditions.get(postcond)
        status_str = "PASS" if obs == val else "FAIL"
        print(f"    - {postcond} == {val}: {status_str} (observed={obs})")

    print(f"\n" + "=" * 70)
    print(f" FINAL CONTROL LOOP RESULT: {verif.status.value}")
    print("=" * 70)

    return 0


if __name__ == "__main__":
    sys.exit(run_demo())
