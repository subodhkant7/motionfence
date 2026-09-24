"""MotionFence: Deterministic Runtime Authorization Layer for AI-Generated Physical Actions.

An AI agent may propose what should happen, but a deterministic MotionFence runtime
independently decides whether the physical action is allowed, requires additional evidence,
or must be denied.
"""

__version__ = "0.1.0"
__author__ = "Subodh Kant"

from motionfence.runtime.core import MotionFenceRuntime, RuntimeCycleResult
from motionfence.policy.engine import PolicyEngine
from motionfence.policy.models import Policy, PolicyDecision, DecisionType
from motionfence.models.actions import ActionProposal, ActionType, AuthorizationTicket
from motionfence.models.world import WorldState, ValveState, CoolingState, HumanZoneState
from motionfence.evidence.models import Evidence, EvidenceSource, ContradictionReport
from motionfence.simulation.world import PhysicalWorld

__all__ = [
    "MotionFenceRuntime",
    "RuntimeCycleResult",
    "PolicyEngine",
    "Policy",
    "PolicyDecision",
    "DecisionType",
    "ActionProposal",
    "ActionType",
    "AuthorizationTicket",
    "WorldState",
    "ValveState",
    "CoolingState",
    "HumanZoneState",
    "Evidence",
    "EvidenceSource",
    "ContradictionReport",
    "PhysicalWorld",
]
