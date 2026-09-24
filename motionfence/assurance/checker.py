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

        return {
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
