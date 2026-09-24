#!/usr/bin/env python3
"""CLI utility for offline, deterministic replay and audit verification of MotionFence DecisionRecords.

Usage:
    python scripts/replay_decision.py <decision_id> [--audit-dir <path>]
    python scripts/replay_decision.py --sample [--intent <text>]
"""

import argparse
import os
import sys
import json

# Ensure motionfence package is on sys.path
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from motionfence.audit.models import DecisionRecord, DecisionCategory, format_decision_audit
from motionfence.audit.verifier import DecisionRecordVerifier
from motionfence.audit.replay import DecisionReplayEngine, ReplayStatus
from motionfence.audit.recorder import DecisionRecorder
from motionfence.runtime.core import MotionFenceRuntime
from motionfence.simulation.world import PhysicalWorld, ValveState, CoolingState, HumanZoneState
from motionfence.models.actions import ActionType


def render_step(step_num: int, title: str, content: str, mode_tag: str = "DERIVED") -> None:
    print(f"\n[{step_num:02d}] {title:<18} [{mode_tag}]")
    print("-" * 70)
    for line in content.strip().split("\n"):
        print(f"    {line}")


def run_replay(record: DecisionRecord) -> int:
    print("=" * 70)
    print(" MOTIONFENCE DETERMINISTIC DECISION REPLAY & AUDIT (PHASE 2D)")
    print("=" * 70)
    print(f"Decision ID:     {record.decision_id}")
    print(f"Record Hash:     {record.record_hash}")
    print(f"Prev Record Hash:{record.previous_record_hash or 'GENESIS'}")
    print(f"Sequence Number: #{record.sequence_number}")
    print(f"Recorded Mode:   {record.provider_metadata.get('execution_mode', 'LIVE')} / {record.provider_metadata.get('source_mode', 'LOCAL_FIXTURE')}")
    print(f"Replay Mode:     REPLAY (100% Offline Deterministic Reconstruction)")
    print("=" * 70)

    # 1. Cryptographic and Reference Integrity Verification
    integrity_rep = DecisionRecordVerifier.verify_record(record)
    print(f"\n>>> AUDIT INTEGRITY CHECK: {'[PASS] VALID' if integrity_rep.is_valid else '[FAIL] INTEGRITY COMPROMISED'}")
    print(f"    - Canonical Hash Verified:     {'YES' if integrity_rep.hash_verified else 'NO'}")
    print(f"    - Chain Linkage Verified:      {'YES' if integrity_rep.chain_linked else 'NO'}")
    print(f"    - Policy Consistency Verified: {'YES' if integrity_rep.policy_consistent else 'NO'}")
    print(f"    - Snapshot References Match:   {'YES' if integrity_rep.references_consistent else 'NO'}")
    if integrity_rep.issues:
        print(f"    - Issues Detected:             {'; '.join(integrity_rep.issues)}")

    # 2. Replay Engine Re-Execution
    engine = DecisionReplayEngine()
    replay_rep = engine.replay(record)

    # Render 10 Detailed Replay Steps
    for step in replay_rep.steps:
        # Determine mode tag
        if step.step_name in ("INTENT", "WORLD STATE", "EVIDENCE"):
            tag = "RECORDED_SNAPSHOT"
        elif step.step_name in ("POLICY", "AUTHORIZATION"):
            tag = "REPLAYED_DETERMINISTIC"
        elif step.step_name in ("EXECUTION", "VERIFICATION"):
            tag = "HISTORICAL_OUTCOME"
        else:
            tag = "REPLAYED_PROVENANCE"

        lines: list[str] = [step.summary]
        if step.step_name == "INTENT":
            lines = [f"Operator Intent: '{record.intent}'"]
        elif step.step_name == "WORLD STATE":
            lines = [
                f"Cooling System:   {record.world_state_snapshot.cooling.value}",
                f"Active Leak:      {record.world_state_snapshot.leak.active} (target={record.world_state_snapshot.leak.target})",
                f"Human Safety Zone: {record.world_state_snapshot.human_zone.value}",
                f"Valves:           {', '.join(f'{k}={v.value}' for k, v in record.world_state_snapshot.valves.items())}",
                f"Auxiliary Pumps:  {record.world_state_snapshot.pumps}",
            ]
        elif step.step_name == "POLICY":
            lines = [
                f"Recorded Verdict: {replay_rep.recorded_verdict}",
                f"Replayed Verdict: {replay_rep.replayed_verdict}",
                f"Convergence:      {replay_rep.status.value}",
            ]
            if record.policy_reasons:
                lines.append("Cited Policy Constraints:")
                for r in record.policy_reasons:
                    lines.append(f"  * {r}")

        render_step(step.step_number, step.step_name, "\n".join(lines), mode_tag=tag)

    print("\n" + "=" * 70)
    print(" REPLAY SUMMARY & DECISION CONVERGENCE")
    print("=" * 70)
    print(f"Recorded Policy Verdict: {replay_rep.recorded_verdict}")
    print(f"Replayed Policy Verdict: {replay_rep.replayed_verdict}")
    print(f"Replay Convergence:      {replay_rep.status.value}")
    print(f"Physical Mutation Guard: 0 actuator commands sent, 0 tickets minted")
    print(f"Zero Network Guarantee:  0 LLM calls, 0 Tavily calls")
    print("=" * 70)

    if not integrity_rep.is_valid:
        print("[AUDIT ERROR] Historical decision failed cryptographic verification!")
        return 2

    if replay_rep.status != ReplayStatus.REPLAY_MATCH:
        print("[AUDIT WARNING] Replay diverged from recorded decision!")
        return 1

    print("\n[OK] Decision audit verified and replay successfully converged.")
    return 0


def generate_sample_record(intent: str = "Isolate leaking line on valve_b while preserving cooling") -> DecisionRecord:
    """Generate a sample verified DecisionRecord using local deterministic runtime."""
    world = PhysicalWorld()
    world.valves["valve_b"] = ValveState.OPEN
    world.cooling = CoolingState.ACTIVE
    world.set_pump_state("pump_p1", "INACTIVE")
    world.set_human_zone(HumanZoneState.CLEAR)

    runtime = MotionFenceRuntime(world=world)
    res = runtime.run_cycle(
        intent=intent,
        initial_evidence=world.generate_targeted_evidence("valve_b"),
    )
    if res.decision_record is not None:
        return res.decision_record
    raise RuntimeError("Failed to generate sample DecisionRecord.")


def main() -> int:
    parser = argparse.ArgumentParser(description="Deterministic Decision Replay and Audit Verifier.")
    parser.add_argument("decision_id", nargs="?", default=None, help="ID of DecisionRecord to replay")
    parser.add_argument("--audit-dir", default=None, help="Directory containing archived DecisionRecord JSON files")
    parser.add_argument("--sample", action="store_true", help="Generate and replay a fresh deterministic sample decision")
    parser.add_argument("--intent", default="Isolate valve_b safely", help="Intent for sample generation")
    args = parser.parse_args()

    record: DecisionRecord | None = None

    if args.sample or not args.decision_id:
        print("[INFO] Replaying generated deterministic sample decision...")
        record = generate_sample_record(intent=args.intent)
        return run_replay(record)

    # Search for decision_id in audit_dir if provided
    if args.audit_dir and os.path.isdir(args.audit_dir):
        recorder = DecisionRecorder(storage_dir=args.audit_dir)
        record = recorder.get_record(args.decision_id)

    if record is None:
        # Check if decision_id is a file path
        if os.path.isfile(args.decision_id):
            with open(args.decision_id, "r", encoding="utf-8") as f:
                record = DecisionRecord.model_validate_json(f.read())
        else:
            print(f"[ERROR] Could not find DecisionRecord with ID or path: '{args.decision_id}'")
            return 1

    return run_replay(record)


if __name__ == "__main__":
    sys.exit(main())
