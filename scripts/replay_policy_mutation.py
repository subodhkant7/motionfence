#!/usr/bin/env python3
"""CLI utility for deterministic, offline replay of policy mutation records (Phase 2J).

SECURITY INVARIANTS:
1. Replay is 100% offline and side-effect free.
2. ZERO ticket minting and ZERO actuator authority.
3. CANNOT alter production policies.

Usage:
    python scripts/replay_policy_mutation.py <mutation_id_or_file> [--records-dir <path>]
"""

import argparse
import json
import os
import sys

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from motionfence.policy_mutation.models import MutationEvaluationResult
from motionfence.policy_mutation.reporting import PolicyDiffExplainer


def replay_mutation_record(record_id_or_file: str, records_dir: str = "mutation_records") -> int:
    """Load and replay a previously recorded mutation evaluation."""
    if os.path.exists(record_id_or_file):
        filepath = record_id_or_file
    else:
        filepath = os.path.join(records_dir, f"{record_id_or_file}.json")
        if not os.path.exists(filepath):
            print(f"Error: Mutation record not found at '{filepath}'.", file=sys.stderr)
            return 1

    with open(filepath, "r", encoding="utf-8") as f:
        data = json.load(f)

    result = MutationEvaluationResult(**data)
    mut = result.mutation

    print("=" * 70)
    print(" MOTIONFENCE DETERMINISTIC MUTATION REPLAY (PHASE 2J/2K)")
    print("=" * 70)
    print(f"Mutation ID:      {mut.mutation_id}")
    print(f"Type:             {mut.mutation_type.value}")
    print(f"Target:           {mut.mutation_target}")
    print(f"Mutation Depth:   {result.mutation_depth}")
    if result.parent_mutations:
        print(f"Parent Mutations: {result.parent_mutations}")
    if result.interaction_type.value != "NO_INTERACTION":
        print(f"Interaction Type: {result.interaction_type.value}")
    print(f"Parent Hash:      {mut.parent_policy_hash[:16]}...")
    print(f"Mutated Hash:     {mut.mutated_policy_hash[:16] if mut.mutated_policy_hash else 'N/A'}...")
    print(f"Firewall Verdict: {result.firewall_decision.value} ({result.regression_type.value})")
    print(f"New Unsafe ALLOW: {result.new_unsafe_allows}")
    print(f"Violated Props:   {result.violated_properties}")
    print(f"Replay Mode:      100% OFFLINE, ZERO NETWORK, ZERO ACTUATION")
    print("-" * 70)

    print("\nPOLICY DIFF EXPLANATION:")
    print(PolicyDiffExplainer.format_policy_diff(result))

    if result.counterexample:
        print("\nMINIMIZED COUNTEREXAMPLE:")
        print(json.dumps(result.counterexample.model_dump(), indent=2))

    return 0


def main() -> int:
    parser = argparse.ArgumentParser(description="Replay a MotionFence policy mutation evaluation record")
    parser.add_argument("mutation_id", help="Mutation ID (e.g., pmut_12345) or path to JSON record")
    parser.add_argument(
        "--records-dir",
        type=str,
        default="mutation_records",
        help="Directory where mutation records are saved",
    )
    args = parser.parse_args()
    return replay_mutation_record(args.mutation_id, args.records_dir)


if __name__ == "__main__":
    sys.exit(main())
