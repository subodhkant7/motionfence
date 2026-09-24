"""Tests for Phase 2B: Evidence Trust, Admissibility & Nemotron Constraint Extraction."""

import json
import time
import pytest

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
from motionfence.constraints.models import (
    CandidateConstraint,
    ConstraintType,
    ConstraintStatus,
    Applicability,
    PlantContext,
    ConflictCategory,
)
from motionfence.constraints.nemotron_extractor import (
    NemotronConstraintExtractor,
    NemotronExtractorError,
    NemotronExtractedItem,
)
from motionfence.constraints.validator import ConstraintValidator
from motionfence.constraints.conflict import ConstraintConflictDetector
from motionfence.models.actions import ActionType, ActionProposal
from motionfence.models.world import WorldState, ValveState, CoolingState, HumanZoneState
from motionfence.policy.engine import PolicyEngine
from motionfence.policy.models import Policy
from motionfence.runtime.core import MotionFenceRuntime
from motionfence.simulation.world import PhysicalWorld
from motionfence.agent.provider import LocalDeterministicProvider


# ==============================================================================
# 1. SOURCE TRUST CLASSIFICATION TESTS
# ==============================================================================

def test_source_trust_classification_official_first_party():
    """Verify local plant safety manual fixture is classified as FIRST_PARTY_OFFICIAL."""
    now = time.time()
    ev = KnowledgeEvidence(
        id="ev_plant_manual_01",
        query="valve b pump operation",
        title="Plant Safety Manual - Section 4",
        source_url="local://plant_manual_v1/pumps#sec4",
        content="Valve B must not be closed while Pump P1 is active.",
        retrieved_at=now,
        provenance="local_fixture:plant_safety_manual_v1",
        confidence=0.98,
        trust_status=TrustStatus.LOCAL_FIXTURE,
    )
    assessment = SourceTrustClassifier.assess(ev)
    assert assessment.source_category == SourceCategory.FIRST_PARTY_OFFICIAL
    assert assessment.authority_level == AuthorityLevel.HIGH
    assert assessment.evidence_role == EvidenceRole.AUTHORIZATION_RELEVANT
    assert assessment.is_authorization_sufficient is True


def test_source_trust_classification_manufacturer_oem():
    """Verify equipment OEM domains are categorized as MANUFACTURER_DOCUMENTATION."""
    ev = KnowledgeEvidence(
        id="ev_ksb_manual_01",
        query="centrifugal pump safety",
        title="KSB Centrifugal Pumps Manual",
        source_url="https://www.ksb.com/en-global/products/pumps/centrifugal",
        content="Do not close discharge valve during active pump operation.",
        retrieved_at=time.time(),
        provenance="tavily:search:ksb_manual",
        confidence=0.95,
        trust_status=TrustStatus.UNVERIFIED_EXTERNAL,
    )
    assessment = SourceTrustClassifier.assess(ev)
    assert assessment.source_category == SourceCategory.MANUFACTURER_DOCUMENTATION
    assert assessment.authority_level == AuthorityLevel.HIGH
    assert assessment.evidence_role == EvidenceRole.AUTHORIZATION_RELEVANT


def test_source_trust_classification_standards_organization():
    """Verify standards bodies (ASME, ISO, OSHA) are categorized as REGULATORY_OR_STANDARDS."""
    ev = KnowledgeEvidence(
        id="ev_asme_std_01",
        query="pump valve isolation standards",
        title="ASME B73.1 Standard",
        source_url="https://asme.org/codes-standards/find-codes-standards/b73-1",
        content="Mandatory pump safety specifications.",
        retrieved_at=time.time(),
        provenance="tavily:search:asme_std",
        confidence=0.97,
        trust_status=TrustStatus.UNVERIFIED_EXTERNAL,
    )
    assessment = SourceTrustClassifier.assess(ev)
    assert assessment.source_category == SourceCategory.REGULATORY_OR_STANDARDS
    assert assessment.authority_level == AuthorityLevel.HIGH
    assert assessment.evidence_role == EvidenceRole.AUTHORIZATION_RELEVANT


def test_source_trust_classification_community_discovery_only():
    """Verify community/forum sites (Reddit, Scribd, Facebook) are assigned DISCOVERY role only."""
    community_urls = [
        "https://reddit.com/r/engineering/comments/pump_valve",
        "https://www.scribd.com/presentation/425705649/pump-isolation-pptx",
        "https://facebook.com/groups/plantops/posts/12345",
        "https://medium.com/@user/industrial-pump-tips",
    ]
    for url in community_urls:
        ev = KnowledgeEvidence(
            id=f"ev_comm_{hash(url)}",
            query="pump isolation tips",
            title="User discussion on valves",
            source_url=url,
            content="Never close Valve B according to someone on shift.",
            retrieved_at=time.time(),
            provenance=f"tavily:search:{url}",
            confidence=0.60,
            trust_status=TrustStatus.UNVERIFIED_EXTERNAL,
        )
        assessment = SourceTrustClassifier.assess(ev)
        assert assessment.source_category == SourceCategory.COMMUNITY_OR_USER_CONTENT
        assert assessment.authority_level == AuthorityLevel.LOW
        assert assessment.evidence_role == EvidenceRole.DISCOVERY
        assert assessment.is_authorization_sufficient is False


def test_source_trust_classification_unknown_source():
    """Verify unattributed or unknown domains are treated as UNKNOWN and DISCOVERY only."""
    ev = KnowledgeEvidence(
        id="ev_unknown_01",
        query="valve operations",
        title="Random note",
        source_url="",
        content="Some unverified statement about valves.",
        retrieved_at=time.time(),
        provenance="",
        confidence=0.30,
        trust_status=TrustStatus.REJECTED,
    )
    assessment = SourceTrustClassifier.assess(ev)
    assert assessment.source_category == SourceCategory.UNKNOWN
    assert assessment.authority_level == AuthorityLevel.UNTRUSTED
    assert assessment.evidence_role == EvidenceRole.REJECTED


def test_source_trust_classification_stale_source():
    """Verify that evidence older than freshness threshold is flagged as STALE."""
    ninety_days_ago = time.time() - (86400.0 * 90.0)
    ev = KnowledgeEvidence(
        id="ev_stale_manual_01",
        query="cooling valve rules",
        title="Old Facility Spec 2021",
        source_url="local://plant_manual_archived/cooling_spec_2021",
        content="Archived cooling specification.",
        retrieved_at=ninety_days_ago,
        provenance="local_fixture:legacy_spec_2021",
        confidence=0.85,
        trust_status=TrustStatus.STALE,
    )
    assessment = SourceTrustClassifier.assess(ev)
    assert assessment.freshness == FreshnessStatus.STALE


# ==============================================================================
# 2. APPLICABILITY & PLANT CONTEXT TESTS
# ==============================================================================

def test_applicability_direct_match():
    """Verify direct equipment ID and model match is classified as DIRECT."""
    plant = PlantContext(equipment_id="pump_p1", equipment_model="P100-A", authorized_targets=["valve_b"])
    ev = KnowledgeEvidence(
        id="ev_p100a_01",
        query="P100-A centrifugal pump rules",
        title="KSB Model P100-A Operations Guide",
        source_url="local://plant_manual_v1/p100a",
        content="Pump P1 model P100-A requires valve B open during flow.",
        retrieved_at=time.time(),
        provenance="plant_manual:p100a",
        confidence=0.95,
        trust_status=TrustStatus.LOCAL_FIXTURE,
    )
    cst = CandidateConstraint(
        constraint_type=ConstraintType.PROHIBITION,
        target="valve_b",
        source_evidence_id=ev.id,
    )
    app = ConstraintValidator.assess_applicability(cst, plant, ev)
    assert app == Applicability.DIRECT


def test_applicability_partial_generic_pump_match():
    """Verify generic centrifugal pump guide without specific model is classified as PARTIAL."""
    plant = PlantContext(equipment_id="pump_p1", equipment_model="P100-A", equipment_type="centrifugal_pump")
    ev = KnowledgeEvidence(
        id="ev_generic_pump_02",
        query="centrifugal pump safety",
        title="Generic Guide to Centrifugal Pumps",
        source_url="https://example.com/guide/centrifugal-pumps",
        content="Standard centrifugal pump operating guidelines.",
        retrieved_at=time.time(),
        provenance="web:generic_pump",
        confidence=0.80,
        trust_status=TrustStatus.UNVERIFIED_EXTERNAL,
    )
    cst = CandidateConstraint(
        constraint_type=ConstraintType.PROHIBITION,
        target="valve_b",
        source_evidence_id=ev.id,
    )
    app = ConstraintValidator.assess_applicability(cst, plant, ev)
    assert app == Applicability.PARTIAL


def test_applicability_mismatch_different_model():
    """Verify guide explicitly targeting a different pump model is classified as MISMATCH."""
    plant = PlantContext(equipment_id="pump_p1", equipment_model="P100-A", equipment_type="centrifugal_pump")
    ev = KnowledgeEvidence(
        id="ev_p200b_mismatch_03",
        query="slurry pump model P200-B",
        title="KSB High-Pressure Slurry Pump Model P200-B Manual",
        source_url="https://ksb.com/manuals/slurry-pump-p200b",
        content="Specific instructions for heavy slurry pump model P200.",
        retrieved_at=time.time(),
        provenance="oem:ksb_p200",
        confidence=0.92,
        trust_status=TrustStatus.UNVERIFIED_EXTERNAL,
    )
    cst = CandidateConstraint(
        constraint_type=ConstraintType.PROHIBITION,
        target="valve_b",
        source_evidence_id=ev.id,
    )
    app = ConstraintValidator.assess_applicability(cst, plant, ev)
    assert app == Applicability.MISMATCH


def test_applicability_mismatch_unauthorized_target():
    """Verify constraint targeting an equipment component outside authorized plant boundary is MISMATCH."""
    plant = PlantContext(authorized_targets=["valve_a", "valve_b"])
    cst = CandidateConstraint(
        constraint_type=ConstraintType.PROHIBITION,
        target="unauthorized_reactor_core",
        source_evidence_id="ev_fake_01",
    )
    app = ConstraintValidator.assess_applicability(cst, plant, None)
    assert app == Applicability.MISMATCH


# ==============================================================================
# 3. CORROBORATION & DEDUPLICATION TESTS
# ==============================================================================

def test_corroboration_two_independent_qualified_sources():
    """Verify two independent high-authority sources yield CORROBORATED status."""
    ev1 = KnowledgeEvidence(
        id="ev_oem_01",
        query="valve b pump rules",
        title="OEM Manual",
        source_url="https://ksb.com/manual/pumps",
        content="Valve B must not be closed under pump pressure.",
        provenance="oem:ksb",
        confidence=0.95,
        trust_status=TrustStatus.UNVERIFIED_EXTERNAL,
    )
    ev2 = KnowledgeEvidence(
        id="ev_standards_02",
        query="valve b pump rules",
        title="ASME Standard",
        source_url="https://asme.org/standards/pumps",
        content="Valve B isolation prohibited during liquid flow.",
        provenance="standards:asme",
        confidence=0.96,
        trust_status=TrustStatus.UNVERIFIED_EXTERNAL,
    )
    assessments = {
        ev1.id: SourceTrustClassifier.assess(ev1),
        ev2.id: SourceTrustClassifier.assess(ev2),
    }
    status, notes = CorroborationEngine.evaluate_corroboration([ev1, ev2], assessments)
    assert status == CorroborationStatus.CORROBORATED


def test_corroboration_rejects_duplicate_scraped_mirrors():
    """Verify verbatim copied text across mirrors is detected as DUPLICATE_SOURCE, not corroboration."""
    verbatim_text = "Valve B must not be closed while Pump P1 is active due to extreme hydraulic shock."
    ev1 = KnowledgeEvidence(
        id="ev_orig_01",
        query="valve b pump rules",
        title="Original Article",
        source_url="https://teffiko.com/safety-guidelines",
        content=verbatim_text,
        provenance="web:teffiko",
        confidence=0.70,
        trust_status=TrustStatus.UNVERIFIED_EXTERNAL,
    )
    ev2 = KnowledgeEvidence(
        id="ev_mirror_02",
        query="valve b pump rules",
        title="Scraped Copy",
        source_url="https://scraped-copy.xyz/safety-guidelines",
        content=verbatim_text,  # Identical scraped text
        provenance="web:scraped_mirror",
        confidence=0.70,
        trust_status=TrustStatus.UNVERIFIED_EXTERNAL,
    )
    assessments = {
        ev1.id: SourceTrustClassifier.assess(ev1),
        ev2.id: SourceTrustClassifier.assess(ev2),
    }
    status, notes = CorroborationEngine.evaluate_corroboration([ev1, ev2], assessments)
    assert status == CorroborationStatus.DUPLICATE_SOURCE


def test_corroboration_single_supporting_source_unsupported():
    """Verify single supporting source lacks corroboration and cannot activate prohibitions."""
    ev = KnowledgeEvidence(
        id="ev_single_01",
        query="valve rules",
        title="Third-party Blog",
        source_url="https://powermag.com/tips",
        content="General pump tips.",
        provenance="web:powermag",
        confidence=0.65,
        trust_status=TrustStatus.UNVERIFIED_EXTERNAL,
    )
    assessments = {ev.id: SourceTrustClassifier.assess(ev)}
    status, notes = CorroborationEngine.evaluate_corroboration([ev], assessments)
    # A single supporting source without HIGH authority is not corroborated
    assert status in (CorroborationStatus.SINGLE_SOURCE, CorroborationStatus.UNSUPPORTED)


# ==============================================================================
# 4. NEMOTRON CONSTRAINT EXTRACTOR TESTS
# ==============================================================================

def test_nemotron_extractor_valid_structured_output():
    """Verify NemotronConstraintExtractor parses valid JSON array into CandidateConstraint objects."""
    evidence = [
        KnowledgeEvidence(
            id="kb_item_101",
            query="valve b pump p1 rules",
            title="Plant Safety Guidelines",
            source_url="local://plant_manual_v1/pumps",
            content="Valve B must not be closed while Pump P1 is active.",
            provenance="plant_manual",
            confidence=0.95,
            trust_status=TrustStatus.LOCAL_FIXTURE,
        )
    ]

    mock_llm_json = json.dumps([
        {
            "constraint_type": "PROHIBITION",
            "action": "CLOSE_VALVE",
            "target": "valve_b",
            "condition": {"pump_p1": "ACTIVE"},
            "source_evidence_id": "kb_item_101",
            "confidence": 0.94,
            "claim_text": "Valve B must not be closed while Pump P1 is active.",
            "rationale": "Direct operational restriction on valve closure while pump is pressurized."
        }
    ])

    extractor = NemotronConstraintExtractor(transport=lambda messages: mock_llm_json)
    candidates = extractor.extract(evidence)

    assert len(candidates) == 1
    cst = candidates[0]
    assert cst.constraint_type == ConstraintType.PROHIBITION
    assert cst.action == ActionType.CLOSE_VALVE
    assert cst.target == "valve_b"
    assert cst.condition == {"pump_p1": "ACTIVE"}
    assert cst.source_evidence_id == "kb_item_101"
    assert cst.confidence == 0.94
    assert cst.claim_text == "Valve B must not be closed while Pump P1 is active."
    assert cst.status == ConstraintStatus.CANDIDATE


def test_nemotron_extractor_malformed_json_raises_error():
    """Verify NemotronConstraintExtractor safely catches malformed JSON output without crashing."""
    evidence = [
        KnowledgeEvidence(
            id="kb_item_102",
            query="test",
            title="Test",
            source_url="local://test",
            content="Some text",
            provenance="test",
            trust_status=TrustStatus.LOCAL_FIXTURE,
        )
    ]
    extractor = NemotronConstraintExtractor(transport=lambda messages: "NOT A VALID JSON STRING {{{")
    with pytest.raises(NemotronExtractorError, match="malformed JSON"):
        extractor.extract(evidence)


def test_nemotron_extractor_rejects_hallucinated_evidence_id():
    """Verify NemotronConstraintExtractor discards constraints referencing hallucinated evidence IDs."""
    evidence = [
        KnowledgeEvidence(
            id="kb_real_id_55",
            query="test",
            title="Test",
            source_url="local://test",
            content="Some text",
            provenance="test",
            trust_status=TrustStatus.LOCAL_FIXTURE,
        )
    ]
    mock_llm_json = json.dumps([
        {
            "constraint_type": "PROHIBITION",
            "action": "CLOSE_VALVE",
            "target": "valve_b",
            "condition": {"pump_p1": "ACTIVE"},
            "source_evidence_id": "kb_hallucinated_fake_99",  # NOT in evidence registry!
            "confidence": 0.90,
            "claim_text": "Close valve b",
            "rationale": "Hallucinated"
        }
    ])
    extractor = NemotronConstraintExtractor(transport=lambda messages: mock_llm_json)
    candidates = extractor.extract(evidence)
    # The hallucinated constraint should be discarded
    assert len(candidates) == 0


def test_nemotron_extractor_unconfigured_api_key_raises_error():
    """Verify calling live extraction without an API key raises NemotronExtractorError."""
    evidence = [
        KnowledgeEvidence(
            id="kb_test",
            query="test",
            title="Test",
            source_url="local://test",
            content="Test content",
            provenance="test",
        )
    ]
    extractor = NemotronConstraintExtractor(api_key="", transport=None)
    with pytest.raises(NemotronExtractorError, match="NEBIUS_API_KEY is not configured"):
        extractor.extract(evidence)


# ==============================================================================
# 5. SAFETY & ADMISSIBILITY GATING TESTS
# ==============================================================================

def test_weak_community_source_cannot_activate_safety_prohibition():
    """Verify a weak community forum post cannot independently become an ACTIVE safety constraint."""
    community_doc = KnowledgeEvidence(
        id="kb_reddit_forum_01",
        query="valve b closure",
        title="Reddit Post",
        source_url="https://reddit.com/r/industrial/comments/valve_b",
        content="Forum comment: Valve B must not be closed under any circumstances.",
        provenance="reddit:thread_123",
        confidence=0.55,
        trust_status=TrustStatus.UNVERIFIED_EXTERNAL,
    )
    registry = {community_doc.id: community_doc}
    cst = CandidateConstraint(
        constraint_type=ConstraintType.PROHIBITION,
        action=ActionType.CLOSE_VALVE,
        target="valve_b",
        condition={"pump_p1": "ACTIVE"},
        source_evidence_id=community_doc.id,
        confidence=0.55,
    )
    plant = PlantContext(equipment_id="pump_p1", authorized_targets=["valve_b"])

    # Admissibility check must return False
    is_admissible = ConstraintValidator.check_admissibility(cst, registry, plant_context=plant)
    assert is_admissible is False

    # Promotion attempt must NOT activate constraint
    promoted = ConstraintValidator.promote_to_active(cst, registry, plant_context=plant)
    assert promoted.is_active is False
    assert promoted.status == ConstraintStatus.STRUCTURALLY_VALID


def test_admissible_corroborated_constraint_blocks_unsafe_action():
    """Verify an admissible, corroborated prohibition promotes to ACTIVE and PolicyEngine returns DENY."""
    now = time.time()
    oem_doc = KnowledgeEvidence(
        id="kb_ksb_oem_01",
        query="pump p1 valve b closure",
        title="KSB OEM Manual",
        source_url="https://ksb.com/manuals/p100/safety",
        content="MANDATORY PROHIBITION: Valve B must not be closed while Pump P1 is active.",
        retrieved_at=now,
        provenance="oem:ksb_manual",
        confidence=0.96,
        trust_status=TrustStatus.LOCAL_FIXTURE,
    )
    registry = {oem_doc.id: oem_doc}
    cst = CandidateConstraint(
        constraint_type=ConstraintType.PROHIBITION,
        action=ActionType.CLOSE_VALVE,
        target="valve_b",
        condition={"pump_p1": "ACTIVE"},
        source_evidence_id=oem_doc.id,
        confidence=0.96,
        description="Valve B must not be closed while Pump P1 is active.",
    )
    plant = PlantContext(equipment_id="pump_p1", authorized_targets=["valve_a", "valve_b", "pump_p1"])

    promoted = ConstraintValidator.promote_to_active(
        cst,
        registry,
        plant_context=plant,
        corroboration_status=CorroborationStatus.CORROBORATED,
    )
    assert promoted.is_active is True
    assert promoted.status == ConstraintStatus.ACTIVE

    # World: Pump P1 = ACTIVE, Cooling = ACTIVE, Human Zone = CLEAR
    world = WorldState(
        valves={"valve_a": ValveState.OPEN, "valve_b": ValveState.OPEN},
        cooling=CoolingState.ACTIVE,
        human_zone=HumanZoneState.CLEAR,
        pumps={"pump_p1": "ACTIVE"},
    )
    proposal = ActionProposal(
        action_type=ActionType.CLOSE_VALVE,
        target="valve_b",
        model_confidence=0.95,
        rationale="Emergency closure requested.",
    )
    # Evaluate policy
    decision = PolicyEngine.evaluate(proposal, world, evidence=[], active_constraints=[promoted])
    assert decision.is_denied is True
    assert any("knowledge_prohibition" in r.constraint for r in decision.reasons)


def test_applicability_mismatch_blocks_constraint_activation():
    """Verify constraint with equipment mismatch cannot be promoted to ACTIVE."""
    mismatch_doc = KnowledgeEvidence(
        id="kb_mismatch_01",
        query="slurry pump model p200",
        title="Slurry Pump P200-B Manual",
        source_url="https://ksb.com/manuals/slurry-pump-p200",
        content="Valve B must not be closed on Model P200 slurry pumps.",
        provenance="oem:ksb_p200",
        confidence=0.94,
        trust_status=TrustStatus.LOCAL_FIXTURE,
    )
    registry = {mismatch_doc.id: mismatch_doc}
    plant = PlantContext(equipment_id="pump_p1", equipment_model="P100-A", equipment_type="centrifugal_pump")
    cst = CandidateConstraint(
        constraint_type=ConstraintType.PROHIBITION,
        action=ActionType.CLOSE_VALVE,
        target="valve_b",
        source_evidence_id=mismatch_doc.id,
        confidence=0.94,
    )
    promoted = ConstraintValidator.promote_to_active(cst, registry, plant_context=plant)
    assert promoted.is_active is False
    assert promoted.applicability == Applicability.MISMATCH


def test_policy_conflict_detected_and_blocks_authorization():
    """Verify constraint requiring an action that base policy prohibits is flagged as POLICY_CONFLICT."""
    cst = CandidateConstraint(
        constraint_id="cst_conflict_with_policy",
        constraint_type=ConstraintType.REQUIREMENT,
        action=ActionType.CLOSE_VALVE,
        target="valve_b",
        condition={"cooling": "INACTIVE"},  # Contradicts base policy cooling invariant!
        source_evidence_id="kb_some_source",
        confidence=0.90,
    )
    base_policy = Policy(require_cooling_active=True)
    conflicts = ConstraintConflictDetector.detect_conflicts([cst], policy=base_policy)
    assert len(conflicts) > 0
    assert conflicts[0].conflict_category == ConflictCategory.POLICY_CONFLICT
    assert cst.status == ConstraintStatus.CONFLICTED


def test_runtime_e2e_weak_source_does_not_block_actuation():
    """Verify in MotionFenceRuntime that a weak community source never creates an active prohibition."""
    community_doc = KnowledgeEvidence(
        id="kb_reddit_runtime_01",
        query="valve b closure",
        title="Reddit Post",
        source_url="https://reddit.com/r/industrial/comments/valve_b_bad",
        content="Someone online said: Valve B must not be closed under pump pressure.",
        provenance="reddit:thread_999",
        confidence=0.55,
        trust_status=TrustStatus.UNVERIFIED_EXTERNAL,
    )
    world = PhysicalWorld()
    world.valves["valve_b"] = ValveState.OPEN
    world.set_pump_state("pump_p1", "INACTIVE")
    world.cooling = CoolingState.ACTIVE
    world.set_human_zone(HumanZoneState.CLEAR)

    from motionfence.knowledge.local_provider import LocalKnowledgeProvider
    from motionfence.knowledge.retrieval import KnowledgeRetrievalService
    from motionfence.constraints.local_extractor import LocalConstraintExtractor

    knowledge_service = KnowledgeRetrievalService(provider=LocalKnowledgeProvider(custom_fixtures=[community_doc]))
    extractor = LocalConstraintExtractor()
    plant = PlantContext(equipment_id="pump_p1", authorized_targets=["valve_a", "valve_b"])

    runtime = MotionFenceRuntime(
        world=world,
        proposal_provider=LocalDeterministicProvider(),
        knowledge_service=knowledge_service,
        constraint_extractor=extractor,
        plant_context=plant,
    )

    cycle = runtime.run_cycle(
        intent="Routine isolate valve_b",
        initial_evidence=world.generate_targeted_evidence("valve_b"),
        knowledge_query="valve b closure",
    )

    # The weak source must NOT block execution!
    assert cycle.policy_decision.is_allowed is True
    assert len(cycle.active_constraints) == 0
    assert cycle.ticket is not None
    assert world.valves["valve_b"] == ValveState.CLOSED


def test_nemotron_extractor_invalid_action_maps_to_none():
    """Verify that an invalid or hallucinated action in Nemotron output maps to None rather than crashing."""
    evidence = [
        KnowledgeEvidence(
            id="kb_item_999",
            query="test",
            title="Test",
            source_url="local://test",
            content="Some text",
            provenance="test",
            trust_status=TrustStatus.LOCAL_FIXTURE,
        )
    ]
    mock_llm_json = json.dumps([
        {
            "constraint_type": "PROHIBITION",
            "action": "NON_EXISTENT_SUPER_ACTION",
            "target": "valve_b",
            "condition": {},
            "source_evidence_id": "kb_item_999",
            "confidence": 0.85,
            "claim_text": "Do not do that",
            "rationale": "Invalid action test"
        }
    ])
    extractor = NemotronConstraintExtractor(transport=lambda messages: mock_llm_json)
    candidates = extractor.extract(evidence)
    assert len(candidates) == 1
    assert candidates[0].action is None

