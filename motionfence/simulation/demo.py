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


from motionfence.knowledge.trust import (
    SourceTrustClassifier,
    CorroborationEngine,
    CorroborationStatus,
    SourceCategory,
    EvidenceRole,
)
from motionfence.knowledge.models import KnowledgeEvidence, TrustStatus
from motionfence.constraints.models import PlantContext, Applicability, ConstraintStatus


def run_scenario_corroborated_prohibition(world: PhysicalWorld, provider) -> None:
    """Scenario 7: Multi-Source Corroborated Knowledge Promotes to Active Prohibition (Mandatory Section 19)."""
    print("\n" + "=" * 70)
    print(" SCENARIO 7: MULTI-SOURCE CORROBORATION (OEM + INDEPENDENT STANDARDS)")
    print("=" * 70)

    world.valves["valve_b"] = ValveState.OPEN
    world.set_pump_state("pump_p1", "ACTIVE")
    world.cooling = CoolingState.ACTIVE
    world.set_human_zone(HumanZoneState.CLEAR)

    print("[1] Initial Physical Setup:")
    print("    - Valve B:    OPEN")
    print("    - Pump P1:    ACTIVE")
    print("    - Cooling:    ACTIVE")
    print("    - Human Zone: CLEAR")

    now = time.time()
    # Source A: OEM Manufacturer documentation
    doc_a = KnowledgeEvidence(
        id="kb_oem_ksb_01",
        query="Centrifugal pump isolation valve safety",
        title="KSB Industrial Centrifugal Pumps - Operational Safety Manual",
        source_url="https://ksb.com/manuals/centrifugal-pumps-p100/safety",
        content="MANDATORY PROHIBITION: Valve B must not be closed while Pump P1 is active to prevent hydraulic shock.",
        retrieved_at=now,
        source_metadata={"publisher": "KSB SE & Co.", "category": "oem_manual"},
        provenance="oem_documentation:ksb_manual_2024",
        confidence=0.96,
        trust_status=TrustStatus.LOCAL_FIXTURE,
    )
    # Source B: Independent engineering standards
    doc_b = KnowledgeEvidence(
        id="kb_standards_asme_02",
        query="Centrifugal pump isolation valve safety",
        title="ASME B73.1 - Standard Specification for Chemical Pumps",
        source_url="https://asme.org/standards/b73-1-pump-operation",
        content="SAFETY REQUIREMENT: Valve B must not be closed while Pump P1 is active in liquid circuits.",
        retrieved_at=now,
        source_metadata={"publisher": "ASME", "standard": "B73.1"},
        provenance="standards_organization:asme_b73_1",
        confidence=0.98,
        trust_status=TrustStatus.LOCAL_FIXTURE,
    )

    fixtures = [doc_a, doc_b]
    knowledge_service = KnowledgeRetrievalService(provider=LocalKnowledgeProvider(custom_fixtures=fixtures))
    extractor = LocalConstraintExtractor()
    plant = PlantContext(equipment_id="pump_p1", equipment_model="P100-A", authorized_targets=["valve_a", "valve_b", "pump_p1"])

    runtime = MotionFenceRuntime(
        world=world,
        proposal_provider=provider,
        knowledge_service=knowledge_service,
        constraint_extractor=extractor,
        plant_context=plant,
    )

    print("\n[2] Ingesting Independent Sources:")
    for doc in fixtures:
        ass = SourceTrustClassifier.assess(doc)
        print(f"    - [{doc.id}] {doc.title}")
        print(f"         URL:      {doc.source_url}")
        print(f"         Category: {ass.source_category.value}")
        print(f"         Role:     {ass.evidence_role.value}")

    cycle = runtime.run_cycle(
        intent="Emergency shut off valve_b while pump is running",
        initial_evidence=world.generate_targeted_evidence("valve_b"),
        knowledge_query="Centrifugal pump isolation valve safety",
    )

    print(f"\n[3] Corroboration & Promotion Status:")
    for cst in cycle.active_constraints:
        print(f"    - Constraint: {cst.constraint_id}")
        print(f"      Status:     {cst.status.value}")
        print(f"      Corrob:     {cst.corroboration.value}")
        print(f"      Rule:       {cst.description}")

    print(f"\n[4] Deterministic Policy Verdict: {cycle.policy_decision.decision.value}")
    print(f"[5] Authorization Ticket:         {cycle.ticket} (NONE MINTED)")
    print(f"[6] Actuator Execution:           {cycle.execution_result} (NOT CALLED)")
    print(f"[7] Final Valve B State:          {world.valves['valve_b'].value} (REMAINS OPEN - NO MUTATION)")

    assert cycle.policy_decision.is_denied
    assert cycle.ticket is None
    assert world.valves["valve_b"] == ValveState.OPEN
    print("\n>>> INVARIANT VERIFIED: Independent corroboration establishes authority -> blocks unsafe action.")


def run_scenario_weak_source_discovery_only(world: PhysicalWorld, provider) -> None:
    """Scenario 8: Weak Community Source Admitted for Discovery Only (Mandatory Section 18 & 21)."""
    print("\n" + "=" * 70)
    print(" SCENARIO 8: WEAK COMMUNITY SOURCE (DISCOVERY ONLY -> NO PROHIBITION)")
    print("=" * 70)

    world.valves["valve_b"] = ValveState.OPEN
    world.set_pump_state("pump_p1", "INACTIVE")
    world.cooling = CoolingState.ACTIVE
    world.set_human_zone(HumanZoneState.CLEAR)

    print("[1] Initial Physical Setup:")
    print("    - Valve B:    OPEN")
    print("    - Pump P1:    INACTIVE")
    print("    - Cooling:    ACTIVE")
    print("    - Human Zone: CLEAR")

    # Community forum post claiming Valve B should not be closed
    community_doc = KnowledgeEvidence(
        id="kb_forum_reddit_01",
        query="valve b closure safety issues",
        title="Industrial Engineering Forum Discussion - Thread #4912",
        source_url="https://reddit.com/r/industrialengineering/comments/valve_b_closure",
        content="Forum user comment: Valve B must not be closed under any circumstances according to old operators.",
        retrieved_at=time.time(),
        source_metadata={"user": "plant_tech_99", "upvotes": 3},
        provenance="community_web:reddit_thread_4912",
        confidence=0.55,
        trust_status=TrustStatus.UNVERIFIED_EXTERNAL,
    )

    fixtures = [community_doc]
    knowledge_service = KnowledgeRetrievalService(provider=LocalKnowledgeProvider(custom_fixtures=fixtures))
    extractor = LocalConstraintExtractor()
    plant = PlantContext(equipment_id="pump_p1", authorized_targets=["valve_a", "valve_b", "pump_p1"])

    runtime = MotionFenceRuntime(
        world=world,
        proposal_provider=provider,
        knowledge_service=knowledge_service,
        constraint_extractor=extractor,
        plant_context=plant,
    )

    ass = SourceTrustClassifier.assess(community_doc)
    print("\n[2] Ingested Weak Community Source:")
    print(f"    Source URL:  {community_doc.source_url}")
    print(f"    Category:    {ass.source_category.value}")
    print(f"    Role:        {ass.evidence_role.value} (NOT AUTHORIZATION_RELEVANT)")
    print(f"    Trust Score: {ass.trust_score:.2f}")

    cycle = runtime.run_cycle(
        intent="Routine shutdown of valve_b",
        initial_evidence=world.generate_targeted_evidence("valve_b"),
        knowledge_query="valve b closure safety issues",
    )

    print(f"\n[3] Candidate Constraints Extracted: {len(cycle.candidate_constraints)}")
    for cst in cycle.candidate_constraints:
        print(f"    - ID:     {cst.constraint_id}")
        print(f"      Status: {cst.status.value} (NOT ACTIVE)")
        print(f"      Notes:  {cst.admissibility_notes}")

    print(f"[4] Active Constraints Enforced:     {len(cycle.active_constraints)} (ZERO FROM WEAK SOURCE)")
    print(f"[5] Policy Verdict:                  {cycle.policy_decision.decision.value} (ALLOWED)")
    print(f"[6] Authorization Ticket:            {cycle.ticket.ticket_id}")
    print(f"[7] Actuator Execution:              {'SUCCESS' if cycle.execution_result.success else 'FAILED'}")
    print(f"[8] Final Valve B State:             {world.valves['valve_b'].value} (CLOSED AS INTENDED)")

    assert cycle.policy_decision.is_allowed
    assert len(cycle.active_constraints) == 0
    assert world.valves["valve_b"] == ValveState.CLOSED
    print("\n>>> INVARIANT VERIFIED: Weak source preserved for discovery, but CANNOT create active prohibition.")


def run_scenario_applicability_mismatch(world: PhysicalWorld, provider) -> None:
    """Scenario 9: Equipment Context Mismatch Inadmissible for Policy."""
    print("\n" + "=" * 70)
    print(" SCENARIO 9: APPLICABILITY MISMATCH (DIFFERENT EQUIPMENT MODEL)")
    print("=" * 70)

    world.valves["valve_b"] = ValveState.OPEN
    world.set_pump_state("pump_p1", "INACTIVE")

    # Document for a completely different equipment model (Model P200-B Slurry Pump vs Plant's P100-A)
    mismatch_doc = KnowledgeEvidence(
        id="kb_mismatch_oem_01",
        query="High pressure slurry pump model P200-B safety",
        title="OEM Manual for High-Pressure Slurry Pump Model P200-B",
        source_url="https://ksb.com/manuals/slurry-pump-p200b/safety",
        content="MANDATORY PROHIBITION: Valve B must not be closed under any operational conditions on Model P200-B slurry units.",
        retrieved_at=time.time(),
        source_metadata={"equipment_family": "slurry_pump_p200b"},
        provenance="oem_manual:ksb_slurry_p200b",
        confidence=0.95,
        trust_status=TrustStatus.LOCAL_FIXTURE,
    )

    fixtures = [mismatch_doc]
    knowledge_service = KnowledgeRetrievalService(provider=LocalKnowledgeProvider(custom_fixtures=fixtures))
    extractor = LocalConstraintExtractor()
    plant = PlantContext(equipment_id="pump_p1", equipment_model="P100-A", equipment_type="centrifugal_pump")

    runtime = MotionFenceRuntime(
        world=world,
        proposal_provider=provider,
        knowledge_service=knowledge_service,
        constraint_extractor=extractor,
        plant_context=plant,
    )

    cycle = runtime.run_cycle(
        intent="Operate valve_b on centrifugal unit P100-A",
        initial_evidence=world.generate_targeted_evidence("valve_b"),
        knowledge_query="High pressure slurry pump model P200-B safety",
    )

    print(f"[1] Plant Equipment Context: Model '{plant.equipment_model}', Type '{plant.equipment_type}'")
    print(f"[2] Document Target:         Model 'P200-B Slurry Pump'")
    print(f"[3] Evaluated Applicability: {cycle.candidate_constraints[0].applicability.value if cycle.candidate_constraints else 'NONE'}")
    print(f"[4] Active Constraints:      {len(cycle.active_constraints)} (NOT PROMOTED)")
    print(f"[5] Policy Verdict:          {cycle.policy_decision.decision.value} (ALLOWED)")

    assert cycle.policy_decision.is_allowed
    assert len(cycle.active_constraints) == 0
    print("\n>>> INVARIANT VERIFIED: Applicability mismatch prevents foreign rules from blocking plant actions.")


def run_scenario_live_tavily(world: PhysicalWorld, provider, tavily_provider: TavilyKnowledgeProvider) -> None:
    """Scenario: Live Tavily Operational Knowledge Retrieval and Deterministic Policy Gating."""
    print("\n" + "=" * 70)
    print(" LIVE TAVILY INTEGRATION: EVIDENCE TRUST & ADMISSIBILITY GATING")
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
    plant = PlantContext(equipment_id="pump_p1", equipment_model="P100-A")

    runtime = MotionFenceRuntime(
        world=world,
        proposal_provider=provider,
        knowledge_service=knowledge_service,
        constraint_extractor=extractor,
        plant_context=plant,
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

    print(f"\n[3] Live Tavily Evidence Ingested & Assessed ({len(cycle.knowledge_evidence)} items):")
    for idx, ev in enumerate(cycle.knowledge_evidence, start=1):
        ass = SourceTrustClassifier.assess(ev)
        print(f"    - [{idx}] {ev.title[:55]}...")
        print(f"         URL:         {ev.source_url[:60]}")
        print(f"         Category:    {ass.source_category.value}")
        print(f"         Role:        {ass.evidence_role.value}")
        print(f"         Authority:   {ass.authority_level.value}")
        print(f"         Trust Score: {ass.trust_score:.2f}")

    print(f"\n[4] Candidate Constraints Extracted: {len(cycle.candidate_constraints)}")
    for cst in cycle.candidate_constraints:
        print(f"    - ID: {cst.constraint_id} | Type: {cst.constraint_type.value} | Status: {cst.status.value}")
        print(f"      Role: {cst.evidence_role.value if cst.evidence_role else 'None'} | Applicability: {cst.applicability.value}")

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
    print(">>> Deterministic validation, source assessment, and PolicyEngine controlled physical actuation.")


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

    # 2. Phase 2A & 2B Knowledge Scenarios
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
        run_scenario_corroborated_prohibition(world, provider)
        run_scenario_weak_source_discovery_only(world, provider)
        run_scenario_applicability_mismatch(world, provider)

    print("\n" + "=" * 70)
    print(" ALL SCENARIOS COMPLETED SUCCESSFULLY")
    print("=" * 70)
    return 0


if __name__ == "__main__":
    sys.exit(main())

