"""Stateful physical environment simulator for physical AI authorization scenarios."""

from typing import Dict, List, Optional
import time

from motionfence.models.world import (
    ValveState,
    CoolingState,
    HumanZoneState,
    LeakState,
    SensorObservation,
    WorldState,
)
from motionfence.evidence.models import Evidence, EvidenceSource


class PhysicalWorld:
    """Stateful physical system modeling valves, cooling loops, leaks, and safety zones.
    
    This is a real state machine simulating physical transitions and sensor outputs.
    """

    def __init__(
        self,
        leak_target: str = "valve_b",
        leak_severity: float = 0.85,
    ) -> None:
        self.valves: Dict[str, ValveState] = {
            "valve_a": ValveState.OPEN,
            "valve_b": ValveState.OPEN,
        }
        self.cooling: CoolingState = CoolingState.ACTIVE
        self.leak_target = leak_target
        self.leak: LeakState = LeakState(
            active=True,
            target=leak_target,
            severity=leak_severity,
            flow_rate_lpm=14.2,
        )
        self.human_zone: HumanZoneState = HumanZoneState.CLEAR
        self.jammed_valves: set[str] = set()
        self.version: int = 1
        self.last_updated: float = time.time()

    def get_state(self) -> WorldState:
        """Export an immutable WorldState snapshot representing the current physical reality."""
        # Calculate nominal sensor readings based on current physical state
        observations = {}
        now = time.time()

        # Pressure sensor reading
        if self.leak.active:
            observations["pressure_main"] = SensorObservation(
                sensor_id="press_sensor_01",
                sensor_type="pressure",
                target="manifold_line",
                reading={"pressure_psi": 42.5, "pressure_drop": True, "pressure_anomaly": True},
                confidence=0.94,
                timestamp=now,
            )
        else:
            observations["pressure_main"] = SensorObservation(
                sensor_id="press_sensor_01",
                sensor_type="pressure",
                target="manifold_line",
                reading={"pressure_psi": 88.0, "pressure_drop": False, "pressure_anomaly": False, "pressure_normal": True},
                confidence=0.98,
                timestamp=now,
            )

        # Cooling temperature sensor
        observations["cooling_temp"] = SensorObservation(
            sensor_id="temp_cooling_01",
            sensor_type="temperature",
            target="cooling_chiller",
            reading={"temperature_c": 4.1, "cooling_active": self.cooling == CoolingState.ACTIVE},
            confidence=0.99,
            timestamp=now,
        )

        return WorldState(
            valves=dict(self.valves),
            cooling=self.cooling,
            leak=self.leak.model_copy(),
            human_zone=self.human_zone,
            observations=observations,
            version=self.version,
            timestamp=self.last_updated,
        )

    def generate_initial_ambiguous_evidence(self) -> List[Evidence]:
        """Produce initial visual and sensor observations containing realistic visual ambiguity.
        
        Demonstrates why unrestricted LLM control is unsafe: both valves look visually similar,
        and wide-angle camera confidence is inadequate for safe physical action.
        """
        now = time.time()
        return [
            Evidence(
                source=EvidenceSource.VISION,
                target="valve_a",
                observation={"visual_vapor_detected": True, "valve_state": "OPEN"},
                confidence=0.74,  # Ambiguous! Looks like vapor near A
                timestamp=now,
                provenance="camera_wide_overhead:v1_detector",
                metadata={"lighting": "nominal", "field_of_view": "wide"},
            ),
            Evidence(
                source=EvidenceSource.VISION,
                target="valve_b",
                observation={"visual_vapor_detected": True, "valve_state": "OPEN"},
                confidence=0.78,  # Ambiguous! Looks slightly more like B, but below safety threshold
                timestamp=now,
                provenance="camera_wide_overhead:v1_detector",
                metadata={"lighting": "nominal", "field_of_view": "wide"},
            ),
            Evidence(
                source=EvidenceSource.PRESSURE_SENSOR,
                target="manifold_line",
                observation={"pressure_anomaly": True, "pressure_drop_rate": "moderate"},
                confidence=0.92,
                timestamp=now,
                provenance="sensor_piezo_pressure_01",
            ),
        ]

    def generate_targeted_evidence(self, target: str = "valve_b") -> List[Evidence]:
        """Generate high-confidence evidence from targeted inspection / multi-modal sensors."""
        now = time.time()
        evidence_list = []

        if target == self.leak_target:
            # High-confidence confirmation on the true leak target
            evidence_list.extend([
                Evidence(
                    source=EvidenceSource.THERMAL_SENSOR,
                    target=target,
                    observation={"thermal_gradient_c": 18.4, "cold_expansion_plume": True, "leak_confirmed": True},
                    confidence=0.96,
                    timestamp=now,
                    provenance="flir_thermal_ptu_02",
                    metadata={"focal_distance_m": 1.2},
                ),
                Evidence(
                    source=EvidenceSource.VISION,
                    target=target,
                    observation={"gasket_failure_visible": True, "condensation_drip": True, "valve_state": "OPEN"},
                    confidence=0.95,
                    timestamp=now,
                    provenance="camera_zoom_macro_01",
                    metadata={"zoom": "4x", "target_lock": True},
                ),
            ])
        else:
            # Confirms target is NOT leaking
            evidence_list.append(
                Evidence(
                    source=EvidenceSource.THERMAL_SENSOR,
                    target=target,
                    observation={"thermal_gradient_c": 0.2, "leak_confirmed": False},
                    confidence=0.97,
                    timestamp=now,
                    provenance="flir_thermal_ptu_02",
                )
            )

        return evidence_list

    def generate_contradictory_evidence(self, target: str = "valve_b") -> List[Evidence]:
        """Generate conflicting observations to test the contradiction detection engine."""
        now = time.time()
        return [
            Evidence(
                source=EvidenceSource.VISION,
                target=target,
                observation={"leak_detected": True, "visual_vapor": True},
                confidence=0.93,
                timestamp=now,
                provenance="camera_zoom_macro_01",
            ),
            Evidence(
                source=EvidenceSource.PRESSURE_SENSOR,
                target=target,
                observation={"pressure_anomaly": False, "pressure_normal": True, "leak_detected": False},
                confidence=0.91,
                timestamp=now,
                provenance="sensor_piezo_pressure_01",
            ),
        ]

    def set_human_zone(self, state: HumanZoneState) -> None:
        """Simulate a human entering or exiting the safety zone."""
        self.human_zone = state
        self.version += 1
        self.last_updated = time.time()

    def inject_valve_jam(self, valve_id: str) -> None:
        """Inject a mechanical jamming fault on a valve."""
        self.jammed_valves.add(valve_id)

    def clear_faults(self) -> None:
        """Clear all injected faults."""
        self.jammed_valves.clear()
