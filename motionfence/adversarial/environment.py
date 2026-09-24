"""Adversarial physical environment simulator capable of independent world mutation and hidden-state injection."""

from typing import Any, Dict, List, Optional, Set
import copy
import random
import time

from motionfence.adversarial.models import (
    AdversarialFault,
    FaultCategory,
    FaultType,
    FaultSeverity,
    FaultTiming,
    ScheduledFault,
)
from motionfence.adversarial.faults import FaultApplier
from motionfence.models.world import (
    CoolingState,
    HumanZoneState,
    LeakState,
    SensorObservation,
    ValveState,
    WorldState,
)
from motionfence.simulation.world import PhysicalWorld
from motionfence.evidence.models import Evidence


class AdversarialEnvironment:
    """Simulates an adversarial physical plant environment with decoupled ground-truth and observable state.
    
    SECURITY INVARIANTS:
    1. Zero Actuator Authority: Cannot command physical actuators directly.
    2. Zero Ticket Minting Authority: Possesses no cryptographic signing keys or TicketAuthority references.
    3. Zero Enclave Authority: Cannot invoke or bypass the SafetyEnclave.
    4. Simulation Scope Only: Represents environmental disturbance in simulation, never production authority.
    """

    def __init__(
        self,
        world: Optional[PhysicalWorld] = None,
        seed: int = 42,
    ) -> None:
        self.world: PhysicalWorld = world or PhysicalWorld()
        self.seed: int = seed
        self.rng: random.Random = random.Random(seed)
        self.scheduled_faults: List[ScheduledFault] = []
        self.applied_faults: List[Dict[str, Any]] = []

        # Hidden state mechanics (Ground Truth vs Observable State)
        self.hidden_state_overrides: Dict[str, Any] = {}
        self.observable_sensor_overrides: Dict[str, SensorObservation] = {}
        self.dropped_sensor_ids: Set[str] = set()

        # Actuator fault behaviors
        self.actuator_jammed_targets: Set[str] = set()
        self.actuator_partial_targets: Set[str] = set()
        self.actuator_no_op_targets: Set[str] = set()
        self.actuator_delay_seconds: float = 0.0

    # -----------------------------------------------------------------------
    # Security Boundary Invariants
    # -----------------------------------------------------------------------

    def can_mint_ticket(self) -> bool:
        """Formal check: AdversarialEnvironment possesses ZERO ticket authority."""
        return False

    def can_bypass_policy(self) -> bool:
        """Formal check: AdversarialEnvironment possesses ZERO policy bypass capability."""
        return False

    def can_invoke_enclave(self) -> bool:
        """Formal check: AdversarialEnvironment possesses ZERO enclave authority."""
        return False

    # -----------------------------------------------------------------------
    # Schedule & Step Execution
    # -----------------------------------------------------------------------

    def schedule_fault(self, fault: AdversarialFault, timing: FaultTiming, step_offset: int = 0) -> ScheduledFault:
        """Register a fault to fire deterministically at a designated lifecycle junction."""
        sf = ScheduledFault(
            fault=fault,
            timing=timing,
            step_offset=step_offset,
        )
        self.scheduled_faults.append(sf)
        return sf

    def step(self, timing_point: FaultTiming, context: Optional[Dict[str, Any]] = None) -> List[str]:
        """Trigger any faults scheduled for this lifecycle junction."""
        actions_taken = []
        for sf in self.scheduled_faults:
            if sf.timing == timing_point and not sf.executed:
                mutation_msg = self.inject_fault(sf.fault)
                sf.executed = True
                sf.execution_timestamp = time.time()
                sf.applied_mutation = mutation_msg
                actions_taken.append(mutation_msg)
        return actions_taken

    def inject_fault(self, fault: AdversarialFault) -> str:
        """Directly inject a typed fault into the environment."""
        category = fault.category
        ft = fault.fault_type
        params = fault.parameters

        # Track actuator-specific malfunction flags
        if ft == FaultType.ACTUATOR_JAM or ft == FaultType.VALVE_JAM:
            target = fault.target or "valve_b"
            self.actuator_jammed_targets.add(target)
            self.world.jammed_valves.add(target)
            msg = f"Injected actuator jam on target '{target}'"

        elif ft == FaultType.ACTUATOR_PARTIAL:
            target = fault.target or "valve_b"
            self.actuator_partial_targets.add(target)
            msg = f"Injected partial actuator movement on target '{target}'"

        elif ft == FaultType.ACTUATOR_NO_OP:
            target = fault.target or "valve_b"
            self.actuator_no_op_targets.add(target)
            msg = f"Injected actuator NO-OP on target '{target}'"

        elif ft == FaultType.ACTUATOR_DELAY:
            self.actuator_delay_seconds = params.get("delay", 0.5)
            msg = f"Injected actuator delay of {self.actuator_delay_seconds}s"

        elif category in (FaultCategory.HUMAN, FaultCategory.EQUIPMENT, FaultCategory.TIMING):
            msg = FaultApplier.apply_world_fault(self.world, fault, rng=self.rng)

        elif category == FaultCategory.SENSOR:
            current_obs = self.world.get_state().observations
            mutated_obs, msg = FaultApplier.apply_sensor_fault(current_obs, fault, rng=self.rng)
            self.observable_sensor_overrides.update(mutated_obs)
            if ft == FaultType.SENSOR_DROPOUT:
                self.dropped_sensor_ids.add(fault.target or "pressure_main")

        else:
            msg = f"Applied generic environmental disturbance: {fault.fault_type.value}"

        self.applied_faults.append({
            "fault_id": fault.fault_id,
            "fault_type": fault.fault_type.value,
            "category": fault.category.value,
            "severity": fault.severity.value,
            "timing": fault.timing.value,
            "message": msg,
            "timestamp": time.time(),
        })
        return msg

    # -----------------------------------------------------------------------
    # Decoupled Ground-Truth vs Observable State
    # -----------------------------------------------------------------------

    def get_ground_truth_state(self) -> WorldState:
        """Returns the true physical state of the plant (ground truth)."""
        return self.world.get_state()

    def get_observable_state(self) -> WorldState:
        """Returns the state as seen through sensors, including noise, stuck values, dropouts, or hidden physical states."""
        true_state = self.world.get_state()
        observable_obs = copy.deepcopy(true_state.observations)

        # Apply sensor overrides (stuck, bias, contradiction)
        for s_id, s_obs in self.observable_sensor_overrides.items():
            observable_obs[s_id] = s_obs

        # Apply dropouts
        for d_id in self.dropped_sensor_ids:
            if d_id in observable_obs:
                del observable_obs[d_id]

        # Apply hidden-state overrides (where ground truth differs from observation)
        valves = dict(true_state.valves)
        if "observable_valve_state" in self.hidden_state_overrides:
            valves.update(self.hidden_state_overrides["observable_valve_state"])

        pumps = dict(true_state.pumps)
        if "observable_pump_state" in self.hidden_state_overrides:
            pumps.update(self.hidden_state_overrides["observable_pump_state"])

        human_zone = true_state.human_zone
        if "observable_human_zone" in self.hidden_state_overrides:
            human_zone = self.hidden_state_overrides["observable_human_zone"]

        cooling = true_state.cooling
        if "observable_cooling" in self.hidden_state_overrides:
            cooling = self.hidden_state_overrides["observable_cooling"]

        return WorldState(
            valves=valves,
            cooling=cooling,
            leak=true_state.leak.model_copy(),
            human_zone=human_zone,
            pumps=pumps,
            observations=observable_obs,
            version=true_state.version,
            timestamp=true_state.timestamp,
        )

    def set_hidden_state_discrepancy(self, key: str, observable_value: Any) -> None:
        """Explicitly configure a discrepancy where observable reality diverges from true physical state."""
        self.hidden_state_overrides[key] = observable_value

    def filter_evidence_pool(self, evidence_list: List[Evidence]) -> List[Evidence]:
        """Apply perception faults (occlusion, ambiguity, viewpoint loss) to an evidence pool."""
        filtered = copy.deepcopy(evidence_list)
        for sf in self.scheduled_faults:
            if sf.fault.category == FaultCategory.PERCEPTION:
                filtered, _ = FaultApplier.apply_perception_fault(filtered, sf.fault, rng=self.rng)
        return filtered

    def filter_knowledge_pool(self, knowledge_list: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        """Apply knowledge base faults (stale, conflicts, content changes) to knowledge items."""
        filtered = copy.deepcopy(knowledge_list)
        for sf in self.scheduled_faults:
            if sf.fault.category == FaultCategory.KNOWLEDGE:
                filtered, _ = FaultApplier.apply_knowledge_fault(filtered, sf.fault)
        return filtered
