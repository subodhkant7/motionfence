"""Structured hardware event definitions for actuator boundary auditability.

SECURITY INVARIANTS:
1. Hardware events capture full operational context without exposing raw secrets.
2. Events cleanly track ticket acceptance, validation, rejection, actuation, and faults.
"""

from typing import Any, Dict, Optional
from motionfence.models.events import EventType, RuntimeEvent
from motionfence.hardware.models import (
    HardwareExecutionRecord,
    HardwareExecutionStatus,
    HardwareFaultType,
)


# Standard Event Types for Hardware Boundary
EVENT_HARDWARE_TICKET_RECEIVED = EventType.HARDWARE_TICKET_RECEIVED
EVENT_HARDWARE_TICKET_VALIDATED = EventType.HARDWARE_TICKET_VALIDATED
EVENT_HARDWARE_TICKET_REJECTED = EventType.HARDWARE_TICKET_REJECTED
EVENT_HARDWARE_ACTUATION_STARTED = EventType.HARDWARE_ACTUATION_STARTED
EVENT_HARDWARE_ACTUATION_COMPLETED = EventType.HARDWARE_ACTUATION_COMPLETED
EVENT_HARDWARE_ACTUATION_BLOCKED = EventType.HARDWARE_ACTUATION_BLOCKED
EVENT_HARDWARE_FAULT_INJECTED = EventType.HARDWARE_FAULT_INJECTED
EVENT_HARDWARE_OBSERVATION_RECORDED = EventType.HARDWARE_OBSERVATION_RECORDED
EVENT_HARDWARE_REPLAY_REJECTED = EventType.HARDWARE_REPLAY_REJECTED


def make_hardware_event(
    event_type: EventType,
    message: str,
    payload: Optional[Dict[str, Any]] = None,
) -> RuntimeEvent:
    """Construct an immutable RuntimeEvent for hardware audit logs."""
    return RuntimeEvent(
        event_type=event_type,
        message=message,
        payload=payload or {},
    )
