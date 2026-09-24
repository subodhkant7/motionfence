"""Reporting, serialization, and automatic delta-debugging minimization for adversarial failures."""

from typing import Any, Callable, Dict, List, Optional
import copy
import json
import os
import time

from motionfence.adversarial.models import (
    AdversarialCounterexample,
    AdversarialEvaluationReport,
    AdversarialScenario,
    ScenarioExecutionResult,
    ScenarioOutcome,
    ScheduledFault,
)
from motionfence.adversarial.executor import AdversarialScenarioExecutor


class AutomaticShrinker:
    """Minimizes failing fault sets to find the minimal reproducible counterexample (delta-debugging)."""

    def __init__(self, executor: Optional[AdversarialScenarioExecutor] = None) -> None:
        self.executor = executor or AdversarialScenarioExecutor()

    def shrink(
        self,
        failing_scenario: AdversarialScenario,
        failure_predicate: Optional[Callable[[ScenarioExecutionResult], bool]] = None,
    ) -> AdversarialCounterexample:
        """Minimizes the scheduled faults in a scenario while preserving the failure predicate.
        
        Args:
            failing_scenario: The initial scenario that produces an invariant violation or unexpected failure.
            failure_predicate: Callable returning True if result is considered a failure.
                               Defaults to checking (unsafe_allow or result != expected).
        """
        if failure_predicate is None:
            failure_predicate = lambda res: (
                res.unsafe_allow
                or (failing_scenario.expected_outcome and res.outcome != failing_scenario.expected_outcome)
            )

        current_faults = list(failing_scenario.fault_schedule)
        minimal_scenario = copy.deepcopy(failing_scenario)

        # Baseline check: confirm original scenario fails
        initial_result = self.executor.execute(failing_scenario)
        if not failure_predicate(initial_result):
            # Did not reproduce failure
            return AdversarialCounterexample(
                scenario_id=failing_scenario.scenario_id,
                faults=[sf.fault.fault_type.value for sf in current_faults],
                decision=str(initial_result.adversarial_decision),
                expected=str(failing_scenario.expected_outcome),
                unsafe=initial_result.unsafe_allow,
                seed=failing_scenario.seed,
                details={"message": "Scenario did not trigger failure predicate initially."},
                shrunk=False,
                minimal_fault_count=len(current_faults),
            )

        # Delta debugging: iteratively attempt 1-reduction (removing each fault one by one)
        reduced = True
        while reduced and len(current_faults) > 1:
            reduced = False
            for i in range(len(current_faults)):
                candidate_faults = current_faults[:i] + current_faults[i + 1:]
                candidate_scenario = copy.deepcopy(failing_scenario)
                candidate_scenario.fault_schedule = candidate_faults

                res = self.executor.execute(candidate_scenario)
                if failure_predicate(res):
                    current_faults = candidate_faults
                    minimal_scenario = candidate_scenario
                    reduced = True
                    break

        final_result = self.executor.execute(minimal_scenario)
        return AdversarialCounterexample(
            scenario_id=failing_scenario.scenario_id,
            faults=[sf.fault.fault_type.value for sf in minimal_scenario.fault_schedule],
            decision=str(final_result.adversarial_decision),
            expected=str(failing_scenario.expected_outcome),
            unsafe=final_result.unsafe_allow,
            seed=failing_scenario.seed,
            details={
                "message": final_result.message,
                "revalidation_status": final_result.revalidation_status,
                "initial_fault_count": len(failing_scenario.fault_schedule),
                "shrunk_fault_count": len(minimal_scenario.fault_schedule),
            },
            shrunk=True,
            minimal_fault_count=len(minimal_scenario.fault_schedule),
        )


class ReportFormatter:
    """Formats adversarial evaluation reports into structured markdown or JSON files."""

    @staticmethod
    def format_markdown(report: AdversarialEvaluationReport) -> str:
        """Render a readable executive report of adversarial findings."""
        lines = [
            "# MotionFence Adversarial Physical Environment Evaluation Report",
            f"**Report ID**: `{report.report_id}`  ",
            f"**Timestamp**: {time.strftime('%Y-%m-%d %H:%M:%S', time.gmtime(report.run_timestamp))} UTC  ",
            f"**Seed**: `{report.seed}` | **Execution Time**: {report.execution_time_seconds:.2f}s  ",
            "",
            "## 1. Summary Statistics",
            "",
            "| Metric | Value | Security Assessment |",
            "| :--- | :--- | :--- |",
            f"| **Total Scenarios Evaluated** | {report.total_scenarios:,} | Exhaustive bounded suite |",
            f"| **Safe ALLOWs** | {report.safe_allows:,} | Valid operations permitted & verified |",
            f"| **Safe Denials** | {report.safe_denials:,} | Unsafe operations blocked by PolicyEngine |",
            f"| **Safe NEED_MORE_EVIDENCE** | {report.safe_need_more_evidence:,} | Ambiguous/discordant telemetry held |",
            f"| **TOCTOU Revalidation Blocks** | {report.revalidation_blocks:,} | Drift detected prior to execution |",
            f"| **Post-Action Verification Failures** | {report.verification_failures:,} | Actuator jam/partial move caught |",
            f"| **Evidence Budget Exhaustions** | {report.evidence_budget_exhaustions:,} | Halted safely after max loops |",
            f"| **CRITICAL: Unsafe ALLOWs** | **{report.unsafe_allows}** | **ZERO TOLERANCE (Must be 0)** |",
            "",
            "## 2. Fault Type Coverage",
            "",
            "| Fault Type | Cases Injected |",
            "| :--- | :--- |",
        ]

        for ft, count in sorted(report.coverage_by_fault_type.items()):
            lines.append(f"| `{ft}` | {count:,} |")

        lines.extend([
            "",
            "## 3. Fault Timing Coverage",
            "",
            "| Lifecycle Junction | Injections |",
            "| :--- | :--- |",
        ])

        for tm, count in sorted(report.coverage_by_fault_timing.items()):
            lines.append(f"| `{tm}` | {count:,} |")

        if report.counterexamples:
            lines.extend([
                "",
                "## 4. Counterexamples & Violations",
                f"Discovered {len(report.counterexamples)} counterexample(s):",
                "",
            ])
            for cx in report.counterexamples:
                lines.append(f"* **ID**: `{cx.counterexample_id}` (Scenario `{cx.scenario_id}`)")
                lines.append(f"  - Faults: {cx.faults}")
                lines.append(f"  - Decision: {cx.decision} (Expected: {cx.expected})")
                lines.append(f"  - Unsafe: {cx.unsafe}")

        return "\n".join(lines)

    @classmethod
    def format_text(cls, report: AdversarialEvaluationReport) -> str:
        """Alias for format_markdown."""
        return cls.format_markdown(report)

    @staticmethod
    def save_report(
        report: AdversarialEvaluationReport,
        target_dir: str = ".adversarial",
        filename: str = "latest_report.json",
    ) -> str:
        """Save report to JSON file on disk."""
        os.makedirs(target_dir, exist_ok=True)
        path = os.path.join(target_dir, filename)
        with open(path, "w", encoding="utf-8") as f:
            f.write(report.model_dump_json(indent=2))
        return path

    @classmethod
    def save_json(cls, report: AdversarialEvaluationReport, full_path: str) -> str:
        """Save report to a specific file path."""
        target_dir = os.path.dirname(full_path) or "."
        filename = os.path.basename(full_path)
        return cls.save_report(report, target_dir=target_dir, filename=filename)
