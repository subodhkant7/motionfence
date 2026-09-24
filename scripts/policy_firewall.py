#!/usr/bin/env python3
"""CI-compatible Policy Mutation Firewall command (Phase 2J/2K).

Evaluates policies against deterministic safety-relevant mutations, compound attacks,
dynamic physical trajectories, and safe repair proposals to prevent regressions.

SECURITY INVARIANTS:
1. Operates 100% offline; zero external network calls.
2. ZERO ticket minting and ZERO actuator authority.
3. NEVER alters production policy files.
4. Exit semantics:
   0 = all evaluated safety mutations were intercepted and no unsafe repair was accepted
   1 = regression detected or safety validation failed
   2 = inconclusive safety analysis requiring rejection/escalation

Usage:
    python scripts/policy_firewall.py [--baseline <policy-file>] [--compound] [--trajectory] [--full]
"""

import argparse
import json
import os
import sys

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from motionfence.policy.models import Policy
from motionfence.policy_mutation.baseline import PolicyBaselineManager
from motionfence.policy_mutation.engine import PolicyMutationEngine
from motionfence.policy_mutation.models import PolicyFirewallDecision


def run_firewall(
    baseline_file: str = None,
    report_output: str = None,
    compound: bool = False,
    trajectory: bool = False,
    full: bool = False,
    seed: int = 42,
) -> int:
    """Execute CI firewall check against a policy configuration."""
    if full:
        compound = True
        trajectory = True

    print("=" * 70)
    print(" MOTIONFENCE CI POLICY MUTATION FIREWALL (PHASE 2K)")
    print("=" * 70)

    # 1. Load policy
    if baseline_file and os.path.exists(baseline_file):
        print(f"Loading policy from: {baseline_file}")
        with open(baseline_file, "r", encoding="utf-8") as f:
            data = json.load(f)
        policy = Policy(**data)
    else:
        print("Using standard production baseline policy.")
        policy = Policy()

    # 2. Create baseline
    engine = PolicyMutationEngine()
    baseline = engine.create_baseline(policy)
    print(f"Policy ID:           {baseline.policy_id}")
    print(f"Canonical Hash:      {baseline.canonical_policy_hash}")
    print(f"Execution Mode:      compound={compound}, trajectory={trajectory}, full={full}, seed={seed}")
    print("=" * 70)

    # 3. Generate and evaluate attack suite
    print("\nRunning safety mutation attack suite...")
    report = engine.run_suite(
        baseline=baseline,
        include_compound=compound,
        include_trajectories=trajectory,
        synthesize_repairs=True,
        seed=seed,
    )

    # 4. Render human-readable summary
    print("\n" + report.render_summary())

    # 5. Output machine-readable report if requested
    if report_output:
        os.makedirs(os.path.dirname(os.path.abspath(report_output)), exist_ok=True)
        with open(report_output, "w", encoding="utf-8") as f:
            json.dump(report.model_dump(), f, indent=2, default=str)
        print(f"\nMachine-readable report written to: {report_output}")

    # 6. CI Exit Semantics:
    # 2 = inconclusive safety analysis requiring rejection/escalation
    # 1 = regression detected or safety validation failed
    # 0 = all evaluated safety mutations were intercepted and no unsafe repair was accepted

    # Check for inconclusive results
    has_inconclusive = any(
        r.firewall_decision == PolicyFirewallDecision.INCONCLUSIVE for r in report.results
    )
    if has_inconclusive:
        print("\n[FIREWALL INCONCLUSIVE] Inconclusive safety analysis detected; fails closed.", file=sys.stderr)
        return 2

    # Check that all safety-relevant mutations were detected
    if report.detected_regressions == report.safety_relevant_mutations:
        print("\n[FIREWALL VERIFIED] All evaluated safety mutations were intercepted and no unsafe repair was accepted.")
        print("The Policy Mutation Firewall is actively defending against combinatorial and dynamic regressions.")
        return 0
    else:
        undetected = report.safety_relevant_mutations - report.detected_regressions
        print(f"\n[FIREWALL FAILURE] {undetected} safety-relevant mutations escaped detection!", file=sys.stderr)
        return 1


def main() -> int:
    parser = argparse.ArgumentParser(description="MotionFence Policy Mutation Firewall CI Tool (Phase 2K)")
    parser.add_argument(
        "--baseline",
        type=str,
        default=None,
        help="Path to JSON file containing the baseline policy",
    )
    parser.add_argument(
        "--report",
        type=str,
        default="firewall_report.json",
        help="Path to output machine-readable JSON report",
    )
    parser.add_argument(
        "--compound",
        action="store_true",
        help="Include bounded compound policy mutations",
    )
    parser.add_argument(
        "--trajectory",
        action="store_true",
        help="Include dynamic physical trajectory exploration",
    )
    parser.add_argument(
        "--full",
        action="store_true",
        help="Run comprehensive compound, trajectory, and repair analysis",
    )
    parser.add_argument(
        "--seed",
        type=int,
        default=42,
        help="Deterministic generation seed",
    )
    args = parser.parse_args()
    return run_firewall(
        baseline_file=args.baseline,
        report_output=args.report,
        compound=args.compound,
        trajectory=args.trajectory,
        full=args.full,
        seed=args.seed,
    )


if __name__ == "__main__":
    sys.exit(main())
