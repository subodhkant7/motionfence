"""Mock hardware adapter wrapping MockHardwareEndpoint and PhysicalWorld.

Provides the deterministic local baseline and zero-dependency offline fallback.
"""

from typing import Any, Dict, Optional
import time
import uuid

from motionfence.models.actions import ActionProposal, AuthorizationTicket
from motionfence.models.world import ValveState, CoolingState, HumanZoneState
from motionfence.simulation.world import PhysicalWorld
from motionfence.simulation.actuator import PhysicalActuator
from motionfence.hardware.mock import MockHardwareEndpoint
from motionfence.hardware.models import (
    ActuatorType,
    HardwareFaultType,
    HardwareExecutionStatus,
)
from motionfence.simulation.adapters.base import PhysicalExecutionAdapter
from motionfence.simulation.adapters.models import (
    PhysicalBackendType,
    PhysicalObservation,
    PhysicalExecutionResult,
    AdapterStatus,
)


class MockHardwareAdapter:
    """Adapter bridging the canonical MockHardwareEndpoint to the PhysicalExecutionAdapter protocol."""

    def __init__(
        self,
        world: Optional[PhysicalWorld] = None,
        hardware_id: str = "HWR_ACTUATOR_VALVE_01",
        secret_key: str = "motionfence_runtime_kernel_secret",
    ) -> None:
        self._world = world or PhysicalWorld()
        self._actuator = PhysicalActuator(self._world, secret_key=secret_key)
        self._hardware = MockHardwareEndpoint(
            world=self._world,
            hardware_id=hardware_id,
            actuator_type=ActuatorType.VALVE_ACTUATOR,
            secret_key=secret_key,
            underlying_actuator=self._actuator,
        )
        self._connected: bool = True
        self._step_count: int = 0
        self._sim_time: float = 0.0

    @property
    def world(self) -> PhysicalWorld:
        return self._world

    @property
    def hardware(self) -> MockHardwareEndpoint:
        return self._hardware

    def connect(self) -> bool:
        self._connected = True
        return True

    def disconnect(self) -> None:
        self._connected = False

    def is_connected(self) -> bool:
        return self._connected

    def is_available(self) -> bool:
        return True  # Mock adapter is always available offline

    @property
    def backend_type(self) -> PhysicalBackendType:
        return PhysicalBackendType.MOCK_PHYSICAL_WORLD

    def get_backend_name(self) -> PhysicalBackendType:
        return PhysicalBackendType.MOCK_PHYSICAL_WORLD

    def get_observation(self) -> PhysicalObservation:
        """Alias for get_state returning normalized telemetry snapshot."""
        return self.get_state()

    def get_status(self) -> AdapterStatus:
        if not self._connected:
            return AdapterStatus.DISCONNECTED
        hw_status = self._hardware.get_status()
        if hw_status.is_locked:
            return AdapterStatus.LOCKED
        if hw_status.active_fault != HardwareFaultType.NONE:
            return AdapterStatus.FAULT_INJECTED
        return AdapterStatus.READY

    def get_state(self) -> PhysicalObservation:
        """Extract and normalize telemetry from PhysicalWorld and MockHardwareEndpoint."""
        valve_b = self._world.valves.get("valve_b", ValveState.OPEN)
        valve_str = valve_b.value if hasattr(valve_b, "value") else str(valve_b)
        valve_angle = 90.0 if valve_str == "CLOSED" else 0.0

        pump_p1 = self._world.pumps.get("pump_p1", "INACTIVE")
        pump_str = pump_p1.value if hasattr(pump_p1, "value") else str(pump_p1)

        cooling = self._world.cooling.value if hasattr(self._world.cooling, "value") else str(self._world.cooling)
        human_zone = self._world.human_zone.value if hasattr(self._world.human_zone, "value") else str(self._world.human_zone)

        hw_status = self._hardware.get_status()
        fault_active = (hw_status.active_fault != HardwareFaultType.NONE)
        fault_type_str = hw_status.active_fault.value if fault_active else None

        actuator_status_str = "READY"
        if hw_status.is_locked:
            actuator_status_str = "LOCKED"
        elif valve_str == "CLOSED":
            actuator_status_str = "ACTUATED"

        is_closed = valve_str == "CLOSED"

        return PhysicalObservation(
            backend_type=PhysicalBackendType.MOCK_PHYSICAL_WORLD,
            simulation_time=self._sim_time,
            step_count=self._step_count,
            world_version=self._world.version,
            valve_b_state=valve_str,
            valve_b_angle_deg=valve_angle,
            pump_p1_state=pump_str,
            pump_p1_rpm=1750.0 if pump_str == "ACTIVE" else 0.0,
            cooling_state=cooling,
            human_zone=human_zone,
            human_distance_m=1.2 if human_zone == "OCCUPIED" else 5.0,
            actuator_status=actuator_status_str,
            pressure_psi=125.0 if is_closed else 95.5,
            flow_rate_lpm=0.0 if is_closed else 14.0,
            leak_active=not is_closed,
            fault_active=fault_active,
            active_fault_type=fault_type_str,
            metadata={"hardware_id": self._hardware.hardware_id},
        )

    def execute_authorized_action(
        self,
        proposal: ActionProposal,
        ticket: Optional[AuthorizationTicket],
        *,
        correlation_id: Optional[str] = None,
    ) -> PhysicalExecutionResult:
        """Forward execution request through MockHardwareEndpoint validation."""
        initial_obs = self.get_state()
        exec_id = f"exec_mock_{uuid.uuid4().hex[:10]}"

        record = self._hardware.receive_and_actuate(
            proposal=proposal,
            ticket=ticket,
            correlation_id=correlation_id or exec_id,
        )

        # Advance simulated physics slightly
        self.advance(steps=2, dt=0.05)
        final_obs = self.get_state()

        success = (record.execution_status == HardwareExecutionStatus.ACTUATED)
        status_str = record.execution_status.value if hasattr(record.execution_status, "value") else str(record.execution_status)
        reval_passed = record.execution_status not in (
            HardwareExecutionStatus.INVALID_TICKET,
            HardwareExecutionStatus.EXPIRED_TICKET,
            HardwareExecutionStatus.REPLAYED_TICKET,
            HardwareExecutionStatus.TARGET_MISMATCH,
            HardwareExecutionStatus.ACTION_MISMATCH,
            HardwareExecutionStatus.LOCKED,
        )

        return PhysicalExecutionResult(
            execution_id=record.record_id,
            backend=PhysicalBackendType.MOCK_PHYSICAL_WORLD,
            success=success,
            status=status_str,
            action_type=proposal.action_type.value if hasattr(proposal.action_type, "value") else str(proposal.action_type),
            target=proposal.target,
            initial_state=initial_obs.model_dump(),
            final_state=final_obs.model_dump(),
            ticket_id=ticket.ticket_id if ticket else None,
            ticket_status=record.ticket_status,
            signature_status=record.signature_status,
            revalidation_passed=reval_passed,
            is_actuated=record.is_actuated,
            error_message=record.message if not success else None,
            steps_advanced=2,
            simulation_elapsed_sec=0.10,
            fault_injected=record.fault_injected.value if hasattr(record.fault_injected, "value") else str(record.fault_injected),
            resulting_observation=final_obs,
        )

    def set_human_position(self, inside_zone: bool) -> PhysicalObservation:
        """Update human occupancy in sector 4 safety zone and advance world version."""
        self._world.human_zone = HumanZoneState.OCCUPIED if inside_zone else HumanZoneState.CLEAR
        self._world.version += 1
        return self.get_state()

    def set_pump_state(self, active: Any) -> PhysicalObservation:
        """Update pump state and advance world version."""
        is_active = (str(active).upper() == "ACTIVE") if isinstance(active, str) else bool(active)
        self._world.pumps["pump_p1"] = "ACTIVE" if is_active else "INACTIVE"
        self._world.version += 1
        return self.get_state()

    def inject_fault(self, fault_type: Any) -> None:
        """Inject deterministic hardware fault."""
        if isinstance(fault_type, HardwareFaultType):
            fault_enum = fault_type
        else:
            fault_enum_map = {
                "NO_OP": HardwareFaultType.NO_OP,
                "WRONG_FINAL_STATE": HardwareFaultType.WRONG_FINAL_STATE,
                "PARTIAL_ACTUATION": HardwareFaultType.PARTIAL_ACTUATION,
                "DELAYED_ACTUATION": HardwareFaultType.DELAYED_ACTUATION,
                "NONE": HardwareFaultType.NONE,
            }
            fault_name = fault_type.value if hasattr(fault_type, "value") else str(fault_type)
            fault_enum = fault_enum_map.get(fault_name.upper(), HardwareFaultType.NO_OP)
        self._hardware.inject_fault(fault_enum)

    def clear_fault(self) -> None:
        self._hardware.clear_fault()

    def advance(self, steps: int = 1, dt: float = 0.05) -> PhysicalObservation:
        self._step_count += steps
        self._sim_time += steps * dt
        return self.get_state()

    def reset(self, initial_state: Optional[Dict[str, Any]] = None) -> PhysicalObservation:
        self._world.valves["valve_b"] = ValveState.OPEN
        self._world.valves["valve_a"] = ValveState.OPEN
        self._world.cooling = CoolingState.ACTIVE
        self._world.pumps["pump_p1"] = "INACTIVE"
        self._world.version = 3
        self._step_count = 0
        self._sim_time = 0.0
        self.clear_fault()
        return self.get_state()

    def get_capabilities(self) -> Dict[str, Any]:
        return {
            "backend": "mock",
            "deterministic": True,
            "offline": True,
            "requires_gpu": False,
            "fault_injection_supported": True,
            "max_step_rate_hz": 1000,
        }
