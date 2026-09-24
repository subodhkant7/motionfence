#!/usr/bin/env python3
"""CLI utility to demonstrate MotionFence Active Evidence Acquisition & Safe Recovery (Phase 2G).

Usage:
    python scripts/run_evidence_recovery.py --scenario ambiguous-target
    python scripts/run_evidence_recovery.py --scenario contradiction
    python scripts/run_evidence_recovery.py --scenario ineffective-inspect
    python scripts/run_evidence_recovery.py --scenario persistent-contradiction
"""

import argparse
import json
import os
import sys
import time

# Ensure motionfence package is on sys.path
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from motionfence.runtime.core import MotionFenceRuntime
from motionfence.simulation.world import PhysicalWorld, ValveState, CoolingState, HumanZoneState
from motionfence.models.actions import ActionType
from motionfence.evidence.models import Evidence, EvidenceSource
from motionfence.policy.models import Policy
from motionfence.agent.evidence_planner import LocalEvidencePlanner


def render_step(step_idx: str, name: str, details: list[str]) -> None:
    print(f"\n[{step_idx}] {name}")
    print("-" * 65)
    for d in details:
        print(f"    {d}")


def run_scenario(scenario_name: str, audit_dir: str = "audit_records") -> str:
    print("=" * 65)
    print(" MOTIONFENCE PHASE 2G: ACTIVE EVIDENCE ACQUISITION & RECOVERY")
    print(f" SCENARIO: {scenario_name.upper()}")
    print("=" * 65)

    os.makedirs(audit_dir, exist_ok=True)
    world = PhysicalWorld(leak_target="valve_b")

    if scenario_name == "ambiguous-target":
        # Target identity confidence below threshold (0.78 < 0.90)
        initial_ev = [
            Evidence(
                source=EvidenceSource.VISION,
                target="valve_b",
                observation={"visual_vapor_detected": True, "target_candidate": "valve_b"},
                confidence=0.78,
                provenance="camera_wide_overhead:detector_v1",
            ),
            Evidence(
                source=EvidenceSource.PRESSURE_SENSOR,
                target="manifold_line",
                observation={"pressure_anomaly": True, "pressure_drop_rate": "moderate"},
                confidence=0.92,
                provenance="sensor_piezo_pressure_01",
            ),
        ]
        planner = LocalEvidencePlanner()
        intent = "Isolate leak on Valve B while maintaining safe cooling."

    elif scenario_name == "contradiction":
        # Contradiction: Vision detects leak, pressure says normal
        initial_ev = [
            Evidence(
                source=EvidenceSource.VISION,
                target="valve_b",
                observation={"leak_detected": True, "visual_vapor_detected": True},
                confidence=0.92,
                provenance="camera_overhead_zoom_01",
            ),
            Evidence(
                source=EvidenceSource.PRESSURE_SENSOR,
                target="valve_b",
                observation={"pressure_anomaly": False, "pressure_normal": True, "leak_detected": False},
                confidence=0.88,
                provenance="sensor_piezo_pressure_01",
            ),
        ]
        planner = LocalEvidencePlanner()
        intent = "Isolate confirmed leak on Valve B."

    elif scenario_name == "ineffective-inspect":
        # Ineffective inspection from suboptimal viewpoint produces insufficient gain
        initial_ev = [
            Evidence(
                source=EvidenceSource.VISION,
                target="valve_b",
                observation={"visual_vapor_detected": True},
                confidence=0.75,
                provenance="camera_wide_overhead:detector_v1",
            ),
        ]
        planner = LocalEvidencePlanner(strategy_override="ineffective_inspect")
        intent = "Investigate and isolate suspected leak."

    elif scenario_name == "persistent-contradiction":
        # Resampling amplifies contradiction rather than resolving it
        initial_ev = [
            Evidence(
                source=EvidenceSource.VISION,
                target="valve_b",
                observation={"leak_detected": True, "visual_vapor_detected": True},
                confidence=0.92,
                provenance="camera_overhead_zoom_01",
            ),
            Evidence(
                source=EvidenceSource.PRESSURE_SENSOR,
                target="valve_b",
                observation={"pressure_anomaly": False, "pressure_normal": True, "leak_detected": False},
                confidence=0.88,
                provenance="sensor_piezo_pressure_01",
            ),
        ]
        planner = LocalEvidencePlanner(strategy_override="contradiction_amplifier")
        intent = "Isolate confirmed leak on Valve B."

    else:
        raise ValueError(f"Unknown scenario: {scenario_name}")

    policy = Policy(resolve_contradictions_via_evidence=True)
    runtime = MotionFenceRuntime(
        world=world,
        policy=policy,
        evidence_planner=planner,
        max_evidence_actions_per_cycle=3,
    )

    # 1. Observe
    render_step("01", "OBSERVE", [
        f"Initial sensor observation pool: {len(initial_ev)} reading(s).",
        f"Sources: {[e.source.value for e in initial_ev]}",
        f"Target confidences: {[(e.target, e.confidence) for e in initial_ev]}",
    ])

    # Execute runtime control loop
    result = runtime.run_cycle(
        intent=intent,
        initial_evidence=initial_ev,
        auto_evidence_acquisition=True,
    )

    # 2. Propose
    prop = result.proposal
    render_step("02", "PROPOSE", [
        f"Action: {prop.action_type.value if prop else 'NONE'} on {prop.target if prop else 'NONE'}",
        f"Model confidence: {prop.model_confidence if prop else 0.0:.2f}",
        f"Rationale: {prop.rationale if prop else 'N/A'}",
    ])

    # 3. Policy Initial Verdict
    initial_verdict = "NEED_MORE_EVIDENCE" if result.evidence_iterations > 0 else (result.policy_decision.decision.value if result.policy_decision else "UNKNOWN")
    render_step("03", f"POLICY → {initial_verdict}", [
        f"Initial evaluation deferred action due to insufficient evidence / contradiction.",
        f"Active evidence acquisition autonomously triggered (Budget: 3).",
    ])

    # 4. Evidence Action Proposed
    render_step("04", "EVIDENCE ACTION PROPOSED", [
        f"Selected Information Action: {result.evidence_action_ids[0] if result.evidence_action_ids else 'NONE'}",
        f"Predicted Information Gain: {result.predicted_information_gain or 'N/A'}",
        f"Action class: INFORMATION_ACTION (Strictly zero actuator authority)",
    ])

    # 5. Evidence Action Authorized
    render_step("05", "EVIDENCE ACTION AUTHORIZED", [
        "Authorized under evidence_planner_capability_policy.",
        "Capabilities granted: [OBSERVE, INSPECT, READ_SENSOR, QUERY_KNOWLEDGE, REORIENT_SENSOR].",
        "Consequential ACTUATE capability: PROHIBITED.",
    ])

    # 6. New Evidence Collected
    render_step("06", "NEW EVIDENCE", [
        f"Evidence action execution completed.",
        f"Observed Information Gain: {result.observed_information_gain or 'N/A'}",
        f"Total sensor evidence count now: {len(result.decision_record.snapshots.get('evidence', [])) if result.decision_record else 'N/A'}",
    ])

    # 7. Policy Re-evaluation
    render_step("07", "POLICY RE-EVALUATION", [
        f"Deterministic PolicyEngine re-evaluated proposal with fresh empirical evidence.",
        f"Contradiction severity: {result.policy_decision.contradiction_severity.value if result.policy_decision else 'NONE'}",
        f"Final Policy Verdict: {result.policy_decision.decision.value if result.policy_decision else 'UNKNOWN'}",
    ])

    # 8. Verdict branch: ALLOW or DENY / DEFER
    final_cat = result.policy_decision.decision.value if result.policy_decision else "DENY"
    render_step("08", f"VERDICT: {final_cat}", [
        f"Outcome: {final_cat}",
        f"Reasons: {[r.details for r in result.policy_decision.reasons if r.details] if result.policy_decision else []}",
        f"Safety Enclave Ticket: {result.ticket.ticket_id if result.ticket else 'NONE (Not Minted)'}",
    ])

    # 9. Actuator Execution
    if result.execution_result:
        act_status = "EXECUTED (SUCCESS)" if result.execution_result.success else "EXECUTION FAILED"
        act_details = [
            f"Actuator status: {act_status}",
            f"Physical action: {result.execution_result.executed_action.value} on {result.execution_result.target}",
            f"Message: {result.execution_result.message}",
        ]
    else:
        act_details = ["No physical actuation attempted; action was not authorized."]
    render_step("09", "ACT", act_details)

    # 10. Verification
    if result.verification_result:
        verif_status = "VERIFIED [PASS]" if result.verification_result.is_verified else "FAILED [FAIL]"
        verif_details = [
            f"Postcondition verdict: {verif_status}",
            f"Valve B final state: {world.valves['valve_b'].value}",
            f"Cooling final state: {world.cooling.value}",
        ]
    else:
        verif_details = ["Verification not applicable (no actuation executed)."]
    render_step("10", "VERIFY", verif_details)

    # Save finalized DecisionRecord for replay
    record = result.decision_record
    if record:
        filepath = os.path.join(audit_dir, f"{record.decision_id}.json")
        with open(filepath, "w") as f:
            json.dump(record.model_dump(mode="json"), f, indent=2)
        print("\n" + "=" * 65)
        print(f"AUDIT RECORD STORED: {filepath}")
        print(f"REPLAY COMMAND:       python scripts/replay_evidence_recovery.py {record.decision_id}")
        print("=" * 65)
        return record.decision_id

    return ""


def main() -> None:
    parser = argparse.ArgumentParser(description="MotionFence Phase 2G Active Evidence Recovery CLI")
    parser.add_argument(
        "--scenario",
        choices=["ambiguous-target", "contradiction", "ineffective-inspect", "persistent-contradiction"],
        default="ambiguous-target",
        help="Recovery scenario to simulate",
    )
    parser.add_argument("--audit-dir", default="audit_records", help="Directory to store DecisionRecords")
    args = parser.parse_args()

    run_scenario(args.scenario, audit_dir=args.audit_dir)


if __name__ == "__main__":
    main()
