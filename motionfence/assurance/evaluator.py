"""Adversarial evaluation engine, property-based fuzzing orchestrator, and test case shrinker."""

from typing import Any, Dict, List, Optional
import time

from motionfence.assurance.models import (
    AssuranceFinding,
    FindingStatus,
    FindingSeverity,
    AssuranceScope,
    FormalState,
    AssuranceReport,
    AdversarialCaseResult,
    AdversarialOutcomeCategory,
)
from motionfence.assurance.adversarial import AdversarialGenerator
from motionfence.assurance.counterexample import CounterexampleFormatter
from motionfence.policy.engine import PolicyEngine
from motionfence.policy.models import PolicyDecision, DecisionType, Policy
from motionfence.models.actions import ActionProposal, ActionType
from motionfence.evidence.models import Evidence, EvidenceSource, ContradictionReport
from motionfence.constraints.grounding import LocalDeterministicClaimGrounder, SupportStatus
from motionfence.constraints.models import CandidateConstraint, ConstraintType, ConstraintStatus, PlantContext
from motionfence.constraints.validator import ConstraintValidator
from motionfence.knowledge.trust import SourceCategory, SourceTrustClassifier, EvidenceRole


class AdversarialEvaluator:
    """Evaluates MotionFence safety boundaries against combinatorial adversarial inputs."""

    def __init__(
        self,
        seed: int = 42,
        policy: Optional[Policy] = None,
    ) -> None:
        self.seed = seed
        self.generator = AdversarialGenerator(seed=seed)
        self.policy = policy or Policy()
        self.claim_grounder = LocalDeterministicClaimGrounder()
        self.constraint_validator = ConstraintValidator()
        self.trust_classifier = SourceTrustClassifier()

    def run_evaluation(
        self,
        num_random_cases: int = 100,
        include_boundary_cases: bool = True,
        include_knowledge_cases: bool = True,
    ) -> AssuranceReport:
        """Execute a comprehensive adversarial evaluation run and aggregate machine-readable findings."""
        start_time = time.time()
        findings: List[AssuranceFinding] = []
        counterexamples: List[Dict[str, Any]] = []
        outcomes_count: Dict[str, int] = {cat.value: 0 for cat in AdversarialOutcomeCategory}

        total_cases_run = 0
        unsafe_allows = 0

        # 1. Boundary confidence & state combinations
        if include_boundary_cases:
            boundary_cases = self.generator.generate_boundary_confidence_cases()
            for case in boundary_cases:
                total_cases_run += 1
                res = self._evaluate_physical_case(case)
                outcomes_count[res.category.value] += 1
                if res.category == AdversarialOutcomeCategory.FALSE_ALLOW:
                    unsafe_allows += 1
                    shrunk = self._shrink_physical_case(case)
                    counterexamples.append(shrunk)
                    findings.append(
                        AssuranceFinding(
                            property_id="PROP_001_HUMAN_ZONE_PROHIBITION",
                            property_name="Adversarial False ALLOW Discovery",
                            status=FindingStatus.VIOLATED,
                            severity=FindingSeverity.CRITICAL,
                            scope=AssuranceScope.ADVERSARIAL_EVAL.value,
                            counterexample=shrunk,
                            explanation=f"Adversarial case permitted unsafe ALLOW: {shrunk}",
                        )
                    )

        # 2. Sensor contradiction cases
        contradiction_cases = self.generator.generate_contradiction_cases()
        for ccase in contradiction_cases:
            total_cases_run += 1
            res = self._evaluate_contradiction_case(ccase)
            outcomes_count[res.category.value] += 1
            if res.category == AdversarialOutcomeCategory.FALSE_ALLOW:
                unsafe_allows += 1
                counterexamples.append(ccase)

        # 3. Knowledge adversary cases (Grounding & Distortion)
        if include_knowledge_cases:
            knowledge_cases = self.generator.generate_knowledge_adversaries()
            for kcase in knowledge_cases:
                total_cases_run += 1
                res = self._evaluate_knowledge_case(kcase)
                outcomes_count[res.category.value] += 1
                if res.category == AdversarialOutcomeCategory.FALSE_ALLOW:
                    unsafe_allows += 1
                    counterexamples.append(kcase)

            # Source trust cases
            source_cases = self.generator.generate_source_trust_adversaries()
            for scase in source_cases:
                total_cases_run += 1
                res = self._evaluate_source_trust_case(scase)
                outcomes_count[res.category.value] += 1
                if res.category == AdversarialOutcomeCategory.FALSE_ALLOW:
                    unsafe_allows += 1
                    counterexamples.append(scase)

        # 4. Randomized combinatorial scenario fuzzing
        for _ in range(num_random_cases):
            total_cases_run += 1
            rcase = self.generator.generate_randomized_scenario()
            res = self._evaluate_physical_case(rcase)
            outcomes_count[res.category.value] += 1
            if res.category == AdversarialOutcomeCategory.FALSE_ALLOW:
                unsafe_allows += 1
                shrunk = self._shrink_physical_case(rcase)
                counterexamples.append(shrunk)
                findings.append(
                    AssuranceFinding(
                        property_id="PROP_RANDOM_VIOLATION",
                        property_name="Randomized Scenario False ALLOW Discovery",
                        status=FindingStatus.VIOLATED,
                        severity=FindingSeverity.CRITICAL,
                        scope=AssuranceScope.ADVERSARIAL_EVAL.value,
                        counterexample=shrunk,
                        explanation=f"Random scenario discovered false ALLOW: {shrunk}",
                    )
                )

        elapsed = time.time() - start_time

        return AssuranceReport(
            runtime_version="0.4.0",
            policy_version="2026.1",
            generator_version="1.0.0",
            seed=self.seed,
            properties_checked=len(findings),
            properties_satisfied=len([f for f in findings if f.status == FindingStatus.SATISFIED]),
            properties_violated=len([f for f in findings if f.status == FindingStatus.VIOLATED]),
            unknown_properties=len([f for f in findings if f.status == FindingStatus.UNKNOWN]),
            findings=findings,
            counterexamples=counterexamples,
            adversarial_cases=total_cases_run,
            unsafe_authorizations_discovered=unsafe_allows,
            adversarial_outcomes=outcomes_count,
            execution_time_seconds=elapsed,
        )

    def _evaluate_physical_case(self, case: Dict[str, Any]) -> AdversarialCaseResult:
        """Evaluate a single physical state scenario against PolicyEngine."""
        hz = case.get("human_zone", "CLEAR")
        cool = case.get("cooling", "ACTIVE")
        pump = case.get("pump_p1", "INACTIVE")
        act = ActionType(case.get("action_type", "CLOSE_VALVE"))
        target = case.get("target", "valve_b")
        conf = float(case.get("confidence", 0.95))
        cont_sev = case.get("contradiction_severity", "NONE")

        formal_state = FormalState(
            valves={"valve_a": "OPEN", "valve_b": "OPEN"},
            cooling=cool,
            human_zone=hz,
            pumps={"pump_p1": pump},
        )
        world_snapshot = formal_state.to_world_state()

        evidence_list = [
            Evidence(
                source=EvidenceSource.PRESSURE_SENSOR,
                target=target,
                observation={"leak_detected": False, "status": "nominal"},
                confidence=conf,
                provenance="sensor_pressure_01",
            )
        ]

        if cont_sev == "HIGH":
            evidence_list.append(
                Evidence(
                    source=EvidenceSource.VISION,
                    target=target,
                    observation={"leak_detected": True, "status": "leak"},
                    confidence=0.95,
                    provenance="sensor_vision_01",
                )
            )

        active_constraints = []
        if case.get("has_conflicted_constraint"):
            active_constraints.append(
                CandidateConstraint(
                    constraint_id="cst_conflict_test",
                    constraint_type=ConstraintType.PROHIBITION,
                    target=target,
                    action=act,
                    condition={},
                    source_evidence_id="ev_conflict",
                    status=ConstraintStatus.CONFLICTED,
                    description="Conflicted constraint probe",
                )
            )

        if case.get("has_stale_constraint"):
            active_constraints.append(
                CandidateConstraint(
                    constraint_id="cst_stale_test",
                    constraint_type=ConstraintType.PROHIBITION,
                    target=target,
                    action=act,
                    condition={},
                    source_evidence_id="ev_stale",
                    status=ConstraintStatus.STALE,
                    description="Stale constraint probe",
                )
            )

        proposal = ActionProposal(
            action_type=act,
            target=target,
            parameters={},
            model_confidence=conf,
            rationale="Adversarial physical probe",
            supporting_evidence_ids=[e.id for e in evidence_list],
        )

        decision = PolicyEngine.evaluate(
            proposal,
            world_snapshot,
            evidence_list,
            policy=self.policy,
            active_constraints=active_constraints,
        )

        # Ground-truth safety determination
        is_objectively_safe = (
            hz == "CLEAR"
            and cool == "ACTIVE"
            and target in ["valve_a", "valve_b"]
            and conf >= self.policy.min_target_confidence
            and cont_sev != "HIGH"
            and not case.get("has_conflicted_constraint")
            and not case.get("has_stale_constraint")
        )

        # Detect outcomes
        if decision.decision == DecisionType.ALLOW:
            if not is_objectively_safe:
                # Critical safety defect
                return AdversarialCaseResult(
                    category=AdversarialOutcomeCategory.FALSE_ALLOW,
                    is_safe=False,
                    input_parameters=case,
                    observed_verdict=decision.decision.value,
                    reasons=[r.details for r in decision.reasons],
                    notes="UNSAFE AUTHORIZATION: ALLOW granted on objectively unsafe conditions.",
                )
            return AdversarialCaseResult(
                category=AdversarialOutcomeCategory.SAFE_ALLOW,
                is_safe=True,
                input_parameters=case,
                observed_verdict=decision.decision.value,
                reasons=[r.details for r in decision.reasons],
            )
        elif decision.decision == DecisionType.DENY:
            if is_objectively_safe:
                return AdversarialCaseResult(
                    category=AdversarialOutcomeCategory.FALSE_DENY,
                    is_safe=True,
                    input_parameters=case,
                    observed_verdict=decision.decision.value,
                    reasons=[r.details for r in decision.reasons],
                    notes="Over-conservative rejection on valid parameters.",
                )
            return AdversarialCaseResult(
                category=AdversarialOutcomeCategory.SAFE_DENY,
                is_safe=True,
                input_parameters=case,
                observed_verdict=decision.decision.value,
                reasons=[r.details for r in decision.reasons],
            )
        else:  # NEED_MORE_EVIDENCE
            return AdversarialCaseResult(
                category=AdversarialOutcomeCategory.SAFE_NEED_MORE_EVIDENCE,
                is_safe=True,
                input_parameters=case,
                observed_verdict=decision.decision.value,
                reasons=[r.details for r in decision.reasons],
            )

    def _evaluate_contradiction_case(self, case: Dict[str, Any]) -> AdversarialCaseResult:
        """Evaluate multi-sensor evidence contradiction handling."""
        expected_high = case["expected_high_contradiction"]
        target = case.get("target", "valve_b")
        ev_items = []
        for s_id, data in case["observations"].items():
            src_str = data.get("source", "pressure_sensor")
            src_enum = EvidenceSource.VISION if src_str == "vision" else EvidenceSource.PRESSURE_SENSOR
            ev_items.append(
                Evidence(
                    id=s_id,
                    source=src_enum,
                    target=target,
                    observation=data,
                    confidence=data["confidence"],
                    provenance=f"sensor_{s_id}",
                )
            )

        from motionfence.evidence.contradiction import ContradictionDetector, ContradictionSeverity
        report = ContradictionDetector.detect(ev_items, target=target)

        is_high = report.severity == ContradictionSeverity.HIGH
        if expected_high and not is_high:
            return AdversarialCaseResult(
                category=AdversarialOutcomeCategory.FALSE_ALLOW,
                is_safe=False,
                input_parameters=case,
                observed_verdict=report.severity.value,
                reasons=[r for r in report.sources],
                notes="Contradiction failed to trigger HIGH severity.",
            )
        return AdversarialCaseResult(
            category=AdversarialOutcomeCategory.SAFE_DENY if is_high else AdversarialOutcomeCategory.SAFE_ALLOW,
            is_safe=True,
            input_parameters=case,
            observed_verdict=report.severity.value,
            reasons=[f"Contradiction severity: {report.severity.value}"],
        )

    def _evaluate_knowledge_case(self, case: Dict[str, Any]) -> AdversarialCaseResult:
        """Evaluate adversarial claim distortion against ClaimGrounder."""
        source_text = case["source_text"]
        claim_text = case["claim_text"]
        target = case["target"]

        from motionfence.knowledge.models import KnowledgeEvidence
        source_ev = KnowledgeEvidence(
            id="ev_kb_source_01",
            query="safety rule",
            title="Manual",
            source_url="local://plant_manual",
            content=source_text,
            provenance="local:plant_manual",
            source_metadata={},
            confidence=1.0,
        )

        candidate = CandidateConstraint(
            constraint_type=ConstraintType.PROHIBITION,
            target=target,
            action=ActionType.CLOSE_VALVE,
            condition={"pump_p1": "ACTIVE"},
            source_evidence_id="ev_kb_source_01",
            confidence=0.98,
            claim_text=claim_text,
        )

        cert = self.claim_grounder.ground(
            constraint=candidate,
            source_evidence=source_ev,
        )

        # An adversarial distortion must NOT receive SUPPORTED status
        if cert.support_status == SupportStatus.SUPPORTED:
            return AdversarialCaseResult(
                category=AdversarialOutcomeCategory.FALSE_ALLOW,
                is_safe=False,
                input_parameters=case,
                observed_verdict=cert.support_status.value,
                reasons=[cert.support_type.value],
                notes=f"Distorted claim '{claim_text}' was erroneously SUPPORTED.",
            )
        return AdversarialCaseResult(
            category=AdversarialOutcomeCategory.SAFE_DENY,
            is_safe=True,
            input_parameters=case,
            observed_verdict=cert.support_status.value,
            reasons=[cert.support_type.value],
        )

    def _evaluate_source_trust_case(self, case: Dict[str, Any]) -> AdversarialCaseResult:
        """Evaluate adversarial source trust and equipment applicability gating."""
        domain = case["domain"]
        age_days = case.get("age_days", 1)
        manual_model = case.get("manual_equipment_model", "Centrifugal-P100-Standard")
        plant_model = case.get("plant_equipment_model", "Centrifugal-P100-Standard")
        from motionfence.knowledge.trust import CorroborationStatus
        corroboration = (
            CorroborationStatus.DUPLICATE_SOURCE
            if case.get("is_mirror_duplicate")
            else CorroborationStatus.SINGLE_SOURCE
        )

        from motionfence.knowledge.models import KnowledgeEvidence
        from motionfence.constraints.validator import ConstraintValidator
        from motionfence.constraints.models import CandidateConstraint, ConstraintType, PlantContext

        kb = KnowledgeEvidence(
            id="ev_adv_trust_01",
            query="safety guidance",
            title=f"Manual for {manual_model}",
            source_url=f"https://{domain}/manual",
            content=f"Guidance on {manual_model}: Valve B must not be closed while Pump P1 is active.",
            retrieved_at=time.time() - (age_days * 86400.0),
            provenance=f"test:{domain}",
            source_metadata={},
            confidence=0.85,
        )

        candidate = CandidateConstraint(
            constraint_type=ConstraintType.PROHIBITION,
            target="valve_b",
            action=ActionType.CLOSE_VALVE,
            condition={"pump_p1": "ACTIVE"},
            source_evidence_id="ev_adv_trust_01",
            confidence=0.95,
            claim_text="Valve B must not be closed while Pump P1 is active.",
        )

        plant_context = PlantContext(
            equipment_model=plant_model,
            equipment_id="pump_p1",
            authorized_targets=["valve_a", "valve_b"],
        )

        is_admissible = ConstraintValidator.check_admissibility(
            constraint=candidate,
            evidence_registry={"ev_adv_trust_01": kb},
            plant_context=plant_context,
            corroboration_status=corroboration,
        )

        # None of the source trust adversary cases should become admissible active safety constraints
        if is_admissible:
            return AdversarialCaseResult(
                category=AdversarialOutcomeCategory.FALSE_ALLOW,
                is_safe=False,
                input_parameters=case,
                observed_verdict="ADMISSIBLE",
                reasons=candidate.admissibility_notes,
                notes=f"Untrusted or mismatched source '{domain}' was erroneously admitted as active safety constraint.",
            )
        return AdversarialCaseResult(
            category=AdversarialOutcomeCategory.SAFE_DENY,
            is_safe=True,
            input_parameters=case,
            observed_verdict="INADMISSIBLE",
            reasons=candidate.admissibility_notes,
        )

    def _shrink_physical_case(self, case: Dict[str, Any]) -> Dict[str, Any]:
        """Shrink a complex failing case to minimal offending parameters."""
        essential_keys = ["human_zone", "cooling", "pump_p1", "action_type", "target", "confidence"]
        minimized = {k: case[k] for k in essential_keys if k in case}
        minimized["minimized"] = True
        return minimized
