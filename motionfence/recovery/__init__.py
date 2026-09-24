"""MotionFence Autonomous Fault Containment, Quarantine & Recovery System (Phase 2I).

Autonomous fault containment, component quarantine management,
deterministic failure classification, recovery planning, and fresh authorization re-evaluations.
"""

from motionfence.recovery.models import (
    ComponentType,
    ContainmentActionReport,
    FailureClass,
    FailureRecord,
    QuarantineRecord,
    QuarantineStatus,
    RecoveryExecutionResult,
    RecoveryOutcome,
    RecoveryPlan,
    RecoveryStep,
    RecoveryStrategy,
    RiskLevel,
)
from motionfence.recovery.classifier import FailureClassifier
from motionfence.recovery.policies import (
    ContainmentPolicy,
    QuarantinePolicy,
    RecoveryBudget,
)
from motionfence.recovery.quarantine import QuarantineManager
from motionfence.recovery.containment import ContainmentManager
from motionfence.recovery.planner import RecoveryPlanner
from motionfence.recovery.metrics import (
    RecoveryEvaluationReport,
    RecoveryMetricsTracker,
)
from motionfence.recovery.executor import RecoveryExecutor

__all__ = [
    "ComponentType",
    "ContainmentActionReport",
    "ContainmentManager",
    "ContainmentPolicy",
    "FailureClass",
    "FailureClassifier",
    "FailureRecord",
    "QuarantineManager",
    "QuarantinePolicy",
    "QuarantineRecord",
    "QuarantineStatus",
    "RecoveryBudget",
    "RecoveryEvaluationReport",
    "RecoveryExecutionResult",
    "RecoveryExecutor",
    "RecoveryMetricsTracker",
    "RecoveryOutcome",
    "RecoveryPlan",
    "RecoveryPlanner",
    "RecoveryStep",
    "RecoveryStrategy",
    "RiskLevel",
]
