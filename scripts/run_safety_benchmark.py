#!/usr/bin/env python3
"""MotionFence Reproducible Safety Benchmark CLI Runner.

Usage:
    # Run all 9 deterministic scenarios
    python scripts/run_safety_benchmark.py --all

    # Run single scenario
    python scripts/run_safety_benchmark.py --scenario sector4_hazard_breach

    # Repeat benchmark 5 times from clean initial state
    python scripts/run_safety_benchmark.py --all --repeat 5

    # Validate registry schemas and ground-truth definitions
    python scripts/run_safety_benchmark.py --validate

    # Export machine-readable JSON benchmark report
    python scripts/run_safety_benchmark.py --all --export results/benchmark_report.json

    # Verify SHA-256 integrity of an exported evidence bundle or report
    python scripts/run_safety_benchmark.py --verify-evidence results/benchmark_report.json

    # Compare two benchmark reports from different runs/revisions
    python scripts/run_safety_benchmark.py --diff report_baseline.json report_candidate.json
"""

import argparse
import json
import os
import sys
import time
from typing import Any, Dict, List

# Ensure repository root is on sys.path
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from motionfence.benchmark.engine import BenchmarkEngine
from motionfence.benchmark.evidence import verify_evidence_integrity
from motionfence.benchmark.models import BenchmarkExecutionMode, BenchmarkReport
from motionfence.benchmark.registry import ScenarioRegistry


def format_metric_row(label: str, val: Any) -> str:
    return f"  {label:<32} : {val}"


def print_report_summary(report: BenchmarkReport) -> None:
    print("\n" + "=" * 78)
    print(f" MOTIONFENCE REPRODUCIBLE SAFETY BENCHMARK REPORT — v{report.benchmark_version}")
    print("=" * 78)
    print(f" Run ID        : {report.run_id}")
    print(f" Timestamp     : {report.timestamp_utc}")
    print(f" Suite Type    : {report.suite_type.upper()} ({report.total_scenarios_evaluated} scenarios: {report.distinct_scenarios} distinct, {report.distinct_variants} variants)")
    print(f" Mode          : {report.execution_mode.value}")
    print(f" SHA-256 Hash  : {report.sha256_hash}")
    print(f" Build ID      : {report.build_id}")
    print("-" * 78)
    print(" SCENARIO EVALUATION RESULTS:")
    for res in report.scenario_results:
        mark = "✓ PASS" if res.passed else "✗ FAIL"
        print(f"  [{mark}] {res.scenario_id:<36} ({res.duration_ms:.2f}ms | pol: {res.policy_duration_ms:.2f}ms)")
        if not res.passed:
            for f in res.failure_reasons:
                print(f"         └─ {f}")
    print("-" * 78)
    print(" QUANTITATIVE SAFETY METRICS:")
    m = report.metrics
    print(format_metric_row("A. Unsafe Actuation Rate", m.unsafe_actuation_rate.formatted_value))
    print(format_metric_row("B. False-Verification Rate", m.false_verification_rate.formatted_value))
    print(format_metric_row("C. Scenario Pass Rate", m.scenario_pass_rate.formatted_value))
    print(format_metric_row("D. False-Denial Rate", m.false_denial_rate.formatted_value))
    print(format_metric_row("E. Fail-Closed Coverage", m.fail_closed_coverage.formatted_value))
    print(format_metric_row("F. Verification Coverage", m.verification_coverage.formatted_value))
    
    if report.timing_breakdown:
        tb = report.timing_breakdown
        pol = tb.get("policy", {})
        sim = tb.get("simulation", {})
        tot = tb.get("total", {})
        print("-" * 78)
        print(" SEPARATED LATENCY PROFILES:")
        print(format_metric_row("Policy Engine (Median / p95)", f"{pol.get('median_ms', 0):.2f} ms / {pol.get('p95_ms', 0):.2f} ms"))
        print(format_metric_row("Simulation Environment (Median)", f"{sim.get('median_ms', 0):.2f} ms / {sim.get('p95_ms', 0):.2f} ms"))
        print(format_metric_row("Total Wall-Clock (Median / p95)", f"{tot.get('median_ms', 0):.2f} ms / {tot.get('p95_ms', 0):.2f} ms"))

    if m.failure_classes_summary:
        print("-" * 78)
        print(" ADVERSARIAL FAILURE CLASSES:")
        print(f"  {'Threat Category':<32} {'Attempts':<10} {'Contained':<12} {'Leaked'}")
        for fc_name, fc_data in m.failure_classes_summary.items():
            print(f"  {fc_name:<32} {fc_data.get('attempts', 0):<10} {fc_data.get('contained', 0):<12} {fc_data.get('leaked', 0)}")

    print("=" * 78)
    status_str = "SUCCESS (All ground truth assertions satisfied)" if report.all_passed else "FAILURE (Safety regressions detected)"
    print(f" OVERALL OUTCOME: {status_str}\n")


def diff_reports(path_a: str, path_b: str) -> int:
    """Compare two benchmark reports and highlight regressions."""
    with open(path_a, "r", encoding="utf-8") as f:
        rep_a = json.load(f)
    with open(path_b, "r", encoding="utf-8") as f:
        rep_b = json.load(f)

    print("\n" + "=" * 78)
    print(f" BENCHMARK REPORT COMPARISON")
    print(f" Baseline : {path_a} (Run: {rep_a.get('run_id')})")
    print(f" Candidate: {path_b} (Run: {rep_b.get('run_id')})")
    print("=" * 78)

    scenarios_a = {s["scenario_id"]: s for s in rep_a.get("scenario_results", [])}
    scenarios_b = {s["scenario_id"]: s for s in rep_b.get("scenario_results", [])}

    all_scenarios = sorted(set(scenarios_a.keys()) | set(scenarios_b.keys()))
    regressions = 0

    print(f"{'Scenario ID':<35} {'Baseline':<12} {'Candidate':<12} {'Change'}")
    print("-" * 78)
    for sc_id in all_scenarios:
        pass_a = scenarios_a.get(sc_id, {}).get("passed")
        pass_b = scenarios_b.get(sc_id, {}).get("passed")
        status_a = "PASS" if pass_a else "FAIL" if pass_a is not None else "N/A"
        status_b = "PASS" if pass_b else "FAIL" if pass_b is not None else "N/A"

        change = "UNCHANGED"
        if pass_a and not pass_b:
            change = "REGRESSION"
            regressions += 1
        elif not pass_a and pass_b:
            change = "IMPROVED"

        print(f"{sc_id:<35} {status_a:<12} {status_b:<12} {change}")

    print("-" * 78)
    print(f"Total Regressions: {regressions}")
    print("=" * 78 + "\n")
    return 1 if regressions > 0 else 0


def main() -> int:
    parser = argparse.ArgumentParser(description="MotionFence Safety Benchmark CLI Runner")
    parser.add_argument("--all", action="store_true", help="Run benchmark suite")
    parser.add_argument("--suite", choices=["canonical", "expanded"], default="expanded", help="Benchmark suite scope: 'canonical' (9 scenarios) or 'expanded' (20 scenarios)")
    parser.add_argument("--scenario", type=str, help="Run a specific scenario ID")
    parser.add_argument("--repeat", type=int, default=1, help="Number of repetitions from clean initial states")
    parser.add_argument("--validate", action="store_true", help="Validate registry schemas and ground-truth definitions")
    parser.add_argument("--export", type=str, help="Export benchmark report to destination JSON file path")
    parser.add_argument("--verify-evidence", type=str, help="Verify SHA-256 integrity hash of exported evidence file")
    parser.add_argument("--diff", nargs=2, metavar=("REPORT_A", "REPORT_B"), help="Compare two benchmark reports")
    parser.add_argument("--seed", type=int, default=42, help="Deterministic random seed")

    args = parser.parse_args()

    # 1. Evidence Verification Mode
    if args.verify_evidence:
        target_path = os.path.abspath(args.verify_evidence)
        if not os.path.exists(target_path):
            print(f"[ERROR] Evidence file not found: {target_path}", file=sys.stderr)
            return 1
        with open(target_path, "r", encoding="utf-8") as f:
            data = json.load(f)
        is_valid, reported, computed = verify_evidence_integrity(data)
        if is_valid:
            print(f"[SUCCESS] SHA-256 integrity verified for {target_path}")
            print(f"          Reported Hash: {reported}")
            print(f"          Computed Hash: {computed}")
            return 0
        else:
            print(f"[FAILED] SHA-256 integrity MISMATCH for {target_path}", file=sys.stderr)
            print(f"         Reported: {reported}", file=sys.stderr)
            print(f"         Computed: {computed}", file=sys.stderr)
            return 2

    # 2. Diff Mode
    if args.diff:
        return diff_reports(args.diff[0], args.diff[1])

    # 3. Registry Validation Mode
    if args.validate:
        scenarios = ScenarioRegistry.list_scenarios()
        print(f"[VALIDATION] Checking {len(scenarios)} registered scenarios in Registry v{ScenarioRegistry.get_version()}...")
        for sc in scenarios:
            assert sc.scenario_id, "Missing scenario_id"
            assert sc.title, "Missing title"
            assert sc.ground_truth, "Missing ground_truth"
            assert len(sc.assertion_rules) > 0, f"Scenario '{sc.scenario_id}' has no assertion rules"
            print(f"  ✓ {sc.scenario_id:<32} ({len(sc.assertion_rules)} assertion rules)")
        print(f"[SUCCESS] All {len(scenarios)} scenarios passed strict schema validation.")
        return 0

    # 4. Execution Mode
    engine = BenchmarkEngine(seed=args.seed)

    if args.scenario:
        sc_def = ScenarioRegistry.get_scenario(args.scenario)
        if not sc_def:
            print(f"[ERROR] Unknown scenario: '{args.scenario}'", file=sys.stderr)
            print(f"Permitted scenarios: {[s.scenario_id for s in ScenarioRegistry.list_scenarios()]}", file=sys.stderr)
            return 1

        print(f"[RUNNING] Scenario: {sc_def.scenario_id} ({sc_def.title})")
        res = engine.run_scenario(sc_def)
        mark = "PASS" if res.passed else "FAIL"
        print(f"Outcome: {mark} (Duration: {res.duration_ms:.2f}ms)")
        print(f"Policy Decision : {res.policy_decision}")
        print(f"Ticket Minted   : {res.ticket_minted}")
        print(f"Execution       : {res.execution_status}")
        print(f"Verification    : {res.verification_status}")
        print("Assertions:")
        for a in res.assertions:
            m = "✓" if a.passed else "✗"
            print(f"  {m} {a.description} (Expected: {a.expected}, Actual: {a.actual})")

        if args.export:
            out_path = os.path.abspath(args.export)
            os.makedirs(os.path.dirname(out_path), exist_ok=True)
            with open(out_path, "w", encoding="utf-8") as f:
                json.dump(res.model_dump(), f, indent=2)
            print(f"[EXPORT] Saved scenario result to {out_path}")

        return 0 if res.passed else 1

    if args.all or len(sys.argv) == 1 or "--suite" in sys.argv:
        last_report = None
        for iteration in range(1, args.repeat + 1):
            if args.repeat > 1:
                print(f"\n--- Repetition {iteration}/{args.repeat} ---")
            report = engine.run_suite(mode=BenchmarkExecutionMode.DETERMINISTIC_REPLAY, suite_type=args.suite)
            last_report = report
            print_report_summary(report)

        if args.export and last_report:
            out_path = os.path.abspath(args.export)
            os.makedirs(os.path.dirname(out_path), exist_ok=True)
            with open(out_path, "w", encoding="utf-8") as f:
                json.dump(last_report.model_dump(), f, indent=2)
            print(f"[EXPORT] Saved full benchmark report to {out_path}")

        return 0 if (last_report and last_report.all_passed) else 1

    parser.print_help()
    return 0


if __name__ == "__main__":
    sys.exit(main())
