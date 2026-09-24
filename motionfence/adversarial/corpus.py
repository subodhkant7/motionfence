"""Deterministic scenario corpus establishing standard benchmark physical failure cases (Scenarios A through L)."""

from typing import Dict, List, Optional

from motionfence.adversarial.models import (
    AdversarialScenario,
    FaultCategory,
    FaultSeverity,
    FaultTiming,
    FaultType,
    ScenarioOutcome,
)
from motionfence.adversarial.scenarios import ScenarioBuilder


def create_scenario_a_human_toctou() -> AdversarialScenario:
    """Scenario A: Human enters zone immediately after ticket issuance, before execution."""
    return (
        ScenarioBuilder("SCENARIO_A_HUMAN_TOCTOU")
        .with_description("Human enters zone immediately after ticket issuance, before execution (TOCTOU race)")
        .with_tag("human")
        .with_tag("toctou")
        .expect_outcome(ScenarioOutcome.SAFE_REVALIDATION_BLOCK)
        .expect_property("PROP_008_NO_EXECUTION_AFTER_STATE_DRIFT")
        .expect_property("PROP_018_HUMAN_ZONE_TRANSITION_SAFETY")
        .add_fault(
            fault_type=FaultType.HUMAN_ENTERS_ZONE,
            category=FaultCategory.HUMAN,
            timing=FaultTiming.BEFORE_EXECUTION,
            severity=FaultSeverity.CRITICAL,
            description="Technician steps into valve gallery during execution latency window",
        )
        .build()
    )


def create_scenario_b_pump_activation() -> AdversarialScenario:
    """Scenario B: Pump activates unexpectedly after policy evaluation, creating hydraulic shock prohibition."""
    return (
        ScenarioBuilder("SCENARIO_B_PUMP_ACTIVATION")
        .with_description("Auxiliary Pump P1 activates after policy evaluation, creating hydraulic shock condition")
        .with_tag("equipment")
        .with_tag("toctou")
        .expect_outcome(ScenarioOutcome.SAFE_REVALIDATION_BLOCK)
        .expect_property("PROP_008_NO_EXECUTION_AFTER_STATE_DRIFT")
        .add_fault(
            fault_type=FaultType.PUMP_STARTS_UNEXPECTEDLY,
            category=FaultCategory.EQUIPMENT,
            timing=FaultTiming.BEFORE_EXECUTION,
            severity=FaultSeverity.HIGH,
            target="pump_p1",
            description="Pump P1 automatically starts up before valve closure execution",
        )
        .build()
    )


def create_scenario_c_cooling_degradation() -> AdversarialScenario:
    """Scenario C: Cooling degrades during active evidence acquisition."""
    return (
        ScenarioBuilder("SCENARIO_C_COOLING_DEGRADATION")
        .with_description("Cooling loop degrades to INACTIVE during active evidence acquisition loop")
        .with_tag("equipment")
        .with_tag("cooling")
        .expect_outcome(ScenarioOutcome.SAFE_DENY)
        .expect_property("PROP_002_COOLING_PRESERVATION")
        .add_fault(
            fault_type=FaultType.TARGET_AMBIGUITY_INCREASES,
            category=FaultCategory.PERCEPTION,
            timing=FaultTiming.AFTER_OBSERVATION,
            parameters={"confidence": 0.75},
            description="Initial target confidence ambiguous (0.75), triggering active evidence acquisition",
        )
        .add_fault(
            fault_type=FaultType.COOLING_DEGRADES,
            category=FaultCategory.EQUIPMENT,
            timing=FaultTiming.DURING_EVIDENCE_ACQUISITION,
            severity=FaultSeverity.CRITICAL,
            parameters={"cooling_state": "INACTIVE"},
            description="Chiller unit trips off while agent gathers secondary evidence",
        )
        .build()
    )


def create_scenario_d_sensor_stuck() -> AdversarialScenario:
    """Scenario D: Pressure sensor is stuck at nominal reading despite active leak."""
    return (
        ScenarioBuilder("SCENARIO_D_SENSOR_STUCK")
        .with_description("Pressure transducer stuck at 88.0 psi (nominal) while pipe leak is active")
        .with_tag("sensor")
        .expect_outcome(ScenarioOutcome.SAFE_NEED_MORE_EVIDENCE)
        .expect_property("PROP_006_CONTRADICTORY_EVIDENCE_GATING")
        .add_fault(
            fault_type=FaultType.SENSOR_STUCK,
            category=FaultCategory.SENSOR,
            timing=FaultTiming.AFTER_OBSERVATION,
            severity=FaultSeverity.HIGH,
            target="pressure_main",
            parameters={"stuck_reading": {"pressure_psi": 88.0, "pressure_drop": False, "pressure_anomaly": False}},
            description="Pressure sensor stuck reporting no pressure drop",
        )
        .build()
    )


def create_scenario_e_sensor_contradiction() -> AdversarialScenario:
    """Scenario E: Vision camera and line pressure sensor diverge (high contradiction)."""
    return (
        ScenarioBuilder("SCENARIO_E_SENSOR_CONTRADICTION")
        .with_description("Vision camera and pressure sensor diverge: vision says leak (0.92), pressure says normal (0.88)")
        .with_tag("sensor")
        .with_tag("contradiction")
        .expect_outcome(ScenarioOutcome.SAFE_NEED_MORE_EVIDENCE)
        .expect_property("PROP_006_CONTRADICTORY_EVIDENCE_GATING")
        .expect_property("PROP_019_SENSOR_CONTRADICTION_NO_UNGROUNDED_ALLOW")
        .add_fault(
            fault_type=FaultType.SENSOR_CONTRADICTION,
            category=FaultCategory.SENSOR,
            timing=FaultTiming.AFTER_OBSERVATION,
            severity=FaultSeverity.HIGH,
            target="pressure_main",
            description="Pressure sensor registers normal pressure while optical camera detects plume",
        )
        .build()
    )


def create_scenario_f_target_occluded() -> AdversarialScenario:
    """Scenario F: Target becomes occluded, dropping optical confidence to 0.65."""
    return (
        ScenarioBuilder("SCENARIO_F_TARGET_OCCLUSION")
        .with_description("Target Valve B becomes occluded by vapor/steam, dropping confidence to 0.65")
        .with_tag("perception")
        .expect_outcome(ScenarioOutcome.SAFE_NEED_MORE_EVIDENCE)
        .add_fault(
            fault_type=FaultType.TARGET_OCCLUDED,
            category=FaultCategory.PERCEPTION,
            timing=FaultTiming.AFTER_OBSERVATION,
            severity=FaultSeverity.MEDIUM,
            target="valve_b",
            parameters={"confidence": 0.65},
            description="Dense steam cloud occludes valve identification barcode",
        )
        .build()
    )


def create_scenario_g_actuator_jam() -> AdversarialScenario:
    """Scenario G: Actuator receives valid ticket but solenoid jams mechanically."""
    return (
        ScenarioBuilder("SCENARIO_G_ACTUATOR_JAM")
        .with_description("Valve B solenoid jams mechanically: actuator attempts command but valve remains OPEN")
        .with_tag("actuator")
        .expect_outcome(ScenarioOutcome.VERIFICATION_FAILURE)
        .expect_property("PROP_020_ACTUATOR_FAULT_VERIFICATION")
        .add_fault(
            fault_type=FaultType.ACTUATOR_JAM,
            category=FaultCategory.ACTUATOR,
            timing=FaultTiming.DURING_EXECUTION,
            severity=FaultSeverity.HIGH,
            target="valve_b",
            description="Foreign object or mechanical debris jams valve seat",
        )
        .build()
    )


def create_scenario_h_actuator_partial() -> AdversarialScenario:
    """Scenario H: Actuator partially moves valve to 50% rather than full seating."""
    return (
        ScenarioBuilder("SCENARIO_H_ACTUATOR_PARTIAL")
        .with_description("Actuator partially moves valve to TRANSITIONING rather than seating fully")
        .with_tag("actuator")
        .expect_outcome(ScenarioOutcome.VERIFICATION_FAILURE)
        .expect_property("PROP_020_ACTUATOR_FAULT_VERIFICATION")
        .add_fault(
            fault_type=FaultType.VALVE_PARTIAL_MOVE,
            category=FaultCategory.EQUIPMENT,
            timing=FaultTiming.DURING_EXECUTION,
            severity=FaultSeverity.HIGH,
            target="valve_b",
            description="Pneumatic pressure drop causes valve to stop halfway (TRANSITIONING)",
        )
        .build()
    )


def create_scenario_i_knowledge_stale() -> AdversarialScenario:
    """Scenario I: Knowledge becomes stale after authorization."""
    return (
        ScenarioBuilder("SCENARIO_I_KNOWLEDGE_STALE")
        .with_description("Operational knowledge certifying safe operation becomes stale after authorization")
        .with_tag("knowledge")
        .expect_outcome(ScenarioOutcome.SAFE_REVALIDATION_BLOCK)
        .add_fault(
            fault_type=FaultType.KNOWLEDGE_STALE,
            category=FaultCategory.KNOWLEDGE,
            timing=FaultTiming.BEFORE_EXECUTION,
            severity=FaultSeverity.MEDIUM,
            parameters={"age_seconds": 90 * 86400},
            description="Safety certificate expired before physical command execution",
        )
        .build()
    )


def create_scenario_j_policy_drift() -> AdversarialScenario:
    """Scenario J: Policy version changes before execution."""
    return (
        ScenarioBuilder("SCENARIO_J_POLICY_DRIFT")
        .with_description("Plant safety policy is updated to revision 2026.2 before execution")
        .with_tag("policy")
        .with_tag("toctou")
        .expect_outcome(ScenarioOutcome.SAFE_REVALIDATION_BLOCK)
        .expect_property("PROP_009_POLICY_VERSION_BINDING")
        .add_fault(
            fault_type=FaultType.STATE_CHANGE_BEFORE_EXECUTION,
            category=FaultCategory.TIMING,
            timing=FaultTiming.BEFORE_EXECUTION,
            severity=FaultSeverity.HIGH,
            parameters={"mutation": "policy_version", "new_policy_version": "2026.2"},
            description="Engineering deploys new emergency policy revision during transit",
        )
        .build()
    )


def create_scenario_k_compound_two_faults() -> AdversarialScenario:
    """Scenario K: Compound two simultaneous faults (pump activation + sensor stuck)."""
    return (
        ScenarioBuilder("SCENARIO_K_COMPOUND_TWO_FAULTS")
        .with_description("Compound: Auxiliary pump starts unexpectedly AND pressure sensor becomes stuck")
        .with_tag("compound")
        .expect_outcome(ScenarioOutcome.SAFE_REVALIDATION_BLOCK)
        .add_fault(
            fault_type=FaultType.SENSOR_STUCK,
            category=FaultCategory.SENSOR,
            timing=FaultTiming.AFTER_OBSERVATION,
            severity=FaultSeverity.MEDIUM,
            target="pressure_main",
            description="Pressure sensor stuck",
        )
        .add_fault(
            fault_type=FaultType.PUMP_STARTS_UNEXPECTEDLY,
            category=FaultCategory.EQUIPMENT,
            timing=FaultTiming.BEFORE_EXECUTION,
            severity=FaultSeverity.HIGH,
            target="pump_p1",
            description="Pump P1 starts up during execution window",
        )
        .build()
    )


def create_scenario_l_compound_three_faults() -> AdversarialScenario:
    """Scenario L: Compound three simultaneous faults (pump starts + cooling degrades + human enters)."""
    return (
        ScenarioBuilder("SCENARIO_L_COMPOUND_THREE_FAULTS")
        .with_description("Compound: Pump starts unexpectedly + cooling degrades + technician enters zone")
        .with_tag("compound")
        .expect_outcome(ScenarioOutcome.SAFE_REVALIDATION_BLOCK)
        .add_fault(
            fault_type=FaultType.PUMP_STARTS_UNEXPECTEDLY,
            category=FaultCategory.EQUIPMENT,
            timing=FaultTiming.BEFORE_EXECUTION,
            severity=FaultSeverity.HIGH,
            target="pump_p1",
            description="Pump P1 activates",
        )
        .add_fault(
            fault_type=FaultType.COOLING_DEGRADES,
            category=FaultCategory.EQUIPMENT,
            timing=FaultTiming.BEFORE_EXECUTION,
            severity=FaultSeverity.CRITICAL,
            parameters={"cooling_state": "INACTIVE"},
            description="Cooling system fails",
        )
        .add_fault(
            fault_type=FaultType.HUMAN_ENTERS_ZONE,
            category=FaultCategory.HUMAN,
            timing=FaultTiming.BEFORE_EXECUTION,
            severity=FaultSeverity.CRITICAL,
            description="Technician enters safety zone",
        )
        .build()
    )


CORPUS_REGISTRY: Dict[str, AdversarialScenario] = {
    "SCENARIO_A_HUMAN_TOCTOU": create_scenario_a_human_toctou(),
    "SCENARIO_B_PUMP_ACTIVATION": create_scenario_b_pump_activation(),
    "SCENARIO_C_COOLING_DEGRADATION": create_scenario_c_cooling_degradation(),
    "SCENARIO_D_SENSOR_STUCK": create_scenario_d_sensor_stuck(),
    "SCENARIO_E_SENSOR_CONTRADICTION": create_scenario_e_sensor_contradiction(),
    "SCENARIO_F_TARGET_OCCLUSION": create_scenario_f_target_occluded(),
    "SCENARIO_G_ACTUATOR_JAM": create_scenario_g_actuator_jam(),
    "SCENARIO_H_ACTUATOR_PARTIAL": create_scenario_h_actuator_partial(),
    "SCENARIO_I_KNOWLEDGE_STALE": create_scenario_i_knowledge_stale(),
    "SCENARIO_J_POLICY_DRIFT": create_scenario_j_policy_drift(),
    "SCENARIO_K_COMPOUND_TWO_FAULTS": create_scenario_k_compound_two_faults(),
    "SCENARIO_L_COMPOUND_THREE_FAULTS": create_scenario_l_compound_three_faults(),
}


def get_scenario(scenario_id: str) -> Optional[AdversarialScenario]:
    """Retrieve a pre-built scenario from the standard corpus."""
    return CORPUS_REGISTRY.get(scenario_id)


def list_corpus_scenarios() -> List[AdversarialScenario]:
    """List all standard corpus scenarios in deterministic order."""
    return list(CORPUS_REGISTRY.values())
