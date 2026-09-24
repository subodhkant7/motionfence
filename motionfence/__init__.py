"""MotionFence: Deterministic Runtime Authorization Layer for AI-Generated Physical Actions.

An AI agent may propose what should happen, but a deterministic MotionFence runtime
independently decides whether the physical action is allowed, requires additional evidence,
or must be denied.
"""

__version__ = "0.2.1"
__author__ = "Subodh Kant"

from motionfence.runtime.core import MotionFenceRuntime, RuntimeCycleResult
from motionfence.policy.engine import PolicyEngine
from motionfence.policy.models import Policy, PolicyDecision, DecisionType
from motionfence.models.actions import ActionProposal, ActionType, AuthorizationTicket
from motionfence.models.world import WorldState, ValveState, CoolingState, HumanZoneState
from motionfence.evidence.models import Evidence, EvidenceSource, ContradictionReport
from motionfence.simulation.world import PhysicalWorld
from motionfence.knowledge.models import KnowledgeEvidence, TrustStatus, FreshnessStatus
from motionfence.knowledge.trust import (
    SourceCategory,
    AuthorityLevel,
    EvidenceRole,
    CorroborationStatus,
    SourceTrustAssessment,
    SourceTrustClassifier,
    CorroborationEngine,
)
from motionfence.knowledge.provider import KnowledgeProvider, KnowledgeProviderError, TavilyProviderError
from motionfence.knowledge.local_provider import LocalKnowledgeProvider
from motionfence.knowledge.tavily_provider import TavilyKnowledgeProvider
from motionfence.knowledge.retrieval import KnowledgeRetrievalService
from motionfence.constraints.models import (
    CandidateConstraint,
    ConstraintType,
    ConstraintStatus,
    ConstraintConflictReport,
    Applicability,
    PlantContext,
    ConflictCategory,
)
from motionfence.constraints.validator import ConstraintValidator
from motionfence.constraints.local_extractor import LocalConstraintExtractor
from motionfence.constraints.nemotron_extractor import NemotronConstraintExtractor
from motionfence.constraints.conflict import ConstraintConflictDetector

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
    "KnowledgeEvidence",
    "TrustStatus",
    "FreshnessStatus",
    "SourceCategory",
    "AuthorityLevel",
    "EvidenceRole",
    "CorroborationStatus",
    "SourceTrustAssessment",
    "SourceTrustClassifier",
    "CorroborationEngine",
    "KnowledgeProvider",
    "KnowledgeProviderError",
    "TavilyProviderError",
    "LocalKnowledgeProvider",
    "TavilyKnowledgeProvider",
    "KnowledgeRetrievalService",
    "CandidateConstraint",
    "ConstraintType",
    "ConstraintStatus",
    "ConstraintConflictReport",
    "Applicability",
    "PlantContext",
    "ConflictCategory",
    "ConstraintValidator",
    "LocalConstraintExtractor",
    "NemotronConstraintExtractor",
    "ConstraintConflictDetector",
]

