"""Data models for Policy Mutation Firewall, Safety Regression Detection, and Baselines (Phase 2J).

CRITICAL INVARIANTS:
1. All mutation analysis operates strictly on detached policy clones.
2. The mutation engine possesses ZERO ticket minting or physical actuation authority.
3. INCONCLUSIVE decisions conservatively default to REJECT for safety-critical changes.
"""

from enum import Enum
from typing import Any, Dict, List, Optional
import time
import uuid
from pydantic import BaseModel, Field

from motionfence.policy.models import DecisionType, PolicyDecision


class PolicyMutationType(str, Enum):
    """Categorical classification of policy mutations."""
    THRESHOLD_WEAKENING = "THRESHOLD_WEAKENING"
    CONDITION_REMOVAL = "CONDITION_REMOVAL"
    CONDITION_INVERSION = "CONDITION_INVERSION"
    RULE_DELETION = "RULE_DELETION"
    REQUIREMENT_WEAKENING = "REQUIREMENT_WEAKENING"
    SCOPE_EXPANSION = "SCOPE_EXPANSION"
    FRESHNESS_WEAKENING = "FRESHNESS_WEAKENING"
    CONTRADICTION_WEAKENING = "CONTRADICTION_WEAKENING"
    EVIDENCE_REQUIREMENT_REMOVAL = "EVIDENCE_REQUIREMENT_REMOVAL"
    AUTHORIZATION_BOUNDARY_MUTATION = "AUTHORIZATION_BOUNDARY_MUTATION"
    NON_SAFETY_MUTATION = "NON_SAFETY_MUTATION"


class PolicyRegressionType(str, Enum):
    """Specific regression modes detected when comparing a mutated policy against baseline."""
    NEW_UNSAFE_ALLOW = "NEW_UNSAFE_ALLOW"
    NEW_PROPERTY_VIOLATION = "NEW_PROPERTY_VIOLATION"
    SAFETY_MONOTONICITY_BREAK = "SAFETY_MONOTONICITY_BREAK"
    AUTHORIZATION_BOUNDARY_WEAKENED = "AUTHORIZATION_BOUNDARY_WEAKENED"
    EVIDENCE_REQUIREMENT_WEAKENED = "EVIDENCE_REQUIREMENT_WEAKENED"
    TOCTOU_DEFENSE_WEAKENED = "TOCTOU_DEFENSE_WEAKENED"
    RECOVERY_GUARD_WEAKENED = "RECOVERY_GUARD_WEAKENED"
    NO_REGRESSION = "NO_REGRESSION"


class PolicyFirewallDecision(str, Enum):
    """Deterministic verdict of the Policy Mutation Firewall."""
    ACCEPT = "ACCEPT"
    REJECT = "REJECT"
    INCONCLUSIVE = "INCONCLUSIVE"


class MutationRelevance(str, Enum):
    """Distinction between safety-relevant and non-safety-relevant mutations."""
    SAFETY_RELEVANT = "SAFETY_RELEVANT"
    NON_SAFETY_RELEVANT = "NON_SAFETY_RELEVANT"
    UNKNOWN = "UNKNOWN"


class PolicyBaseline(BaseModel):
    """Immutable baseline snapshot representing the last accepted safe policy."""
    baseline_id: str = Field(default_factory=lambda: f"base_{uuid.uuid4().hex[:10]}")
    policy_id: str = Field(..., description="ID of the baseline policy.")
    policy_version: str = Field(..., description="Version of the baseline policy.")
    canonical_policy_hash: str = Field(..., description="Deterministic SHA-256 hash of baseline policy.")
    policy_snapshot: Dict[str, Any] = Field(..., description="Serialized baseline policy parameters.")
    assurance_results: Dict[str, str] = Field(
        default_factory=dict,
        description="Pre-computed formal assurance property statuses (PROP_001..PROP_030).",
    )
    adversarial_results: Dict[str, Any] = Field(
        default_factory=dict,
        description="Pre-computed baseline adversarial scenario results (unsafe_allows=0).",
    )
    created_at: float = Field(default_factory=time.time)


class PolicyMutation(BaseModel):
    """Deterministic, reproducible record of an applied policy mutation."""
    mutation_id: str = Field(default_factory=lambda: f"pmut_{uuid.uuid4().hex[:10]}")
    parent_policy_hash: str = Field(..., description="Canonical hash of the parent policy before mutation.")
    mutated_policy_hash: Optional[str] = Field(default=None, description="Canonical hash of the mutated policy.")
    mutation_type: PolicyMutationType = Field(..., description="Taxonomic mutation class.")
    mutation_target: str = Field(..., description="Specific policy field, rule, or constraint mutated.")
    before_value: Any = Field(..., description="Value prior to mutation.")
    after_value: Any = Field(..., description="Value after mutation.")
    description: str = Field(..., description="Operational rationale or explanation of mutation.")
    relevance: MutationRelevance = Field(default=MutationRelevance.SAFETY_RELEVANT)
    created_at: float = Field(default_factory=time.time)
    parent_mutations: List[str] = Field(default_factory=list, description="Explicit list of applied mutation types.")
    mutation_depth: int = Field(default=1, description="Depth of mutation (1 for single, 2 for pairwise, 3 for triplet).")
    individual_mutations: List[Any] = Field(default_factory=list, description="Sub-mutations if this is a compound mutation.")



class MutationCounterexample(BaseModel):
    """Concrete, minimized scenario demonstrating a policy regression."""
    counterexample_id: str = Field(default_factory=lambda: f"cex_{uuid.uuid4().hex[:10]}")
    mutation_id: str = Field(..., description="ID of the offending policy mutation.")
    action_type: str = Field(..., description="Commanded action type (e.g. CLOSE_VALVE).")
    target: str = Field(..., description="Commanded target (e.g. valve_b).")
    human_zone: str = Field(..., description="Human zone state during counterexample.")
    cooling: str = Field(..., description="Cooling state during counterexample.")
    contradiction_severity: str = Field(..., description="Contradiction severity observed.")
    confidence: float = Field(..., description="Effective proposal confidence score.")
    baseline_decision: str = Field(..., description="Verdict under baseline (e.g. DENY).")
    mutated_decision: str = Field(..., description="Verdict under mutated policy (e.g. ALLOW).")
    regression: PolicyRegressionType = Field(..., description="Observed regression mode.")
    explanation: str = Field(..., description="Human-readable root cause explanation.")
    minimized_scenario: Dict[str, Any] = Field(default_factory=dict, description="Minimized state attributes.")


class MutationInteractionType(str, Enum):
    """Deterministic classification of interactions between combined policy mutations."""
    NO_INTERACTION = "NO_INTERACTION"
    ADDITIVE = "ADDITIVE"
    AMPLIFYING = "AMPLIFYING"
    CONFLICTING = "CONFLICTING"
    MASKING = "MASKING"


class CompoundPolicyMutation(BaseModel):
    """Deterministic, reproducible record of a compound (multi-operator) policy mutation."""
    compound_mutation_id: str = Field(default_factory=lambda: f"cmut_{uuid.uuid4().hex[:10]}")
    parent_policy_hash: str = Field(..., description="Canonical hash of parent policy before mutation.")
    mutated_policy_hash: Optional[str] = Field(default=None, description="Canonical hash of mutated policy.")
    parent_mutations: List[str] = Field(default_factory=list, description="Explicit list of applied mutation types.")
    individual_mutations: List[PolicyMutation] = Field(default_factory=list, description="Underlying individual mutation records.")
    mutation_depth: int = Field(default=2, description="Number of combined mutations (e.g. 2=pairwise, 3=triplet).")
    description: str = Field(..., description="Human-readable summary of compound attack.")
    relevance: MutationRelevance = Field(default=MutationRelevance.SAFETY_RELEVANT)
    created_at: float = Field(default_factory=time.time)


class TrajectoryStep(BaseModel):
    """Individual discrete transition in a physical trajectory."""
    step_index: int
    timestamp: float = Field(default_factory=time.time)
    event_name: str
    world_state: Dict[str, Any] = Field(default_factory=dict)
    action: Optional[str] = None
    target: Optional[str] = None
    decision: Optional[str] = None
    fault: Optional[str] = None
    outcome: Optional[str] = None
    revalidation_passed: Optional[bool] = None
    verification_passed: Optional[bool] = None


class DynamicTrajectory(BaseModel):
    """A bounded, ordered sequence of dynamic physical environment states and actions."""
    trajectory_id: str = Field(default_factory=lambda: f"traj_{uuid.uuid4().hex[:10]}")
    description: str
    steps: List[TrajectoryStep] = Field(default_factory=list)
    max_depth: int = Field(default=5, description="Configured trajectory depth limit.")
    seed: int = Field(default=42, description="Deterministic generation seed.")


class TrajectoryOutcomeType(str, Enum):
    """Categorical outcome of evaluating a physical trajectory under policy constraints."""
    BLOCKED_BEFORE_EXECUTION = "BLOCKED_BEFORE_EXECUTION"
    BLOCKED_BY_REVALIDATION = "BLOCKED_BY_REVALIDATION"
    EXECUTED_AND_VERIFIED = "EXECUTED_AND_VERIFIED"
    EXECUTED_AND_FAILED_VERIFICATION = "EXECUTED_AND_FAILED_VERIFICATION"
    CONTAINED_AND_RECOVERED = "CONTAINED_AND_RECOVERED"
    QUARANTINED = "QUARANTINED"
    NEW_UNSAFE_ALLOW = "NEW_UNSAFE_ALLOW"


class TrajectoryEvaluationResult(BaseModel):
    """Result of executing a dynamic physical trajectory against a policy candidate."""
    trajectory_id: str
    outcome: TrajectoryOutcomeType
    is_regression: bool = False
    new_unsafe_allows: int = 0
    failing_step_index: Optional[int] = None
    minimized_steps: List[str] = Field(default_factory=list)
    explanation: str = ""
    duration_seconds: float = 0.0


class PolicyRepairProposal(BaseModel):
    """A safe, non-authoritative candidate repair proposal synthesized for a detected regression."""
    proposal_id: str = Field(default_factory=lambda: f"prep_{uuid.uuid4().hex[:10]}")
    source_mutation_id: str
    detected_regression: PolicyRegressionType
    affected_field: str
    proposed_change: str
    before_value: Any
    after_value: Any
    safety_rationale: str
    counterexample_ref: Optional[str] = None
    expected_invariant_restored: str
    confidence: float = 1.0
    proposal_hash: str = ""
    status: str = "PROPOSED"
    created_at: float = Field(default_factory=time.time)


class MutationEvaluationResult(BaseModel):
    """Comprehensive evaluation result for a single or compound policy mutation."""
    evaluation_id: str = Field(default_factory=lambda: f"meval_{uuid.uuid4().hex[:10]}")
    mutation: PolicyMutation
    regression_type: PolicyRegressionType
    firewall_decision: PolicyFirewallDecision
    baseline_unsafe_allows: int = 0
    mutated_unsafe_allows: int = 0
    new_unsafe_allows: int = 0
    violated_properties: List[str] = Field(default_factory=list)
    counterexample: Optional[MutationCounterexample] = None
    diff_explanation: str = ""
    duration_seconds: float = 0.0
    survived: bool = False  # True if mutation did not trigger rejection

    # Phase 2K: Compound mutation & trajectory diagnostic dimensions
    parent_mutations: List[str] = Field(default_factory=list)
    mutation_depth: int = 1
    interaction_type: MutationInteractionType = MutationInteractionType.NO_INTERACTION
    formal_regressions: List[str] = Field(default_factory=list)
    authorization_boundary_regressions: List[str] = Field(default_factory=list)
    recovery_regressions: List[str] = Field(default_factory=list)
    verification_regressions: List[str] = Field(default_factory=list)
    trajectory_results: List[TrajectoryEvaluationResult] = Field(default_factory=list)

    @property
    def is_rejected(self) -> bool:
        return self.firewall_decision == PolicyFirewallDecision.REJECT

    @property
    def is_accepted(self) -> bool:
        return self.firewall_decision == PolicyFirewallDecision.ACCEPT


class FirewallEvaluationReport(BaseModel):
    """Aggregate report from running a suite of policy mutations through the firewall."""
    report_id: str = Field(default_factory=lambda: f"fwrep_{uuid.uuid4().hex[:10]}")
    timestamp: float = Field(default_factory=time.time)
    baseline_policy_id: str
    baseline_policy_hash: str
    total_mutations: int = 0
    safety_relevant_mutations: int = 0
    detected_regressions: int = 0
    survived_mutations: int = 0
    overall_decision: PolicyFirewallDecision = PolicyFirewallDecision.ACCEPT
    results: List[MutationEvaluationResult] = Field(default_factory=list)
    duration_seconds: float = 0.0

    # Phase 2K: Extended metrics for compound, trajectory, and repair tracking
    single_mutations_tested: int = 0
    compound_mutations_tested: int = 0
    interaction_classifications: Dict[str, int] = Field(default_factory=dict)
    trajectories_tested: int = 0
    minimized_trajectories: List[Dict[str, Any]] = Field(default_factory=list)
    repair_proposals_generated: int = 0
    repairs_rejected: int = 0
    repairs_accepted_by_validation: int = 0
    inconclusive_repairs: int = 0
    unsafe_allow_count: int = 0
    formal_property_results: Dict[str, str] = Field(default_factory=dict)
    deterministic_seed: int = 42
    execution_mode: str = "OFFLINE_ANALYSIS"
    source_mode: str = "DETERMINISTIC"
    replay_metadata: Dict[str, Any] = Field(default_factory=dict)

    def render_summary(self) -> str:
        """Render a clean, human-readable executive summary of the firewall evaluation."""
        lines = [
            "======================================================================",
            " MOTIONFENCE POLICY MUTATION FIREWALL EVALUATION REPORT (PHASE 2K)",
            "======================================================================",
            f"Baseline Policy ID:        {self.baseline_policy_id}",
            f"Baseline Policy Hash:      {self.baseline_policy_hash[:16]}...",
            f"Overall Firewall Decision: {self.overall_decision.value}",
            f"Total Mutations Tested:    {self.total_mutations}",
            f"  - Single Mutations:      {self.single_mutations_tested}",
            f"  - Compound Mutations:    {self.compound_mutations_tested}",
            f"Safety-Relevant Mutations: {self.safety_relevant_mutations}",
            f"Detected Regressions:      {self.detected_regressions}",
            f"Survived Mutations:        {self.survived_mutations}",
            f"Trajectories Tested:       {self.trajectories_tested}",
            f"Repairs Generated:         {self.repair_proposals_generated} (Accepted: {self.repairs_accepted_by_validation}, Rejected: {self.repairs_rejected})",
            "----------------------------------------------------------------------",
            "Mutation Breakdown:",
        ]
        for res in self.results:
            mut = res.mutation
            status = "REJECTED (DETECTED)" if res.is_rejected else "ACCEPTED (SURVIVED)"
            depth_tag = f"[D{res.mutation_depth}]" if res.mutation_depth > 1 else "[D1]"
            inter_tag = f" ({res.interaction_type.value})" if res.interaction_type != MutationInteractionType.NO_INTERACTION else ""
            lines.append(f"  * {depth_tag} [{mut.mutation_type.value:<22}] {mut.description[:36]:<36} -> {status}{inter_tag}")
            if res.new_unsafe_allows > 0 or res.violated_properties:
                lines.append(f"      Regression: {res.regression_type.value} (new_unsafe_allows={res.new_unsafe_allows}, props={res.violated_properties})")
        lines.append("======================================================================")
        return "\n".join(lines)

