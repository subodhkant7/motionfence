"""MotionFence Adversarial Physical Environment & Scenario Evaluation Engine (Phase 2H)."""

from motionfence.adversarial.models import (
    AdversarialCounterexample,
    AdversarialEvaluationReport,
    AdversarialFault,
    AdversarialScenario,
    FaultCategory,
    FaultSeverity,
    FaultTiming,
    FaultType,
    ScenarioExecutionResult,
    ScenarioOutcome,
    ScheduledFault,
)
from motionfence.adversarial.faults import FaultApplier
from motionfence.adversarial.environment import AdversarialEnvironment
from motionfence.adversarial.scenarios import (
    ScenarioBuilder,
    scenario_from_json,
    scenario_to_json,
)
from motionfence.adversarial.corpus import (
    CORPUS_REGISTRY,
    get_scenario,
    list_corpus_scenarios,
)
from motionfence.adversarial.generators import AdversarialScenarioGenerator
from motionfence.adversarial.executor import AdversarialScenarioExecutor
from motionfence.adversarial.metrics import AdversarialMetricsTracker
from motionfence.adversarial.reporting import AutomaticShrinker, ReportFormatter

__all__ = [
    "AdversarialCounterexample",
    "AdversarialEnvironment",
    "AdversarialEvaluationReport",
    "AdversarialFault",
    "AdversarialMetricsTracker",
    "AdversarialScenario",
    "AdversarialScenarioExecutor",
    "AdversarialScenarioGenerator",
    "AutomaticShrinker",
    "CORPUS_REGISTRY",
    "FaultApplier",
    "FaultCategory",
    "FaultSeverity",
    "FaultTiming",
    "FaultType",
    "ReportFormatter",
    "ScenarioBuilder",
    "ScenarioExecutionResult",
    "ScenarioOutcome",
    "ScheduledFault",
    "get_scenario",
    "list_corpus_scenarios",
    "scenario_from_json",
    "scenario_to_json",
]
