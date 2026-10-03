"""Bridge mapping NVIDIA Isaac Sim physical observations into MotionFence WorldState.

SECURITY INVARIANT:
State changes in Isaac Sim (e.g. human entering safety zone) increment the monotonic
world version (v3 -> v4), enabling execution-time revalidation to detect physical drift
and invalidate pre-issued AuthorizationTickets (TOCTOU defense).
"""

from typing import Any, Dict, Optional
import time

from motionfence.models.world import WorldState, ValveState, CoolingState, HumanZoneState
from motionfence.simulation.adapters.models import PhysicalObservation, PhysicalBackendType


class IsaacWorldStateBridge:
    """Translates Isaac Sim physical observations into MotionFence WorldState representations."""

    def to_motionfence_world(self, obs: PhysicalObservation) -> WorldState:
        """Instance alias mapping normalized observation to MotionFence WorldState."""
        return self.observation_to_world_state(obs)

    @staticmethod
    def observation_to_world_state(obs: PhysicalObservation) -> WorldState:
        """Map a normalized Isaac Sim PhysicalObservation to a MotionFence WorldState."""
        valve_b_val = obs.valve_b_state
        valve_b_enum = ValveState.CLOSED if valve_b_val == "CLOSED" else ValveState.OPEN
        
        cooling_enum = CoolingState.ACTIVE if obs.cooling_state == "ACTIVE" else CoolingState.DEGRADED
        human_enum = HumanZoneState.OCCUPIED if obs.human_zone == "OCCUPIED" else HumanZoneState.CLEAR
        
        is_closed = valve_b_val == "CLOSED"

        leak_data = {
            "active": not is_closed,
            "target": "valve_b",
            "severity": 0.0 if is_closed else 0.85,
            "flow_rate_lpm": 0.0 if is_closed else obs.flow_rate_lpm,
        }

        # Build sensor observation dict
        sensor_obs = {
            "valve_b_position": {
                "sensor_id": "isaac_joint_sensor_vb",
                "sensor_type": "revolute_joint_encoder",
                "target": "valve_b",
                "reading": {
                    "angle_degrees": obs.valve_b_angle_deg,
                    "state": valve_b_val,
                },
                "confidence": 0.99,
                "timestamp": time.time(),
                "metadata": {"prim_path": obs.isaac_prim_paths.get("valve_b") if obs.isaac_prim_paths else "/World/IndustrialCell/CoolantManifold/ValveB"},
            },
            "pressure_main": {
                "sensor_id": "isaac_pressure_sensor_pt01",
                "sensor_type": "piezo_pressure",
                "target": "manifold_line",
                "reading": {
                    "pressure_psi": obs.pressure_psi,
                    "pressure_nominal": is_closed,
                },
                "confidence": 0.98,
                "timestamp": time.time(),
            },
            "safety_zone_occupancy": {
                "sensor_id": "isaac_lidar_zone_s4",
                "sensor_type": "spatial_occupancy",
                "target": "human_zone",
                "reading": {
                    "occupied": obs.human_zone == "OCCUPIED",
                    "distance_m": obs.human_distance_m,
                },
                "confidence": 0.99,
                "timestamp": time.time(),
            },
        }

        return WorldState(
            valves={
                "valve_a": "OPEN",
                "valve_b": valve_b_val,
            },
            cooling=cooling_enum.value,
            human_zone=human_enum.value,
            pumps={
                "pump_p1": obs.pump_p1_state,
            },
            leak=leak_data,
            version=obs.world_version,
            timestamp=time.time(),
            observations=sensor_obs,
            external_observations={
                "simulation_backend": obs.backend_type.value,
                "simulation_time_sec": obs.simulation_time,
                "physics_steps": obs.step_count,
                "isaac_prims": obs.isaac_prim_paths or {},
                "actuator_status": obs.actuator_status,
                "fault_active": obs.fault_active,
            },
        )
