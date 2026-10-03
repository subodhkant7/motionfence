"""Physical simulation execution adapters package for MotionFence.

Supports interchangeable physical backends:
- MockHardwareAdapter (deterministic software simulation)
- IsaacSimAdapter (NVIDIA Isaac Sim standalone USD physical engine)
"""

from motionfence.simulation.adapters.models import (
    PhysicalBackendType,
    AdapterStatus,
    PhysicalObservation,
    PhysicalExecutionResult,
    IsaacSimConfig,
    IsaacEntityMapping,
)
from motionfence.simulation.adapters.base import PhysicalExecutionAdapter
from motionfence.simulation.adapters.mock_adapter import MockHardwareAdapter
from motionfence.simulation.adapters.registry import (
    get_physical_adapter,
    detect_preferred_backend,
    ADAPTER_REGISTRY,
    ReplayPhysicalAdapter,
)

__all__ = [
    "PhysicalBackendType",
    "AdapterStatus",
    "PhysicalObservation",
    "PhysicalExecutionResult",
    "IsaacSimConfig",
    "IsaacEntityMapping",
    "PhysicalExecutionAdapter",
    "MockHardwareAdapter",
    "ReplayPhysicalAdapter",
    "get_physical_adapter",
    "detect_preferred_backend",
    "ADAPTER_REGISTRY",
]
