"""Physical world state and observation models for MotionFence."""

from enum import Enum
from typing import Any, Dict, Optional
import time
from pydantic import BaseModel, Field


class ValveState(str, Enum):
    """Discrete state of a physical valve."""
    OPEN = "OPEN"
    CLOSED = "CLOSED"
    JAMMED = "JAMMED"
    TRANSITIONING = "TRANSITIONING"


class CoolingState(str, Enum):
    """Operational status of the cooling system."""
    ACTIVE = "ACTIVE"
    INACTIVE = "INACTIVE"
    DEGRADED = "DEGRADED"


class HumanZoneState(str, Enum):
    """Presence detection in human safety exclusion zones."""
    CLEAR = "CLEAR"
    OCCUPIED = "OCCUPIED"
    WARNING = "WARNING"


class LeakState(BaseModel):
    """Status of fluid/gas leaks in the physical environment."""
    active: bool = Field(default=False, description="Whether a leak is currently active.")
    target: Optional[str] = Field(default=None, description="Physical entity or line associated with the leak.")
    severity: float = Field(default=0.0, ge=0.0, le=1.0, description="Severity score of the leak from 0.0 to 1.0.")
    flow_rate_lpm: float = Field(default=0.0, ge=0.0, description="Estimated flow rate in liters per minute.")


class SensorObservation(BaseModel):
    """Individual sensor reading recorded in the physical environment."""
    sensor_id: str
    sensor_type: str
    target: Optional[str] = None
    reading: Any
    confidence: float = Field(default=1.0, ge=0.0, le=1.0)
    timestamp: float = Field(default_factory=time.time)
    metadata: Dict[str, Any] = Field(default_factory=dict)


class WorldState(BaseModel):
    """Comprehensive snapshot of the physical environment state."""
    valves: Dict[str, ValveState] = Field(
        default_factory=lambda: {"valve_a": ValveState.OPEN, "valve_b": ValveState.OPEN}
    )
    cooling: CoolingState = Field(default=CoolingState.ACTIVE)
    leak: LeakState = Field(default_factory=LeakState)
    human_zone: HumanZoneState = Field(default=HumanZoneState.CLEAR)
    pumps: Dict[str, str] = Field(
        default_factory=lambda: {"pump_p1": "ACTIVE"},
        description="Operational status of auxiliary industrial pumps (e.g. pump_p1: ACTIVE)."
    )
    observations: Dict[str, SensorObservation] = Field(default_factory=dict)
    version: int = Field(default=1, description="Monotonically increasing state version number.")
    timestamp: float = Field(default_factory=time.time)

    def is_human_present(self) -> bool:
        """Helper to check if any human is in the exclusion safety zone."""
        return self.human_zone != HumanZoneState.CLEAR

    def is_cooling_active(self) -> bool:
        """Helper to verify if cooling is currently active."""
        return self.cooling == CoolingState.ACTIVE
