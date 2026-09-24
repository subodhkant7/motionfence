import argparse
import os
import sys
import time

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from motionfence.assurance.checker import BoundedAssuranceChecker
from motionfence.assurance.temporal import BoundedTemporalChecker
from motionfence.assurance.invariants import AssurancePropertyRegistry
from motionfence.assurance.models import AssuranceReport, FindingStatus, FormalState
from motionfence.assurance.reporting import AssuranceReportWriter
from motionfence.models.actions import ActionType


def main() -> int:
    parser = argparse.ArgumentParser(description="MotionFence Bounded Assurance Verification (Phase 2E)")
    parser.add_argument("--output", type=str, default=".assurance/latest_assurance.json", help="Path to save JSON report")
    args = parser.parse_args()

    print("======================================================================")
    print(" MOTIONFENCE BOUNDED ASSURANCE VERIFIER (PHASE 2E)")
    print("======================================================================")
    print("Tool: Z3 SMT Solver & Bounded Temporal Sequence Checker")
    print("Scope: Modeled state variables and transition rules")
    print("Note: BOUNDED PROPERTY SATISFIED ≠ REAL-WORLD SAFETY PROVEN")
    print("----------------------------------------------------------------------")

    start_time = time.time()
    registry = AssurancePropertyRegistry()
    checker = BoundedAssuranceChecker(registry=registry)
    temporal_checker = BoundedTemporalChecker()

    findings = []

    # 1. Evaluate registered properties via SMT
    print("\n[1] Evaluating Static Invariant Properties via Z3 SMT Solver...")
    for prop in registry.list_all():
        finding = checker.check_property(prop.property_id)
        findings.append(finding)
        status_symbol = "[PASS]" if finding.status == FindingStatus.SATISFIED else "[FAIL]"
        print(f"    {status_symbol} {prop.property_id:<45} -> {finding.status.value}")

    # 2. Evaluate Bounded Temporal Properties
    print("\n[2] Evaluating Bounded Temporal Sequences (Horizon H = 3)...")
    init_state = FormalState(
        valves={"valve_a": "OPEN", "valve_b": "OPEN"},
        cooling="ACTIVE",
        human_zone="CLEAR",
        pumps={"pump_p1": "INACTIVE"},
    )
    t_finding = temporal_checker.check_cooling_preservation_sequence(
        initial_state=init_state,
        action_sequence=[ActionType.CLOSE_VALVE, ActionType.OPEN_VALVE, ActionType.CLOSE_VALVE],
        horizon=3,
    )
    findings.append(t_finding)
    status_symbol = "[PASS]" if t_finding.status == FindingStatus.SATISFIED else "[FAIL]"
    print(f"    {status_symbol} {t_finding.property_id:<45} -> {t_finding.status.value}")

    # Dynamic human incursion test
    h_finding = temporal_checker.check_dynamic_human_incursion(horizon=3, incursion_step=1)
    findings.append(h_finding)
    status_symbol = "[PASS]" if h_finding.status == FindingStatus.SATISFIED else "[FAIL]"
    print(f"    {status_symbol} {h_finding.property_id:<45} -> {h_finding.status.value}")

    elapsed = time.time() - start_time

    satisfied = len([f for f in findings if f.status == FindingStatus.SATISFIED])
    violated = len([f for f in findings if f.status == FindingStatus.VIOLATED])
    unknown = len([f for f in findings if f.status == FindingStatus.UNKNOWN])

    report = AssuranceReport(
        runtime_version="0.4.0",
        policy_version="2026.1",
        properties_checked=len(findings),
        properties_satisfied=satisfied,
        properties_violated=violated,
        unknown_properties=unknown,
        findings=findings,
        counterexamples=[f.counterexample for f in findings if f.counterexample],
        execution_time_seconds=elapsed,
    )

    out_file = AssuranceReportWriter.save_report(report, args.output)

    print("\n" + report.summary_text())
    print(f"\n[OK] Machine-readable assurance report written to: {out_file}")

    return 0 if violated == 0 else 1


if __name__ == "__main__":
    sys.exit(main())
