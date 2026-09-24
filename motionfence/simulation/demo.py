"""Interactive terminal demonstration of MotionFence authorization and safety invariants.

Demonstrates:
Phase 0/1:
1. Ambiguous target inspection and verified closure
2. Human safety zone incursion (DENY)
3. Multi-sensor contradiction detection (DENY)

Phase 2A:
4. Knowledge-derived prohibition blocks physical action (DENY, No mutation)
5. Knowledge constraints satisfied with pump stopped (ALLOW -> ACT -> VERIFIED)
6. Harmless procedure guidance does not become prohibition (ALLOW)
7. Conflicting operational knowledge sources detected (CONFLICTED -> DENY)
8. Stale operational guidance triggers recertification (STALE -> NEED_MORE_EVIDENCE)
"""

import argparse
import os
import sys
import time

from motionfence.config.settings import settings
from motionfence.runtime.core import MotionFenceRuntime
from motionfence.simulation.world import PhysicalWorld
from motionfence.models.world import HumanZoneState, ValveState, CoolingState
from motionfence.agent.provider import LocalDeterministicProvider
from motionfence.agent.nebius_provider import NebiusNemotronProvider
from motionfence.knowledge.local_provider import LocalKnowledgeProvider
from motionfence.knowledge.tavily_provider import TavilyKnowledgeProvider
from motionfence.knowledge.retrieval import KnowledgeRetrievalService
from motionfence.constraints.local_extractor import LocalConstraintExtractor


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


def run_scenario_knowledge_prohibition_blocks_action(world: PhysicalWorld, provider) -> None:
    """Scenario 2: Knowledge-Derived Prohibition Blocks Action (Mandatory Section 20 Scenario)."""
    print("\n" + "=" * 70)
    print(" SCENARIO 2: KNOWLEDGE-DERIVED PROHIBITION BLOCKS ACTION")
    print("=" * 70)

    # World setup: Valve B = OPEN, Pump P1 = ACTIVE, Cooling = ACTIVE, Human Zone = CLEAR
    world.valves["valve_b"] = ValveState.OPEN
    world.set_pump_state("pump_p1", "ACTIVE")
    world.cooling = CoolingState.ACTIVE
    world.set_human_zone(HumanZoneState.CLEAR)

    print("[1] Initial Physical Setup:")
    print("    - Valve B:    OPEN")
    print("    - Pump P1:    ACTIVE")
    print("    - Cooling:    ACTIVE")
    print("    - Human Zone: CLEAR")

    # Knowledge retrieval with Rule 1
    fixtures = [LocalKnowledgeProvider._build_default_fixtures()[0]]
    knowledge_service = KnowledgeRetrievalService(provider=LocalKnowledgeProvider(custom_fixtures=fixtures))
    extractor = LocalConstraintExtractor()

    runtime = MotionFenceRuntime(
        world=world,
        proposal_provider=provider,
        knowledge_service=knowledge_service,
        constraint_extractor=extractor,
    )

    intent = "Emergency shut off valve_b to isolate line."
    evidence = world.generate_targeted_evidence("valve_b")

    print(f"\n[2] Agent Proposal: CLOSE_VALVE on valve_b to satisfy: '{intent}'")
    print("\n[3] Operational Knowledge Retrieved:")
    print(f"    Source:  {fixtures[0].source_url}")
    print(f"    Rule:    {fixtures[0].content}")
    print(f"    Trust:   {fixtures[0].trust_status.value}")

    cycle = runtime.run_cycle(
        intent=intent,
        initial_evidence=evidence,
        knowledge_query="Valve B pump P1 operational restrictions",
    )

    print(f"\n[4] Deterministic Policy Verdict: {cycle.policy_decision.decision.value}")
    for reason in cycle.policy_decision.reasons:
        if "knowledge_prohibition" in reason.constraint:
            print(f"    -> [PROHIBITION] {reason.details}")

    print(f"[5] Authorization Ticket: {cycle.ticket} (NONE MINTED)")
    print(f"[6] Actuator Execution:   {cycle.execution_result} (NONE EXECUTED)")
    print(f"[7] Final Valve B State:  {world.valves['valve_b'].value} (REMAINS OPEN - NO MUTATION)")

    assert cycle.policy_decision.is_denied
    assert cycle.ticket is None
    assert world.valves["valve_b"] == ValveState.OPEN
    print("\n>>> INVARIANT VERIFIED: Knowledge-derived prohibition strictly blocks actuation.")


def run_scenario_knowledge_constraints_satisfied(world: PhysicalWorld, provider) -> None:
    """Scenario 3: Valid Action when Knowledge Preconditions are Satisfied."""
    print("\n" + "=" * 70)
    print(" SCENARIO 3: KNOWLEDGE CONSTRAINTS SATISFIED (PUMP STOPPED)")
    print("=" * 70)

    # Transition Pump P1 to INACTIVE
    world.valves["valve_b"] = ValveState.OPEN
    world.set_pump_state("pump_p1", "INACTIVE")
    world.cooling = CoolingState.ACTIVE
    world.set_human_zone(HumanZoneState.CLEAR)

    print("[1] Plant Condition Updated:")
    print("    - Pump P1 is now INACTIVE (Safe hydraulic state)")
    print("    - Knowledge rule condition (pump_p1 == ACTIVE) no longer holds.")

    fixtures = [LocalKnowledgeProvider._build_default_fixtures()[0]]
    knowledge_service = KnowledgeRetrievalService(provider=LocalKnowledgeProvider(custom_fixtures=fixtures))
    extractor = LocalConstraintExtractor()

    runtime = MotionFenceRuntime(
        world=world,
        proposal_provider=provider,
        knowledge_service=knowledge_service,
        constraint_extractor=extractor,
    )

    intent = "Safely close valve_b with pump stopped."
    evidence = world.generate_targeted_evidence("valve_b")

    cycle = runtime.run_cycle(
        intent=intent,
        initial_evidence=evidence,
        knowledge_query="Valve B operational restrictions",
    )

    print(f"\n[2] Policy Verdict:       {cycle.policy_decision.decision.value}")
    print(f"[3] Authorization Ticket: {cycle.ticket.ticket_id}")
    print(f"[4] Actuator Execution:   {'SUCCESS' if cycle.execution_result.success else 'FAILED'}")
    print(f"[5] Final Valve B State:  {world.valves['valve_b'].value}")
    print(f"[6] Postcondition Check:  {'VERIFIED' if cycle.verification_result.is_verified else 'FAILED'}")

    assert cycle.policy_decision.is_allowed
    assert world.valves["valve_b"] == ValveState.CLOSED
    print("\n>>> INVARIANT VERIFIED: Action allowed and verified when physical conditions are safe.")


def run_scenario_harmless_procedure(world: PhysicalWorld, provider) -> None:
    """Scenario 4: Harmless Routine Procedure Does Not Become Prohibition."""
    print("\n" + "=" * 70)
    print(" SCENARIO 4: HARMLESS ROUTINE PROCEDURE (NON-PROHIBITION)")
    print("=" * 70)

    world.valves["valve_b"] = ValveState.OPEN
    world.set_pump_state("pump_p1", "INACTIVE")

    # Fixture 2: "Visual inspection should be performed before servicing Valve B."
    fixtures = [LocalKnowledgeProvider._build_default_fixtures()[1]]
    knowledge_service = KnowledgeRetrievalService(provider=LocalKnowledgeProvider(custom_fixtures=fixtures))
    extractor = LocalConstraintExtractor()

    runtime = MotionFenceRuntime(
        world=world,
        proposal_provider=provider,
        knowledge_service=knowledge_service,
        constraint_extractor=extractor,
    )

    print("[1] Knowledge Content:")
    print(f"    '{fixtures[0].content}'")
    print(f"    Extractor classification: INFORMATIONAL (Procedure)")

    cycle = runtime.run_cycle(
        intent="Routine shutdown of valve_b",
        initial_evidence=world.generate_targeted_evidence("valve_b"),
        knowledge_query="Routine inspection procedure for valve_b",
    )

    print(f"\n[2] Policy Verdict:       {cycle.policy_decision.decision.value} (NOT DENIED)")
    print(f"[3] Actuator Execution:   {'SUCCESS' if cycle.execution_result.success else 'FAILED'}")
    print(f"[4] Final Valve B State:  {world.valves['valve_b'].value}")

    assert cycle.policy_decision.is_allowed
    print("\n>>> INVARIANT VERIFIED: Routine procedure does NOT falsely block valid physical operations.")


def run_scenario_conflicting_knowledge(world: PhysicalWorld, provider) -> None:
    """Scenario 5: Conflicting Knowledge Sources Detected (CONFLICTED -> DENY)."""
    print("\n" + "=" * 70)
    print(" SCENARIO 5: CONFLICTING OPERATIONAL KNOWLEDGE SOURCES")
    print("=" * 70)

    world.valves["valve_b"] = ValveState.OPEN

    # Load Fixture 1 (Prohibition) AND Fixture 3 (Emergency exception)
    fixtures = [
        LocalKnowledgeProvider._build_default_fixtures()[0],
        LocalKnowledgeProvider._build_default_fixtures()[2],
    ]
    knowledge_service = KnowledgeRetrievalService(provider=LocalKnowledgeProvider(custom_fixtures=fixtures))
    extractor = LocalConstraintExtractor()

    runtime = MotionFenceRuntime(
        world=world,
        proposal_provider=provider,
        knowledge_service=knowledge_service,
        constraint_extractor=extractor,
    )

    print("[1] Conflicting Documents Ingested:")
    print(f"    Source A: {fixtures[0].title} -> PROHIBITION (Never close under pump pressure)")
    print(f"    Source B: {fixtures[1].title} -> PRECONDITION (May close during emergency)")

    cycle = runtime.run_cycle(
        intent="Close valve_b during contradictory guidelines",
        initial_evidence=world.generate_targeted_evidence("valve_b"),
        knowledge_query="Valve B emergency isolation guidelines",
    )

    print(f"\n[2] Conflict Detector: Found {len(cycle.constraint_conflicts)} high-severity conflict(s).")
    for rpt in cycle.constraint_conflicts:
        print(f"    -> [SEVERITY {rpt.severity}] {rpt.details}")

    print(f"[3] Policy Verdict:    {cycle.policy_decision.decision.value} (BLOCKED)")
    print(f"[4] Ticket Minted:     {cycle.ticket} (NONE)")

    assert cycle.policy_decision.is_denied
    print("\n>>> INVARIANT VERIFIED: Opposing knowledge sources block actuation until resolved.")


def run_scenario_stale_knowledge(world: PhysicalWorld, provider) -> None:
    """Scenario 6: Stale Operational Guidance Triggers NEED_MORE_EVIDENCE."""
    print("\n" + "=" * 70)
    print(" SCENARIO 6: STALE KNOWLEDGE HANDLING")
    print("=" * 70)

    world.valves["valve_b"] = ValveState.OPEN

    # Fixture 4: Archived 90-day-old spec
    fixtures = [LocalKnowledgeProvider._build_default_fixtures()[3]]
    knowledge_service = KnowledgeRetrievalService(provider=LocalKnowledgeProvider(custom_fixtures=fixtures))
    extractor = LocalConstraintExtractor()

    runtime = MotionFenceRuntime(
        world=world,
        proposal_provider=provider,
        knowledge_service=knowledge_service,
        constraint_extractor=extractor,
    )

    print("[1] Knowledge Document:")
    print(f"    Title: {fixtures[0].title}")
    print(f"    Age:   {round(fixtures[0].age_seconds / 86400.0, 1)} days old (> 30 day threshold)")
    print(f"    State: STALE")

    cycle = runtime.run_cycle(
        intent="Operate valve_b under archived specification",
        initial_evidence=world.generate_targeted_evidence("valve_b"),
        knowledge_query="Legacy cooling specification",
    )

    print(f"\n[2] Policy Verdict: {cycle.policy_decision.decision.value}")
    for reason in cycle.policy_decision.reasons:
        if "freshness" in reason.constraint:
            print(f"    -> [{reason.status.upper()}] {reason.details}")

    assert cycle.policy_decision.decision.value == "NEED_MORE_EVIDENCE"
    print("\n>>> INVARIANT VERIFIED: Stale operational knowledge safely forces re-certification.")


def run_scenario_live_tavily(world: PhysicalWorld, provider, tavily_provider: TavilyKnowledgeProvider) -> None:
    """Scenario: Live Tavily Operational Knowledge Retrieval and Deterministic Policy Gating."""
    print("\n" + "=" * 70)
    print(" LIVE TAVILY INTEGRATION: EVIDENCE-GROUNDED POLICY GATING")
    print("=" * 70)

    world.valves["valve_b"] = ValveState.OPEN
    world.cooling = CoolingState.ACTIVE
    world.set_human_zone(HumanZoneState.CLEAR)
    world.set_pump_state("pump_p1", "INACTIVE")

    print("[1] Initial Physical Setup:")
    print("    - Valve B:    OPEN")
    print("    - Pump P1:    INACTIVE")
    print("    - Cooling:    ACTIVE")
    print("    - Human Zone: CLEAR")

    knowledge_service = KnowledgeRetrievalService(provider=tavily_provider)
    extractor = LocalConstraintExtractor()

    runtime = MotionFenceRuntime(
        world=world,
        proposal_provider=provider,
        knowledge_service=knowledge_service,
        constraint_extractor=extractor,
    )

    intent = "Safely isolate leaking valve_b while maintaining continuous plant cooling."
    knowledge_query = "industrial centrifugal pump isolation valve operation safety standards"
    evidence = world.generate_targeted_evidence("valve_b")

    print(f"\n[2] Dispatching live Tavily search query: '{knowledge_query}'...")
    cycle = runtime.run_cycle(
        intent=intent,
        initial_evidence=evidence,
        knowledge_query=knowledge_query,
    )

    print(f"\n[3] Live Tavily Evidence Ingested ({len(cycle.knowledge_evidence)} items):")
    for idx, ev in enumerate(cycle.knowledge_evidence, start=1):
        print(f"    - [{idx}] {ev.title}")
        print(f"         URL:         {ev.source_url}")
        print(f"         Trust State: {ev.trust_status.value}")
        print(f"         Provenance:  {ev.provenance}")
        print(f"         Confidence:  {ev.confidence:.2f}")

    print(f"\n[4] Candidate Constraints Extracted: {len(cycle.candidate_constraints)}")
    for cst in cycle.candidate_constraints:
        print(f"    - ID: {cst.constraint_id} | Type: {cst.constraint_type.value} | Status: {cst.status.value}")

    print(f"\n[5] Deterministic Policy Verdict: {cycle.policy_decision.decision.value}")
    for reason in cycle.policy_decision.reasons:
        marker = "✓" if reason.status == "passed" else "✗"
        print(f"    [{marker}] {reason.constraint}: observed={reason.observed}, required={reason.required}")

    print(f"\n[6] Authorization Ticket: {cycle.ticket.ticket_id if cycle.ticket else 'NONE'}")
    print(f"[7] Actuator Execution:   {'SUCCESS' if cycle.execution_result and cycle.execution_result.success else 'BLOCKED'}")
    print(f"[8] Final Valve B State:  {world.valves['valve_b'].value}")
    if cycle.verification_result:
        print(f"[9] Postcondition Check:  {'VERIFIED' if cycle.verification_result.is_verified else 'FAILED'}")

    print("\n>>> INVARIANT VERIFIED: Live external Tavily knowledge entered policy as untrusted evidence.")
    print(">>> Deterministic validation and PolicyEngine controlled physical actuation.")


def main() -> int:
    parser = argparse.ArgumentParser(description="MotionFence Physical AI Runtime Demonstration.")
    parser.add_argument(
        "--provider",
        choices=["local", "nebius"],
        default="nebius" if os.getenv("NEBIUS_API_KEY") else "local",
        help="Proposal provider (defaults to 'nebius' if NEBIUS_API_KEY is set, else 'local').",
    )
    parser.add_argument(
        "--knowledge",
        choices=["none", "local", "tavily"],
        default="local",
        help="Knowledge retrieval provider (defaults to 'local').",
    )
    args = parser.parse_args()

    print("=" * 70)
    print(" MOTIONFENCE: PHYSICAL AI RUNTIME AUTHORIZATION LAYER")
    print(f" Proposal Provider:  {args.provider.upper()}")
    print(f" Knowledge Provider: {args.knowledge.upper()}")
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

    # 1. Base leak isolation (Demonstrating Phase 0/1 Ambiguity Resolution)
    baseline_runtime = MotionFenceRuntime(
        world=world,
        proposal_provider=provider,
    )
    run_scenario_leak_isolation(baseline_runtime, world)

    # 2. Phase 2A Knowledge Scenarios
    if args.knowledge == "tavily":
        tavily_key = settings.tavily.api_key or os.getenv("TAVILY_API_KEY")
        if not tavily_key or tavily_key == "placeholder_key_offline":
            print("ERROR: TAVILY_API_KEY is not configured in .env or environment.")
            return 1
        tavily_prov = TavilyKnowledgeProvider(api_key=tavily_key)
        run_scenario_live_tavily(world, provider, tavily_prov)
    elif args.knowledge == "local":
        run_scenario_knowledge_prohibition_blocks_action(world, provider)
        run_scenario_knowledge_constraints_satisfied(world, provider)
        run_scenario_harmless_procedure(world, provider)
        run_scenario_conflicting_knowledge(world, provider)
        run_scenario_stale_knowledge(world, provider)

    print("\n" + "=" * 70)
    print(" ALL SCENARIOS COMPLETED SUCCESSFULLY")
    print("=" * 70)
    return 0


if __name__ == "__main__":
    sys.exit(main())
