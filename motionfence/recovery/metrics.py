"""Metrics tracking and statistical analysis for autonomous recovery and quarantine enforcement."""

from typing import Dict, List, Optional
import time
from pydantic import BaseModel, Field

from motionfence.recovery.models import FailureClass, RecoveryExecutionResult, RecoveryOutcome


class RecoveryEvaluationReport(BaseModel):
    """Aggregated metrics report for autonomous fault containment and recovery evaluation."""
    report_id: str = Field(default_factory=lambda: f"recrep_{int(time.time())}")
    run_timestamp: float = Field(default_factory=time.time)
    failures_detected: int = 0
    failures_classified: int = 0
    components_quarantined: int = 0
    components_suspect: int = 0
    successful_recoveries: int = 0
    recovery_failures: int = 0
    recovery_budget_exhaustions: int = 0
    fresh_authorizations: int = 0
    repeat_actions_blocked: int = 0
    unsafe_retries: int = 0  # CRITICAL ZERO METRIC: Must strictly equal 0
    failure_breakdown_by_class: Dict[str, int] = Field(default_factory=dict)
    duration_seconds: float = 0.0

    def summary_text(self) -> str:
        """Render a readable executive summary of recovery findings."""
        lines = [
            "======================================================================",
            " MOTIONFENCE FAULT CONTAINMENT & AUTONOMOUS RECOVERY REPORT (PHASE 2I)",
            "======================================================================",
            f"Failures Detected:             {self.failures_detected}",
            f"Failures Classified:           {self.failures_classified}",
            f"Components Quarantined:        {self.components_quarantined}",
            f"Components Marked Suspect:     {self.components_suspect}",
            f"Successful Autonomous Retries: {self.successful_recoveries}",
            f"Recovery Failures (Safe Block):{self.recovery_failures}",
            f"Recovery Budget Exhaustions:   {self.recovery_budget_exhaustions}",
            f"Fresh Authorizations Minted:   {self.fresh_authorizations}",
            f"Repeat Actions Blocked:        {self.repeat_actions_blocked}",
            f"CRITICAL: Unsafe Retries:      {self.unsafe_retries} (Must strictly equal 0)",
            "----------------------------------------------------------------------",
            "Failures by Classification:",
        ]
        for f_cls, count in sorted(self.failure_breakdown_by_class.items()):
            lines.append(f"  * {f_cls:<26}: {count}")
        lines.append("======================================================================")
        return "\n".join(lines)


class RecoveryMetricsTracker:
    """Accumulates recovery execution metrics and validates security invariants."""

    def __init__(self) -> None:
        self.results: List[RecoveryExecutionResult] = []
        self.start_time = time.time()
        self.repeat_actions_blocked = 0

    def record_result(self, result: RecoveryExecutionResult) -> None:
        """Record an individual recovery cycle execution result."""
        self.results.append(result)

    def record_blocked_repeat(self) -> None:
        """Record an attempt to repeat an action that was deterministically blocked."""
        self.repeat_actions_blocked += 1

    def build_report(self) -> RecoveryEvaluationReport:
        """Compile aggregate recovery metrics report."""
        failures_detected = len(self.results)
        failures_classified = sum(1 for r in self.results if r.failure_record.failure_class != FailureClass.UNKNOWN_FAILURE)
        
        quarantined_comps = set()
        suspect_comps = set()
        for r in self.results:
            for c_id, q_rec in r.quarantine_records.items():
                if q_rec.is_quarantined:
                    quarantined_comps.add(c_id)
                elif q_rec.is_suspect:
                    suspect_comps.add(c_id)

        successful_recoveries = sum(1 for r in self.results if r.outcome == RecoveryOutcome.SUCCESS)
        recovery_failures = sum(1 for r in self.results if r.outcome == RecoveryOutcome.FAILED)
        budget_exhaustions = sum(1 for r in self.results if r.outcome == RecoveryOutcome.BUDGET_EXHAUSTION)
        fresh_auths = sum(1 for r in self.results if r.fresh_ticket is not None)
        unsafe_retries = sum(r.unsafe_retries for r in self.results)

        breakdown: Dict[str, int] = {}
        for r in self.results:
            cls_name = r.failure_record.failure_class.value
            breakdown[cls_name] = breakdown.get(cls_name, 0) + 1

        duration = time.time() - self.start_time

        return RecoveryEvaluationReport(
            failures_detected=failures_detected,
            failures_classified=failures_classified,
            components_quarantined=len(quarantined_comps),
            components_suspect=len(suspect_comps),
            successful_recoveries=successful_recoveries,
            recovery_failures=recovery_failures,
            recovery_budget_exhaustions=budget_exhaustions,
            fresh_authorizations=fresh_auths,
            repeat_actions_blocked=self.repeat_actions_blocked,
            unsafe_retries=unsafe_retries,
            failure_breakdown_by_class=breakdown,
            duration_seconds=duration,
        )
