"""MotionFence hardware boundary package.

Exposes mock physical hardware endpoints, ticket validation, and structured hardware events.
"""

from motionfence.hardware.models import (
    ActuatorType,
    HardwareExecutionRecord,
    HardwareExecutionStatus,
    HardwareFaultType,
    HardwareStatus,
    HardwareTicketValidationResult,
)
from motionfence.hardware.interface import HardwareEndpoint
from motionfence.hardware.validation import HardwareTicketValidator
from motionfence.hardware.mock import MockHardwareEndpoint
from motionfence.hardware.events import (
    EVENT_HARDWARE_TICKET_RECEIVED,
    EVENT_HARDWARE_TICKET_VALIDATED,
    EVENT_HARDWARE_TICKET_REJECTED,
    EVENT_HARDWARE_ACTUATION_STARTED,
    EVENT_HARDWARE_ACTUATION_COMPLETED,
    EVENT_HARDWARE_ACTUATION_BLOCKED,
    EVENT_HARDWARE_FAULT_INJECTED,
    EVENT_HARDWARE_OBSERVATION_RECORDED,
    EVENT_HARDWARE_REPLAY_REJECTED,
    make_hardware_event,
)

__all__ = [
    "ActuatorType",
    "HardwareExecutionRecord",
    "HardwareExecutionStatus",
    "HardwareFaultType",
    "HardwareStatus",
    "HardwareTicketValidationResult",
    "HardwareEndpoint",
    "HardwareTicketValidator",
    "MockHardwareEndpoint",
    "EVENT_HARDWARE_TICKET_RECEIVED",
    "EVENT_HARDWARE_TICKET_VALIDATED",
    "EVENT_HARDWARE_TICKET_REJECTED",
    "EVENT_HARDWARE_ACTUATION_STARTED",
    "EVENT_HARDWARE_ACTUATION_COMPLETED",
    "EVENT_HARDWARE_ACTUATION_BLOCKED",
    "EVENT_HARDWARE_FAULT_INJECTED",
    "EVENT_HARDWARE_OBSERVATION_RECORDED",
    "EVENT_HARDWARE_REPLAY_REJECTED",
    "make_hardware_event",
]
