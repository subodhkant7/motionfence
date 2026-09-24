"""Deterministic policy mutation operators for attacking safety policies in an isolated test environment (Phase 2J).

CRITICAL INVARIANTS:
1. Mutators MUST clone the input policy and NEVER mutate production objects in place.
2. Every mutation produces a complete, reproducible PolicyMutation record.
"""

from typing import Any, Callable, Dict, List, Tuple
import copy
import hashlib
import json

from motionfence.policy.models import Policy
from motionfence.evidence.models import ContradictionSeverity
from motionfence.policy_mutation.models import (
    MutationRelevance,
    PolicyMutation,
    PolicyMutationType,
)


def compute_canonical_policy_hash(policy: Policy) -> str:
    """Compute a deterministic SHA-256 hash of policy parameters."""
    data = policy.model_dump()
    # Sort keys for stable hashing
    canonical_json = json.dumps(data, sort_keys=True, default=str)
    return hashlib.sha256(canonical_json.encode("utf-8")).hexdigest()


class PolicyMutatorRegistry:
    """Collection of deterministic policy mutation operators."""

    @staticmethod
    def mutate_confidence_threshold_weakening(
        policy: Policy, new_threshold: float = 0.70
    ) -> Tuple[Policy, PolicyMutation]:
        """Weakens target identity confidence requirement (e.g. 0.90 -> 0.70)."""
        mutated = copy.deepcopy(policy)
        parent_hash = compute_canonical_policy_hash(policy)
        before = mutated.min_target_confidence
        mutated.min_target_confidence = new_threshold
        mut_hash = compute_canonical_policy_hash(mutated)

        record = PolicyMutation(
            parent_policy_hash=parent_hash,
            mutated_policy_hash=mut_hash,
            mutation_type=PolicyMutationType.THRESHOLD_WEAKENING,
            mutation_target="min_target_confidence",
            before_value=before,
            after_value=new_threshold,
            description=f"Weakened minimum target confidence threshold from {before:.2f} to {new_threshold:.2f}.",
            relevance=MutationRelevance.SAFETY_RELEVANT,
        )
        return mutated, record

    @staticmethod
    def mutate_confidence_threshold_tightening(
        policy: Policy, new_threshold: float = 0.95
    ) -> Tuple[Policy, PolicyMutation]:
        """Tightens target identity confidence requirement (e.g. 0.90 -> 0.95)."""
        mutated = copy.deepcopy(policy)
        parent_hash = compute_canonical_policy_hash(policy)
        before = mutated.min_target_confidence
        mutated.min_target_confidence = new_threshold
        mut_hash = compute_canonical_policy_hash(mutated)

        record = PolicyMutation(
            parent_policy_hash=parent_hash,
            mutated_policy_hash=mut_hash,
            mutation_type=PolicyMutationType.THRESHOLD_WEAKENING,
            mutation_target="min_target_confidence",
            before_value=before,
            after_value=new_threshold,
            description=f"Tightened minimum target confidence threshold from {before:.2f} to {new_threshold:.2f}.",
            relevance=MutationRelevance.SAFETY_RELEVANT,
        )
        return mutated, record

    @staticmethod
    def mutate_human_zone_guard_removal(policy: Policy) -> Tuple[Policy, PolicyMutation]:
        """Removes the human safety zone check (require_human_zone_clear = False)."""
        mutated = copy.deepcopy(policy)
        parent_hash = compute_canonical_policy_hash(policy)
        before = mutated.require_human_zone_clear
        mutated.require_human_zone_clear = False
        mut_hash = compute_canonical_policy_hash(mutated)

        record = PolicyMutation(
            parent_policy_hash=parent_hash,
            mutated_policy_hash=mut_hash,
            mutation_type=PolicyMutationType.CONDITION_REMOVAL,
            mutation_target="require_human_zone_clear",
            before_value=before,
            after_value=False,
            description="Removed hard human-zone clearance safety guard.",
            relevance=MutationRelevance.SAFETY_RELEVANT,
        )
        return mutated, record

    @staticmethod
    def mutate_cooling_invariant_deletion(policy: Policy) -> Tuple[Policy, PolicyMutation]:
        """Deletes the active cooling system invariant check (require_cooling_active = False)."""
        mutated = copy.deepcopy(policy)
        parent_hash = compute_canonical_policy_hash(policy)
        before = mutated.require_cooling_active
        mutated.require_cooling_active = False
        mut_hash = compute_canonical_policy_hash(mutated)

        record = PolicyMutation(
            parent_policy_hash=parent_hash,
            mutated_policy_hash=mut_hash,
            mutation_type=PolicyMutationType.RULE_DELETION,
            mutation_target="require_cooling_active",
            before_value=before,
            after_value=False,
            description="Deleted operational cooling system active requirement.",
            relevance=MutationRelevance.SAFETY_RELEVANT,
        )
        return mutated, record

    @staticmethod
    def mutate_contradiction_blocking_removal(policy: Policy) -> Tuple[Policy, PolicyMutation]:
        """Weakens contradiction tolerance to HIGH, allowing actions despite contradictory sensors."""
        mutated = copy.deepcopy(policy)
        parent_hash = compute_canonical_policy_hash(policy)
        before = mutated.max_tolerated_contradiction
        mutated.max_tolerated_contradiction = ContradictionSeverity.HIGH
        mut_hash = compute_canonical_policy_hash(mutated)

        record = PolicyMutation(
            parent_policy_hash=parent_hash,
            mutated_policy_hash=mut_hash,
            mutation_type=PolicyMutationType.CONTRADICTION_WEAKENING,
            mutation_target="max_tolerated_contradiction",
            before_value=before.value,
            after_value=ContradictionSeverity.HIGH.value,
            description="Weakened contradiction blocking: allows HIGH contradiction severity without blocking.",
            relevance=MutationRelevance.SAFETY_RELEVANT,
        )
        return mutated, record

    @staticmethod
    def mutate_scope_expansion(policy: Policy) -> Tuple[Policy, PolicyMutation]:
        """Expands permissible actuator targets beyond authorized equipment."""
        mutated = copy.deepcopy(policy)
        parent_hash = compute_canonical_policy_hash(policy)
        before = list(mutated.allowed_actuator_targets)
        mutated.allowed_actuator_targets = ["valve_a", "valve_b", "valve_c", "pump_p1", "pump_p2", "*"]
        mut_hash = compute_canonical_policy_hash(mutated)

        record = PolicyMutation(
            parent_policy_hash=parent_hash,
            mutated_policy_hash=mut_hash,
            mutation_type=PolicyMutationType.SCOPE_EXPANSION,
            mutation_target="allowed_actuator_targets",
            before_value=before,
            after_value=mutated.allowed_actuator_targets,
            description="Broadened actuator target scope to unmanaged plant actuators and wildcard.",
            relevance=MutationRelevance.SAFETY_RELEVANT,
        )
        return mutated, record

    @staticmethod
    def mutate_evidence_requirement_removal(policy: Policy) -> Tuple[Policy, PolicyMutation]:
        """Removes required evidence sources and zeroes confidence threshold."""
        mutated = copy.deepcopy(policy)
        parent_hash = compute_canonical_policy_hash(policy)
        before_sources = list(mutated.required_evidence_sources)
        before_conf = mutated.min_target_confidence
        mutated.required_evidence_sources = []
        mutated.min_target_confidence = 0.0
        mut_hash = compute_canonical_policy_hash(mutated)

        record = PolicyMutation(
            parent_policy_hash=parent_hash,
            mutated_policy_hash=mut_hash,
            mutation_type=PolicyMutationType.EVIDENCE_REQUIREMENT_REMOVAL,
            mutation_target="required_evidence_sources",
            before_value={"sources": before_sources, "confidence": before_conf},
            after_value={"sources": [], "confidence": 0.0},
            description="Removed all empirical evidence requirements and zeroed confidence threshold.",
            relevance=MutationRelevance.SAFETY_RELEVANT,
        )
        return mutated, record

    @staticmethod
    def mutate_toctou_revalidation_removal(policy: Policy) -> Tuple[Policy, PolicyMutation]:
        """Attempts to disable TOCTOU revalidation binding in policy configuration."""
        mutated = copy.deepcopy(policy)
        parent_hash = compute_canonical_policy_hash(policy)
        mutated.expected_postconditions["disable_revalidation"] = True
        mut_hash = compute_canonical_policy_hash(mutated)

        record = PolicyMutation(
            parent_policy_hash=parent_hash,
            mutated_policy_hash=mut_hash,
            mutation_type=PolicyMutationType.AUTHORIZATION_BOUNDARY_MUTATION,
            mutation_target="toctou_revalidation",
            before_value=False,
            after_value=True,
            description="Attempted to disable execution-time revalidation checks.",
            relevance=MutationRelevance.SAFETY_RELEVANT,
        )
        return mutated, record

    @staticmethod
    def mutate_quarantine_bypass(policy: Policy) -> Tuple[Policy, PolicyMutation]:
        """Attempts to disable component quarantine enforcement."""
        mutated = copy.deepcopy(policy)
        parent_hash = compute_canonical_policy_hash(policy)
        mutated.expected_postconditions["bypass_quarantine"] = True
        mut_hash = compute_canonical_policy_hash(mutated)

        record = PolicyMutation(
            parent_policy_hash=parent_hash,
            mutated_policy_hash=mut_hash,
            mutation_type=PolicyMutationType.AUTHORIZATION_BOUNDARY_MUTATION,
            mutation_target="quarantine_enforcement",
            before_value=False,
            after_value=True,
            description="Attempted to bypass component quarantine and recovery gating.",
            relevance=MutationRelevance.SAFETY_RELEVANT,
        )
        return mutated, record

    @staticmethod
    def mutate_stale_knowledge_acceptance(policy: Policy) -> Tuple[Policy, PolicyMutation]:
        """Allows stale sensor knowledge by vastly expanding allowable observation age."""
        mutated = copy.deepcopy(policy)
        parent_hash = compute_canonical_policy_hash(policy)
        before = mutated.expected_postconditions.get("max_knowledge_age_seconds", 5.0)
        mutated.expected_postconditions["max_knowledge_age_seconds"] = 86400.0  # 24 hours
        mut_hash = compute_canonical_policy_hash(mutated)

        record = PolicyMutation(
            parent_policy_hash=parent_hash,
            mutated_policy_hash=mut_hash,
            mutation_type=PolicyMutationType.FRESHNESS_WEAKENING,
            mutation_target="max_knowledge_age_seconds",
            before_value=before,
            after_value=86400.0,
            description="Weakened knowledge freshness constraint, accepting up to 24-hour-old observations.",
            relevance=MutationRelevance.SAFETY_RELEVANT,
        )
        return mutated, record

    @staticmethod
    def mutate_recovery_budget_expansion(policy: Policy) -> Tuple[Policy, PolicyMutation]:
        """Expands recovery retry limits and disables escalation containment."""
        mutated = copy.deepcopy(policy)
        parent_hash = compute_canonical_policy_hash(policy)
        before = mutated.expected_postconditions.get("recovery_retry_budget", 3)
        mutated.expected_postconditions["recovery_retry_budget"] = 9999
        mutated.expected_postconditions["unlimited_recovery"] = True
        mut_hash = compute_canonical_policy_hash(mutated)

        record = PolicyMutation(
            parent_policy_hash=parent_hash,
            mutated_policy_hash=mut_hash,
            mutation_type=PolicyMutationType.REQUIREMENT_WEAKENING,
            mutation_target="recovery_retry_budget",
            before_value=before,
            after_value=9999,
            description="Weakened recovery containment budget by allowing unlimited recovery retries.",
            relevance=MutationRelevance.SAFETY_RELEVANT,
        )
        return mutated, record

    @staticmethod
    def mutate_authorization_precondition_weakening(policy: Policy) -> Tuple[Policy, PolicyMutation]:
        """Removes cooling adjustment prohibition from prohibited_actions."""
        mutated = copy.deepcopy(policy)
        parent_hash = compute_canonical_policy_hash(policy)
        before = [a.value if hasattr(a, "value") else str(a) for a in mutated.prohibited_actions]
        mutated.prohibited_actions = []
        mut_hash = compute_canonical_policy_hash(mutated)

        record = PolicyMutation(
            parent_policy_hash=parent_hash,
            mutated_policy_hash=mut_hash,
            mutation_type=PolicyMutationType.AUTHORIZATION_BOUNDARY_MUTATION,
            mutation_target="prohibited_actions",
            before_value=before,
            after_value=[],
            description="Weakened authorization preconditions by clearing prohibited actions list.",
            relevance=MutationRelevance.SAFETY_RELEVANT,
        )
        return mutated, record

    @staticmethod
    def mutate_non_safety_metadata(
        policy: Policy, new_objective: str = "Updated plant operational narrative"
    ) -> Tuple[Policy, PolicyMutation]:
        """Modifies non-safety-relevant documentation/metadata without affecting invariants."""
        mutated = copy.deepcopy(policy)
        parent_hash = compute_canonical_policy_hash(policy)
        before = mutated.objective
        mutated.objective = new_objective
        mut_hash = compute_canonical_policy_hash(mutated)

        record = PolicyMutation(
            parent_policy_hash=parent_hash,
            mutated_policy_hash=mut_hash,
            mutation_type=PolicyMutationType.NON_SAFETY_MUTATION,
            mutation_target="objective",
            before_value=before,
            after_value=new_objective,
            description="Updated operational objective documentation (non-safety metadata).",
            relevance=MutationRelevance.NON_SAFETY_RELEVANT,
        )
        return mutated, record

    @classmethod
    def get_canonical_corpus(cls, policy: Policy) -> List[Tuple[Policy, PolicyMutation]]:
        """Generate the complete 10-operator canonical safety mutation corpus plus non-safety mutation."""
        corpus = [
            cls.mutate_confidence_threshold_weakening(policy, new_threshold=0.70),
            cls.mutate_human_zone_guard_removal(policy),
            cls.mutate_cooling_invariant_deletion(policy),
            cls.mutate_contradiction_blocking_removal(policy),
            cls.mutate_stale_knowledge_acceptance(policy),
            cls.mutate_evidence_requirement_removal(policy),
            cls.mutate_toctou_revalidation_removal(policy),
            cls.mutate_recovery_budget_expansion(policy),
            cls.mutate_quarantine_bypass(policy),
            cls.mutate_authorization_precondition_weakening(policy),
            cls.mutate_non_safety_metadata(policy),
        ]
        return corpus

    @classmethod
    def create_compound_mutation(
        cls,
        policy: Policy,
        mutator_fns: List[Callable[[Policy], Tuple[Policy, PolicyMutation]]],
        description: str,
    ) -> Tuple[Policy, PolicyMutation]:
        """Sequentially apply multiple mutation operators on detached policy clones."""
        current_policy = copy.deepcopy(policy)
        parent_hash = compute_canonical_policy_hash(policy)
        individual_records: List[PolicyMutation] = []
        parent_mutation_types: List[str] = []

        for fn in mutator_fns:
            current_policy, rec = fn(current_policy)
            individual_records.append(rec)
            parent_mutation_types.append(rec.mutation_type.value)

        final_hash = compute_canonical_policy_hash(current_policy)
        compound_record = PolicyMutation(
            parent_policy_hash=parent_hash,
            mutated_policy_hash=final_hash,
            mutation_type=individual_records[0].mutation_type,
            mutation_target=", ".join(r.mutation_target for r in individual_records),
            before_value=[r.before_value for r in individual_records],
            after_value=[r.after_value for r in individual_records],
            description=description,
            relevance=MutationRelevance.SAFETY_RELEVANT,
            parent_mutations=parent_mutation_types,
            mutation_depth=len(individual_records),
            individual_mutations=[r.model_dump() for r in individual_records],
        )
        return current_policy, compound_record

    @classmethod
    def mutate_compound_threshold_and_contradiction(cls, policy: Policy) -> Tuple[Policy, PolicyMutation]:
        """Pairwise: threshold weakening + contradiction weakening."""
        return cls.create_compound_mutation(
            policy,
            [
                lambda p: cls.mutate_confidence_threshold_weakening(p, new_threshold=0.70),
                cls.mutate_contradiction_blocking_removal,
            ],
            "Compound: threshold weakening (0.70) + contradiction blocking removal (HIGH)",
        )

    @classmethod
    def mutate_compound_human_zone_and_scope(cls, policy: Policy) -> Tuple[Policy, PolicyMutation]:
        """Pairwise: human-zone condition removal + target scope expansion."""
        return cls.create_compound_mutation(
            policy,
            [
                cls.mutate_human_zone_guard_removal,
                cls.mutate_scope_expansion,
            ],
            "Compound: human-zone guard removal + target scope expansion (wildcard)",
        )

    @classmethod
    def mutate_stale_sensor_acceptance(cls, policy: Policy) -> Tuple[Policy, PolicyMutation]:
        """Mutate policy to accept stale sensor telemetry without recertification."""
        mutated = copy.deepcopy(policy)
        parent_hash = compute_canonical_policy_hash(policy)
        mutated.expected_postconditions["accept_stale_telemetry"] = True
        mut_hash = compute_canonical_policy_hash(mutated)
        record = PolicyMutation(
            parent_policy_hash=parent_hash,
            mutated_policy_hash=mut_hash,
            mutation_type=PolicyMutationType.FRESHNESS_WEAKENING,
            mutation_target="accept_stale_telemetry",
            before_value=False,
            after_value=True,
            description="Accepted stale sensor telemetry without recertification.",
            relevance=MutationRelevance.SAFETY_RELEVANT,
        )
        return mutated, record

    @classmethod
    def mutate_compound_freshness_and_stale_acceptance(cls, policy: Policy) -> Tuple[Policy, PolicyMutation]:
        """Pairwise: freshness weakening + stale sensor acceptance."""
        return cls.create_compound_mutation(
            policy,
            [
                cls.mutate_stale_knowledge_acceptance,
                cls.mutate_stale_sensor_acceptance,
            ],
            "Compound: freshness weakening (24h) + stale sensor acceptance",
        )

    @classmethod
    def mutate_compound_evidence_removal_and_threshold(cls, policy: Policy) -> Tuple[Policy, PolicyMutation]:
        """Pairwise: evidence requirement removal + confidence threshold weakening."""
        return cls.create_compound_mutation(
            policy,
            [
                cls.mutate_evidence_requirement_removal,
                lambda p: cls.mutate_confidence_threshold_weakening(p, new_threshold=0.50),
            ],
            "Compound: evidence requirement removal + confidence threshold zeroing (0.50)",
        )

    @classmethod
    def mutate_compound_cooling_and_human_zone(cls, policy: Policy) -> Tuple[Policy, PolicyMutation]:
        """Pairwise: cooling requirement deletion + human-zone guard removal."""
        return cls.create_compound_mutation(
            policy,
            [
                cls.mutate_cooling_invariant_deletion,
                cls.mutate_human_zone_guard_removal,
            ],
            "Compound: cooling invariant deletion + human-zone guard removal",
        )

    @classmethod
    def mutate_compound_recovery_and_quarantine(cls, policy: Policy) -> Tuple[Policy, PolicyMutation]:
        """Pairwise: recovery retry weakening + quarantine weakening."""
        return cls.create_compound_mutation(
            policy,
            [
                cls.mutate_recovery_budget_expansion,
                cls.mutate_quarantine_bypass,
            ],
            "Compound: recovery retry weakening (9999) + quarantine bypass",
        )

    @classmethod
    def mutate_compound_scope_and_state_bound(cls, policy: Policy) -> Tuple[Policy, PolicyMutation]:
        """Pairwise: target scope expansion + state-bound authorization weakening."""
        return cls.create_compound_mutation(
            policy,
            [
                cls.mutate_scope_expansion,
                cls.mutate_toctou_revalidation_removal,
            ],
            "Compound: target scope expansion (wildcard) + state-bound TOCTOU weakening",
        )

    @classmethod
    def mutate_compound_triplet_human_cooling_threshold(cls, policy: Policy) -> Tuple[Policy, PolicyMutation]:
        """Triplet: human-zone removal + cooling deletion + threshold weakening."""
        return cls.create_compound_mutation(
            policy,
            [
                cls.mutate_human_zone_guard_removal,
                cls.mutate_cooling_invariant_deletion,
                lambda p: cls.mutate_confidence_threshold_weakening(p, new_threshold=0.70),
            ],
            "Compound Triplet: human-zone removal + cooling deletion + threshold weakening (0.70)",
        )

    @classmethod
    def mutate_compound_triplet_contradiction_evidence_freshness(cls, policy: Policy) -> Tuple[Policy, PolicyMutation]:
        """Triplet: contradiction weakening + evidence removal + freshness weakening."""
        return cls.create_compound_mutation(
            policy,
            [
                cls.mutate_contradiction_blocking_removal,
                cls.mutate_evidence_requirement_removal,
                cls.mutate_stale_knowledge_acceptance,
            ],
            "Compound Triplet: contradiction weakening + evidence removal + freshness weakening",
        )

    @classmethod
    def mutate_compound_triplet_quarantine_recovery_revalidation(cls, policy: Policy) -> Tuple[Policy, PolicyMutation]:
        """Triplet: quarantine bypass + recovery budget expansion + TOCTOU revalidation removal."""
        return cls.create_compound_mutation(
            policy,
            [
                cls.mutate_quarantine_bypass,
                cls.mutate_recovery_budget_expansion,
                cls.mutate_toctou_revalidation_removal,
            ],
            "Compound Triplet: quarantine bypass + recovery budget expansion + TOCTOU revalidation removal",
        )

    @classmethod
    def get_canonical_compound_corpus(cls, policy: Policy, seed: int = 42) -> List[Tuple[Policy, PolicyMutation]]:
        """Generate deterministic bounded compound mutation corpus (pairwise + selected triplets)."""
        corpus = [
            cls.mutate_compound_threshold_and_contradiction(policy),
            cls.mutate_compound_human_zone_and_scope(policy),
            cls.mutate_compound_evidence_removal_and_threshold(policy),
            cls.mutate_compound_cooling_and_human_zone(policy),
            cls.mutate_compound_recovery_and_quarantine(policy),
            cls.mutate_compound_scope_and_state_bound(policy),
            cls.mutate_compound_triplet_human_cooling_threshold(policy),
            cls.mutate_compound_triplet_contradiction_evidence_freshness(policy),
            cls.mutate_compound_triplet_quarantine_recovery_revalidation(policy),
        ]
        return corpus

    @classmethod
    def shrink_compound_mutation(
        cls,
        compound_mutation: PolicyMutation,
        policy: Policy,
    ) -> List[Tuple[Policy, PolicyMutation]]:
        """Generate shrunk sub-combinations of a compound mutation to find minimal regression cause."""
        if compound_mutation.mutation_depth <= 1:
            return [(policy, compound_mutation)]

        sub_mutations = compound_mutation.individual_mutations
        shrunk_cases: List[Tuple[Policy, PolicyMutation]] = []

        # Return single component mutations first (depth 1)
        for sub in sub_mutations:
            # Reconstruct single mutation applied to baseline
            single_mut = PolicyMutation(**sub)
            mutated_clone = copy.deepcopy(policy)
            target = single_mut.mutation_target
            after = single_mut.after_value
            if hasattr(mutated_clone, target):
                setattr(mutated_clone, target, after)
            elif target in mutated_clone.expected_postconditions:
                mutated_clone.expected_postconditions[target] = after
            shrunk_cases.append((mutated_clone, single_mut))

        return shrunk_cases


def create_compound_mutation(*args, **kwargs):
    return PolicyMutatorRegistry.create_compound_mutation(*args, **kwargs)


def shrink_compound_mutation(*args, **kwargs):
    return PolicyMutatorRegistry.shrink_compound_mutation(*args, **kwargs)



