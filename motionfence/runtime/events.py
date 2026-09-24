"""Structured event streaming and auditable telemetry for the MotionFence runtime."""

import logging
from typing import Any, Callable, Dict, List, Optional
import time

from motionfence.models.events import EventType, RuntimeEvent

logger = logging.getLogger("motionfence.runtime")


class EventBus:
    """In-memory event bus and structured audit log for runtime state transitions."""

    def __init__(self) -> None:
        self._events: List[RuntimeEvent] = []
        self._subscribers: List[Callable[[RuntimeEvent], None]] = []

    def subscribe(self, handler: Callable[[RuntimeEvent], None]) -> None:
        """Register a callback for runtime events."""
        self._subscribers.append(handler)

    def emit(self, event_type: EventType, message: str, payload: Optional[Dict[str, Any]] = None) -> RuntimeEvent:
        """Create, store, and publish a structured runtime event."""
        event = RuntimeEvent(
            event_type=event_type,
            message=message,
            payload=payload or {},
            timestamp=time.time(),
        )
        self._events.append(event)

        # Standard structured logging
        log_msg = f"[{event.event_type.value}] {event.message}"
        if event_type in (EventType.ACTION_DENIED, EventType.POSTCONDITION_FAILED):
            logger.warning(log_msg)
        elif event_type in (EventType.ACTION_AUTHORIZED, EventType.POSTCONDITION_VERIFIED):
            logger.info(log_msg)
        else:
            logger.debug(log_msg)

        # Dispatch to subscribers
        for sub in self._subscribers:
            try:
                sub(event)
            except Exception as e:
                logger.error(f"Error in event subscriber {sub}: {e}")

        return event

    def get_events(self, event_type: Optional[EventType] = None) -> List[RuntimeEvent]:
        """Return recorded events, optionally filtered by event type."""
        if event_type is None:
            return list(self._events)
        return [e for e in self._events if e.event_type == event_type]

    def clear(self) -> None:
        """Clear recorded events."""
        self._events.clear()
