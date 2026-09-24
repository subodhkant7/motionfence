import argparse
import os
import sys

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from motionfence.assurance.evaluator import AdversarialEvaluator
from motionfence.assurance.reporting import AssuranceReportWriter


def main() -> int:
    parser = argparse.ArgumentParser(description="MotionFence Adversarial Evaluation Engine (Phase 2E)")
    parser.add_argument("--seed", type=int, default=42, help="RNG seed for reproducible generation")
    parser.add_argument("--cases", type=int, default=500, help="Number of randomized combinatorial cases")
    parser.add_argument("--output", type=str, default=".assurance/latest_report.json", help="Report destination path")
    args = parser.parse_args()

    print("======================================================================")
    print(" MOTIONFENCE ADVERSARIAL EVALUATION ENGINE (PHASE 2E)")
    print("======================================================================")
    print(f"Seed:       {args.seed} (Deterministic Reproducibility)")
    print(f"Test Cases: {args.cases} randomized + boundary combinations")
    print("Objective:  Discover potential false ALLOWs or safety regressions")
    print("----------------------------------------------------------------------")

    evaluator = AdversarialEvaluator(seed=args.seed)
    report = evaluator.run_evaluation(num_random_cases=args.cases)

    # Persist machine-readable report
    out_file = AssuranceReportWriter.save_report(report, args.output)

    print("\n" + report.summary_text())
    print(f"\n[OK] Machine-readable report saved to: {out_file}")

    if report.unsafe_authorizations_discovered > 0:
        print(f"\n[CRITICAL HAZARD] Discovered {report.unsafe_authorizations_discovered} unsafe ALLOW authorizations!")
        return 1

    print("\n[VERIFIED] Zero unsafe authorizations discovered across all adversarial combinations.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
