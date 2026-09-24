"""Domain models for mock physical hardware endpoints and actuator security boundaries.

SECURITY INVARIANTS:
1. Mock hardware possesses ZERO safety authority and ZERO ticket-minting authority.
2. Direct actuation without a valid MotionFence AuthorizationTicket is locked.
3. Cryptographic secrets and signing keys are never exposed in hardware models or logs.
"""

from enum import Enum
from typing import Any, Dict, List, Optional
import time
import uuid
from pydantic import BaseModel, Field

from motionfence.models.actions import ActionType


class ActuatorType(str, Enum):
    """Classification of industrial physical actuators."""
    VALVE_ACTUATOR = "VALVE_ACTUATOR"
    PUMP_CONTROLLER = "PUMP_CONTROLLER"
    SOLENOID = "SOLENOID"
    RELAY = "RELAY"


class HardwareExecutionStatus(str, Enum):
    """Terminal and operational execution states of the hardware endpoint."""
    WAITING = "WAITING"
    ACTUATED = "ACTUATED"
    LOCKED = "LOCKED"
    INVALID_TICKET = "INVALID_TICKET"
    EXPIRED_TICKET = "EXPIRED_TICKET"
    TARGET_MISMATCH = "TARGET_MISMATCH"
    ACTION_MISMATCH = "ACTION_MISMATCH"
    REPLAYED_TICKET = "REPLAYED_TICKET"
    HARDWARE_FAULT = "HARDWARE_FAULT"
    VERIFICATION_FAILED = "VERIFICATION_FAILED"


class HardwareFaultType(str, Enum):
    """Deterministic hardware fault injection modes for resilience testing."""
    NONE = "NONE"
    NO_OP = "NO_OP"                       # Command accepted, but mechanical actuator does not move
    PARTIAL_ACTUATION = "PARTIAL_ACTUATION"  # Valve strokes partially (e.g. 50%), leak persists
    DELAYED_ACTUATION = "DELAYED_ACTUATION"  # Actuation completes outside acceptable time window
    WRONG_FINAL_STATE = "WRONG_FINAL_STATE"  # Actuator moves to inverted/incorrect physical position


class HardwareTicketValidationResult(BaseModel):
    """Detailed result of hardware-boundary ticket verification."""
    is_valid: bool = Field(..., description="Whether the ticket passed all hardware-boundary checks.")
    status: HardwareExecutionStatus = Field(..., description="Validation outcome state.")
    signature_valid: bool = Field(default=False, description="Cryptographic signature verification status.")
    expiry_valid: bool = Field(default=False, description="Expiration time check status.")
    target_valid: bool = Field(default=False, description="Target entity binding check status.")
    action_valid: bool = Field(default=False, description="Action type binding check status.")
    single_use_valid: bool = Field(default=False, description="Anti-replay consumption check status.")
    context_valid: bool = Field(default=False, description="State-bound authorization context check status.")
    reasons: List[str] = Field(default_factory=list, description="Descriptive validation or rejection reasons.")
    timestamp: float = Field(default_factory=time.time)


class HardwareExecutionRecord(BaseModel):
    """Immutable audit record produced by the mock hardware endpoint upon actuation attempt.

    Contains all minimum fields required by Phase 2M specification with zero exposed secrets.
    """
    record_id: str = Field(default_factory=lambda: f"hwr_{uuid.uuid4().hex[:12]}")
    hardware_id: str = Field(..., description="Identifier of the physical hardware unit.")
    actuator_type: ActuatorType = Field(default=ActuatorType.VALVE_ACTUATOR, description="Actuator classification.")
    target: str = Field(..., description="Target equipment being actuated.")
    requested_action: str = Field(..., description="Action requested from the hardware.")
    ticket_id: Optional[str] = Field(default=None, description="ID of presented AuthorizationTicket, if any.")
    ticket_status: str = Field(..., description="Presented ticket status (VALID, INVALID, EXPIRED, NONE, etc.).")
    signature_status: str = Field(..., description="Cryptographic signature status (VALID, INVALID, UNVERIFIED).")
    execution_status: HardwareExecutionStatus = Field(..., description="Terminal execution status.")
    observed_state: Dict[str, Any] = Field(default_factory=dict, description="Sensory/telemetry state observed after actuation.")
    correlation_id: str = Field(default_factory=lambda: f"corr_{uuid.uuid4().hex[:10]}", description="Tracing correlation ID.")
    timestamp: float = Field(default_factory=time.time)
    fault_injected: HardwareFaultType = Field(default=HardwareFaultType.NONE, description="Fault injected during execution, if any.")
    message: str = Field(default="", description="Descriptive status message.")
    execution_latency_ms: float = Field(default=0.0, description="Measured execution latency in milliseconds.")

    @property
    def is_actuated(self) -> bool:
        """True if physical actuation successfully executed."""
        return self.execution_status == HardwareExecutionStatus.ACTUATED


class HardwareStatus(BaseModel):
    """Diagnostic status snapshot of the physical hardware endpoint."""
    hardware_id: str
    actuator_type: ActuatorType
    is_locked: bool
    current_target: str
    last_status: HardwareExecutionStatus
    consumed_ticket_count: int = 0
    active_fault: HardwareFaultType = HardwareFaultType.NONE
    uptime_seconds: float = 0.0
