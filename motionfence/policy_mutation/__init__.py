"""Policy Mutation Firewall, Compound Mutations, Dynamic Trajectories & Safe Repairs (Phase 2J/2K).

CRITICAL INVARIANTS:
1. Mutations operate exclusively on detached policy clones.
2. ZERO ticket minting and ZERO actuator authority.
3. INCONCLUSIVE decisions conservatively default to REJECT for safety-critical changes.
4. Deterministic and completely offline by default.
5. Safe repair proposals are strictly non-authoritative and evaluated through detached validation.
"""

from motionfence.policy_mutation.models import (
    CompoundPolicyMutation,
    DynamicTrajectory,
    FirewallEvaluationReport,
    MutationCounterexample,
    MutationEvaluationResult,
    MutationInteractionType,
    MutationRelevance,
    PolicyBaseline,
    PolicyFirewallDecision,
    PolicyMutation,
    PolicyMutationType,
    PolicyRegressionType,
    PolicyRepairProposal,
    TrajectoryEvaluationResult,
    TrajectoryOutcomeType,
    TrajectoryStep,
)
from motionfence.policy_mutation.mutators import (
    PolicyMutatorRegistry,
    compute_canonical_policy_hash,
    create_compound_mutation,
    shrink_compound_mutation,
)
from motionfence.policy_mutation.minimizer import MutationCounterexampleMinimizer
from motionfence.policy_mutation.baseline import PolicyBaselineManager
from motionfence.policy_mutation.evaluator import PolicyMutationEvaluator
from motionfence.policy_mutation.engine import PolicyMutationEngine
from motionfence.policy_mutation.reporting import PolicyDiffExplainer
from motionfence.policy_mutation.trajectory import (
    DynamicTrajectoryEvaluator,
    TrajectoryFaultType,
    TrajectoryGenerator,
    shrink_trajectory,
)
from motionfence.policy_mutation.repair import (
    PolicyRepairSynthesizer,
    PolicyRepairValidator,
    RepairStatus,
    RepairValidationResult,
    SafetyMonotonicityReport,
)

__all__ = [
    "CompoundPolicyMutation",
    "DynamicTrajectory",
    "DynamicTrajectoryEvaluator",
    "FirewallEvaluationReport",
    "MutationCounterexample",
    "MutationCounterexampleMinimizer",
    "MutationEvaluationResult",
    "MutationInteractionType",
    "MutationRelevance",
    "PolicyBaseline",
    "PolicyBaselineManager",
    "PolicyDiffExplainer",
    "PolicyFirewallDecision",
    "PolicyMutation",
    "PolicyMutationEngine",
    "PolicyMutationEvaluator",
    "PolicyMutationType",
    "PolicyMutatorRegistry",
    "PolicyRegressionType",
    "PolicyRepairProposal",
    "PolicyRepairSynthesizer",
    "PolicyRepairValidator",
    "RepairStatus",
    "RepairValidationResult",
    "SafetyMonotonicityReport",
    "TrajectoryEvaluationResult",
    "TrajectoryFaultType",
    "TrajectoryGenerator",
    "TrajectoryOutcomeType",
    "TrajectoryStep",
    "compute_canonical_policy_hash",
    "create_compound_mutation",
    "shrink_compound_mutation",
    "shrink_trajectory",
]
