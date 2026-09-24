"""Action proposals, execution authorization tickets, and actuator outcome models."""

from enum import Enum
from typing import Any, Dict, List, Optional
import time
import uuid
from pydantic import BaseModel, Field


class ActionType(str, Enum):
    """Permissible action categories in the physical environment."""
    INSPECT = "INSPECT"
    GATHER_EVIDENCE = "GATHER_EVIDENCE"
    CLOSE_VALVE = "CLOSE_VALVE"
    OPEN_VALVE = "OPEN_VALVE"
    ADJUST_COOLING = "ADJUST_COOLING"
    EMERGENCY_STOP = "EMERGENCY_STOP"


class ActionProposal(BaseModel):
    """An AI-agent generated proposal for a physical action.
    
    IMPORTANT: An ActionProposal possesses ZERO execution authority.
    It cannot mutate world state without an approved AuthorizationTicket.
    """
    id: str = Field(default_factory=lambda: f"prop_{uuid.uuid4().hex[:8]}")
    action_type: ActionType = Field(..., description="Proposed action type.")
    target: str = Field(..., description="Target actuator or subsystem (e.g., 'valve_b').")
    parameters: Dict[str, Any] = Field(default_factory=dict, description="Action-specific parameters.")
    rationale: str = Field(..., description="Explanation or reasoning for the proposed action.")
    model_confidence: float = Field(..., ge=0.0, le=1.0, description="Confidence score from proposal generator.")
    supporting_evidence_ids: List[str] = Field(
        default_factory=list,
        description="IDs of evidence objects supporting this proposal."
    )
    timestamp: float = Field(default_factory=time.time)


class AuthorizationTicket(BaseModel):
    """Cryptographically verifiable or runtime-minted authorization ticket.
    
    Only the MotionFence runtime core can mint this ticket after deterministic
    policy evaluation succeeds with an ALLOW decision.
    Actuators reject any action missing a valid, unconsumed ticket.
    """
    ticket_id: str = Field(default_factory=lambda: f"tkt_{uuid.uuid4().hex[:12]}")
    proposal_id: str = Field(..., description="ID of the authorized ActionProposal.")
    action_type: ActionType = Field(..., description="Specifically authorized action type.")
    target: str = Field(..., description="Specifically authorized target.")
    issued_at: float = Field(default_factory=time.time)
    expires_at: float = Field(..., description="Timestamp after which this ticket is invalid.")
    authorized_by: str = Field(default="MotionFence.PolicyEngine.DeterministicEvaluator")
    signature: str = Field(..., description="Deterministic authorization signature token.")
    consumed: bool = Field(default=False, description="Prevents replay attacks or double-actuation.")


class ExecutionResult(BaseModel):
    """Outcome report from actuator execution attempt."""
    success: bool = Field(..., description="Whether the actuator command physically completed.")
    action_id: str = Field(..., description="Associated proposal ID.")
    ticket_id: Optional[str] = Field(default=None, description="Ticket ID used for execution.")
    executed_action: ActionType
    target: str
    message: str = Field(default="")
    state_version_before: int
    state_version_after: int
    timestamp: float = Field(default_factory=time.time)
