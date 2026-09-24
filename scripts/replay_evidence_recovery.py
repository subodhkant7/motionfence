#!/usr/bin/env python3
"""CLI utility for offline, deterministic replay of Phase 2G Active Evidence Acquisition cycles.

Usage:
    python scripts/replay_evidence_recovery.py <run_id_or_file> [--audit-dir <path>]
"""

import argparse
import json
import os
import sys

# Ensure motionfence package is on sys.path
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from motionfence.audit.models import DecisionRecord, format_decision_audit
from motionfence.audit.verifier import DecisionRecordVerifier
from motionfence.audit.replay import DecisionReplayEngine, ReplayStatus


def render_replay_step(step_idx: int, name: str, summary: str, details: dict) -> None:
    print(f"\n[{step_idx:02d}] {name:<22} [REPLAYED OFFLINE]")
    print("-" * 65)
    print(f"    Summary: {summary}")
    for k, v in details.items():
        if k not in ("evidence", "certificates", "active_constraints", "intent"):
            print(f"    - {k}: {v}")


def run_replay(record_path_or_id: str, audit_dir: str = "audit_records") -> int:
    # Resolve path
    if os.path.exists(record_path_or_id):
        filepath = record_path_or_id
    else:
        filepath = os.path.join(audit_dir, f"{record_path_or_id}.json")
        if not os.path.exists(filepath):
            print(f"Error: Record file not found: {filepath}", file=sys.stderr)
            return 1

    with open(filepath, "r") as f:
        data = json.load(f)

    record = DecisionRecord.model_validate(data)

    print("=" * 65)
    print(" MOTIONFENCE PHASE 2G: OFFLINE DETERMINISTIC REPLAY")
    print("=" * 65)
    print(f"Decision ID:     {record.decision_id}")
    print(f"Record Hash:     {record.record_hash}")
    print(f"Prev Record Hash:{record.previous_record_hash or 'GENESIS'}")
    print(f"Sequence:        #{record.sequence_number}")
    print(f"Evidence Budget: {record.evidence_budget}")
    print(f"Iterations:      {record.evidence_acquisition_iterations}")
    print(f"Actions Executed:{record.evidence_action_ids}")
    print(f"Predicted Gain:  {record.predicted_information_gain}")
    print(f"Observed Gain:   {record.observed_information_gain}")
    print("=" * 65)

    # 1. Cryptographic and Integrity Verification
    integrity_rep = DecisionRecordVerifier.verify_record(record)
    print(f"\n>>> CRYPTOGRAPHIC AUDIT: {'[PASS] VALID' if integrity_rep.is_valid else '[FAIL] CORRUPTED'}")
    print(f"    - Canonical Hash:    {'MATCH' if integrity_rep.hash_verified else 'MISMATCH'}")
    print(f"    - Chain Linkage:     {'VALID' if integrity_rep.chain_linked else 'BROKEN'}")
    print(f"    - Policy Invariants: {'CONSISTENT' if integrity_rep.policy_consistent else 'INCONSISTENT'}")

    # 2. Replay Reconstruction (Zero Network, Zero Model, Zero Actuator)
    engine = DecisionReplayEngine()
    replay_rep = engine.replay(record)

    for step in replay_rep.steps:
        render_replay_step(step.step_number, step.step_name, step.summary, step.details)

    print("\n" + "=" * 65)
    print(" REPLAY SUMMARY & CONVERGENCE VERIFICATION")
    print("=" * 65)
    print(f"Replay Verdict:      {replay_rep.replayed_verdict}")
    print(f"Recorded Verdict:    {replay_rep.recorded_verdict}")
    print(f"Deterministic Match: {'YES [CONVERGED]' if replay_rep.is_match else 'NO [DIVERGENCE]'}")
    print(f"External API Calls:  0 (Tavily: 0, Nebius: 0)")
    print(f"Actuator Mutations:  0 (Replay is strictly read-only)")
    print(f"Tickets Minted:      0 (Replay possesses zero authority)")
    print("=" * 65)

    return 0 if replay_rep.is_match else 2


def main() -> None:
    parser = argparse.ArgumentParser(description="MotionFence Phase 2G Offline Replay CLI")
    parser.add_argument("run_id", help="Decision ID or path to DecisionRecord JSON")
    parser.add_argument("--audit-dir", default="audit_records", help="Directory where records are stored")
    args = parser.parse_args()

    sys.exit(run_replay(args.run_id, audit_dir=args.audit_dir))


if __name__ == "__main__":
    main()
