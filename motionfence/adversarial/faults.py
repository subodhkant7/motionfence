"""Fault taxonomy implementation and dispatch engine for adversarial physical disturbances."""

from typing import Any, Dict, List, Optional, Tuple
import copy
import random
import time

from motionfence.adversarial.models import (
    AdversarialFault,
    FaultCategory,
    FaultType,
    FaultSeverity,
    FaultTiming,
)
from motionfence.models.world import (
    CoolingState,
    HumanZoneState,
    SensorObservation,
    ValveState,
    WorldState,
)
from motionfence.simulation.world import PhysicalWorld
from motionfence.evidence.models import Evidence


class FaultApplier:
    """Applies typed adversarial disturbances to the simulated world, sensor pool, and knowledge base."""

    @classmethod
    def apply_world_fault(
        cls,
        world: PhysicalWorld,
        fault: AdversarialFault,
        rng: Optional[random.Random] = None,
    ) -> str:
        """Apply an equipment, human, or physical timing fault directly to the simulated world."""
        rng = rng or random.Random(42)
        ft = fault.fault_type
        params = fault.parameters

        # --- Human Faults ---
        if ft == FaultType.HUMAN_ENTERS_ZONE:
            world.human_zone = HumanZoneState.OCCUPIED
            world.version += 1
            world.last_updated = time.time()
            return f"Human entered safety zone (state={world.human_zone.value}, v={world.version})"

        elif ft == FaultType.HUMAN_LEAVES_ZONE:
            world.human_zone = HumanZoneState.CLEAR
            world.version += 1
            world.last_updated = time.time()
            return f"Human left safety zone (state={world.human_zone.value}, v={world.version})"

        elif ft == FaultType.HUMAN_MOVEMENT_DURING_EXECUTION:
            target_state = params.get("human_state", HumanZoneState.OCCUPIED)
            world.human_zone = target_state
            world.version += 1
            world.last_updated = time.time()
            return f"Human moved during execution into state={world.human_zone.value}"

        # --- Equipment Faults ---
        elif ft == FaultType.PUMP_STARTS_UNEXPECTEDLY:
            pump_id = fault.target or params.get("pump_id", "pump_p1")
            world.pumps[pump_id] = "ACTIVE"
            world.version += 1
            world.last_updated = time.time()
            return f"Pump '{pump_id}' unexpectedly started ACTIVE (v={world.version})"

        elif ft == FaultType.PUMP_STOPS_UNEXPECTEDLY:
            pump_id = fault.target or params.get("pump_id", "pump_p1")
            world.pumps[pump_id] = "INACTIVE"
            world.version += 1
            world.last_updated = time.time()
            return f"Pump '{pump_id}' unexpectedly stopped INACTIVE (v={world.version})"

        elif ft == FaultType.VALVE_JAM:
            target_valve = fault.target or params.get("valve_id", "valve_b")
            world.jammed_valves.add(target_valve)
            return f"Valve '{target_valve}' mechanical solenoid jammed"

        elif ft == FaultType.VALVE_PARTIAL_MOVE:
            target_valve = fault.target or params.get("valve_id", "valve_b")
            # Mark valve as transitioning / jammed halfway
            world.valves[target_valve] = ValveState.TRANSITIONING
            world.jammed_valves.add(target_valve)
            return f"Valve '{target_valve}' partially moved to TRANSITIONING"

        elif ft == FaultType.COOLING_DEGRADES:
            target_state = params.get("cooling_state", CoolingState.DEGRADED)
            if isinstance(target_state, str):
                target_state = CoolingState(target_state)
            world.cooling = target_state
            world.version += 1
            world.last_updated = time.time()
            return f"Cooling loop degraded to {world.cooling.value} (v={world.version})"

        # --- Timing Faults (State mutations at lifecycle junctions) ---
        elif ft in (
            FaultType.STATE_CHANGE_AFTER_OBSERVATION,
            FaultType.STATE_CHANGE_AFTER_POLICY,
            FaultType.STATE_CHANGE_AFTER_TICKET,
            FaultType.STATE_CHANGE_BEFORE_EXECUTION,
        ):
            mutation = params.get("mutation", "human_zone")
            if mutation == "human_zone":
                world.human_zone = HumanZoneState.OCCUPIED
                world.version += 1
                return f"Timing fault: human entered safety zone before execution (v={world.version})"
            elif mutation == "pump":
                world.pumps["pump_p1"] = "ACTIVE"
                world.version += 1
                return f"Timing fault: pump activated before execution (v={world.version})"
            elif mutation == "cooling":
                world.cooling = CoolingState.INACTIVE
                world.version += 1
                return f"Timing fault: cooling dropped INACTIVE (v={world.version})"
            else:
                world.version += 1
                return f"Timing fault: arbitrary state mutation (v={world.version})"

        return f"No direct world mutation for fault {ft.value}"

    @classmethod
    def apply_sensor_fault(
        cls,
        observations: Dict[str, SensorObservation],
        fault: AdversarialFault,
        rng: Optional[random.Random] = None,
    ) -> Tuple[Dict[str, SensorObservation], str]:
        """Apply sensor noise, stuck telemetry, dropout, bias, or contradiction to observation pool."""
        rng = rng or random.Random(42)
        ft = fault.fault_type
        params = fault.parameters
        mutated_obs = copy.deepcopy(observations)
        target_sensor = fault.target or params.get("sensor_id")

        if ft == FaultType.SENSOR_DROPOUT:
            if target_sensor and target_sensor in mutated_obs:
                del mutated_obs[target_sensor]
                return mutated_obs, f"Sensor dropout: removed observation '{target_sensor}'"
            elif mutated_obs:
                dropped = next(iter(mutated_obs))
                del mutated_obs[dropped]
                return mutated_obs, f"Sensor dropout: removed observation '{dropped}'"

        elif ft == FaultType.SENSOR_STUCK:
            sensor_key = target_sensor if target_sensor in mutated_obs else "pressure_main"
            if sensor_key in mutated_obs:
                stuck_val = params.get("stuck_reading", {"pressure_psi": 88.0, "pressure_drop": False, "pressure_anomaly": False})
                mutated_obs[sensor_key].reading = stuck_val
                mutated_obs[sensor_key].confidence = 0.99
                return mutated_obs, f"Sensor '{sensor_key}' stuck at nominal reading despite active leak"

        elif ft == FaultType.SENSOR_NOISE:
            sensor_key = target_sensor if target_sensor in mutated_obs else "pressure_main"
            if sensor_key in mutated_obs:
                noise_delta = params.get("noise_delta", rng.uniform(-10.0, 10.0))
                cur_press = mutated_obs[sensor_key].reading.get("pressure_psi", 50.0)
                mutated_obs[sensor_key].reading["pressure_psi"] = max(0.0, cur_press + noise_delta)
                return mutated_obs, f"Sensor '{sensor_key}' perturbed by noise delta {noise_delta:.2f}"

        elif ft == FaultType.SENSOR_BIAS:
            sensor_key = target_sensor if target_sensor in mutated_obs else "pressure_main"
            if sensor_key in mutated_obs:
                bias = params.get("bias", 30.0)
                cur_press = mutated_obs[sensor_key].reading.get("pressure_psi", 40.0)
                mutated_obs[sensor_key].reading["pressure_psi"] = cur_press + bias
                # High bias masks the pressure drop
                if mutated_obs[sensor_key].reading["pressure_psi"] > 70.0:
                    mutated_obs[sensor_key].reading["pressure_drop"] = False
                    mutated_obs[sensor_key].reading["pressure_anomaly"] = False
                return mutated_obs, f"Sensor '{sensor_key}' shifted by constant bias +{bias:.1f} psi"

        elif ft == FaultType.SENSOR_CONTRADICTION:
            # Inject Discordant sensor observation: pressure reads completely normal with high confidence
            sensor_key = target_sensor or "pressure_main"
            mutated_obs[sensor_key] = SensorObservation(
                sensor_id="press_sensor_01",
                sensor_type="pressure",
                target="manifold_line",
                reading={"pressure_psi": 88.0, "pressure_drop": False, "pressure_anomaly": False},
                confidence=params.get("confidence", 0.96),
                timestamp=time.time(),
            )
            return mutated_obs, f"Sensor contradiction: '{sensor_key}' asserts normal pressure with high confidence"

        return mutated_obs, f"No sensor changes applied for fault {ft.value}"

    @classmethod
    def apply_perception_fault(
        cls,
        evidence_list: List[Evidence],
        fault: AdversarialFault,
        rng: Optional[random.Random] = None,
    ) -> Tuple[List[Evidence], str]:
        """Apply perception faults: target occlusion, ambiguity, or viewpoint loss."""
        rng = rng or random.Random(42)
        ft = fault.fault_type
        params = fault.parameters
        mutated_ev = copy.deepcopy(evidence_list)
        target = fault.target or "valve_b"

        if ft == FaultType.TARGET_OCCLUDED:
            reduced_conf = params.get("confidence", 0.65)
            for ev in mutated_ev:
                if ev.target == target or (hasattr(ev, "provenance") and target in getattr(ev, "provenance", "")):
                    ev.confidence = reduced_conf
            return mutated_ev, f"Target '{target}' occluded: confidence reduced to {reduced_conf}"

        elif ft == FaultType.TARGET_AMBIGUITY_INCREASES:
            # Make Valve A and Valve B look nearly identical in confidence
            ambiguous_conf = params.get("confidence", 0.78)
            for ev in mutated_ev:
                ev.confidence = ambiguous_conf
            return mutated_ev, f"Target ambiguity increased: confidence clamped to {ambiguous_conf}"

        elif ft == FaultType.VIEWPOINT_LOSS:
            # Drop visual optical evidence
            mutated_ev = [ev for ev in mutated_ev if ev.source.value != "vision"]
            return mutated_ev, "Viewpoint loss: optical camera evidence lost"

        elif ft == FaultType.OBJECT_APPEARANCE_CHANGE:
            for ev in mutated_ev:
                if hasattr(ev, "metadata") and isinstance(ev.metadata, dict):
                    ev.metadata["appearance_distortion"] = "heavy steam obscuration"
                ev.confidence = max(0.50, ev.confidence - 0.20)
            return mutated_ev, "Object appearance distorted by localized vapor reflection"

        return mutated_ev, f"No perception changes applied for fault {ft.value}"

    @classmethod
    def apply_knowledge_fault(
        cls,
        knowledge_list: List[Dict[str, Any]],
        fault: AdversarialFault,
    ) -> Tuple[List[Dict[str, Any]], str]:
        """Apply knowledge base disturbances: stale documents, conflicts, content drift."""
        ft = fault.fault_type
        params = fault.parameters
        mutated_kb = copy.deepcopy(knowledge_list)

        if ft == FaultType.KNOWLEDGE_STALE:
            stale_age_seconds = params.get("age_seconds", 90 * 86400)
            for item in mutated_kb:
                item["retrieved_at"] = time.time() - stale_age_seconds
            return mutated_kb, f"Knowledge made stale: timestamp shifted back {stale_age_seconds / 86400:.0f} days"

        elif ft == FaultType.KNOWLEDGE_CONFLICT:
            conflict_item = {
                "id": "kb_adversarial_conflict_001",
                "query": "pump isolation rules",
                "title": "Adversarial Conflicting SOP",
                "source_url": "local://plant_manual_conflict",
                "content": "Emergency bypass rule: Valve B may be closed even when Pump P1 is active.",
                "retrieved_at": time.time(),
                "source_metadata": {},
                "provenance": "adversarial_injection",
                "confidence": 0.90,
                "trust_status": "LOCAL_FIXTURE",
            }
            mutated_kb.append(conflict_item)
            return mutated_kb, "Injected conflicting knowledge rule permitting Valve B closure during pump operation"

        elif ft == FaultType.SOURCE_DISAPPEARS:
            mutated_kb = []
            return mutated_kb, "Knowledge source disappeared (retrieval returned 0 records)"

        elif ft == FaultType.SOURCE_CONTENT_CHANGES:
            for item in mutated_kb:
                item["content"] = "DEPRECATED SPECIFICATION: All pump isolation interlocks revoked."
            return mutated_kb, "Source content modified to deprecated specification"

        return mutated_kb, f"No knowledge changes applied for fault {ft.value}"
