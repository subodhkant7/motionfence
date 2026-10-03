"""Abstract protocol and base interface for physical simulation adapters.

SECURITY INVARIANT:
Consequential physical actuation strictly requires an authenticated AuthorizationTicket.
Raw ActionProposals have ZERO authority to actuate valves or mutate simulation state.
"""

from typing import Any, Dict, Optional, Protocol, runtime_checkable
from motionfence.models.actions import ActionProposal, AuthorizationTicket
from motionfence.simulation.adapters.models import (
    PhysicalBackendType,
    PhysicalObservation,
    PhysicalExecutionResult,
    AdapterStatus,
)


@runtime_checkable
class PhysicalExecutionAdapter(Protocol):
    """Abstract interface for physical simulation backends (Mock, Isaac Sim, etc.)."""

    def connect(self) -> bool:
        """Establish communication with the physical simulator backend."""
        ...

    def disconnect(self) -> None:
        """Gracefully terminate simulator connection."""
        ...

    def is_connected(self) -> bool:
        """Return True if connection to simulator is active."""
        ...

    def is_available(self) -> bool:
        """Return True if the underlying physical engine/runtime is installed and available."""
        ...

    def get_state(self) -> PhysicalObservation:
        """Query and return normalized physical telemetry from the simulator."""
        ...

    def execute_authorized_action(
        self,
        proposal: ActionProposal,
        ticket: Optional[AuthorizationTicket],
        *,
        correlation_id: Optional[str] = None,
    ) -> PhysicalExecutionResult:
        """Execute physical actuation strictly conditioned on a valid AuthorizationTicket.

        SECURITY INVARIANT:
        If ticket is None, expired, consumed, mismatched, or stale, the adapter
        MUST reject the request and return status 'LOCKED' without physical mutation.
        """
        ...

    def inject_fault(self, fault_type: str) -> None:
        """Configure deterministic hardware fault injection for failure simulation."""
        ...

    def clear_fault(self) -> None:
        """Reset fault injection mode to nominal physical operation."""
        ...

    def advance(self, steps: int = 1, dt: float = 0.05) -> PhysicalObservation:
        """Advance the physical simulation by a discrete number of physics steps."""
        ...

    def reset(self, initial_state: Optional[Dict[str, Any]] = None) -> PhysicalObservation:
        """Reset the physical simulation scene to nominal starting conditions."""
        ...

    def get_backend_name(self) -> PhysicalBackendType:
        """Return the physical backend type (e.g. MOCK_PHYSICAL_WORLD, ISAAC_SIM)."""
        ...

    def get_status(self) -> AdapterStatus:
        """Return current diagnostic status of the adapter."""
        ...

    def get_capabilities(self) -> Dict[str, Any]:
        """Return backend capabilities, limits, and runtime features."""
        ...
