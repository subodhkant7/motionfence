"""Structured runtime event models for deterministic auditability and observability."""

from enum import Enum
from typing import Any, Dict
import time
import uuid
from pydantic import BaseModel, Field


class EventType(str, Enum):
    """Enumeration of standard lifecycle events in the MotionFence control loop."""
    INTENT_RECEIVED = "INTENT_RECEIVED"
    OBSERVATION_RECORDED = "OBSERVATION_RECORDED"
    ACTION_PROPOSED = "ACTION_PROPOSED"
    POLICY_EVALUATED = "POLICY_EVALUATED"
    ACTION_DENIED = "ACTION_DENIED"
    MORE_EVIDENCE_REQUIRED = "MORE_EVIDENCE_REQUIRED"
    ACTION_AUTHORIZED = "ACTION_AUTHORIZED"
    ACTION_EXECUTED = "ACTION_EXECUTED"
    POSTCONDITION_VERIFIED = "POSTCONDITION_VERIFIED"
    POSTCONDITION_FAILED = "POSTCONDITION_FAILED"


class RuntimeEvent(BaseModel):
    """Immutable structured log event capturing every step of the authorization loop."""
    event_id: str = Field(default_factory=lambda: f"evt_{uuid.uuid4().hex[:10]}")
    event_type: EventType = Field(..., description="Classification of the runtime event.")
    timestamp: float = Field(default_factory=time.time)
    message: str = Field(..., description="Human-readable event summary.")
    payload: Dict[str, Any] = Field(default_factory=dict, description="Machine-readable structured context.")
