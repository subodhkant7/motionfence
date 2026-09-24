"""Automated scenario generator with boundary probes and metamorphic property testing."""

from typing import Any, Dict, List, Optional, Tuple
import random
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
from motionfence.adversarial.scenarios import ScenarioBuilder
from motionfence.evidence.models import Evidence, EvidenceSource
from motionfence.models.actions import ActionProposal, ActionType
from motionfence.models.world import HumanZoneState, CoolingState, ValveState, SensorObservation


class AdversarialScenarioGenerator:
    """Generates combinatorial and boundary-probing adversarial test scenarios with deterministic seeds."""

    def __init__(self, seed: int = 42) -> None:
        self.seed = seed
        self.rng = random.Random(seed)

    def generate_random_scenario(self, scenario_idx: int) -> AdversarialScenario:
        """Generate a random valid adversarial scenario combining world states, faults, and timings."""
        scenario_id = f"ADV_GEN_{scenario_idx:04d}"

        # Choose 1 to 3 faults
        fault_count = self.rng.choices([1, 2, 3], weights=[0.6, 0.3, 0.1])[0]

        # Candidate fault types
        all_fault_types = [
            (FaultType.HUMAN_ENTERS_ZONE, FaultCategory.HUMAN),
            (FaultType.PUMP_STARTS_UNEXPECTEDLY, FaultCategory.EQUIPMENT),
            (FaultType.COOLING_DEGRADES, FaultCategory.EQUIPMENT),
            (FaultType.VALVE_JAM, FaultCategory.EQUIPMENT),
            (FaultType.VALVE_PARTIAL_MOVE, FaultCategory.EQUIPMENT),
            (FaultType.SENSOR_STUCK, FaultCategory.SENSOR),
            (FaultType.SENSOR_NOISE, FaultCategory.SENSOR),
            (FaultType.SENSOR_CONTRADICTION, FaultCategory.SENSOR),
            (FaultType.TARGET_OCCLUDED, FaultCategory.PERCEPTION),
            (FaultType.KNOWLEDGE_STALE, FaultCategory.KNOWLEDGE),
            (FaultType.ACTUATOR_JAM, FaultCategory.ACTUATOR),
            (FaultType.ACTUATOR_PARTIAL, FaultCategory.ACTUATOR),
        ]

        all_timings = [
            FaultTiming.AFTER_OBSERVATION,
            FaultTiming.AFTER_POLICY,
            FaultTiming.AFTER_TICKET,
            FaultTiming.BEFORE_EXECUTION,
            FaultTiming.DURING_EXECUTION,
        ]

        builder = (
            ScenarioBuilder(scenario_id)
            .with_description(f"Randomly generated adversarial scenario #{scenario_idx}")
            .with_seed(self.seed + scenario_idx)
            .with_tag("generated")
        )

        selected_faults = self.rng.sample(all_fault_types, k=min(fault_count, len(all_fault_types)))
        for ft, cat in selected_faults:
            timing = self.rng.choice(all_timings)
            severity = self.rng.choice([FaultSeverity.LOW, FaultSeverity.MEDIUM, FaultSeverity.HIGH, FaultSeverity.CRITICAL])
            builder.add_fault(
                fault_type=ft,
                category=cat,
                timing=timing,
                severity=severity,
                target="valve_b" if cat in (FaultCategory.EQUIPMENT, FaultCategory.ACTUATOR, FaultCategory.PERCEPTION) else "",
            )

        return builder.build()

    def generate_scenario(self, index: int = 0) -> AdversarialScenario:
        """Alias for generate_random_scenario."""
        return self.generate_random_scenario(index)

    def generate_boundary_probes(self) -> List[AdversarialScenario]:
        """Generate scenarios focused specifically on confidence threshold and state boundary probing."""
        probes = []
        # Confidence boundary values around policy threshold 0.900
        boundary_confidences = [0.890, 0.899, 0.900, 0.901, 0.910]

        for i, conf in enumerate(boundary_confidences):
            expected = ScenarioOutcome.SAFE_ALLOW if conf >= 0.900 else ScenarioOutcome.SAFE_NEED_MORE_EVIDENCE
            sc = (
                ScenarioBuilder(f"ADV_PROBE_CONF_{int(conf * 1000)}")
                .with_description(f"Boundary probe: optical evidence target confidence at exactly {conf:.3f}")
                .with_tag("boundary_probe")
                .expect_outcome(expected)
                .add_fault(
                    fault_type=FaultType.TARGET_OCCLUDED,
                    category=FaultCategory.PERCEPTION,
                    timing=FaultTiming.AFTER_OBSERVATION,
                    parameters={"confidence": conf},
                    target="valve_b",
                    description=f"Confidence dialed to boundary value {conf:.3f}",
                )
                .build()
            )
            probes.append(sc)

        # State transition boundaries: Human Zone CLEAR vs OCCUPIED
        probes.append(
            ScenarioBuilder("ADV_PROBE_HUMAN_TRANSITION")
            .with_description("Boundary probe: human zone transitions CLEAR -> OCCUPIED right before execution")
            .with_tag("boundary_probe")
            .expect_outcome(ScenarioOutcome.SAFE_REVALIDATION_BLOCK)
            .add_fault(
                fault_type=FaultType.HUMAN_ENTERS_ZONE,
                category=FaultCategory.HUMAN,
                timing=FaultTiming.BEFORE_EXECUTION,
                severity=FaultSeverity.CRITICAL,
            )
            .build()
        )

        # State transition boundaries: Cooling ACTIVE vs INACTIVE
        probes.append(
            ScenarioBuilder("ADV_PROBE_COOLING_TRANSITION")
            .with_description("Boundary probe: cooling transitions ACTIVE -> INACTIVE right before execution")
            .with_tag("boundary_probe")
            .expect_outcome(ScenarioOutcome.SAFE_REVALIDATION_BLOCK)
            .add_fault(
                fault_type=FaultType.COOLING_DEGRADES,
                category=FaultCategory.EQUIPMENT,
                timing=FaultTiming.BEFORE_EXECUTION,
                severity=FaultSeverity.CRITICAL,
                parameters={"cooling_state": "INACTIVE"},
            )
            .build()
        )

        return probes

    def generate_metamorphic_pairs(self) -> List[Tuple[AdversarialScenario, AdversarialScenario, str]]:
        """Generate paired scenarios (Base, Transformed) to test metamorphic preservation and monotonicity properties.
        
        Returns:
            List of (BaseScenario, TransformedScenario, property_name)
        """
        pairs = []

        # 1. Metamorphic Property: Unrelated Evidence Addition
        # Adding an irrelevant ambient sensor observation must not alter a valid authorization decision.
        base_unrelated = (
            ScenarioBuilder("ADV_META_UNRELATED_BASE")
            .with_description("Base: Normal valid leak isolation scenario")
            .build()
        )
        mut_unrelated = (
            ScenarioBuilder("ADV_META_UNRELATED_MUTATED")
            .with_description("Mutated: Adding unrelated ambient humidity sensor reading")
            .add_fault(
                fault_type=FaultType.SENSOR_NOISE,
                category=FaultCategory.SENSOR,
                timing=FaultTiming.AFTER_OBSERVATION,
                target="ambient_humidity",
                parameters={"noise_delta": 2.0},
                description="Irrelevant ambient sensor perturbation",
            )
            .build()
        )
        pairs.append((base_unrelated, mut_unrelated, "PROP_META_UNRELATED_EVIDENCE_INVARIANCE"))

        # 2. Metamorphic Property: Weaker Evidence Monotonicity
        # Reducing target confidence below threshold must never turn DENY into ALLOW.
        base_weaker = (
            ScenarioBuilder("ADV_META_WEAKER_BASE")
            .with_description("Base: High confidence observation")
            .build()
        )
        mut_weaker = (
            ScenarioBuilder("ADV_META_WEAKER_MUTATED")
            .with_description("Mutated: Lowering confidence below threshold to 0.75")
            .add_fault(
                fault_type=FaultType.TARGET_OCCLUDED,
                category=FaultCategory.PERCEPTION,
                timing=FaultTiming.AFTER_OBSERVATION,
                parameters={"confidence": 0.75},
            )
            .build()
        )
        pairs.append((base_weaker, mut_weaker, "PROP_META_WEAKER_EVIDENCE_MONOTONICITY"))

        # 3. Metamorphic Property: Safety Degradation Monotonicity
        # Degrading safety (human entering zone) must never convert a denial into an allowance.
        base_safety = (
            ScenarioBuilder("ADV_META_SAFETY_BASE")
            .with_description("Base: Clear human zone")
            .build()
        )
        mut_safety = (
            ScenarioBuilder("ADV_META_SAFETY_MUTATED")
            .with_description("Mutated: Human enters safety zone")
            .add_fault(
                fault_type=FaultType.HUMAN_ENTERS_ZONE,
                category=FaultCategory.HUMAN,
                timing=FaultTiming.BEFORE_EXECUTION,
            )
            .build()
        )
        pairs.append((base_safety, mut_safety, "PROP_META_SAFETY_DEGRADATION_MONOTONICITY"))

        # 4. Metamorphic Property: Stale Evidence Non-Inflation
        # Aging a knowledge document can never increase its authorization authority.
        base_stale = (
            ScenarioBuilder("ADV_META_STALE_BASE")
            .with_description("Base: Fresh knowledge documentation")
            .build()
        )
        mut_stale = (
            ScenarioBuilder("ADV_META_STALE_MUTATED")
            .with_description("Mutated: Knowledge aged 120 days into stale state")
            .add_fault(
                fault_type=FaultType.KNOWLEDGE_STALE,
                category=FaultCategory.KNOWLEDGE,
                timing=FaultTiming.AFTER_TICKET,
                parameters={"age_seconds": 120 * 86400},
            )
            .build()
        )
        pairs.append((base_stale, mut_stale, "PROP_META_STALE_EVIDENCE_NON_INFLATION"))

        return pairs
