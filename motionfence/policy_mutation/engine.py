"""Policy Mutation Engine orchestrating deterministic mutation generation and evaluation (Phase 2J/2K).

CRITICAL INVARIANTS:
1. Operates exclusively on detached policy clones; NEVER modifies production policies in place.
2. Possesses ZERO AuthorizationTicket minting or PhysicalActuator authority.
3. Completely offline by default; zero external network calls.
4. INCONCLUSIVE conservatively maps to REJECT for safety-critical changes.
5. Emits auditable, replayable events for all compound mutations, trajectory probes, and repair proposals.
"""

from typing import Any, Dict, List, Optional, Tuple
import time

from motionfence.assurance.checker import BoundedAssuranceChecker
from motionfence.models.events import EventType
from motionfence.policy.models import Policy
from motionfence.policy_mutation.baseline import PolicyBaselineManager
from motionfence.policy_mutation.evaluator import PolicyMutationEvaluator
from motionfence.policy_mutation.minimizer import MutationCounterexampleMinimizer
from motionfence.policy_mutation.models import (
    DynamicTrajectory,
    FirewallEvaluationReport,
    MutationEvaluationResult,
    MutationInteractionType,
    MutationRelevance,
    PolicyBaseline,
    PolicyFirewallDecision,
    PolicyMutation,
    PolicyRegressionType,
    PolicyRepairProposal,
    TrajectoryEvaluationResult,
    TrajectoryOutcomeType,
)
from motionfence.policy_mutation.mutators import PolicyMutatorRegistry
from motionfence.policy_mutation.repair import (
    PolicyRepairSynthesizer,
    PolicyRepairValidator,
    RepairStatus,
    RepairValidationResult,
)
from motionfence.policy_mutation.trajectory import (
    DynamicTrajectoryEvaluator,
    TrajectoryGenerator,
    shrink_trajectory,
)
from motionfence.runtime.events import EventBus


class PolicyMutationEngine:
    """Orchestrates single & compound mutation evaluation, trajectory exploration, and safe repair validation."""

    def __init__(
        self,
        event_bus: Optional[EventBus] = None,
        evaluator: Optional[PolicyMutationEvaluator] = None,
    ) -> None:
        self.event_bus = event_bus
        self.evaluator = evaluator or PolicyMutationEvaluator()
        self.trajectory_evaluator = DynamicTrajectoryEvaluator()
        self.repair_validator = PolicyRepairValidator()
        self._history: Dict[str, MutationEvaluationResult] = {}
        self._baselines: Dict[str, PolicyBaseline] = {}

    def create_baseline(self, policy: Policy) -> PolicyBaseline:
        """Capture an immutable PolicyBaseline snapshot from an accepted production policy."""
        baseline = PolicyBaselineManager.create_baseline(policy)
        self._baselines[baseline.baseline_id] = baseline

        if self.event_bus:
            self.event_bus.emit(
                event_type=EventType.POLICY_BASELINE_CREATED,
                message=f"Policy baseline created: {baseline.baseline_id} (hash: {baseline.canonical_policy_hash[:16]}...)",
                payload={
                    "baseline_id": baseline.baseline_id,
                    "policy_id": baseline.policy_id,
                    "canonical_policy_hash": baseline.canonical_policy_hash,
                },
            )
        return baseline

    def evaluate_mutation(
        self,
        mutated_policy: Policy,
        mutation: PolicyMutation,
        baseline: PolicyBaseline,
    ) -> MutationEvaluationResult:
        """Evaluate a single or compound mutated policy against the baseline snapshot."""
        is_compound = mutation.mutation_depth >= 2

        if self.event_bus:
            event_type = EventType.COMPOUND_MUTATION_CREATED if is_compound else EventType.POLICY_MUTATION_CREATED
            self.event_bus.emit(
                event_type=event_type,
                message=f"Mutation created: {mutation.mutation_id} (depth={mutation.mutation_depth}, type={mutation.mutation_type.value})",
                payload={
                    "mutation_id": mutation.mutation_id,
                    "mutation_type": mutation.mutation_type.value,
                    "mutation_target": mutation.mutation_target,
                    "parent_policy_hash": mutation.parent_policy_hash,
                    "parent_mutations": mutation.parent_mutations,
                    "mutation_depth": mutation.mutation_depth,
                },
            )

        result = self.evaluator.evaluate(
            mutated_policy=mutated_policy,
            baseline=baseline,
            mutation=mutation,
        )
        self._history[mutation.mutation_id] = result

        if self.event_bus:
            eval_event = EventType.COMPOUND_MUTATION_EVALUATED if is_compound else EventType.POLICY_MUTATION_EVALUATED
            self.event_bus.emit(
                event_type=eval_event,
                message=f"Mutation evaluated: {mutation.mutation_id} -> {result.firewall_decision.value}",
                payload={
                    "mutation_id": mutation.mutation_id,
                    "regression_type": result.regression_type.value,
                    "firewall_decision": result.firewall_decision.value,
                    "new_unsafe_allows": result.new_unsafe_allows,
                    "violated_properties": result.violated_properties,
                    "interaction_type": result.interaction_type.value,
                },
            )

            if result.interaction_type != MutationInteractionType.NO_INTERACTION:
                self.event_bus.emit(
                    event_type=EventType.MUTATION_INTERACTION_DETECTED,
                    message=f"Mutation interaction detected: {result.interaction_type.value} on {mutation.mutation_id}",
                    payload={
                        "mutation_id": mutation.mutation_id,
                        "interaction_type": result.interaction_type.value,
                        "parent_mutations": mutation.parent_mutations,
                        "new_unsafe_allows": result.new_unsafe_allows,
                    },
                )

            if result.regression_type != PolicyRegressionType.NO_REGRESSION:
                self.event_bus.emit(
                    event_type=EventType.POLICY_REGRESSION_DETECTED,
                    message=f"Policy regression detected: {result.regression_type.value} on mutation {mutation.mutation_id}",
                    payload={
                        "mutation_id": mutation.mutation_id,
                        "regression_type": result.regression_type.value,
                        "counterexample_id": result.counterexample.counterexample_id if result.counterexample else None,
                    },
                )

            if result.is_rejected:
                self.event_bus.emit(
                    event_type=EventType.POLICY_MUTATION_REJECTED,
                    message=f"Policy mutation rejected by firewall: {mutation.mutation_id}",
                    payload={"mutation_id": mutation.mutation_id},
                )
            elif result.is_accepted:
                self.event_bus.emit(
                    event_type=EventType.POLICY_MUTATION_ACCEPTED,
                    message=f"Policy mutation accepted by firewall: {mutation.mutation_id}",
                    payload={"mutation_id": mutation.mutation_id},
                )

        return result

    def evaluate_trajectories(
        self,
        policy: Policy,
        baseline: PolicyBaseline,
        trajectories: Optional[List[DynamicTrajectory]] = None,
        seed: int = 42,
    ) -> List[TrajectoryEvaluationResult]:
        """Execute dynamic physical trajectories against a policy candidate."""
        baseline_policy = PolicyBaselineManager.restore_policy_from_baseline(baseline)
        if trajectories is None:
            trajectories = TrajectoryGenerator.generate_trajectories(seed=seed, depths=[3, 5, 8])

        results: List[TrajectoryEvaluationResult] = []
        for traj in trajectories:
            res = self.trajectory_evaluator.evaluate_trajectory(traj, policy, baseline_policy)
            results.append(res)

            if self.event_bus:
                self.event_bus.emit(
                    event_type=EventType.TRAJECTORY_EVALUATED,
                    message=f"Trajectory evaluated: {traj.trajectory_id} -> {res.outcome.value}",
                    payload={
                        "trajectory_id": traj.trajectory_id,
                        "outcome": res.outcome.value,
                        "is_regression": res.is_regression,
                        "new_unsafe_allows": res.new_unsafe_allows,
                    },
                )

                if res.is_regression or res.outcome == TrajectoryOutcomeType.NEW_UNSAFE_ALLOW:
                    self.event_bus.emit(
                        event_type=EventType.TRAJECTORY_REGRESSION_DETECTED,
                        message=f"Trajectory regression detected on {traj.trajectory_id}: {res.explanation}",
                        payload={
                            "trajectory_id": traj.trajectory_id,
                            "outcome": res.outcome.value,
                            "failing_step_index": res.failing_step_index,
                        },
                    )

        return results

    def synthesize_and_validate_repair(
        self,
        evaluation_result: MutationEvaluationResult,
        baseline: PolicyBaseline,
        mutated_policy: Policy,
    ) -> RepairValidationResult:
        """Synthesize candidate repair proposal and immediately validate it through detached firewall."""
        proposal = PolicyRepairSynthesizer.synthesize_repair(evaluation_result, baseline)

        if self.event_bus:
            self.event_bus.emit(
                event_type=EventType.REPAIR_PROPOSAL_CREATED,
                message=f"Repair proposal created: {proposal.proposal_id} ({proposal.proposed_change})",
                payload={
                    "proposal_id": proposal.proposal_id,
                    "affected_field": proposal.affected_field,
                    "proposal_hash": proposal.proposal_hash,
                    "status": proposal.status,
                },
            )

        val_result = self.repair_validator.validate(proposal, mutated_policy, baseline)

        if self.event_bus:
            if val_result.status == RepairStatus.ACCEPTABLE:
                self.event_bus.emit(
                    event_type=EventType.REPAIR_VALIDATED,
                    message=f"Repair proposal validated as acceptable: {proposal.proposal_id}",
                    payload={"proposal_id": proposal.proposal_id, "status": val_result.status.value},
                )
            elif val_result.status == RepairStatus.REJECTED:
                self.event_bus.emit(
                    event_type=EventType.REPAIR_REJECTED,
                    message=f"Repair proposal rejected by firewall: {proposal.proposal_id}",
                    payload={"proposal_id": proposal.proposal_id, "rationale": val_result.rationale},
                )
            else:
                self.event_bus.emit(
                    event_type=EventType.REPAIR_INCONCLUSIVE,
                    message=f"Repair proposal inconclusive (fails closed): {proposal.proposal_id}",
                    payload={"proposal_id": proposal.proposal_id},
                )

        return val_result

    def run_suite(
        self,
        baseline: PolicyBaseline,
        mutations: Optional[List[Tuple[Policy, PolicyMutation]]] = None,
        include_compound: bool = False,
        include_trajectories: bool = False,
        synthesize_repairs: bool = False,
        seed: int = 42,
    ) -> FirewallEvaluationReport:
        """Run the firewall against a suite of mutations, optional compound attacks, trajectories, and repairs."""
        start_time = time.time()
        baseline_policy = PolicyBaselineManager.restore_policy_from_baseline(baseline)

        if mutations is None:
            mutations = PolicyMutatorRegistry.get_canonical_corpus(baseline_policy)
            if include_compound:
                compound_corpus = PolicyMutatorRegistry.get_canonical_compound_corpus(baseline_policy, seed=seed)
                mutations.extend(compound_corpus)

        results: List[MutationEvaluationResult] = []
        detected_regressions = 0
        survived_mutations = 0
        safety_relevant_count = 0
        single_count = 0
        compound_count = 0
        total_unsafe_allows = 0
        interaction_counts: Dict[str, int] = {}

        repairs_generated = 0
        repairs_accepted = 0
        repairs_rejected = 0
        inconclusive_repairs = 0

        for mut_policy, mutation in mutations:
            if mutation.mutation_depth > 1:
                compound_count += 1
            else:
                single_count += 1

            if mutation.relevance == MutationRelevance.SAFETY_RELEVANT:
                safety_relevant_count += 1

            res = self.evaluate_mutation(mut_policy, mutation, baseline)
            results.append(res)
            total_unsafe_allows += res.new_unsafe_allows

            inter_str = res.interaction_type.value
            interaction_counts[inter_str] = interaction_counts.get(inter_str, 0) + 1

            if res.is_rejected:
                detected_regressions += 1
                if synthesize_repairs:
                    rep_val = self.synthesize_and_validate_repair(res, baseline, mut_policy)
                    repairs_generated += 1
                    if rep_val.status == RepairStatus.ACCEPTABLE:
                        repairs_accepted += 1
                    elif rep_val.status == RepairStatus.REJECTED:
                        repairs_rejected += 1
                    else:
                        inconclusive_repairs += 1
            else:
                survived_mutations += 1

        # Dynamic trajectories
        trajectories_tested = 0
        minimized_trajectories: List[Dict[str, Any]] = []
        if include_trajectories:
            trajectories = TrajectoryGenerator.generate_trajectories(seed=seed, depths=[3, 5, 8])
            trajectories_tested = len(trajectories)
            for traj in trajectories:
                t_res = self.trajectory_evaluator.evaluate_trajectory(traj, baseline_policy, baseline_policy)
                if t_res.is_regression or t_res.outcome == TrajectoryOutcomeType.NEW_UNSAFE_ALLOW:
                    min_t = MutationCounterexampleMinimizer.minimize_trajectory(
                        trajectory_id=traj.trajectory_id,
                        steps=traj.steps,
                        regression_type=PolicyRegressionType.NEW_UNSAFE_ALLOW,
                        failing_step_index=t_res.failing_step_index,
                        explanation=t_res.explanation,
                    )
                    minimized_trajectories.append(min_t)

        overall_decision = (
            PolicyFirewallDecision.REJECT
            if detected_regressions > 0
            else PolicyFirewallDecision.ACCEPT
        )

        # Formal properties check snapshot
        checker = BoundedAssuranceChecker()
        prop_findings = checker.check_all()
        prop_results = {f.property_id: f.status.value for f in prop_findings}

        return FirewallEvaluationReport(
            baseline_policy_id=baseline.policy_id,
            baseline_policy_hash=baseline.canonical_policy_hash,
            total_mutations=len(mutations),
            safety_relevant_mutations=safety_relevant_count,
            detected_regressions=detected_regressions,
            survived_mutations=survived_mutations,
            overall_decision=overall_decision,
            results=results,
            duration_seconds=time.time() - start_time,
            single_mutations_tested=single_count,
            compound_mutations_tested=compound_count,
            interaction_classifications=interaction_counts,
            trajectories_tested=trajectories_tested,
            minimized_trajectories=minimized_trajectories,
            repair_proposals_generated=repairs_generated,
            repairs_rejected=repairs_rejected,
            repairs_accepted_by_validation=repairs_accepted,
            inconclusive_repairs=inconclusive_repairs,
            unsafe_allow_count=total_unsafe_allows,
            formal_property_results=prop_results,
            deterministic_seed=seed,
            execution_mode="OFFLINE_ANALYSIS",
            source_mode="DETERMINISTIC",
            replay_metadata={"seed": seed, "compound_included": include_compound, "trajectories_included": include_trajectories},
        )

    def replay_mutation(self, mutation_id: str) -> Optional[MutationEvaluationResult]:
        """Replay and retrieve a recorded mutation evaluation deterministically."""
        return self._history.get(mutation_id)
