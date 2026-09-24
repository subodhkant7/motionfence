"""Bounded formal analysis using Z3 SMT solver.

CRITICAL INVARIANTS:
1. Z3 is isolated strictly to this analysis layer.
2. Z3 NEVER participates in real-time runtime authorization.
3. BOUNDED PROPERTY SATISFIED ≠ REAL-WORLD SAFETY PROVEN.
   Verification applies strictly to the modeled state variables, bounded
   transitions, and deterministic rules represented below.
"""

from typing import Any, Dict, List, Optional
import time
import z3

from motionfence.assurance.models import (
    AssuranceFinding,
    FindingStatus,
    FindingSeverity,
    AssuranceScope,
)
from motionfence.assurance.invariants import AssurancePropertyRegistry
from motionfence.assurance.counterexample import CounterexampleFormatter


class BoundedAssuranceChecker:
    """Bounded SMT verification engine evaluating MotionFence policy invariants via Z3."""

    def __init__(self, registry: Optional[AssurancePropertyRegistry] = None) -> None:
        self.registry = registry or AssurancePropertyRegistry()

    def check_property(
        self,
        property_id: str,
        policy_mutations: Optional[Dict[str, bool]] = None,
    ) -> AssuranceFinding:
        """Evaluate a registered property using Z3 SMT solver.

        Args:
            property_id: The ID of the property to verify.
            policy_mutations: Optional test-only policy alterations (e.g. disabling a guard)
                              used to deliberately test counterexample discovery.
        """
        prop = self.registry.get(property_id)
        if not prop:
            return AssuranceFinding(
                property_id=property_id,
                property_name="Unknown Property",
                status=FindingStatus.NOT_APPLICABLE,
                severity=FindingSeverity.INFO,
                scope=AssuranceScope.STATIC_INVARIANT.value,
                explanation=f"Property '{property_id}' is not registered in AssurancePropertyRegistry.",
            )

        mutations = policy_mutations or {}

        # Build fresh Z3 solver and symbolic variables
        solver = z3.Solver()
        vars_dict = self._declare_variables()

        # Encode standard or mutated policy rules into solver
        self._encode_policy_rules(solver, vars_dict, mutations)

        # Encode the negation of the target property
        property_negated, description = self._encode_property_negation(property_id, vars_dict)
        solver.add(property_negated)

        check_result = solver.check()

        if check_result == z3.unsat:
            # No assignment can violate the property under the policy rules
            return AssuranceFinding(
                property_id=prop.property_id,
                property_name=prop.name,
                status=FindingStatus.SATISFIED,
                severity=prop.severity,
                scope=prop.scope.value,
                explanation=(
                    f"BOUNDED PROPERTY SATISFIED: Z3 proved that no state in the bounded model "
                    f"can violate '{prop.name}' under active deterministic policy rules."
                ),
            )
        elif check_result == z3.sat:
            # A concrete counterexample was discovered that violates the property!
            model = solver.model()
            raw_counterexample = self._extract_counterexample(model, vars_dict)
            minimized_counterexample = CounterexampleFormatter.minimize(raw_counterexample)

            return AssuranceFinding(
                property_id=prop.property_id,
                property_name=prop.name,
                status=FindingStatus.VIOLATED,
                severity=prop.severity,
                scope=prop.scope.value,
                counterexample=minimized_counterexample,
                explanation=(
                    f"BOUNDED PROPERTY VIOLATED: Z3 discovered a concrete counterexample "
                    f"demonstrating a state where '{prop.name}' is violated."
                ),
            )
        else:
            return AssuranceFinding(
                property_id=prop.property_id,
                property_name=prop.name,
                status=FindingStatus.UNKNOWN,
                severity=prop.severity,
                scope=prop.scope.value,
                explanation=f"SMT Solver returned UNKNOWN for property '{prop.name}'.",
            )

    def check_all(
        self, policy_mutations: Optional[Dict[str, bool]] = None
    ) -> List[AssuranceFinding]:
        """Check all registered static invariant and temporal properties."""
        findings = []
        for prop in self.registry.list_all():
            # Check properties expressible via SMT
            findings.append(self.check_property(prop.property_id, policy_mutations))
        return findings

    def _declare_variables(self) -> Dict[str, Any]:
        """Declare bounded symbolic variables for physical state, inputs, and policy decisions."""
        return {
            # Human zone: 0=CLEAR, 1=OCCUPIED, 2=WARNING
            "human_zone": z3.Int("human_zone"),
            # Cooling state: 0=INACTIVE, 1=ACTIVE, 2=DEGRADED
            "cooling": z3.Int("cooling"),
            # Auxiliary pump P1: 0=INACTIVE, 1=ACTIVE
            "pump_p1": z3.Int("pump_p1"),
            # Target valve B: 0=CLOSED, 1=OPEN, 2=JAMMED, 3=TRANSITIONING
            "valve_b": z3.Int("valve_b"),
            # Proposed action: 0=NONE, 1=CLOSE_VALVE, 2=OPEN_VALVE
            "action": z3.Int("action"),
            # Proposal effective confidence: [0.0, 1.0]
            "confidence": z3.Real("confidence"),
            # Contradiction severity: 0=NONE, 1=LOW, 2=HIGH
            "contradiction_severity": z3.Int("contradiction_severity"),
            # Policy decision: 0=DENY, 1=ALLOW, 2=NEED_MORE_EVIDENCE
            "policy_decision": z3.Int("policy_decision"),
            # Knowledge flags
            "has_conflicted_constraint": z3.Bool("has_conflicted_constraint"),
            "has_stale_constraint": z3.Bool("has_stale_constraint"),
            # Ticket and actuator execution
            "has_ticket": z3.Bool("has_ticket"),
            "world_mutated": z3.Bool("world_mutated"),
            # Phase 2F: State-binding and TOCTOU variables
            "auth_world_version": z3.Int("auth_world_version"),
            "exec_world_version": z3.Int("exec_world_version"),
            "auth_policy_version": z3.Int("auth_policy_version"),
            "exec_policy_version": z3.Int("exec_policy_version"),
            "auth_constraint_hash": z3.Int("auth_constraint_hash"),
            "exec_constraint_hash": z3.Int("exec_constraint_hash"),
            "revalidation_passed": z3.Bool("revalidation_passed"),
            "execution_attempted": z3.Bool("execution_attempted"),
            # Phase 2G: Active Evidence Acquisition & Capability variables
            "action_class": z3.Int("action_class"),  # 0=INFORMATION_ACTION, 1=CONSEQUENTIAL_ACTION
            "is_info_action": z3.Bool("is_info_action"),
            "is_consequential_action": z3.Bool("is_consequential_action"),
            "planner_can_actuate": z3.Bool("planner_can_actuate"),
            "planner_can_mint_ticket": z3.Bool("planner_can_mint_ticket"),
            "evidence_iterations": z3.Int("evidence_iterations"),
            "evidence_budget": z3.Int("evidence_budget"),
            "has_new_evidence": z3.Bool("has_new_evidence"),
            "is_planner_proposal": z3.Bool("is_planner_proposal"),
            # Phase 2H: Adversarial Physical Environment & Robustness variables
            "human_transition_to_occupied": z3.Bool("human_transition_to_occupied"),
            "has_admissible_new_evidence": z3.Bool("has_admissible_new_evidence"),
            "actuator_fault": z3.Bool("actuator_fault"),
            "verification_status": z3.Int("verification_status"),  # 0=VERIFIED, 1=VERIFICATION_FAILED
            "prev_decision": z3.Int("prev_decision"),  # 0=DENY, 1=ALLOW, 2=NEED_MORE_EVIDENCE
            "safety_degraded": z3.Bool("safety_degraded"),
            "adversary_can_mint_ticket": z3.Bool("adversary_can_mint_ticket"),
            "adversary_can_bypass_enclave": z3.Bool("adversary_can_bypass_enclave"),
            "environmental_drift": z3.Bool("environmental_drift"),
            # Phase 2I: Fault Containment, Quarantine & Autonomous Recovery variables
            "action_failed": z3.Bool("action_failed"),
            "ticket_invalidated": z3.Bool("ticket_invalidated"),
            "component_quarantined": z3.Bool("component_quarantined"),
            "blocked_capability_executed": z3.Bool("blocked_capability_executed"),
            "recovery_reuses_stale_ticket": z3.Bool("recovery_reuses_stale_ticket"),
            "recovery_fresh_eval_done": z3.Bool("recovery_fresh_eval_done"),
            "consequential_action_authorized": z3.Bool("consequential_action_authorized"),
            "sensor_quarantined": z3.Bool("sensor_quarantined"),
            "quarantined_sensor_evidence_admitted": z3.Bool("quarantined_sensor_evidence_admitted"),
            "recovery_attempts": z3.Int("recovery_attempts"),
            "recovery_budget": z3.Int("recovery_budget"),
            "recovery_action_class": z3.Int("recovery_action_class"),  # 0=INFO, 1=CONSEQUENTIAL
            "recovery_planner_can_escalate": z3.Bool("recovery_planner_can_escalate"),

            # Phase 2J: Policy Mutation Firewall & Safety Regression Detection
            "human_guard_removed": z3.Bool("human_guard_removed"),
            "regression_detected_human_zone": z3.Bool("regression_detected_human_zone"),
            "confidence_weakened": z3.Bool("confidence_weakened"),
            "evades_assurance": z3.Bool("evades_assurance"),
            "regression_detected_confidence": z3.Bool("regression_detected_confidence"),
            "contradiction_guard_removed": z3.Bool("contradiction_guard_removed"),
            "regression_detected_contradiction": z3.Bool("regression_detected_contradiction"),
            "state_binding_disabled": z3.Bool("state_binding_disabled"),
            "regression_detected_state_bound": z3.Bool("regression_detected_state_bound"),
            "revalidation_disabled": z3.Bool("revalidation_disabled"),
            "regression_detected_revalidation": z3.Bool("regression_detected_revalidation"),
            "recovery_containment_disabled": z3.Bool("recovery_containment_disabled"),
            "regression_detected_recovery": z3.Bool("regression_detected_recovery"),
            # Phase 2K: Combinatorial Attacks, Dynamic Trajectories & Safe Repairs
            "is_compound_mutation": z3.Bool("is_compound_mutation"),
            "compound_regression_detected": z3.Bool("compound_regression_detected"),
            "is_amplifying_interaction": z3.Bool("is_amplifying_interaction"),
            "amplifying_detected": z3.Bool("amplifying_detected"),
            "trajectory_regression_present": z3.Bool("trajectory_regression_present"),
            "trajectory_blockable_by_reval": z3.Bool("trajectory_blockable_by_reval"),
            "repair_modifies_production_policy": z3.Bool("repair_modifies_production_policy"),
            "repair_proposal_applied_without_validation": z3.Bool("repair_proposal_applied_without_validation"),
            "repair_weakens_auth_boundary": z3.Bool("repair_weakens_auth_boundary"),
            "repair_accepted_with_weakened_boundary": z3.Bool("repair_accepted_with_weakened_boundary"),
            "trajectory_counterexample_deterministic": z3.Bool("trajectory_counterexample_deterministic"),
            "repair_is_inconclusive": z3.Bool("repair_is_inconclusive"),
            "inconclusive_repair_auto_applied": z3.Bool("inconclusive_repair_auto_applied"),
            # Phase 2M: Mock Hardware & Actuator Boundary variables
            "hardware_actuated": z3.Bool("hardware_actuated"),
            "ticket_is_valid": z3.Bool("ticket_is_valid"),
            "ticket_is_expired": z3.Bool("ticket_is_expired"),
            "ticket_is_replayed": z3.Bool("ticket_is_replayed"),
            "target_is_mismatched": z3.Bool("target_is_mismatched"),
            "action_is_mismatched": z3.Bool("action_is_mismatched"),
            "auth_is_stale": z3.Bool("auth_is_stale"),
        }


    def _encode_policy_rules(
        self,
        solver: z3.Solver,
        v: Dict[str, Any],
        mutations: Dict[str, bool],
    ) -> None:
        """Encode the deterministic MotionFence ruleset into Z3 constraints."""
        # 1. State domain boundaries
        solver.add(v["human_zone"] >= 0, v["human_zone"] <= 2)
        solver.add(v["cooling"] >= 0, v["cooling"] <= 2)
        solver.add(v["pump_p1"] >= 0, v["pump_p1"] <= 1)
        solver.add(v["valve_b"] >= 0, v["valve_b"] <= 3)
        solver.add(v["action"] >= 0, v["action"] <= 2)
        solver.add(v["confidence"] >= 0.0, v["confidence"] <= 1.0)
        solver.add(v["contradiction_severity"] >= 0, v["contradiction_severity"] <= 2)
        solver.add(v["policy_decision"] >= 0, v["policy_decision"] <= 2)

        # Phase 2F: State-binding domain boundaries
        solver.add(v["auth_world_version"] >= 1)
        solver.add(v["exec_world_version"] >= 1)
        solver.add(v["auth_policy_version"] >= 1)
        solver.add(v["exec_policy_version"] >= 1)
        solver.add(v["auth_constraint_hash"] >= 0)
        solver.add(v["exec_constraint_hash"] >= 0)

        # Phase 2G: Active Evidence & Capability bounds
        solver.add(v["action_class"] >= 0, v["action_class"] <= 1)
        solver.add(v["evidence_iterations"] >= 0)
        solver.add(v["evidence_budget"] >= 1)
        solver.add(v["is_info_action"] == (v["action_class"] == 0))
        solver.add(v["is_consequential_action"] == (v["action_class"] == 1))

        # 2. Invariant Rule 1: Human Safety Zone
        # If human_zone != 0 (CLEAR), decision must be DENY (0)
        if not mutations.get("disable_human_zone_check", False):
            solver.add(z3.Implies(v["human_zone"] != 0, v["policy_decision"] == 0))

        # 3. Invariant Rule 2: Cooling System Active
        # If cooling != 1 (ACTIVE), decision must be DENY (0)
        if not mutations.get("disable_cooling_check", False):
            solver.add(z3.Implies(v["cooling"] != 1, v["policy_decision"] == 0))

        # 4. Invariant Rule 3: High Contradiction
        # If contradiction_severity == 2 (HIGH), decision cannot be ALLOW (1)
        if not mutations.get("disable_contradiction_check", False):
            solver.add(z3.Implies(v["contradiction_severity"] == 2, v["policy_decision"] != 1))

        # 5. Invariant Rule 4: Confidence Threshold (min 0.90)
        if not mutations.get("disable_confidence_check", False):
            solver.add(z3.Implies(v["confidence"] < 0.90, v["policy_decision"] != 1))

        # 6. Invariant Rule 5: Conflicted Knowledge
        if not mutations.get("disable_conflict_check", False):
            solver.add(z3.Implies(v["has_conflicted_constraint"], v["policy_decision"] != 1))

        # 7. Invariant Rule 6: Stale Knowledge
        if not mutations.get("disable_stale_check", False):
            solver.add(z3.Implies(v["has_stale_constraint"], v["policy_decision"] != 1))

        # 8. Actuator Authority Rule: World mutation requires a valid ticket
        if not mutations.get("allow_unauthorized_mutation", False):
            solver.add(z3.Implies(v["world_mutated"], v["has_ticket"]))

        # 9. Safety Enclave Rule: Ticket minting strictly requires ALLOW (1)
        if not mutations.get("allow_ticket_without_allow", False):
            solver.add(z3.Implies(v["has_ticket"], v["policy_decision"] == 1))

        # Phase 2F Rules: State-bound authorization and TOCTOU defense

        # 10. Revalidation passes only if all bindings match
        if not mutations.get("disable_revalidation", False):
            solver.add(z3.Implies(
                v["revalidation_passed"],
                z3.And(
                    v["auth_world_version"] == v["exec_world_version"],
                    v["auth_policy_version"] == v["exec_policy_version"],
                    v["auth_constraint_hash"] == v["exec_constraint_hash"],
                )
            ))

        # 11. Execution requires passed revalidation
        if not mutations.get("disable_execution_requires_revalidation", False):
            solver.add(z3.Implies(v["execution_attempted"], v["revalidation_passed"]))

        # 12. World mutation requires execution
        if not mutations.get("allow_mutation_without_execution", False):
            solver.add(z3.Implies(v["world_mutated"], v["execution_attempted"]))

        # Phase 2G Rules: Active Evidence Acquisition & Capability Boundaries

        # 13. Rule 13: Information actions cannot mutate consequential physical world state
        if not mutations.get("allow_info_action_mutation", False):
            solver.add(z3.Implies(v["is_info_action"], z3.Not(v["world_mutated"])))

        # 14. Rule 14: Evidence planner cannot possess ACTUATE or ticket minting authority
        if not mutations.get("allow_planner_actuation_authority", False):
            solver.add(z3.Not(v["planner_can_actuate"]))
            solver.add(z3.Not(v["planner_can_mint_ticket"]))

        # 15. Rule 15: Evidence acquisition iterations cannot exceed evidence budget
        if not mutations.get("allow_unbounded_evidence_budget", False):
            solver.add(v["evidence_iterations"] <= v["evidence_budget"])

        # 16. Rule 16: Evidence acquisition cannot bypass policy (execution still requires ALLOW)
        if not mutations.get("allow_evidence_bypass_policy", False):
            solver.add(z3.Implies(v["execution_attempted"], v["policy_decision"] == 1))

        # 17. Rule 17: Additional evidence cannot force ALLOW if safety conditions are violated
        if not mutations.get("allow_evidence_override_safety", False):
            if not mutations.get("disable_human_zone_check", False):
                solver.add(z3.Implies(z3.And(v["has_new_evidence"], v["human_zone"] != 0), v["policy_decision"] != 1))
            if not mutations.get("disable_cooling_check", False):
                solver.add(z3.Implies(z3.And(v["has_new_evidence"], v["cooling"] != 1), v["policy_decision"] != 1))
            if not mutations.get("disable_contradiction_check", False):
                solver.add(z3.Implies(z3.And(v["has_new_evidence"], v["contradiction_severity"] == 2), v["policy_decision"] != 1))

        # 18. Rule 18: Planner cannot escalate action class from information to consequential
        if not mutations.get("allow_planner_action_escalation", False):
            solver.add(z3.Implies(v["is_planner_proposal"], v["is_info_action"]))

        # Phase 2H Rules: Adversarial Physical Environment & Robustness Bounds
        solver.add(v["verification_status"] >= 0, v["verification_status"] <= 1)
        solver.add(v["prev_decision"] >= 0, v["prev_decision"] <= 2)

        # 19. Rule 19: Unsafe human-zone transition causes world version drift
        if not mutations.get("allow_human_transition_execution", False):
            solver.add(z3.Implies(
                v["human_transition_to_occupied"],
                v["auth_world_version"] != v["exec_world_version"]
            ))

        # 20. Rule 20: Sensor contradiction blocks ALLOW unless admissible new evidence exists
        if not mutations.get("allow_ungrounded_contradiction_clearance", False):
            solver.add(z3.Implies(
                z3.And(v["contradiction_severity"] == 2, z3.Not(v["has_admissible_new_evidence"])),
                v["policy_decision"] != 1
            ))

        # 21. Rule 21: Actuator fault forces VERIFICATION_FAILED (1)
        if not mutations.get("allow_actuator_fault_verification", False):
            solver.add(z3.Implies(v["actuator_fault"], v["verification_status"] == 1))

        # 22. Rule 22: Safety degradation cannot convert previous DENY to ALLOW
        if not mutations.get("allow_safety_degradation_allow", False):
            solver.add(z3.Implies(
                z3.And(v["prev_decision"] == 0, v["safety_degraded"]),
                v["policy_decision"] != 1
            ))

        # 23. Rule 23: Adversarial environment has zero ticket or enclave authority
        if not mutations.get("allow_adversary_authority", False):
            solver.add(z3.Not(v["adversary_can_mint_ticket"]))
            solver.add(z3.Not(v["adversary_can_bypass_enclave"]))

        # 24. Rule 24: Environmental drift forces version drift
        if not mutations.get("allow_stale_ticket_execution", False):
            solver.add(z3.Implies(
                v["environmental_drift"],
                v["auth_world_version"] != v["exec_world_version"]
            ))

        # Phase 2I Rules: Fault Containment, Quarantine & Autonomous Recovery
        solver.add(v["recovery_attempts"] >= 0)
        solver.add(v["recovery_budget"] >= 1)
        solver.add(v["recovery_action_class"] >= 0, v["recovery_action_class"] <= 1)

        # 25. Rule 25: Action failure unconditionally invalidates the associated ticket
        if not mutations.get("disable_failure_ticket_invalidation", False):
            solver.add(z3.Implies(v["action_failed"], v["ticket_invalidated"]))

        # 26. Rule 26: Quarantined component cannot execute blocked capabilities
        if not mutations.get("allow_quarantined_execution", False):
            solver.add(z3.Implies(v["component_quarantined"], z3.Not(v["blocked_capability_executed"])))

        # 27. Rule 27: Autonomous recovery cannot silently reuse stale consequential authorization
        if not mutations.get("allow_stale_recovery_ticket", False):
            solver.add(z3.Not(v["recovery_reuses_stale_ticket"]))

        # 28. Rule 28: Consequential action authorization during recovery requires fresh policy reevaluation
        if not mutations.get("allow_recovery_without_reevaluation", False):
            solver.add(z3.Implies(v["consequential_action_authorized"], v["recovery_fresh_eval_done"]))

        # 29. Rule 29: Quarantined sensor evidence cannot be admitted into authorization context
        if not mutations.get("admit_quarantined_sensor_evidence", False):
            solver.add(z3.Implies(v["sensor_quarantined"], z3.Not(v["quarantined_sensor_evidence_admitted"])))

        # 30. Rule 30: Recovery attempts cannot exceed finite recovery budget
        if not mutations.get("allow_infinite_recovery_budget", False):
            solver.add(v["recovery_attempts"] <= v["recovery_budget"])

        # 31. Rule 31: Recovery planner cannot escalate capability class
        if not mutations.get("allow_recovery_capability_escalation", False):
            solver.add(z3.Not(v["recovery_planner_can_escalate"]))

        # Phase 2J Rules: Policy Mutation Firewall & Safety Regression Detection
        # 32. Rule 32: Human-zone guard removal must trigger regression detection
        if not mutations.get("disable_human_mutation_detection", False):
            solver.add(z3.Implies(v["human_guard_removed"], v["regression_detected_human_zone"]))

        # 33. Rule 33: Confidence weakening cannot evade assurance detection
        if not mutations.get("allow_confidence_weakening_evasion", False):
            solver.add(z3.Implies(v["confidence_weakened"], z3.Not(v["evades_assurance"])))
            solver.add(z3.Implies(v["confidence_weakened"], v["regression_detected_confidence"]))

        # 34. Rule 34: Contradiction removal must trigger regression detection
        if not mutations.get("disable_contradiction_mutation_detection", False):
            solver.add(z3.Implies(v["contradiction_guard_removed"], v["regression_detected_contradiction"]))

        # 35. Rule 35: State-bound authorization cannot be silently disabled
        if not mutations.get("allow_state_binding_bypass", False):
            solver.add(z3.Implies(v["state_binding_disabled"], v["regression_detected_state_bound"]))

        # 36. Rule 36: Execution revalidation cannot be silently disabled
        if not mutations.get("allow_revalidation_bypass", False):
            solver.add(z3.Implies(v["revalidation_disabled"], v["regression_detected_revalidation"]))

        # 37. Rule 37: Recovery containment cannot be silently disabled
        if not mutations.get("allow_recovery_containment_bypass", False):
            solver.add(z3.Implies(v["recovery_containment_disabled"], v["regression_detected_recovery"]))

        # Phase 2K Rules: Combinatorial Attacks, Dynamic Trajectories & Safe Repairs
        # 38. Rule 38: Compound safety mutations must trigger regression detection
        if not mutations.get("allow_compound_evasion", False):
            solver.add(z3.Implies(v["is_compound_mutation"], v["compound_regression_detected"]))

        # 39. Rule 39: Amplifying mutation interactions must be classified and detected
        if not mutations.get("disable_amplifying_detection", False):
            solver.add(z3.Implies(v["is_amplifying_interaction"], v["amplifying_detected"]))

        # 40. Rule 40: Dynamic trajectory regressions must remain blockable by revalidation
        if not mutations.get("disable_trajectory_blockability", False):
            solver.add(z3.Implies(v["trajectory_regression_present"], v["trajectory_blockable_by_reval"]))

        # 41. Rule 41: Repair proposals cannot directly modify production policy
        if not mutations.get("allow_repair_production_mutation", False):
            solver.add(z3.Not(v["repair_modifies_production_policy"]))

        # 42. Rule 42: Repair proposals must pass the existing safety firewall before acceptance
        if not mutations.get("allow_unvalidated_repair", False):
            solver.add(z3.Not(v["repair_proposal_applied_without_validation"]))

        # 43. Rule 43: Repair proposals cannot weaken the authorization boundary
        if not mutations.get("allow_weakened_repair", False):
            solver.add(z3.Implies(v["repair_weakens_auth_boundary"], z3.Not(v["repair_accepted_with_weakened_boundary"])))

        # 44. Rule 44: Trajectory counterexamples must be deterministic and reproducible
        if not mutations.get("non_deterministic_counterexample", False):
            solver.add(v["trajectory_counterexample_deterministic"] == True)

        # 45. Rule 45: Inconclusive repairs cannot be automatically applied
        if not mutations.get("allow_auto_apply_inconclusive", False):
            solver.add(z3.Implies(v["repair_is_inconclusive"], z3.Not(v["inconclusive_repair_auto_applied"])))

        # Phase 2M Rules: Mock Hardware & Actuator Boundary Invariants
        # 46. Rule 46: Hardware cannot actuate without valid, unexpired, unconsumed, matching authorization
        if not mutations.get("allow_hardware_unauthorized_actuation", False):
            solver.add(
                z3.Implies(
                    v["hardware_actuated"],
                    z3.And(
                        v["has_ticket"] == True,
                        v["ticket_is_valid"] == True,
                        v["ticket_is_expired"] == False,
                        v["ticket_is_replayed"] == False,
                        v["target_is_mismatched"] == False,
                        v["action_is_mismatched"] == False,
                        v["auth_is_stale"] == False,
                    )
                )
            )



    def _encode_property_negation(
        self, property_id: str, v: Dict[str, Any]
    ) -> tuple[z3.BoolRef, str]:
        """Encode the negation of a safety property for refutation analysis."""
        if property_id == "PROP_001_HUMAN_ZONE_PROHIBITION":
            # Property: (human_zone == OCCUPIED and action == CLOSE_VALVE) -> policy_decision != ALLOW
            # Negation: human_zone == 1 (OCCUPIED) and action == 1 (CLOSE_VALVE) and policy_decision == 1 (ALLOW)
            return (
                z3.And(v["human_zone"] == 1, v["action"] == 1, v["policy_decision"] == 1),
                "Human occupied safety zone but CLOSE_VALVE was allowed.",
            )

        elif property_id == "PROP_002_COOLING_PRESERVATION":
            # Property: policy_decision == ALLOW -> cooling == ACTIVE
            # Negation: policy_decision == 1 (ALLOW) and cooling != 1 (ACTIVE)
            return (
                z3.And(v["policy_decision"] == 1, v["cooling"] != 1),
                "ALLOW verdict granted while cooling system is inactive or degraded.",
            )

        elif property_id == "PROP_003_UNAUTHORIZED_MUTATION_IMPOSSIBLE":
            # Property: world_mutated -> has_ticket
            # Negation: world_mutated == True and has_ticket == False
            return (
                z3.And(v["world_mutated"] == True, v["has_ticket"] == False),
                "Physical world mutated without a valid AuthorizationTicket.",
            )

        elif property_id == "PROP_004_CONFLICTED_POLICY_BLOCKS_AUTHORIZATION":
            # Property: has_conflicted_constraint -> policy_decision != ALLOW
            # Negation: has_conflicted_constraint == True and policy_decision == 1 (ALLOW)
            return (
                z3.And(v["has_conflicted_constraint"] == True, v["policy_decision"] == 1),
                "ALLOW verdict granted despite presence of conflicting policy constraints.",
            )

        elif property_id == "PROP_005_STALE_SAFETY_CONSTRAINT_BLOCKS_AUTHORIZATION":
            # Property: has_stale_constraint -> policy_decision != ALLOW
            # Negation: has_stale_constraint == True and policy_decision == 1 (ALLOW)
            return (
                z3.And(v["has_stale_constraint"] == True, v["policy_decision"] == 1),
                "ALLOW verdict granted despite presence of stale safety constraints.",
            )

        elif property_id == "PROP_006_CONTRADICTORY_EVIDENCE_GATING":
            # Property: contradiction_severity == HIGH -> policy_decision != ALLOW
            # Negation: contradiction_severity == 2 and policy_decision == 1 (ALLOW)
            return (
                z3.And(v["contradiction_severity"] == 2, v["policy_decision"] == 1),
                "ALLOW verdict granted despite high-severity sensor contradiction.",
            )

        elif property_id == "PROP_007_TEMPORAL_COOLING_PRESERVATION":
            # Bounded temporal cooling property: an authorized transition cannot co-exist with degraded cooling
            return (
                z3.And(v["action"] == 1, v["policy_decision"] == 1, v["cooling"] == 0),
                "Valve transition authorized during cooling system failure.",
            )

        # Phase 2F Properties

        elif property_id == "PROP_008_NO_EXECUTION_AFTER_STATE_DRIFT":
            # Property: (auth_world_version != exec_world_version) -> NOT execution_attempted
            # Negation: world versions differ AND execution was attempted
            return (
                z3.And(
                    v["auth_world_version"] != v["exec_world_version"],
                    v["execution_attempted"] == True,
                ),
                "Execution attempted after safety-relevant world state drifted from authorization context.",
            )

        elif property_id == "PROP_009_POLICY_VERSION_BINDING":
            # Property: (auth_policy_version != exec_policy_version) -> NOT execution_attempted
            # Negation: policy versions differ AND execution was attempted
            return (
                z3.And(
                    v["auth_policy_version"] != v["exec_policy_version"],
                    v["execution_attempted"] == True,
                ),
                "Execution attempted under different policy version than authorization.",
            )

        elif property_id == "PROP_010_CONSTRAINT_SET_BINDING":
            # Property: (auth_constraint_hash != exec_constraint_hash) -> NOT execution_attempted
            # Negation: constraint hashes differ AND execution was attempted
            return (
                z3.And(
                    v["auth_constraint_hash"] != v["exec_constraint_hash"],
                    v["execution_attempted"] == True,
                ),
                "Execution attempted with different constraint set than authorization.",
            )

        elif property_id == "PROP_011_EXECUTION_TIME_VALIDITY":
            # Property: execution_attempted -> revalidation_passed
            # Negation: execution attempted without revalidation passing
            return (
                z3.And(
                    v["execution_attempted"] == True,
                    v["revalidation_passed"] == False,
                ),
                "Execution attempted without passing execution-time revalidation.",
            )

        # Phase 2G: Active Evidence Acquisition Properties

        elif property_id == "PROP_012_INFO_ACTION_NO_CONSEQUENTIAL_MUTATION":
            # Property: is_info_action -> NOT world_mutated
            # Negation: is_info_action == True AND world_mutated == True
            return (
                z3.And(v["is_info_action"] == True, v["world_mutated"] == True),
                "Information action mutated consequential physical world state.",
            )

        elif property_id == "PROP_013_PLANNER_CANNOT_AUTHORIZE_CONSEQUENTIAL":
            # Property: NOT (planner_can_actuate OR planner_can_mint_ticket)
            # Negation: planner possessed actuation or ticket minting authority
            return (
                z3.Or(v["planner_can_actuate"] == True, v["planner_can_mint_ticket"] == True),
                "Evidence planner possessed consequential actuation or ticket minting authority.",
            )

        elif property_id == "PROP_014_EVIDENCE_BUDGET_FINITE":
            # Property: evidence_iterations <= evidence_budget
            # Negation: evidence_iterations > evidence_budget
            return (
                v["evidence_iterations"] > v["evidence_budget"],
                "Evidence acquisition loop exceeded bounded iteration budget.",
            )

        elif property_id == "PROP_015_EVIDENCE_CANNOT_BYPASS_POLICY":
            # Property: execution_attempted -> policy_decision == ALLOW (1)
            # Negation: execution attempted when policy did NOT ALLOW
            return (
                z3.And(v["execution_attempted"] == True, v["policy_decision"] != 1),
                "Evidence acquisition loop bypassed policy authorization and attempted actuation.",
            )

        elif property_id == "PROP_016_NEW_EVIDENCE_DOES_NOT_IMPLY_ALLOW":
            # Property: (human_zone != CLEAR or cooling != ACTIVE or contradiction == HIGH) -> policy != ALLOW
            # Negation: safety violation present, new evidence acquired, but policy granted ALLOW
            return (
                z3.And(
                    v["has_new_evidence"] == True,
                    z3.Or(v["human_zone"] != 0, v["cooling"] != 1, v["contradiction_severity"] == 2),
                    v["policy_decision"] == 1,
                ),
                "Additional evidence caused false ALLOW despite active safety violation.",
            )

        elif property_id == "PROP_017_PLANNER_CANNOT_ESCALATE_ACTION_CLASS":
            # Property: is_planner_proposal -> is_info_action
            # Negation: planner proposal is a consequential action
            return (
                z3.And(v["is_planner_proposal"] == True, v["is_consequential_action"] == True),
                "Planner escalated proposal domain into consequential action.",
            )

        # Phase 2H Properties: Adversarial Physical Environment & Robustness

        elif property_id == "PROP_018_HUMAN_ZONE_TRANSITION_SAFETY":
            # Property: human_transition_to_occupied -> NOT execution_attempted
            # Negation: human transitioned to occupied AND execution was attempted
            return (
                z3.And(v["human_transition_to_occupied"] == True, v["execution_attempted"] == True),
                "Execution attempted despite unsafe human-zone transition during latency window.",
            )

        elif property_id == "PROP_019_SENSOR_CONTRADICTION_NO_UNGROUNDED_ALLOW":
            # Property: (contradiction == HIGH and NOT has_admissible_new_evidence) -> policy != ALLOW
            # Negation: high contradiction without admissible new evidence resulted in ALLOW
            return (
                z3.And(
                    v["contradiction_severity"] == 2,
                    v["has_admissible_new_evidence"] == False,
                    v["policy_decision"] == 1,
                ),
                "ALLOW granted despite unresolved high sensor contradiction without new evidence.",
            )

        elif property_id == "PROP_020_ACTUATOR_FAULT_VERIFICATION":
            # Property: actuator_fault -> verification_status == VERIFICATION_FAILED (1)
            # Negation: actuator fault occurred but verification_status was VERIFIED (0)
            return (
                z3.And(v["actuator_fault"] == True, v["verification_status"] == 0),
                "Actuator fault produced false VERIFIED postcondition status.",
            )

        elif property_id == "PROP_021_SAFETY_DEGRADATION_MONOTONICITY":
            # Property: (prev_decision == DENY and safety_degraded) -> policy != ALLOW
            # Negation: safety degradation converted a previous DENY into ALLOW
            return (
                z3.And(v["prev_decision"] == 0, v["safety_degraded"] == True, v["policy_decision"] == 1),
                "Safety degradation converted a previous DENY verdict into ALLOW.",
            )

        elif property_id == "PROP_022_ADVERSARIAL_ENV_ZERO_AUTHORITY":
            # Property: NOT (adversary_can_mint_ticket OR adversary_can_bypass_enclave)
            # Negation: adversary possessed ticket minting or enclave bypass authority
            return (
                z3.Or(v["adversary_can_mint_ticket"] == True, v["adversary_can_bypass_enclave"] == True),
                "Adversarial environment possessed ticket minting or enclave bypass authority.",
            )

        elif property_id == "PROP_023_STALE_TICKET_ENVIRONMENTAL_DRIFT":
            # Property: environmental_drift -> NOT execution_attempted
            # Negation: environmental drift occurred AND execution was attempted
            return (
                z3.And(v["environmental_drift"] == True, v["execution_attempted"] == True),
                "Stale ticket executed after modeled environmental drift.",
            )

        elif property_id == "PROP_024_FAILED_ACTIONS_INVALIDATE_AUTHORITY":
            # Property: action_failed -> ticket_invalidated
            # Negation: action failed occurred but ticket was not invalidated
            return (
                z3.And(v["action_failed"] == True, v["ticket_invalidated"] == False),
                "Action failed but the associated authorization ticket was not invalidated.",
            )

        elif property_id == "PROP_025_QUARANTINED_COMPONENTS_CANNOT_EXECUTE":
            # Property: component_quarantined -> NOT blocked_capability_executed
            # Negation: component is quarantined and executed a blocked capability
            return (
                z3.And(v["component_quarantined"] == True, v["blocked_capability_executed"] == True),
                "Quarantined component executed a blocked capability.",
            )

        elif property_id == "PROP_026_RECOVERY_CANNOT_REUSE_STALE_AUTHORIZATION":
            # Property: NOT recovery_reuses_stale_ticket
            # Negation: recovery reused stale authorization ticket
            return (
                v["recovery_reuses_stale_ticket"] == True,
                "Recovery attempted to reuse stale authorization ticket.",
            )

        elif property_id == "PROP_027_RECOVERY_REQUIRES_POLICY_REEVALUATION":
            # Property: consequential_action_authorized -> recovery_fresh_eval_done
            # Negation: consequential action authorized during recovery without fresh policy reevaluation
            return (
                z3.And(v["consequential_action_authorized"] == True, v["recovery_fresh_eval_done"] == False),
                "Consequential action authorized during recovery without fresh policy reevaluation.",
            )

        elif property_id == "PROP_028_SENSOR_QUARANTINE_REMOVES_UNSAFE_EVIDENCE":
            # Property: sensor_quarantined -> NOT quarantined_sensor_evidence_admitted
            # Negation: quarantined sensor evidence admitted into authorization context
            return (
                z3.And(v["sensor_quarantined"] == True, v["quarantined_sensor_evidence_admitted"] == True),
                "Evidence from quarantined sensor was admitted into authorization context.",
            )

        elif property_id == "PROP_029_RECOVERY_BUDGET_IS_FINITE":
            # Property: recovery_attempts <= recovery_budget
            # Negation: recovery attempts exceeded finite recovery budget
            return (
                v["recovery_attempts"] > v["recovery_budget"],
                "Recovery attempts exceeded finite recovery budget.",
            )

        elif property_id == "PROP_030_RECOVERY_CANNOT_ESCALATE_CAPABILITY":
            # Property: NOT recovery_planner_can_escalate
            # Negation: recovery planner was able to escalate capability class
            return (
                v["recovery_planner_can_escalate"] == True,
                "Recovery planner was able to escalate capability class directly.",
            )

        # Phase 2J Properties: Policy Mutation Firewall & Safety Regression Detection

        elif property_id == "PROP_031_MUTATION_HUMAN_ZONE_GUARD_REMOVAL_DETECTED":
            # Property: human_guard_removed -> regression_detected_human_zone
            # Negation: human guard removed but regression not detected
            return (
                z3.And(v["human_guard_removed"] == True, v["regression_detected_human_zone"] == False),
                "Policy mutation removing human-zone guard was not detected as a regression.",
            )

        elif property_id == "PROP_032_MUTATION_CONFIDENCE_WEAKENING_CANNOT_EVADE_ASSURANCE":
            # Property: confidence_weakened -> NOT evades_assurance
            # Negation: confidence weakened AND evades assurance
            return (
                z3.And(v["confidence_weakened"] == True, v["evades_assurance"] == True),
                "Policy mutation weakening target confidence requirement evaded assurance detection.",
            )

        elif property_id == "PROP_033_MUTATION_CONTRADICTION_REMOVAL_DETECTED":
            # Property: contradiction_guard_removed -> regression_detected_contradiction
            # Negation: contradiction guard removed but regression not detected
            return (
                z3.And(v["contradiction_guard_removed"] == True, v["regression_detected_contradiction"] == False),
                "Policy mutation removing contradiction blocking was not detected as a regression.",
            )

        elif property_id == "PROP_034_MUTATION_CANNOT_DISABLE_STATE_BOUND_AUTHORIZATION":
            # Property: state_binding_disabled -> regression_detected_state_bound
            # Negation: state binding disabled but regression not detected
            return (
                z3.And(v["state_binding_disabled"] == True, v["regression_detected_state_bound"] == False),
                "Policy mutation silently disabled state-bound authorization without regression detection.",
            )

        elif property_id == "PROP_035_MUTATION_CANNOT_DISABLE_EXECUTION_REVALIDATION":
            # Property: revalidation_disabled -> regression_detected_revalidation
            # Negation: execution revalidation disabled but regression not detected
            return (
                z3.And(v["revalidation_disabled"] == True, v["regression_detected_revalidation"] == False),
                "Policy mutation silently disabled execution revalidation without regression detection.",
            )

        elif property_id == "PROP_036_MUTATION_CANNOT_DISABLE_RECOVERY_CONTAINMENT":
            # Property: recovery_containment_disabled -> regression_detected_recovery
            # Negation: recovery containment disabled but regression not detected
            return (
                z3.And(v["recovery_containment_disabled"] == True, v["regression_detected_recovery"] == False),
                "Policy mutation silently disabled recovery containment without regression detection.",
            )

        # Phase 2K Properties: Combinatorial Attacks, Dynamic Trajectories & Safe Repairs

        elif property_id == "PROP_037_COMPOUND_SAFETY_MUTATION_DETECTED":
            # Property: is_compound_mutation -> compound_regression_detected
            # Negation: compound mutation occurred but regression was not detected
            return (
                z3.And(v["is_compound_mutation"] == True, v["compound_regression_detected"] == False),
                "Compound safety mutation occurred without regression detection.",
            )

        elif property_id == "PROP_038_AMPLIFYING_MUTATION_INTERACTION_DETECTED":
            # Property: is_amplifying_interaction -> amplifying_detected
            # Negation: amplifying interaction occurred but was not detected
            return (
                z3.And(v["is_amplifying_interaction"] == True, v["amplifying_detected"] == False),
                "Amplifying mutation interaction occurred without detection.",
            )

        elif property_id == "PROP_039_TRAJECTORY_REGRESSION_REMAINS_BLOCKABLE":
            # Property: trajectory_regression_present -> trajectory_blockable_by_reval
            # Negation: trajectory regression present but not blockable by revalidation
            return (
                z3.And(v["trajectory_regression_present"] == True, v["trajectory_blockable_by_reval"] == False),
                "Dynamic trajectory regression was not interceptable by revalidation.",
            )

        elif property_id == "PROP_040_REPAIR_PROPOSAL_CANNOT_MODIFY_PRODUCTION_POLICY":
            # Property: NOT repair_modifies_production_policy
            # Negation: repair proposal directly modified production policy
            return (
                v["repair_modifies_production_policy"] == True,
                "Repair proposal directly modified live production policy.",
            )

        elif property_id == "PROP_041_REPAIR_MUST_PASS_EXISTING_SAFETY_FIREWALL":
            # Property: NOT repair_proposal_applied_without_validation
            # Negation: repair proposal applied without firewall validation
            return (
                v["repair_proposal_applied_without_validation"] == True,
                "Repair proposal was applied without passing through safety firewall validation.",
            )

        elif property_id == "PROP_042_REPAIR_CANNOT_WEAKEN_AUTHORIZATION_BOUNDARY":
            # Property: repair_weakens_auth_boundary -> NOT repair_accepted_with_weakened_boundary
            # Negation: repair weakened authorization boundary AND was accepted
            return (
                z3.And(v["repair_weakens_auth_boundary"] == True, v["repair_accepted_with_weakened_boundary"] == True),
                "Repair proposal weakened authorization boundary but was accepted.",
            )

        elif property_id == "PROP_043_TRAJECTORY_COUNTEREXAMPLE_IS_REPRODUCIBLE":
            # Property: trajectory_counterexample_deterministic == True
            # Negation: trajectory counterexample is non-deterministic
            return (
                v["trajectory_counterexample_deterministic"] == False,
                "Dynamic trajectory counterexample was not deterministically reproducible.",
            )

        elif property_id == "PROP_044_INCONCLUSIVE_REPAIR_IS_NOT_AUTO_APPLIED":
            # Property: repair_is_inconclusive -> NOT inconclusive_repair_auto_applied
            # Negation: repair was inconclusive BUT was automatically applied
            return (
                z3.And(v["repair_is_inconclusive"] == True, v["inconclusive_repair_auto_applied"] == True),
                "Inconclusive repair proposal was automatically applied into production.",
            )

        elif property_id == "PROP_045_HARDWARE_CANNOT_ACTUATE_WITHOUT_AUTHORIZATION":
            # Property: hardware_actuated -> has_ticket
            # Negation: hardware actuated without ticket
            return (
                z3.And(v["hardware_actuated"] == True, v["has_ticket"] == False),
                "Hardware endpoint actuated without an AuthorizationTicket.",
            )

        elif property_id == "PROP_046_INVALID_TICKET_CANNOT_ACTUATE":
            # Property: hardware_actuated -> ticket_is_valid
            # Negation: hardware actuated with invalid ticket
            return (
                z3.And(v["hardware_actuated"] == True, v["ticket_is_valid"] == False),
                "Hardware endpoint actuated with an invalid cryptographic ticket.",
            )

        elif property_id == "PROP_047_EXPIRED_TICKET_CANNOT_ACTUATE":
            # Property: hardware_actuated -> NOT ticket_is_expired
            # Negation: hardware actuated with expired ticket
            return (
                z3.And(v["hardware_actuated"] == True, v["ticket_is_expired"] == True),
                "Hardware endpoint actuated with an expired AuthorizationTicket.",
            )

        elif property_id == "PROP_048_REPLAYED_TICKET_CANNOT_ACTUATE":
            # Property: hardware_actuated -> NOT ticket_is_replayed
            # Negation: hardware actuated with replayed ticket
            return (
                z3.And(v["hardware_actuated"] == True, v["ticket_is_replayed"] == True),
                "Hardware endpoint actuated with a replayed/already consumed ticket.",
            )

        elif property_id == "PROP_049_TARGET_MISMATCH_CANNOT_ACTUATE":
            # Property: hardware_actuated -> NOT target_is_mismatched
            # Negation: hardware actuated on mismatched target
            return (
                z3.And(v["hardware_actuated"] == True, v["target_is_mismatched"] == True),
                "Hardware endpoint actuated on target mismatched with ticket authorization.",
            )

        elif property_id == "PROP_050_ACTION_MISMATCH_CANNOT_ACTUATE":
            # Property: hardware_actuated -> NOT action_is_mismatched
            # Negation: hardware actuated on mismatched action
            return (
                z3.And(v["hardware_actuated"] == True, v["action_is_mismatched"] == True),
                "Hardware endpoint actuated on action type mismatched with ticket authorization.",
            )

        elif property_id == "PROP_051_STALE_AUTHORIZATION_CANNOT_ACTUATE":
            # Property: hardware_actuated -> NOT auth_is_stale
            # Negation: hardware actuated with stale authorization context
            return (
                z3.And(v["hardware_actuated"] == True, v["auth_is_stale"] == True),
                "Hardware endpoint actuated with stale world-state authorization context.",
            )

        else:
            # Fallback trivial unsatisfiable negation
            return (z3.BoolVal(False), "Generic unnegated property")


    def _extract_counterexample(self, model: z3.ModelRef, v: Dict[str, Any]) -> Dict[str, Any]:
        """Convert Z3 model assignments into clean, human-readable domain values."""
        human_zone_map = {0: "CLEAR", 1: "OCCUPIED", 2: "WARNING"}
        cooling_map = {0: "INACTIVE", 1: "ACTIVE", 2: "DEGRADED"}
        action_map = {0: "NONE", 1: "CLOSE_VALVE", 2: "OPEN_VALVE"}
        decision_map = {0: "DENY", 1: "ALLOW", 2: "NEED_MORE_EVIDENCE"}
        contradiction_map = {0: "NONE", 1: "LOW", 2: "HIGH"}
        action_class_map = {0: "INFORMATION_ACTION", 1: "CONSEQUENTIAL_ACTION"}

        def get_int(key: str, default: int = 0) -> int:
            val = model.eval(v[key])
            try:
                return val.as_long()
            except Exception:
                return default

        def get_bool(key: str, default: bool = False) -> bool:
            val = model.eval(v[key])
            return z3.is_true(val)

        def get_float(key: str, default: float = 0.0) -> float:
            val = model.eval(v[key])
            try:
                return float(val.as_decimal(4).replace("?", ""))
            except Exception:
                return default

        hz = get_int("human_zone")
        cl = get_int("cooling")
        act = get_int("action")
        dec = get_int("policy_decision")
        cont = get_int("contradiction_severity")

        result = {
            "human_zone": human_zone_map.get(hz, f"UNKNOWN_{hz}"),
            "cooling": cooling_map.get(cl, f"UNKNOWN_{cl}"),
            "action": action_map.get(act, f"UNKNOWN_{act}"),
            "policy_decision": decision_map.get(dec, f"UNKNOWN_{dec}"),
            "confidence": get_float("confidence"),
            "contradiction_severity": contradiction_map.get(cont, f"UNKNOWN_{cont}"),
            "has_conflicted_constraint": get_bool("has_conflicted_constraint"),
            "has_stale_constraint": get_bool("has_stale_constraint"),
            "has_ticket": get_bool("has_ticket"),
            "world_mutated": get_bool("world_mutated"),
        }

        # Phase 2F: Include state-binding variables if present
        if "auth_world_version" in v:
            result["auth_world_version"] = get_int("auth_world_version", 1)
            result["exec_world_version"] = get_int("exec_world_version", 1)
            result["auth_policy_version"] = get_int("auth_policy_version", 1)
            result["exec_policy_version"] = get_int("exec_policy_version", 1)
            result["auth_constraint_hash"] = get_int("auth_constraint_hash", 0)
            result["exec_constraint_hash"] = get_int("exec_constraint_hash", 0)
            result["revalidation_passed"] = get_bool("revalidation_passed")
            result["execution_attempted"] = get_bool("execution_attempted")

        # Phase 2G: Active Evidence Acquisition variables
        if "action_class" in v:
            ac = get_int("action_class")
            result["action_class"] = action_class_map.get(ac, f"UNKNOWN_{ac}")
            result["is_info_action"] = get_bool("is_info_action")
            result["is_consequential_action"] = get_bool("is_consequential_action")
            result["planner_can_actuate"] = get_bool("planner_can_actuate")
            result["planner_can_mint_ticket"] = get_bool("planner_can_mint_ticket")
            result["evidence_iterations"] = get_int("evidence_iterations", 0)
            result["evidence_budget"] = get_int("evidence_budget", 3)
            result["has_new_evidence"] = get_bool("has_new_evidence")
            result["is_planner_proposal"] = get_bool("is_planner_proposal")

        # Phase 2H: Adversarial Physical Environment variables
        if "human_transition_to_occupied" in v:
            result["human_transition_to_occupied"] = get_bool("human_transition_to_occupied")
            result["has_admissible_new_evidence"] = get_bool("has_admissible_new_evidence")
            result["actuator_fault"] = get_bool("actuator_fault")
            result["verification_status"] = get_int("verification_status", 0)
            result["prev_decision"] = decision_map.get(get_int("prev_decision", 0), "DENY")
            result["safety_degraded"] = get_bool("safety_degraded")
            result["adversary_can_mint_ticket"] = get_bool("adversary_can_mint_ticket")
            result["adversary_can_bypass_enclave"] = get_bool("adversary_can_bypass_enclave")
            result["environmental_drift"] = get_bool("environmental_drift")

        # Phase 2I: Fault Containment, Quarantine & Autonomous Recovery variables
        if "action_failed" in v:
            result["action_failed"] = get_bool("action_failed")
            result["ticket_invalidated"] = get_bool("ticket_invalidated")
            result["component_quarantined"] = get_bool("component_quarantined")
            result["blocked_capability_executed"] = get_bool("blocked_capability_executed")
            result["recovery_reuses_stale_ticket"] = get_bool("recovery_reuses_stale_ticket")
            result["recovery_fresh_eval_done"] = get_bool("recovery_fresh_eval_done")
            result["consequential_action_authorized"] = get_bool("consequential_action_authorized")
            result["sensor_quarantined"] = get_bool("sensor_quarantined")
            result["quarantined_sensor_evidence_admitted"] = get_bool("quarantined_sensor_evidence_admitted")
            result["recovery_attempts"] = get_int("recovery_attempts", 0)
            result["recovery_budget"] = get_int("recovery_budget", 3)
            result["recovery_action_class"] = action_class_map.get(get_int("recovery_action_class", 0), "INFORMATION_ACTION")
            result["recovery_planner_can_escalate"] = get_bool("recovery_planner_can_escalate")

        # Phase 2J: Policy Mutation Firewall variables
        if "human_guard_removed" in v:
            result["human_guard_removed"] = get_bool("human_guard_removed")
            result["regression_detected_human_zone"] = get_bool("regression_detected_human_zone")
            result["confidence_weakened"] = get_bool("confidence_weakened")
            result["evades_assurance"] = get_bool("evades_assurance")
            result["regression_detected_confidence"] = get_bool("regression_detected_confidence")
            result["contradiction_guard_removed"] = get_bool("contradiction_guard_removed")
            result["regression_detected_contradiction"] = get_bool("regression_detected_contradiction")
            result["state_binding_disabled"] = get_bool("state_binding_disabled")
            result["regression_detected_state_bound"] = get_bool("regression_detected_state_bound")
            result["revalidation_disabled"] = get_bool("revalidation_disabled")
            result["regression_detected_revalidation"] = get_bool("regression_detected_revalidation")
            result["recovery_containment_disabled"] = get_bool("recovery_containment_disabled")
            result["regression_detected_recovery"] = get_bool("regression_detected_recovery")

        # Phase 2K: Combinatorial Attacks, Dynamic Trajectories & Safe Repairs
        if "is_compound_mutation" in v:
            result["is_compound_mutation"] = get_bool("is_compound_mutation")
            result["compound_regression_detected"] = get_bool("compound_regression_detected")
            result["is_amplifying_interaction"] = get_bool("is_amplifying_interaction")
            result["amplifying_detected"] = get_bool("amplifying_detected")
            result["trajectory_regression_present"] = get_bool("trajectory_regression_present")
            result["trajectory_blockable_by_reval"] = get_bool("trajectory_blockable_by_reval")
            result["repair_modifies_production_policy"] = get_bool("repair_modifies_production_policy")
            result["repair_proposal_applied_without_validation"] = get_bool("repair_proposal_applied_without_validation")
            result["repair_weakens_auth_boundary"] = get_bool("repair_weakens_auth_boundary")
            result["repair_accepted_with_weakened_boundary"] = get_bool("repair_accepted_with_weakened_boundary")
            result["trajectory_counterexample_deterministic"] = get_bool("trajectory_counterexample_deterministic")
            result["repair_is_inconclusive"] = get_bool("repair_is_inconclusive")
            result["inconclusive_repair_auto_applied"] = get_bool("inconclusive_repair_auto_applied")

        return result


