"""Metrics accumulator and statistical analyzer for adversarial environment evaluation."""

from typing import Any, Dict, List, Optional
from collections import defaultdict
import time

from motionfence.adversarial.models import (
    AdversarialCounterexample,
    AdversarialEvaluationReport,
    FaultCategory,
    FaultTiming,
    FaultType,
    ScenarioExecutionResult,
    ScenarioOutcome,
)


class AdversarialMetricsTracker:
    """Accumulates and computes coverage and safety metrics across adversarial scenario runs."""

    def __init__(self, seed: int = 42) -> None:
        self.seed = seed
        self.start_time = time.time()
        self.results: List[ScenarioExecutionResult] = []
        self.counterexamples: List[AdversarialCounterexample] = []
        self.minimal_counterexamples: List[AdversarialCounterexample] = []

        self.coverage_by_fault_type: Dict[str, int] = defaultdict(int)
        self.coverage_by_fault_timing: Dict[str, int] = defaultdict(int)

    def record_result(
        self,
        result: Any,
        execution_result: Optional[ScenarioExecutionResult] = None,
        fault_types: Optional[List[FaultType]] = None,
        fault_timings: Optional[List[FaultTiming]] = None,
    ) -> None:
        """Record an individual scenario execution result into the aggregate statistics."""
        if hasattr(result, "fault_schedule") and execution_result is not None:
            actual_res = execution_result
            if fault_types is None:
                fault_types = [sf.fault.fault_type for sf in result.fault_schedule]
            if fault_timings is None:
                fault_timings = [sf.timing for sf in result.fault_schedule]
        else:
            actual_res = result

        self.results.append(actual_res)

        if fault_types:
            for ft in fault_types:
                ft_key = ft.value if hasattr(ft, "value") else str(ft)
                self.coverage_by_fault_type[ft_key] += 1

        if fault_timings:
            for tm in fault_timings:
                tm_key = tm.value if hasattr(tm, "value") else str(tm)
                self.coverage_by_fault_timing[tm_key] += 1

        # Check for Critical Safety Violation (Unsafe ALLOW)
        if actual_res.unsafe_allow or actual_res.outcome == ScenarioOutcome.UNSAFE_ALLOW:
            cx = AdversarialCounterexample(
                scenario_id=actual_res.scenario_id,
                faults=actual_res.faults_applied,
                decision=str(actual_res.adversarial_decision),
                expected="SAFE_BLOCK",
                unsafe=True,
                seed=self.seed,
                details={"revalidation_status": actual_res.revalidation_status, "message": actual_res.message},
            )
            self.counterexamples.append(cx)

    def build_report(self) -> AdversarialEvaluationReport:
        """Alias for generate_report."""
        return self.generate_report()

    def generate_report(self) -> AdversarialEvaluationReport:
        """Produce the comprehensive final evaluation report."""
        total = len(self.results)
        safe_allows = sum(1 for r in self.results if r.outcome == ScenarioOutcome.SAFE_ALLOW)
        safe_denials = sum(1 for r in self.results if r.outcome == ScenarioOutcome.SAFE_DENY)
        safe_need_ev = sum(1 for r in self.results if r.outcome == ScenarioOutcome.SAFE_NEED_MORE_EVIDENCE)
        reval_blocks = sum(1 for r in self.results if r.outcome == ScenarioOutcome.SAFE_REVALIDATION_BLOCK)
        verif_fails = sum(1 for r in self.results if r.outcome == ScenarioOutcome.VERIFICATION_FAILURE)
        unsafe_allows = sum(1 for r in self.results if r.unsafe_allow or r.outcome == ScenarioOutcome.UNSAFE_ALLOW)
        false_denials = sum(1 for r in self.results if r.false_denial)
        budget_exhaustions = sum(1 for r in self.results if r.outcome == ScenarioOutcome.BUDGET_EXHAUSTION)
        unexpected_mutations = sum(1 for r in self.results if r.outcome == ScenarioOutcome.UNEXPECTED_MUTATION)

        duration = time.time() - self.start_time

        return AdversarialEvaluationReport(
            seed=self.seed,
            total_scenarios=total,
            safe_allows=safe_allows,
            safe_denials=safe_denials,
            safe_need_more_evidence=safe_need_ev,
            revalidation_blocks=reval_blocks,
            verification_failures=verif_fails,
            unsafe_allows=unsafe_allows,
            false_denials=false_denials,
            evidence_budget_exhaustions=budget_exhaustions,
            unexpected_mutations=unexpected_mutations,
            counterexamples=self.counterexamples,
            minimal_counterexamples=self.minimal_counterexamples,
            coverage_by_fault_type=dict(self.coverage_by_fault_type),
            coverage_by_fault_timing=dict(self.coverage_by_fault_timing),
            execution_time_seconds=duration,
        )
