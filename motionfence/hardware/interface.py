"""Hardware endpoint contract and interface specifications.

SECURITY INVARIANTS:
1. Physical mutation requires explicit presentation of a valid AuthorizationTicket.
2. The endpoint interface enforces that raw proposals cannot directly command actuators.
"""

from typing import Any, Dict, Optional, Protocol, runtime_checkable
from motionfence.models.actions import ActionProposal, AuthorizationTicket
from motionfence.hardware.models import (
    ActuatorType,
    HardwareExecutionRecord,
    HardwareFaultType,
    HardwareStatus,
)


@runtime_checkable
class HardwareEndpoint(Protocol):
    """Protocol defining the observable physical hardware actuator interface."""

    @property
    def hardware_id(self) -> str:
        """Unique identifier of this hardware actuator unit."""
        ...

    @property
    def actuator_type(self) -> ActuatorType:
        """Physical classification of this actuator."""
        ...

    def receive_and_actuate(
        self,
        proposal: ActionProposal,
        ticket: Optional[AuthorizationTicket],
        *,
        correlation_id: Optional[str] = None,
    ) -> HardwareExecutionRecord:
        """Receive an action proposal accompanied by an AuthorizationTicket, validate, and execute.

        If the ticket is missing, invalid, expired, replayed, mismatched, or stale,
        the actuator transitions to LOCKED and returns a rejected record without mutating state.
        """
        ...

    def get_observed_state(self, target: Optional[str] = None) -> Dict[str, Any]:
        """Read sensory telemetry from the hardware/physical plant."""
        ...

    def get_status(self) -> HardwareStatus:
        """Return diagnostic status of the hardware endpoint."""
        ...

    def inject_fault(self, fault: HardwareFaultType) -> None:
        """Configure deterministic mock hardware fault for failure simulation."""
        ...

    def clear_fault(self) -> None:
        """Reset fault injection mode to nominal operation."""
        ...
