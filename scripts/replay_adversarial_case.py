import argparse
import sys
import json
import os

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from motionfence.assurance.evaluator import AdversarialEvaluator
from motionfence.assurance.counterexample import CounterexampleFormatter


def main() -> int:
    parser = argparse.ArgumentParser(description="Replay specific adversarial case or counterexample")
    parser.add_argument("case_id", nargs="?", default=None, help="Case ID or index to replay")
    parser.add_argument("--report", type=str, default=".assurance/latest_report.json", help="Path to report JSON")
    parser.add_argument("--sample", action="store_true", help="Replay a synthesized adversarial sample")
    args = parser.parse_args()

    print("======================================================================")
    print(" MOTIONFENCE ADVERSARIAL CASE REPLAY & DIAGNOSTIC (PHASE 2E)")
    print("======================================================================")

    evaluator = AdversarialEvaluator()

    if args.sample or not args.case_id:
        print("[INFO] Replaying synthesized adversarial boundary case...")
        sample_case = {
            "human_zone": "OCCUPIED",
            "cooling": "ACTIVE",
            "pump_p1": "INACTIVE",
            "action_type": "CLOSE_VALVE",
            "target": "valve_b",
            "confidence": 0.98,
        }
        res = evaluator._evaluate_physical_case(sample_case)
        print("\nCase Parameters:")
        for k, v in sample_case.items():
            print(f"  {k:<15} = {v}")
        print(f"\nResult Category:  {res.category.value}")
        print(f"Observed Verdict: {res.observed_verdict}")
        print(f"Policy Reasons:   {res.reasons}")
        print(f"Is Safe:          {res.is_safe}")
        return 0

    if not os.path.exists(args.report):
        print(f"[ERROR] Report file not found: {args.report}")
        return 1

    with open(args.report, "r", encoding="utf-8") as f:
        report_data = json.load(f)

    # Search for counterexamples or findings matching case_id
    counterexamples = report_data.get("counterexamples", [])
    if not counterexamples:
        print(f"[INFO] Zero counterexamples exist in {args.report}. All evaluated cases satisfied safety requirements.")
        return 0

    print(f"[INFO] Inspecting {len(counterexamples)} counterexample(s) in report...")
    for idx, ce in enumerate(counterexamples):
        formatted = CounterexampleFormatter.format_counterexample(
            property_name=f"Case #{idx} ({args.case_id})",
            counterexample=ce,
        )
        print(formatted)

    return 0


if __name__ == "__main__":
    sys.exit(main())
