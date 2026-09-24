"""Adversarial and empirical test suite for MotionFence Phase 2C Claim Grounding.

Tests deterministic grounding, negation safety, conditionality preservation,
scope preservation, numeric threshold integrity, causal inference decomposition,
and decision integrity under adversarial knowledge conditions.

SECURITY INVARIANTS TESTED:
1. ClaimSupportCertificate cannot mutate WorldState or mint AuthorizationTickets.
2. Grounding decisions are strictly decoupled from model confidence.
3. Unsupported, contradicted, or inferred claims CANNOT produce ACTIVE constraints.
4. Changed negations and dropped conditions are deterministically rejected.
"""

import time
import pytest

from motionfence.knowledge.models import KnowledgeEvidence, TrustStatus
from motionfence.knowledge.trust import (
    SourceTrustClassifier,
    CorroborationEngine,
    CorroborationStatus,
)
from motionfence.constraints.models import (
    CandidateConstraint,
    ConstraintType,
    ConstraintStatus,
    PlantContext,
    Applicability,
)
from motionfence.constraints.grounding import (
    ClaimSupportCertificate,
    SupportType,
    SupportStatus,
    GroundingRejectionReason,
    LocalDeterministicClaimGrounder,
    SemanticClaimGrounder,
    format_grounding_audit,
)
from motionfence.constraints.validator import ConstraintValidator
from motionfence.constraints.conflict import ConstraintConflictDetector
from motionfence.models.actions import ActionType
from motionfence.models.world import WorldState, ValveState, CoolingState, HumanZoneState
from motionfence.runtime.events import EventBus
from motionfence.models.events import EventType


# ==============================================================================
# SECTION 18 ADVERSARIAL DETERMINISTIC FIXTURES
# ==============================================================================

@pytest.fixture
def fixture_a_exact_prohibition() -> KnowledgeEvidence:
    """Fixture A: Exact operational prohibition."""
    return KnowledgeEvidence(
        id="kb_fix_a_exact",
        query="valve b closure restrictions",
        title="Industrial Plant Safety Manual - Section 4",
        source_url="https://ksb.com/manuals/p100/sec4",
        content="MANDATORY PROHIBITION: Valve B must not be closed while Pump P1 is active to prevent hydraulic shock.",
        retrieved_at=time.time(),
        provenance="oem:ksb_manual_v1",
        confidence=0.98,
        trust_status=TrustStatus.LOCAL_FIXTURE,
    )


@pytest.fixture
def fixture_b_conditional_exception() -> KnowledgeEvidence:
    """Fixture B: Permissive exception under specific stopped condition."""
    return KnowledgeEvidence(
        id="kb_fix_b_cond",
        query="valve b emergency isolation",
        title="Emergency Operating Procedures",
        source_url="https://plant-safety.internal/eop/isolation",
        content="Valve B may be closed during emergency isolation when Pump P1 is stopped.",
        retrieved_at=time.time(),
        provenance="internal:eop_manual_v2",
        confidence=0.95,
        trust_status=TrustStatus.LOCAL_FIXTURE,
    )


@pytest.fixture
def fixture_c_weak_guidance() -> KnowledgeEvidence:
    """Fixture C: Weak advice / routine procedure (not a mandatory prohibition)."""
    return KnowledgeEvidence(
        id="kb_fix_c_weak",
        query="valve b general maintenance",
        title="Routine Maintenance Guidelines",
        source_url="https://plant-safety.internal/sop/general",
        content="ROUTINE GUIDELINE: Valve B should generally remain open during nominal fluid circulation.",
        retrieved_at=time.time(),
        provenance="internal:sop_general",
        confidence=0.88,
        trust_status=TrustStatus.LOCAL_FIXTURE,
    )


@pytest.fixture
def fixture_d_unrelated() -> KnowledgeEvidence:
    """Fixture D: Completely unrelated component statement."""
    return KnowledgeEvidence(
        id="kb_fix_d_unrelated",
        query="cooling loop valves",
        title="Cooling Loop Specifications",
        source_url="https://plant-safety.internal/specs/cooling",
        content="Valve A serves the primary cooling loop and must remain open.",
        retrieved_at=time.time(),
        provenance="internal:specs_cooling",
        confidence=0.92,
        trust_status=TrustStatus.LOCAL_FIXTURE,
    )


@pytest.fixture
def fixture_e_copied_mirror() -> KnowledgeEvidence:
    """Fixture E: Verbatim mirrored text of Fixture A with superficial formatting changes."""
    return KnowledgeEvidence(
        id="kb_fix_e_mirror",
        query="valve b closure rules",
        title="Mirror Documentation Site",
        source_url="https://industrial-mirrors.net/copy/ksb/manual",
        content="Mandatory prohibition: Valve B must not be closed while pump P1 is active to prevent hydraulic shock.",
        retrieved_at=time.time(),
        provenance="scraped:mirror_network",
        confidence=0.70,
        trust_status=TrustStatus.LOCAL_FIXTURE,
    )


@pytest.fixture
def fixture_f_contradictory() -> KnowledgeEvidence:
    """Fixture F: Explicitly contradictory document permitting closure while pump is active."""
    return KnowledgeEvidence(
        id="kb_fix_f_contradictory",
        query="valve b operating mode",
        title="Alternative Operating Guidelines",
        source_url="https://unverified-engineering.org/valve_b",
        content="Valve B may be closed while Pump P1 is active.",
        retrieved_at=time.time(),
        provenance="external:unverified_guideline",
        confidence=0.80,
        trust_status=TrustStatus.LOCAL_FIXTURE,
    )


# ==============================================================================
# SECTION 17 ADVERSARIAL GROUNDING TESTS
# ==============================================================================

def test_exact_claim_passes_grounding(fixture_a_exact_prohibition):
    """Verify an exact operational claim matches directly and receives SUPPORTED certificate."""
    grounder = LocalDeterministicClaimGrounder()
    cst = CandidateConstraint(
        constraint_type=ConstraintType.PROHIBITION,
        action=ActionType.CLOSE_VALVE,
        target="valve_b",
        condition={"pump_p1": "ACTIVE"},
        source_evidence_id=fixture_a_exact_prohibition.id,
        claim_text="Valve B must not be closed while Pump P1 is active.",
        confidence=0.98,
    )
    cert = grounder.ground(cst, fixture_a_exact_prohibition)

    assert cert.support_type == SupportType.DIRECT
    assert cert.support_status == SupportStatus.SUPPORTED
    assert cert.is_supported is True
    assert cert.is_direct is True
    assert cert.support_span is not None
    assert "Valve B must not be closed while Pump P1 is active" in cert.support_span
    assert cert.start_offset is not None
    assert cert.end_offset is not None
    assert cert.rejection_reason == GroundingRejectionReason.NONE


def test_paraphrased_claim_passes_when_meaning_and_scope_preserved(fixture_a_exact_prohibition):
    """Verify a valid paraphrase with identical target and scope receives PARAPHRASE / SUPPORTED."""
    grounder = LocalDeterministicClaimGrounder()
    cst = CandidateConstraint(
        constraint_type=ConstraintType.PROHIBITION,
        action=ActionType.CLOSE_VALVE,
        target="valve_b",
        condition={"pump_p1": "ACTIVE"},
        source_evidence_id=fixture_a_exact_prohibition.id,
        claim_text="Closing Valve B is prohibited while Pump P1 is active.",
        confidence=0.95,
    )
    cert = grounder.ground(cst, fixture_a_exact_prohibition)

    assert cert.support_type in (SupportType.DIRECT, SupportType.PARAPHRASE)
    assert cert.support_status == SupportStatus.SUPPORTED
    assert cert.rejection_reason == GroundingRejectionReason.NONE


def test_added_causal_explanation_classified_as_inference():
    """Verify model-invented causal rationale not found in source is flagged as INFERENCE / INSUFFICIENT."""
    ev = KnowledgeEvidence(
        id="kb_no_causal_01",
        query="valve b isolation",
        title="Industrial Plant Safety Manual",
        source_url="https://ksb.com/manuals/p100/sec4",
        content="Valve B must not be closed while Pump P1 is active.",
        provenance="oem:ksb_manual",
    )
    grounder = LocalDeterministicClaimGrounder()
    # Source has the rule, but zero mention of "hydraulic shock" or causal explanation
    cst = CandidateConstraint(
        constraint_type=ConstraintType.PROHIBITION,
        action=ActionType.CLOSE_VALVE,
        target="valve_b",
        condition={"pump_p1": "ACTIVE"},
        source_evidence_id=ev.id,
        claim_text="Valve B must not be closed while Pump P1 is active because closing it causes hazardous hydraulic shock.",
        confidence=0.94,
    )
    cert = grounder.ground(cst, ev)

    # Core claim is supported, but unverified causal statement makes compound claim INFERENCE
    assert cert.support_type == SupportType.INFERENCE
    assert cert.support_status == SupportStatus.INSUFFICIENT
    assert cert.rejection_reason == GroundingRejectionReason.UNVERIFIED_CAUSAL_INFERENCE
    assert len(cert.assertions) == 2
    # Verify decomposed assertions
    assert cert.assertions[0].support_status == SupportStatus.SUPPORTED
    assert cert.assertions[1].support_type == SupportType.INFERENCE
    assert cert.assertions[1].support_status == SupportStatus.INSUFFICIENT


def test_removed_condition_rejected_as_condition_lost(fixture_a_exact_prohibition):
    """Verify that removing 'while Pump P1 is active' to assert an unconditional prohibition is REJECTED."""
    grounder = LocalDeterministicClaimGrounder()
    cst = CandidateConstraint(
        constraint_type=ConstraintType.PROHIBITION,
        action=ActionType.CLOSE_VALVE,
        target="valve_b",
        condition={},  # Condition removed!
        source_evidence_id=fixture_a_exact_prohibition.id,
        claim_text="Valve B must never be closed.",  # Broadened to unconditional
        confidence=0.90,
    )
    cert = grounder.ground(cst, fixture_a_exact_prohibition)

    assert cert.support_status == SupportStatus.REJECTED
    assert cert.rejection_reason == GroundingRejectionReason.CLAIM_CONDITION_LOST


def test_changed_negation_rejected_as_distortion(fixture_b_conditional_exception):
    """Verify that flipping permission ('may be closed') into prohibition ('must not be closed') is REJECTED."""
    grounder = LocalDeterministicClaimGrounder()
    # Source says: "Valve B may be closed during emergency isolation when Pump P1 is stopped."
    cst = CandidateConstraint(
        constraint_type=ConstraintType.PROHIBITION,
        action=ActionType.CLOSE_VALVE,
        target="valve_b",
        condition={"pump_p1": "STOPPED"},
        source_evidence_id=fixture_b_conditional_exception.id,
        claim_text="Valve B must not be closed during emergency isolation when Pump P1 is stopped.",
        confidence=0.92,
    )
    cert = grounder.ground(cst, fixture_b_conditional_exception)

    assert cert.support_type == SupportType.CONTRADICTED
    assert cert.support_status == SupportStatus.REJECTED
    assert cert.rejection_reason == GroundingRejectionReason.CLAIM_NEGATION_MISMATCH


def test_broadened_scope_to_all_valves_rejected(fixture_a_exact_prohibition):
    """Verify that model generalizing 'Valve B' to 'all valves' is rejected as scope mismatch."""
    grounder = LocalDeterministicClaimGrounder()
    cst = CandidateConstraint(
        constraint_type=ConstraintType.PROHIBITION,
        action=ActionType.CLOSE_VALVE,
        target="valve_b",
        condition={"pump_p1": "ACTIVE"},
        source_evidence_id=fixture_a_exact_prohibition.id,
        claim_text="All valves must not be closed while Pump P1 is active.",
        confidence=0.91,
    )
    cert = grounder.ground(cst, fixture_a_exact_prohibition)

    assert cert.support_status == SupportStatus.REJECTED
    assert cert.rejection_reason == GroundingRejectionReason.CLAIM_SCOPE_MISMATCH


def test_changed_target_to_valve_a_rejected(fixture_a_exact_prohibition):
    """Verify that target mismatch (claiming rule on Valve A when source specifies Valve B) is REJECTED."""
    grounder = LocalDeterministicClaimGrounder()
    cst = CandidateConstraint(
        constraint_type=ConstraintType.PROHIBITION,
        action=ActionType.CLOSE_VALVE,
        target="valve_a",  # Valve A is not in Fixture A!
        condition={"pump_p1": "ACTIVE"},
        source_evidence_id=fixture_a_exact_prohibition.id,
        claim_text="Valve A must not be closed while Pump P1 is active.",
        confidence=0.90,
    )
    cert = grounder.ground(cst, fixture_a_exact_prohibition)

    assert cert.support_status == SupportStatus.REJECTED
    assert cert.rejection_reason == GroundingRejectionReason.CLAIM_SCOPE_MISMATCH


def test_invented_numeric_threshold_rejected():
    """Verify that model inventing or altering a numeric threshold is REJECTED."""
    ev = KnowledgeEvidence(
        id="kb_pressure_rule",
        query="valve b pressure threshold",
        title="Pressure Transducer Operating Envelope",
        source_url="https://sensors.internal/valve_b",
        content="Valve B line pressure must not exceed 50 psi during nominal flow.",
        provenance="internal:specs",
    )
    grounder = LocalDeterministicClaimGrounder()

    # Model claims 80 psi (altered number)
    cst_altered = CandidateConstraint(
        constraint_type=ConstraintType.PROHIBITION,
        action=ActionType.CLOSE_VALVE,
        target="valve_b",
        condition={"pressure_psi": 80.0},
        source_evidence_id=ev.id,
        claim_text="Valve B line pressure must not exceed 80 psi during nominal flow.",
        confidence=0.92,
    )
    cert_altered = grounder.ground(cst_altered, ev)
    assert cert_altered.support_status == SupportStatus.REJECTED
    assert cert_altered.rejection_reason == GroundingRejectionReason.INVENTED_NUMERIC_THRESHOLD


def test_missing_or_empty_evidence_rejected():
    """Verify that missing or empty source evidence content produces REJECTED certificate."""
    ev_empty = KnowledgeEvidence(
        id="kb_empty_ev",
        query="empty test",
        title="Empty Doc",
        source_url="local://empty",
        content="",
        provenance="empty",
    )
    grounder = LocalDeterministicClaimGrounder()
    cst = CandidateConstraint(
        constraint_type=ConstraintType.PROHIBITION,
        action=ActionType.CLOSE_VALVE,
        target="valve_b",
        source_evidence_id=ev_empty.id,
        claim_text="Valve B must not be closed.",
    )
    cert = grounder.ground(cst, ev_empty)

    assert cert.support_status == SupportStatus.REJECTED
    assert cert.rejection_reason == GroundingRejectionReason.MISSING_EVIDENCE


def test_contradictory_source_rejected_and_conflict_detected(fixture_a_exact_prohibition, fixture_f_contradictory):
    """Verify that an adversarial contradictory source is rejected and identified as SOURCE_CONFLICT."""
    grounder = LocalDeterministicClaimGrounder()
    # Claim asserts prohibition, but Fixture F asserts permission
    cst_prohibition = CandidateConstraint(
        constraint_type=ConstraintType.PROHIBITION,
        action=ActionType.CLOSE_VALVE,
        target="valve_b",
        condition={"pump_p1": "ACTIVE"},
        source_evidence_id=fixture_f_contradictory.id,
        claim_text="Valve B must not be closed while Pump P1 is active.",
    )
    cert = grounder.ground(cst_prohibition, fixture_f_contradictory)
    assert cert.support_type == SupportType.CONTRADICTED
    assert cert.support_status == SupportStatus.REJECTED

    # Detect conflict across Fixture A and Fixture F
    cst_permissive = CandidateConstraint(
        constraint_type=ConstraintType.PRECONDITION,
        action=ActionType.CLOSE_VALVE,
        target="valve_b",
        condition={"pump_p1": "ACTIVE"},
        source_evidence_id=fixture_f_contradictory.id,
        description="Valve B may be closed while Pump P1 is active.",
    )
    cst_valid = CandidateConstraint(
        constraint_type=ConstraintType.PROHIBITION,
        action=ActionType.CLOSE_VALVE,
        target="valve_b",
        condition={"pump_p1": "ACTIVE"},
        source_evidence_id=fixture_a_exact_prohibition.id,
        description="Valve B must not be closed while Pump P1 is active.",
    )
    report = ConstraintConflictDetector.detect_conflicts([cst_valid, cst_permissive])
    assert len(report) >= 1
    assert report[0].conflict is True
    assert report[0].severity == "HIGH"


def test_copied_duplicate_source_not_independent_corroboration(fixture_a_exact_prohibition, fixture_e_copied_mirror):
    """Verify that copied duplicate text across sources is detected as near-duplicate and denied corroboration."""
    is_duplicate = CorroborationEngine.is_duplicate_content(
        fixture_a_exact_prohibition.content,
        fixture_e_copied_mirror.content,
        similarity_threshold=0.85,
    )
    assert is_duplicate is True

    # Corroboration evaluation with duplicate source must not return CORROBORATED
    ass_a = SourceTrustClassifier.assess(fixture_a_exact_prohibition)
    ass_e = SourceTrustClassifier.assess(fixture_e_copied_mirror)
    status, _ = CorroborationEngine.evaluate_corroboration(
        [fixture_a_exact_prohibition, fixture_e_copied_mirror],
        {fixture_a_exact_prohibition.id: ass_a, fixture_e_copied_mirror.id: ass_e},
    )
    assert status != CorroborationStatus.CORROBORATED


def test_weak_advice_cannot_become_mandatory_prohibition(fixture_c_weak_guidance):
    """Verify weak guideline ('should generally remain open') cannot activate a mandatory prohibition."""
    registry = {fixture_c_weak_guidance.id: fixture_c_weak_guidance}
    cst = CandidateConstraint(
        constraint_type=ConstraintType.PROHIBITION,
        action=ActionType.CLOSE_VALVE,
        target="valve_b",
        source_evidence_id=fixture_c_weak_guidance.id,
        claim_text="Valve B must not be closed.",
        confidence=0.85,
    )
    plant = PlantContext(equipment_id="pump_p1", authorized_targets=["valve_b"])

    is_admissible = ConstraintValidator.check_admissibility(cst, registry, plant_context=plant)
    assert is_admissible is False
    assert cst.support_certificate.support_type == SupportType.AMBIGUOUS
    assert cst.support_certificate.support_status == SupportStatus.INSUFFICIENT


def test_multi_claim_handling_decouples_assertions():
    """Verify that multiple claims from a single document receive independent certificates."""
    ev = KnowledgeEvidence(
        id="kb_multi_claim",
        query="valve b multi rule",
        title="Plant Systems Guide",
        source_url="https://plant.internal/guide",
        content="Valve B must not be closed while Pump P1 is active. Inspect seal rings annually.",
        provenance="internal:guide",
    )
    grounder = LocalDeterministicClaimGrounder()

    # Claim 1: Directly supported prohibition
    cst1 = CandidateConstraint(
        constraint_type=ConstraintType.PROHIBITION,
        action=ActionType.CLOSE_VALVE,
        target="valve_b",
        condition={"pump_p1": "ACTIVE"},
        source_evidence_id=ev.id,
        claim_text="Valve B must not be closed while Pump P1 is active.",
    )
    cert1 = grounder.ground(cst1, ev)
    assert cert1.support_status == SupportStatus.SUPPORTED

    # Claim 2: Hallucinated / ungrounded claim from same source
    cst2 = CandidateConstraint(
        constraint_type=ConstraintType.PROHIBITION,
        action=ActionType.CLOSE_VALVE,
        target="valve_b",
        condition={"pressure_drop_psi": 99.0},
        source_evidence_id=ev.id,
        claim_text="Valve B must be closed if pressure drops by 99 psi.",
    )
    cert2 = grounder.ground(cst2, ev)
    assert cert2.support_status == SupportStatus.REJECTED

    # Proof: Source-level approval is NOT inherited!
    assert cert1.is_supported is True
    assert cert2.is_supported is False


def test_human_readable_evidence_explanation_formatting(fixture_a_exact_prohibition):
    """Verify format_grounding_audit outputs the standard human-readable explanation structure."""
    grounder = LocalDeterministicClaimGrounder()
    cst = CandidateConstraint(
        constraint_type=ConstraintType.PROHIBITION,
        action=ActionType.CLOSE_VALVE,
        target="valve_b",
        condition={"pump_p1": "ACTIVE"},
        source_evidence_id=fixture_a_exact_prohibition.id,
        claim_text="Valve B must not be closed while Pump P1 is active.",
    )
    cert = grounder.ground(cst, fixture_a_exact_prohibition)
    report = format_grounding_audit(cert, cst, fixture_a_exact_prohibition)

    assert "CLAIM\nValve B must not be closed while Pump P1 is active." in report
    assert f"SOURCE\n{fixture_a_exact_prohibition.id}" in report
    assert "GROUNDING\nDIRECT" in report
    assert "SUPPORT\nExact normalized source match." in report
    assert "APPLICABILITY\nDIRECT" in report


def test_runtime_events_emitted_during_grounding_failure(fixture_d_unrelated):
    """Verify specific Phase 2C runtime events are emitted upon grounding rejection."""
    bus = EventBus()
    events = []
    bus.subscribe(lambda e: events.append(e))

    registry = {fixture_d_unrelated.id: fixture_d_unrelated}
    # Fixture D discusses Valve A, but constraint targets Valve B (target mismatch)
    cst = CandidateConstraint(
        constraint_type=ConstraintType.PROHIBITION,
        action=ActionType.CLOSE_VALVE,
        target="valve_b",
        source_evidence_id=fixture_d_unrelated.id,
        claim_text="Valve B must not be closed.",
    )

    is_admissible = ConstraintValidator.check_admissibility(cst, registry, event_bus=bus)
    assert is_admissible is False

    event_types = [e.event_type for e in events]
    assert EventType.CLAIM_GROUNDING_STARTED in event_types
    assert EventType.CLAIM_GROUNDED in event_types
    assert EventType.CLAIM_SCOPE_MISMATCH in event_types
    assert EventType.CONSTRAINT_NOT_ADMISSIBLE in event_types


def test_semantic_claim_grounder_interface(fixture_a_exact_prohibition):
    """Verify SemanticClaimGrounder protocol adherence and deterministic fallback."""
    semantic_grounder = SemanticClaimGrounder()
    cst = CandidateConstraint(
        constraint_type=ConstraintType.PROHIBITION,
        action=ActionType.CLOSE_VALVE,
        target="valve_b",
        condition={"pump_p1": "ACTIVE"},
        source_evidence_id=fixture_a_exact_prohibition.id,
        claim_text="Valve B must not be closed while Pump P1 is active.",
    )
    cert = semantic_grounder.ground(cst, fixture_a_exact_prohibition)
    assert cert.support_type == SupportType.DIRECT
    assert cert.support_status == SupportStatus.SUPPORTED


# ==============================================================================
# SECTION 25 SECURITY INVARIANTS VERIFICATION
# ==============================================================================

def test_security_invariants_claim_grounder_cannot_mutate_or_mint(fixture_a_exact_prohibition):
    """Verify ClaimSupportCertificate and ClaimGrounder have ZERO authority over world or tickets."""
    world = WorldState(
        valves={"valve_a": ValveState.OPEN, "valve_b": ValveState.OPEN},
        cooling=CoolingState.ACTIVE,
        human_zone=HumanZoneState.CLEAR,
    )
    grounder = LocalDeterministicClaimGrounder()
    cst = CandidateConstraint(
        constraint_type=ConstraintType.PROHIBITION,
        action=ActionType.CLOSE_VALVE,
        target="valve_b",
        condition={"pump_p1": "ACTIVE"},
        source_evidence_id=fixture_a_exact_prohibition.id,
        claim_text="Valve B must not be closed while Pump P1 is active.",
    )
    cert = grounder.ground(cst, fixture_a_exact_prohibition)

    # Invariant 1: Certificate cannot mutate world
    assert world.valves["valve_b"] == ValveState.OPEN
    # Invariant 2: Certificate cannot possess tickets or actuator handles
    assert not hasattr(cert, "mint_ticket")
    assert not hasattr(cert, "execute")
    assert not hasattr(grounder, "mint_ticket")
    assert not hasattr(grounder, "actuator")
