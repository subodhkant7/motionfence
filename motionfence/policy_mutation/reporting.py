"""Human-readable reporting and diff explanations for Policy Mutation Firewall (Phase 2J).

CRITICAL INVARIANT: All values in diff explanations must originate from actual analysis data.
"""

from typing import Any, Dict
import json

from motionfence.policy_mutation.models import (
    FirewallEvaluationReport,
    MutationEvaluationResult,
    PolicyFirewallDecision,
)


class PolicyDiffExplainer:
    """Produces human-readable diff explanations and structured reports for policy mutations."""

    @staticmethod
    def format_policy_diff(result: MutationEvaluationResult) -> str:
        """Format an evaluation result into the standardized MotionFence policy diff explanation."""
        mut = result.mutation
        lines = [
            "======================================================================",
            "POLICY MUTATION",
            "======================================================================",
            f"Rule:\n{mut.description}",
            "",
            "BEFORE",
            f"{mut.before_value}",
            "",
            "AFTER",
            f"{mut.after_value}",
            "",
            "EFFECT",
        ]

        if result.new_unsafe_allows > 0:
            lines.append("Adversarial scenario discovered a newly permitted unsafe proposal.")
        elif result.violated_properties:
            lines.append(f"Formal assurance check violated properties: {result.violated_properties}")
        elif not result.survived:
            lines.append(f"Safety boundary weakening detected: {result.regression_type.value}")
        else:
            lines.append("No unsafe proposals permitted. Safety boundaries preserved.")

        lines.extend([
            "",
            "REGRESSION",
            f"{result.regression_type.value}",
            "",
            "DECISION",
            f"{result.firewall_decision.value}",
            "======================================================================",
        ])
        return "\n".join(lines)

    @staticmethod
    def render_markdown_report(report: FirewallEvaluationReport) -> str:
        """Render a complete, audit-grade markdown report of the firewall evaluation suite."""
        lines = [
            "# MotionFence Policy Mutation Firewall Report",
            "",
            f"**Baseline Policy ID:** `{report.baseline_policy_id}`  ",
            f"**Baseline Policy Hash:** `{report.baseline_policy_hash}`  ",
            f"**Overall Decision:** `{report.overall_decision.value}`  ",
            f"**Timestamp:** `{report.timestamp}`  ",
            f"**Duration:** `{report.duration_seconds:.3f}s`  ",
            "",
            "## Summary Metrics",
            "",
            f"| Metric | Value |",
            f"| :--- | :--- |",
            f"| Total Mutations Tested | {report.total_mutations} |",
            f"| Safety-Relevant Mutations | {report.safety_relevant_mutations} |",
            f"| Detected Regressions | {report.detected_regressions} |",
            f"| Survived Mutations | {report.survived_mutations} |",
            f"| Firewall Verdict | **{report.overall_decision.value}** |",
            "",
            "## Mutation Analysis Details",
            "",
        ]

        for res in report.results:
            mut = res.mutation
            status = "REJECTED (DETECTED)" if res.is_rejected else "ACCEPTED (SURVIVED)"
            lines.extend([
                f"### Mutation: `{mut.mutation_id}` — {mut.mutation_type.value}",
                f"- **Target:** `{mut.mutation_target}`",
                f"- **Verdict:** `{status}`",
                f"- **Regression Mode:** `{res.regression_type.value}`",
                f"- **New Unsafe ALLOWs:** `{res.new_unsafe_allows}`",
                f"- **Violated Properties:** `{res.violated_properties}`",
            ])
            if res.counterexample:
                cex = res.counterexample
                lines.extend([
                    "- **Counterexample:**",
                    "  ```json",
                    f"  {json.dumps(cex.model_dump(), indent=2)}",
                    "  ```",
                ])
            lines.append("")

        return "\n".join(lines)
