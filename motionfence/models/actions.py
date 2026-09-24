"""Action proposals, execution authorization tickets, and actuator outcome models."""

from enum import Enum
from typing import Any, Dict, List, Optional
import time
import uuid
from pydantic import BaseModel, Field


class ActionClass(str, Enum):
    """Categorical boundary between information-gathering actions and consequential plant mutations."""
    INFORMATION_ACTION = "INFORMATION_ACTION"
    CONSEQUENTIAL_ACTION = "CONSEQUENTIAL_ACTION"


class ActionType(str, Enum):
    """Permissible action categories in the physical and perception environments."""
    # Consequential Actions (Require full Safety Enclave AuthorizationTicket)
    CLOSE_VALVE = "CLOSE_VALVE"
    OPEN_VALVE = "OPEN_VALVE"
    START_PUMP = "START_PUMP"
    STOP_PUMP = "STOP_PUMP"
    ADJUST_COOLING = "ADJUST_COOLING"
    EMERGENCY_STOP = "EMERGENCY_STOP"

    # Information Actions (Bounded, passive/perceptual, executed via EvidenceActionGateway)
    INSPECT = "INSPECT"
    GATHER_EVIDENCE = "GATHER_EVIDENCE"
    INSPECT_TARGET = "INSPECT_TARGET"
    RESAMPLE_SENSOR = "RESAMPLE_SENSOR"
    CHANGE_VIEWPOINT = "CHANGE_VIEWPOINT"
    READ_SENSOR = "READ_SENSOR"
    WAIT_FOR_STABLE_STATE = "WAIT_FOR_STABLE_STATE"
    QUERY_KNOWLEDGE = "QUERY_KNOWLEDGE"


_INFORMATION_ACTIONS = {
    ActionType.INSPECT,
    ActionType.GATHER_EVIDENCE,
    ActionType.INSPECT_TARGET,
    ActionType.RESAMPLE_SENSOR,
    ActionType.CHANGE_VIEWPOINT,
    ActionType.READ_SENSOR,
    ActionType.WAIT_FOR_STABLE_STATE,
    ActionType.QUERY_KNOWLEDGE,
}

_CONSEQUENTIAL_ACTIONS = {
    ActionType.CLOSE_VALVE,
    ActionType.OPEN_VALVE,
    ActionType.START_PUMP,
    ActionType.STOP_PUMP,
    ActionType.ADJUST_COOLING,
    ActionType.EMERGENCY_STOP,
}


def get_action_class(action: ActionType) -> ActionClass:
    """Deterministically determine whether an action is informational or consequential."""
    if action in _INFORMATION_ACTIONS:
        return ActionClass.INFORMATION_ACTION
    return ActionClass.CONSEQUENTIAL_ACTION


def is_information_action(action: ActionType) -> bool:
    """Return True if the action is bounded to information-gathering only."""
    return get_action_class(action) == ActionClass.INFORMATION_ACTION


def is_consequential_action(action: ActionType) -> bool:
    """Return True if the action can physically alter plant state and requires Enclave authorization."""
    return get_action_class(action) == ActionClass.CONSEQUENTIAL_ACTION


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
    """Cryptographically verifiable, state-bound runtime-minted authorization ticket.
    
    Only the MotionFence runtime core can mint this ticket after deterministic
    policy evaluation succeeds with an ALLOW decision.
    Actuators reject any action missing a valid, unconsumed ticket.

    Phase 2F: Tickets are bound to a deterministic authorization context.
    State-binding fields ensure that authorization cannot survive world-state
    drift, policy changes, constraint mutations, or evidence invalidation.
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
    # Phase 2F: State-binding fields for TOCTOU defense
    authorization_context_hash: str = Field(
        default="",
        description="SHA-256 hash of the full authorization context at issuance time."
    )
    world_state_version: int = Field(
        default=0,
        description="Monotonic world state version at authorization time."
    )
    world_state_hash: str = Field(
        default="",
        description="SHA-256 hash of canonical safety-relevant world state at authorization."
    )
    policy_version: str = Field(
        default="",
        description="Policy version string at authorization time."
    )
    constraint_set_hash: str = Field(
        default="",
        description="SHA-256 hash of canonical active constraint set at authorization."
    )
    evidence_context_hash: str = Field(
        default="",
        description="SHA-256 hash of canonical safety-relevant evidence at authorization."
    )
    nonce: str = Field(
        default_factory=lambda: uuid.uuid4().hex[:16],
        description="Single-use nonce preventing ticket replay across contexts."
    )


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
