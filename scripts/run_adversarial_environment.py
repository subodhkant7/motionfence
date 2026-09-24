#!/usr/bin/env python3
"""CLI script to run large-scale adversarial physical environment evaluations (Phase 2H).

Evaluates the MotionFence architecture against the 12 standard corpus scenarios,
confidence boundary probes, metamorphic invariant pairs, and randomized compound fault fuzzing.
"""

import argparse
import os
import sys
import time

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from motionfence.adversarial.corpus import list_corpus_scenarios
from motionfence.adversarial.executor import AdversarialScenarioExecutor
from motionfence.adversarial.generators import AdversarialScenarioGenerator
from motionfence.adversarial.metrics import AdversarialMetricsTracker
from motionfence.adversarial.reporting import ReportFormatter


def main() -> int:
    parser = argparse.ArgumentParser(description="MotionFence Adversarial Environment Evaluation Engine (Phase 2H)")
    parser.add_argument("--seed", type=int, default=42, help="Deterministic RNG seed")
    parser.add_argument("--cases", type=int, default=1000, help="Total number of evaluated scenarios")
    parser.add_argument("--output", type=str, default=".adversarial/latest_report.json", help="Destination path for evaluation report")
    args = parser.parse_args()

    print("=" * 72)
    print(" MOTIONFENCE ADVERSARIAL PHYSICAL ENVIRONMENT EVALUATOR (PHASE 2H)")
    print("=" * 72)
    print(f"Seed:               {args.seed} (Deterministic Reproducibility)")
    print(f"Target Scenarios:   {args.cases}")
    print(f"Report Destination: {args.output}")
    print("=" * 72)

    tracker = AdversarialMetricsTracker(seed=args.seed)
    executor = AdversarialScenarioExecutor(seed=args.seed)
    generator = AdversarialScenarioGenerator(seed=args.seed)

    print("\n[Phase 1/4] Executing 12 Standard Corpus Scenarios (A through L)...")
    corpus_scenarios = list_corpus_scenarios()
    for sc in corpus_scenarios:
        res = executor.execute(sc)
        tracker.record_result(sc, res)
        print(f"  [{sc.scenario_id:<32}] -> {res.outcome.value:<26} (Faults applied: {len(res.faults_applied)})")

    print("\n[Phase 2/4] Executing Threshold & Boundary Probes...")
    probes = generator.generate_boundary_probes()
    for probe in probes:
        res = executor.execute(probe)
        tracker.record_result(probe, res)
        print(f"  [{probe.scenario_id:<32}] -> {res.outcome.value:<26}")

    print("\n[Phase 3/4] Executing Metamorphic Invariant Pairs...")
    meta_pairs = generator.generate_metamorphic_pairs()
    for base_sc, mut_sc, prop_name in meta_pairs:
        res_base = executor.execute(base_sc)
        res_mut = executor.execute(mut_sc)
        tracker.record_result(base_sc, res_base)
        tracker.record_result(mut_sc, res_mut)
        print(f"  [{prop_name:<42}] Base: {res_base.outcome.value} | Mutated: {res_mut.outcome.value}")

    already_run = len(corpus_scenarios) + len(probes) + (len(meta_pairs) * 2)
    remaining_cases = max(0, args.cases - already_run)

    print(f"\n[Phase 4/4] Executing {remaining_cases} Randomized Combinatorial Scenarios...")
    start_fuzz = time.time()
    for i in range(remaining_cases):
        sc = generator.generate_scenario(index=i)
        res = executor.execute(sc)
        tracker.record_result(sc, res)
        if (i + 1) % 250 == 0 or (i + 1) == remaining_cases:
            elapsed = time.time() - start_fuzz
            rate = (i + 1) / max(elapsed, 0.001)
            print(f"  Progress: {i + 1}/{remaining_cases} completed ({rate:.1f} scenarios/sec)")

    report = tracker.build_report()
    summary = ReportFormatter.format_text(report)
    print("\n" + summary)

    out_file = ReportFormatter.save_json(report, args.output)
    print(f"\n[OK] Machine-readable evaluation report saved to: {out_file}")

    if report.unsafe_allows > 0:
        print(f"\n[CRITICAL VIOLATION] Discovered {report.unsafe_allows} UNSAFE ALLOW outcomes!")
        return 1

    print("\n[VERIFIED] Zero unsafe authorizations discovered across all adversarial scenarios.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
