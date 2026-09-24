"""Scenario builder and serialization utilities for adversarial physical testing."""

from typing import Any, Dict, List, Optional
import json
import uuid

from motionfence.adversarial.models import (
    AdversarialFault,
    AdversarialScenario,
    FaultCategory,
    FaultSeverity,
    FaultTiming,
    FaultType,
    ScenarioOutcome,
    ScheduledFault,
)


class ScenarioBuilder:
    """Fluent builder to easily construct typed AdversarialScenario instances."""

    def __init__(self, scenario_id: Optional[str] = None, description: str = "") -> None:
        self.scenario_id = scenario_id or f"ADV_{uuid.uuid4().hex[:8]}"
        self.description = description
        self.initial_world_state: Optional[Dict[str, Any]] = None
        self.initial_evidence: List[Dict[str, Any]] = []
        self.initial_knowledge: List[Dict[str, Any]] = []
        self.initial_policy_modifications: Dict[str, Any] = {}
        self.fault_schedule: List[ScheduledFault] = []
        self.seed: int = 42
        self.expected_safety_properties: List[str] = []
        self.expected_outcome: Optional[ScenarioOutcome] = None
        self.tags: List[str] = []

    def with_id(self, scenario_id: str) -> "ScenarioBuilder":
        self.scenario_id = scenario_id
        return self

    def with_description(self, description: str) -> "ScenarioBuilder":
        self.description = description
        return self

    def with_seed(self, seed: int) -> "ScenarioBuilder":
        self.seed = seed
        return self

    def with_initial_world_state(self, state: Dict[str, Any]) -> "ScenarioBuilder":
        self.initial_world_state = state
        return self

    def with_policy_mod(self, key: str, value: Any) -> "ScenarioBuilder":
        self.initial_policy_modifications[key] = value
        return self

    def with_tag(self, tag: str) -> "ScenarioBuilder":
        self.tags.append(tag)
        return self

    def expect_outcome(self, outcome: ScenarioOutcome) -> "ScenarioBuilder":
        self.expected_outcome = outcome
        return self

    def expect_property(self, property_id: str) -> "ScenarioBuilder":
        self.expected_safety_properties.append(property_id)
        return self

    def add_fault(
        self,
        fault_type: FaultType,
        category: FaultCategory,
        timing: FaultTiming,
        severity: FaultSeverity = FaultSeverity.MEDIUM,
        target: str = "",
        parameters: Optional[Dict[str, Any]] = None,
        description: str = "",
    ) -> "ScenarioBuilder":
        """Add a scheduled fault to the scenario."""
        fault = AdversarialFault(
            fault_type=fault_type,
            category=category,
            severity=severity,
            timing=timing,
            target=target,
            parameters=parameters or {},
            description=description or f"{fault_type.value} at {timing.value}",
        )
        self.fault_schedule.append(
            ScheduledFault(
                fault=fault,
                timing=timing,
                step_offset=len(self.fault_schedule),
            )
        )
        return self

    def build(self) -> AdversarialScenario:
        """Construct the immutable AdversarialScenario instance."""
        return AdversarialScenario(
            scenario_id=self.scenario_id,
            description=self.description,
            initial_world_state=self.initial_world_state,
            initial_evidence=self.initial_evidence,
            initial_knowledge=self.initial_knowledge,
            initial_policy_modifications=self.initial_policy_modifications,
            fault_schedule=self.fault_schedule,
            seed=self.seed,
            expected_safety_properties=self.expected_safety_properties,
            expected_outcome=self.expected_outcome,
            tags=self.tags,
        )


def scenario_to_json(scenario: AdversarialScenario, indent: int = 2) -> str:
    """Serialize scenario to canonical JSON format."""
    return scenario.model_dump_json(indent=indent)


def scenario_from_json(json_str: str) -> AdversarialScenario:
    """Parse an AdversarialScenario from a JSON string."""
    return AdversarialScenario.model_validate_json(json_str)
