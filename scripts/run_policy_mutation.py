#!/usr/bin/env python3
"""CLI utility for executing policy mutations against the Policy Mutation Firewall (Phase 2J).

SECURITY INVARIANTS:
1. Operates 100% offline; zero external API or network calls.
2. ZERO ticket minting and ZERO actuator authority.
3. Does NOT alter production policy in place; evaluations run on detached clones.

Usage:
    python scripts/run_policy_mutation.py --mutation human-zone-guard
    python scripts/run_policy_mutation.py --mutation confidence-threshold
    python scripts/run_policy_mutation.py --all-safety-mutations
    python scripts/run_policy_mutation.py --output report.json
"""

import argparse
import json
import os
import sys

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from motionfence.policy.models import Policy
from motionfence.policy_mutation.engine import PolicyMutationEngine
from motionfence.policy_mutation.mutators import PolicyMutatorRegistry
from motionfence.policy_mutation.reporting import PolicyDiffExplainer


MUTATION_CHOICES = {
    "human-zone-guard": PolicyMutatorRegistry.mutate_human_zone_guard_removal,
    "confidence-threshold": lambda p: PolicyMutatorRegistry.mutate_confidence_threshold_weakening(p, new_threshold=0.70),
    "confidence-tighten": lambda p: PolicyMutatorRegistry.mutate_confidence_threshold_tightening(p, new_threshold=0.95),
    "cooling-invariant": PolicyMutatorRegistry.mutate_cooling_invariant_deletion,
    "contradiction-blocking": PolicyMutatorRegistry.mutate_contradiction_blocking_removal,
    "scope-expansion": PolicyMutatorRegistry.mutate_scope_expansion,
    "evidence-requirement": PolicyMutatorRegistry.mutate_evidence_requirement_removal,
    "toctou-revalidation": PolicyMutatorRegistry.mutate_toctou_revalidation_removal,
    "quarantine-bypass": PolicyMutatorRegistry.mutate_quarantine_bypass,
    "stale-knowledge": PolicyMutatorRegistry.mutate_stale_knowledge_acceptance,
    "recovery-budget": PolicyMutatorRegistry.mutate_recovery_budget_expansion,
    "authorization-precondition": PolicyMutatorRegistry.mutate_authorization_precondition_weakening,
    "non-safety-metadata": PolicyMutatorRegistry.mutate_non_safety_metadata,
}


def main() -> int:
    parser = argparse.ArgumentParser(description="MotionFence Policy Mutation Firewall CLI")
    parser.add_argument(
        "--mutation",
        choices=list(MUTATION_CHOICES.keys()),
        help="Specific mutation operator to execute",
    )
    parser.add_argument(
        "--all-safety-mutations",
        action="store_true",
        help="Execute all canonical safety-relevant mutations",
    )
    parser.add_argument(
        "--output",
        type=str,
        default=None,
        help="Path to output machine-readable JSON evaluation report",
    )
    parser.add_argument(
        "--records-dir",
        type=str,
        default="mutation_records",
        help="Directory to save reproducible mutation records",
    )

    args = parser.parse_args()

    if not args.mutation and not args.all_safety_mutations:
        parser.print_help()
        print("\nError: Specify either --mutation <name> or --all-safety-mutations.", file=sys.stderr)
        return 1

    engine = PolicyMutationEngine()
    policy = Policy()
    baseline = engine.create_baseline(policy)

    if args.mutation:
        mutator_fn = MUTATION_CHOICES[args.mutation]
        mut_policy, mut_record = mutator_fn(policy)
        result = engine.evaluate_mutation(mut_policy, mut_record, baseline)

        print(PolicyDiffExplainer.format_policy_diff(result))
        if result.counterexample:
            print("\nMINIMIZED COUNTEREXAMPLE:")
            print(json.dumps(result.counterexample.model_dump(), indent=2))

        # Save single record for replay
        os.makedirs(args.records_dir, exist_ok=True)
        rec_path = os.path.join(args.records_dir, f"{mut_record.mutation_id}.json")
        with open(rec_path, "w", encoding="utf-8") as f:
            json.dump(result.model_dump(), f, indent=2, default=str)
        print(f"\nSaved mutation record to: {rec_path}")

        if args.output:
            with open(args.output, "w", encoding="utf-8") as f:
                json.dump(result.model_dump(), f, indent=2, default=str)

        return 1 if result.is_rejected else 0

    if args.all_safety_mutations:
        report = engine.run_suite(baseline)
        print(report.render_summary())

        os.makedirs(args.records_dir, exist_ok=True)
        for res in report.results:
            rec_path = os.path.join(args.records_dir, f"{res.mutation.mutation_id}.json")
            with open(rec_path, "w", encoding="utf-8") as f:
                json.dump(res.model_dump(), f, indent=2, default=str)

        # Also save latest report summary
        summary_path = os.path.join(args.records_dir, "latest_firewall_report.json")
        with open(summary_path, "w", encoding="utf-8") as f:
            json.dump(report.model_dump(), f, indent=2, default=str)

        if args.output:
            with open(args.output, "w", encoding="utf-8") as f:
                json.dump(report.model_dump(), f, indent=2, default=str)

        print(f"\nSaved {len(report.results)} mutation records to '{args.records_dir}/'")
        return 1 if report.overall_decision.value == "REJECT" else 0

    return 0


if __name__ == "__main__":
    sys.exit(main())
