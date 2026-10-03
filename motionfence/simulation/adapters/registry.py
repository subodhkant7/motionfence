"""Factory and registry for physical execution simulation adapters.

Provides clean selection between Mock Hardware and NVIDIA Isaac Sim backends.
"""

from typing import Optional, Union, Dict, Any
from motionfence.simulation.adapters.models import (
    PhysicalBackendType,
    AdapterStatus,
    PhysicalObservation,
    PhysicalExecutionResult,
    IsaacSimConfig,
)
from motionfence.simulation.adapters.base import PhysicalExecutionAdapter
from motionfence.models.actions import ActionProposal, AuthorizationTicket
from motionfence.hardware.models import HardwareExecutionStatus, HardwareFaultType


class ReplayPhysicalAdapter:
    """Side-effect-free replay adapter for recorded physical simulation traces.
    
    SECURITY INVARIANT:
    Replay represents past historical execution records. It cannot command
    live actuators or running simulation instances.
    """
    
    def __init__(self, trace_file: Optional[str] = None):
        self.trace_file = trace_file
        self.backend_type = PhysicalBackendType.OFFLINE_REPLAY
        self.status = AdapterStatus.READY
        self._step = 0
        self._sim_time = 0.0
        self._world_version = 1
        self._valve_b_state = "OPEN"
        self._pump_p1_state = "INACTIVE"
        self._human_zone_occupied = False
        
    def connect(self) -> bool:
        self.status = AdapterStatus.CONNECTED
        return True
        
    def disconnect(self) -> None:
        self.status = AdapterStatus.DISCONNECTED
        
    def is_available(self) -> bool:
        return True
        
    def get_observation(self) -> PhysicalObservation:
        return PhysicalObservation(
            snapshot_id=f"snap_replay_{self._step:04d}",
            sim_time=self._sim_time,
            world_state_version=self._world_version,
            valve_b_state=self._valve_b_state,
            pump_p1_state=self._pump_p1_state,
            human_zone_occupied=self._human_zone_occupied,
            actuator_gateway_locked=False,
            physical_backend=PhysicalBackendType.OFFLINE_REPLAY,
        )
        
    def execute_authorized_action(
        self,
        proposal: ActionProposal,
        ticket: Optional[AuthorizationTicket],
    ) -> PhysicalExecutionResult:
        # Replay is strictly read-only and historical
        return PhysicalExecutionResult(
            execution_id="exec_replay_read_only",
            status=HardwareExecutionStatus.LOCKED,
            is_actuated=False,
            ticket_status="REPLAY_MODE_READ_ONLY",
            signature_status="SKIPPED",
            target=proposal.target,
            action=proposal.action_type.value,
            resulting_observation=self.get_observation(),
            error_message="ReplayPhysicalAdapter is strictly read-only and cannot execute commands.",
        )
        
    def advance(self, steps: int = 1) -> PhysicalObservation:
        self._step += steps
        self._sim_time += steps * 0.01667
        return self.get_observation()
        
    def reset(self) -> PhysicalObservation:
        self._step = 0
        self._sim_time = 0.0
        self._world_version = 1
        self._valve_b_state = "OPEN"
        self._pump_p1_state = "INACTIVE"
        self._human_zone_occupied = False
        return self.get_observation()
        
    def inject_fault(self, fault: HardwareFaultType) -> None:
        pass
        
    def clear_fault(self) -> None:
        pass


def detect_preferred_backend() -> PhysicalBackendType:
    """Dynamically detect host environment capabilities and return preferred backend."""
    from motionfence.simulation.isaac.environment import detect_isaac_environment
    report = detect_isaac_environment()
    if report.meets_hardware_requirements and report.is_available:
        return PhysicalBackendType.ISAAC_SIM
    return PhysicalBackendType.MOCK_PHYSICAL_WORLD


def get_physical_adapter(
    backend: Union[PhysicalBackendType, str] = PhysicalBackendType.MOCK_PHYSICAL_WORLD,
    *,
    isaac_config: Optional[IsaacSimConfig] = None,
    secret_key: str = "motionfence_runtime_kernel_secret",
) -> PhysicalExecutionAdapter:
    """Instantiate and return the configured physical execution simulation adapter.
    
    Args:
        backend: Backend selection ('mock', 'isaac', or 'replay').
        isaac_config: Optional Isaac Sim configuration.
        secret_key: HMAC secret key used by runtime safety enclave.
        
    Returns:
        Instance conforming to PhysicalExecutionAdapter.
    """
    backend_str = backend.value if isinstance(backend, PhysicalBackendType) else str(backend).lower()

    if backend_str in {"isaac", "isaac_sim", "isaacsim"}:
        from motionfence.simulation.isaac.adapter import IsaacSimAdapter
        adapter = IsaacSimAdapter(config=isaac_config, secret_key=secret_key)
        adapter.connect()
        return adapter
    elif backend_str in {"mock", "mock_hardware", "mock_physical_world"}:
        from motionfence.simulation.adapters.mock_adapter import MockHardwareAdapter
        adapter = MockHardwareAdapter(secret_key=secret_key)
        adapter.connect()
        return adapter
    elif backend_str in {"replay", "offline_replay"}:
        adapter = ReplayPhysicalAdapter()
        adapter.connect()
        return adapter
    else:
        raise ValueError(
            f"Unsupported physical simulation backend '{backend}'. "
            f"Supported backends: 'mock' (MockHardwareAdapter), 'isaac' (IsaacSimAdapter), 'replay' (ReplayPhysicalAdapter)."
        )


class _LazyAdapterRegistry(dict):
    """Lazy resolver for adapter classes to avoid circular imports."""
    def __getitem__(self, key: str) -> Any:
        k = key.lower()
        if k in {"mock", "mock_hardware", "mock_physical_world"}:
            from motionfence.simulation.adapters.mock_adapter import MockHardwareAdapter
            return MockHardwareAdapter
        elif k in {"isaac", "isaac_sim", "isaacsim"}:
            from motionfence.simulation.isaac.adapter import IsaacSimAdapter
            return IsaacSimAdapter
        elif k in {"replay", "offline_replay"}:
            return ReplayPhysicalAdapter
        raise KeyError(key)

    def __contains__(self, key: object) -> bool:
        if not isinstance(key, str):
            return False
        return key.lower() in {"mock", "mock_hardware", "mock_physical_world", "isaac", "isaac_sim", "isaacsim", "replay", "offline_replay"}


ADAPTER_REGISTRY: Dict[str, Any] = _LazyAdapterRegistry()
