"""MotionFence Assurance Package — Bounded Formal Analysis & Adversarial Evaluation Engine.

Provides machine-checkable assurance evidence, SMT-based bounded invariant analysis (Z3),
bounded temporal sequence checking, and property-based adversarial falsification.

CRITICAL INVARIANTS:
1. Z3 and assurance logic are strictly isolated analysis tools.
2. The Assurance Engine has ZERO actuator authority and cannot mint AuthorizationTickets.
3. BOUNDED PROPERTY SATISFIED ≠ REAL-WORLD SAFETY PROVEN.
"""

from motionfence.assurance.models import (
    AssuranceFinding,
    FindingStatus,
    FindingSeverity,
    AssuranceScope,
    FormalState,
    AssuranceReport,
    AdversarialCaseResult,
    AdversarialOutcomeCategory,
)
from motionfence.assurance.invariants import AssuranceProperty, AssurancePropertyRegistry
from motionfence.assurance.checker import BoundedAssuranceChecker
from motionfence.assurance.temporal import BoundedTemporalChecker
from motionfence.assurance.counterexample import CounterexampleFormatter
from motionfence.assurance.adversarial import AdversarialGenerator
from motionfence.assurance.evaluator import AdversarialEvaluator
from motionfence.assurance.reporting import AssuranceReportWriter

__all__ = [
    "AssuranceFinding",
    "FindingStatus",
    "FindingSeverity",
    "AssuranceScope",
    "FormalState",
    "AssuranceReport",
    "AdversarialCaseResult",
    "AdversarialOutcomeCategory",
    "AssuranceProperty",
    "AssurancePropertyRegistry",
    "BoundedAssuranceChecker",
    "BoundedTemporalChecker",
    "CounterexampleFormatter",
    "AdversarialGenerator",
    "AdversarialEvaluator",
    "AssuranceReportWriter",
]
