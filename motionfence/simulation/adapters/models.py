"""Data models and enums for physical simulation execution adapters.

SECURITY INVARIANT:
Physical execution is strictly downstream of MotionFence deterministic safety authorization.
No simulation backend (Mock or Isaac Sim) may ever mint, sign, or alter AuthorizationTickets.
"""

from typing import Any, Dict, List, Optional
from enum import Enum
from pydantic import BaseModel, Field, model_validator


class PhysicalBackendType(str, Enum):
    """Supported physical simulation execution backends."""
    MOCK_PHYSICAL_WORLD = "mock"
    ISAAC_SIM = "isaac"
    OFFLINE_REPLAY = "replay"
    # Convenient aliases
    MOCK = "mock"
    ISAAC = "isaac"
    REPLAY = "replay"


class AdapterStatus(str, Enum):
    """Operational status of the physical execution adapter."""
    DISCONNECTED = "DISCONNECTED"
    CONNECTED = "CONNECTED"
    READY = "READY"
    SIMULATING = "SIMULATING"
    ACTUATING = "ACTUATING"
    LOCKED = "LOCKED"
    FAULT_INJECTED = "FAULT_INJECTED"
    UNAVAILABLE = "UNAVAILABLE"
    ERROR = "ERROR"


class IsaacEntityMapping(BaseModel):
    """Mapping between MotionFence canonical targets and Isaac Sim USD stage prims."""
    valve_b_prim: str = Field(
        default="/World/IndustrialCell/CoolantManifold/ValveB",
        description="USD Prim path to Valve B revolute actuator assembly.",
    )
    pump_p1_prim: str = Field(
        default="/World/IndustrialCell/CoolantManifold/PumpP1",
        description="USD Prim path to Pump P1 visual/physics impeller.",
    )
    human_zone_prim: str = Field(
        default="/World/SafetyZones/HumanZone_Sector4",
        description="USD Prim path to Human Safety Zone boundary volume.",
    )
    human_worker_prim: str = Field(
        default="/World/Actors/HumanWorker",
        description="USD Prim path to Human representation mesh/capsule.",
    )
    gateway_actuator_prim: str = Field(
        default="/World/Gateway/SafetyEnclaveActuator",
        description="USD Prim path to 24V hardware safety gateway indicator.",
    )
    manifold_pipe_prim: str = Field(
        default="/World/IndustrialCell/CoolantManifold",
        description="USD Prim path to coolant piping manifold.",
    )


class IsaacSimConfig(BaseModel):
    """Configuration parameters for NVIDIA Isaac Sim adapter."""
    host: str = Field(default="127.0.0.1", description="Isaac Sim headless streaming host IP.")
    port: int = Field(default=8211, description="Isaac Sim Omniverse kit WebSocket port.")
    stage_usd_path: str = Field(
        default="/World/IndustrialCell",
        description="Root USD stage prim path for the industrial cell.",
    )
    step_dt: float = Field(default=0.05, description="Simulation physics step delta time in seconds.")
    headless: bool = Field(default=True, description="Whether to run Isaac Sim in headless mode.")
    target_version: str = Field(default="6.0.0", description="Target NVIDIA Isaac Sim release version.")
    timeout_seconds: float = Field(default=5.0, description="Network/socket communication timeout.")
    entity_mapping: IsaacEntityMapping = Field(
        default_factory=IsaacEntityMapping,
        description="USD stage prim mapping.",
    )


class PhysicalObservation(BaseModel):
    """Normalized physical telemetry snapshot emitted by a simulation backend."""
    backend_type: PhysicalBackendType = Field(default=PhysicalBackendType.MOCK_PHYSICAL_WORLD, description="Simulation backend producing this observation.")
    physical_backend: Optional[PhysicalBackendType] = Field(default=None, description="Alias for backend_type.")
    snapshot_id: str = Field(default="", description="Unique snapshot identifier.")
    simulation_time: float = Field(default=0.0, description="Elapsed simulation time in seconds.")
    sim_time: Optional[float] = Field(default=None, description="Alias for simulation_time.")
    step_count: int = Field(default=0, description="Total simulation physics steps advanced.")
    world_version: int = Field(default=3, description="Monotonic world state version.")
    world_state_version: Optional[int] = Field(default=None, description="Alias for world_version.")
    valve_b_state: str = Field(default="OPEN", description="State of Valve B ('OPEN', 'CLOSING', 'CLOSED').")
    valve_b_angle_deg: float = Field(default=0.0, description="Revolute joint angle (0.0=OPEN, 90.0=CLOSED).")
    pump_p1_state: str = Field(default="INACTIVE", description="State of Pump P1 ('ACTIVE', 'INACTIVE').")
    pump_p1_rpm: float = Field(default=0.0, description="Impeller angular velocity in RPM.")
    cooling_state: str = Field(default="ACTIVE", description="Cooling loop status ('ACTIVE', 'DEGRADED', 'DISABLED').")
    human_zone: str = Field(default="CLEAR", description="Safety zone status ('CLEAR', 'OCCUPIED').")
    human_zone_occupied: Optional[bool] = Field(default=None, description="Boolean occupancy indicator.")
    human_distance_m: float = Field(default=5.0, description="Distance from human to safety zone centroid in meters.")
    actuator_status: str = Field(default="READY", description="Hardware actuator status ('READY', 'ACTUATED', 'LOCKED', 'FAILED', 'VERIFIED').")
    actuator_gateway_locked: bool = Field(default=False, description="Whether safety enclave actuator gateway is locked.")
    pressure_psi: float = Field(default=95.5, description="Manifold line hydraulic pressure in PSI.")
    flow_rate_lpm: float = Field(default=14.0, description="Coolant manifold volumetric flow rate in L/min.")
    leak_active: bool = Field(default=True, description="Whether coolant line leak is active.")
    fault_active: bool = Field(default=False, description="Whether a physical hardware fault is injected.")
    active_fault_type: Optional[str] = Field(default=None, description="Active injected fault type.")
    isaac_prim_paths: Optional[Dict[str, str]] = Field(default=None, description="Mapped Isaac USD prim paths.")
    metadata: Dict[str, Any] = Field(default_factory=dict, description="Arbitrary adapter metadata.")

    @model_validator(mode="after")
    def sync_aliases(self) -> "PhysicalObservation":
        if self.physical_backend is not None and self.backend_type == PhysicalBackendType.MOCK_PHYSICAL_WORLD:
            self.backend_type = self.physical_backend
        elif self.physical_backend is None:
            self.physical_backend = self.backend_type

        if self.sim_time is not None and self.simulation_time == 0.0:
            self.simulation_time = self.sim_time
        elif self.sim_time is None:
            self.sim_time = self.simulation_time

        if self.world_state_version is not None and self.world_version == 3:
            self.world_version = self.world_state_version
        elif self.world_state_version is None:
            self.world_state_version = self.world_version

        if self.human_zone_occupied is not None:
            self.human_zone = "OCCUPIED" if self.human_zone_occupied else "CLEAR"
        else:
            self.human_zone_occupied = (self.human_zone == "OCCUPIED")

        if self.actuator_status == "LOCKED":
            self.actuator_gateway_locked = True
        return self


class PhysicalExecutionResult(BaseModel):
    """Result of an authorized actuation request executed against a physical simulator."""
    execution_id: str = Field(description="Unique execution transaction identifier.")
    backend: PhysicalBackendType = Field(default=PhysicalBackendType.MOCK_PHYSICAL_WORLD, description="Executing simulation backend.")
    success: bool = Field(default=False, description="Whether the actuation sequence completed successfully.")
    status: Any = Field(default="LOCKED", description="Final execution status.")
    action_type: str = Field(default="NONE", description="Commanded action type (e.g. 'CLOSE_VALVE').")
    action: Optional[str] = Field(default=None, description="Alias for action_type.")
    target: str = Field(default="valve_b", description="Commanded actuator target (e.g. 'valve_b').")
    initial_state: Dict[str, Any] = Field(default_factory=dict, description="Physical state before execution.")
    final_state: Dict[str, Any] = Field(default_factory=dict, description="Physical state after execution attempt.")
    ticket_id: Optional[str] = Field(default=None, description="Associated AuthorizationTicket ID.")
    ticket_status: Optional[str] = Field(default=None, description="Verification status of presented ticket.")
    signature_status: Optional[str] = Field(default=None, description="Cryptographic signature verification status.")
    revalidation_passed: bool = Field(default=True, description="Whether pre-execution revalidation passed.")
    is_actuated: bool = Field(default=False, description="Whether mechanical actuation occurred.")
    error_message: Optional[str] = Field(default=None, description="Error message if execution failed or locked.")
    steps_advanced: int = Field(default=0, description="Physics steps simulated during actuation.")
    simulation_elapsed_sec: float = Field(default=0.0, description="Simulated physics elapsed time in seconds.")
    fault_injected: Optional[Any] = Field(default=None, description="Fault injected during execution if any.")
    resulting_observation: Optional[PhysicalObservation] = Field(default=None, description="Observation snapshot after execution.")

    @model_validator(mode="after")
    def sync_result_fields(self) -> "PhysicalExecutionResult":
        if self.action is None:
            self.action = self.action_type
        elif self.action_type == "NONE":
            self.action_type = self.action
        return self
