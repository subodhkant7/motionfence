"""Phase 2A comprehensive test suite: Knowledge retrieval, constraint validation,

conflict detection, freshness handling, policy gating, and authority security invariants.
"""

import time
from typing import Dict, List
import pytest
import urllib.error

from motionfence.knowledge.models import (
    KnowledgeEvidence,
    TrustStatus,
    FreshnessStatus,
)
from motionfence.knowledge.provider import KnowledgeProvider, TavilyProviderError
from motionfence.knowledge.local_provider import LocalKnowledgeProvider
from motionfence.knowledge.tavily_provider import TavilyKnowledgeProvider
from motionfence.knowledge.retrieval import KnowledgeRetrievalService
from motionfence.constraints.models import (
    CandidateConstraint,
    ConstraintType,
    ConstraintStatus,
    ConstraintConflictReport,
)
from motionfence.constraints.local_extractor import LocalConstraintExtractor
from motionfence.constraints.validator import ConstraintValidator
from motionfence.constraints.conflict import ConstraintConflictDetector
from motionfence.constraints.extractor import ConstraintValidationError
from motionfence.models.actions import ActionProposal, ActionType, AuthorizationTicket
from motionfence.policy.models import DecisionType, PolicyDecision
from motionfence.models.world import WorldState, ValveState, CoolingState, HumanZoneState
from motionfence.policy.models import Policy
from motionfence.policy.engine import PolicyEngine
from motionfence.simulation.world import PhysicalWorld
from motionfence.simulation.actuator import PhysicalActuator
from motionfence.simulation.exceptions import UnauthorizedActionError
from motionfence.agent.provider import LocalDeterministicProvider
from motionfence.runtime.ticket import TicketAuthority
from motionfence.runtime.core import MotionFenceRuntime


# ==============================================================================
# 1. KNOWLEDGE RETRIEVAL & FIXTURE TESTS
# ==============================================================================

def test_local_knowledge_retrieval_succeeds():
    """Verify local provider returns deterministic fixtures with complete provenance."""
    provider = LocalKnowledgeProvider()
    results = provider.retrieve("Valve B pump P1 restriction")

    assert len(results) > 0
    # Must retrieve Fixture 1
    fix1 = next((r for r in results if r.id == "kb_fixture_001"), None)
    assert fix1 is not None
    assert fix1.trust_status == TrustStatus.LOCAL_FIXTURE
    assert "local://plant_manual_v1" in fix1.source_url
    assert fix1.provenance == "local_fixture:plant_safety_manual_v1"
    assert fix1.confidence > 0.9
    assert fix1.retrieved_at > 0


def test_empty_results_handled_safely():
    """Verify retrieval service handles queries cleanly without crashing."""
    empty_provider = LocalKnowledgeProvider(custom_fixtures=[])
    service = KnowledgeRetrievalService(provider=empty_provider)
    results = service.query("any random nonexistent topic")

    assert results == []
    assert len(service._evidence_registry) == 0


def test_malformed_tavily_response_handled_safely():
    """Verify TavilyKnowledgeProvider safely rejects malformed or error payloads."""
    # Transport returning invalid json structure
    def mock_bad_transport(url, payload, timeout):
        return {"unexpected_root_key": "not a list"}

    provider = TavilyKnowledgeProvider(api_key="tvly-mock-test-key", transport=mock_bad_transport)
    results = provider.retrieve("any query")
    assert results == []


def test_missing_provenance_fixture_marked_rejected():
    """Verify Fixture 5 with missing provenance is correctly categorized as REJECTED."""
    provider = LocalKnowledgeProvider()
    all_fixtures = provider.fixtures
    malformed = next((f for f in all_fixtures if f.id == "kb_fixture_005"), None)

    assert malformed is not None
    assert malformed.provenance == ""
    assert malformed.trust_status == TrustStatus.REJECTED


def test_stale_knowledge_detection():
    """Verify knowledge evidence age calculation flags stale documents."""
    provider = LocalKnowledgeProvider()
    stale_fixture = next((f for f in provider.fixtures if f.id == "kb_fixture_004"), None)

    assert stale_fixture is not None
    assert stale_fixture.age_seconds > (86400.0 * 30.0)  # > 30 days
    assert stale_fixture.is_stale(max_age_seconds=86400.0) is True


def test_tavily_missing_key_fails_safely():
    """Verify TavilyKnowledgeProvider raises TavilyProviderError when API key is missing."""
    provider = TavilyKnowledgeProvider(api_key="")
    with pytest.raises(TavilyProviderError) as exc_info:
        provider.retrieve("testing query")
    assert "TAVILY_API_KEY" in str(exc_info.value)
    assert "not configured" in str(exc_info.value)


def test_tavily_timeout_failure_fails_safely():
    """Verify Tavily timeout error raises TavilyProviderError without fabricating evidence."""
    def mock_timeout_transport(url, payload, timeout):
        raise TimeoutError("Simulated request timed out")

    provider = TavilyKnowledgeProvider(api_key="tvly-mock-test-key", transport=mock_timeout_transport)
    with pytest.raises(TavilyProviderError) as exc_info:
        provider.retrieve("testing query")
    assert "timed out" in str(exc_info.value)


def test_tavily_http_401_403_failure_fails_safely():
    """Verify Tavily HTTP 401/403 raises TavilyProviderError with authentication error."""
    def mock_auth_err_transport(url, payload, timeout):
        raise urllib.error.HTTPError(url=url, code=401, msg="Unauthorized", hdrs={}, fp=None)

    provider = TavilyKnowledgeProvider(api_key="tvly-mock-bad-key", transport=mock_auth_err_transport)
    with pytest.raises(TavilyProviderError) as exc_info:
        provider.retrieve("testing query")
    assert "authentication error" in str(exc_info.value).lower()


def test_tavily_http_500_failure_fails_safely():
    """Verify Tavily HTTP 500 raises TavilyProviderError without fabricating knowledge."""
    def mock_500_err_transport(url, payload, timeout):
        raise urllib.error.HTTPError(url=url, code=500, msg="Internal Server Error", hdrs={}, fp=None)

    provider = TavilyKnowledgeProvider(api_key="tvly-mock-test-key", transport=mock_500_err_transport)
    with pytest.raises(TavilyProviderError) as exc_info:
        provider.retrieve("testing query")
    assert "HTTP error 500" in str(exc_info.value)


def test_tavily_network_failure_fails_safely():
    """Verify Tavily network disconnect raises TavilyProviderError without mutating world."""
    def mock_net_err_transport(url, payload, timeout):
        raise urllib.error.URLError(reason="Connection refused")

    provider = TavilyKnowledgeProvider(api_key="tvly-mock-test-key", transport=mock_net_err_transport)
    with pytest.raises(TavilyProviderError) as exc_info:
        provider.retrieve("testing query")
    assert "network connection error" in str(exc_info.value).lower()


def test_tavily_empty_results_fails_safely():
    """Verify empty search results return clean empty list without hallucinating rules."""
    def mock_empty_transport(url, payload, timeout):
        return {"results": []}

    provider = TavilyKnowledgeProvider(api_key="tvly-mock-test-key", transport=mock_empty_transport)
    results = provider.retrieve("any query")
    assert results == []


def test_tavily_failure_in_runtime_causes_no_world_mutation():
    """Verify provider failure during runtime control loop does not grant authority or mutate world."""
    def mock_failing_transport(url, payload, timeout):
        raise urllib.error.HTTPError(url=url, code=500, msg="Server Error", hdrs={}, fp=None)

    world = PhysicalWorld()
    world.valves["valve_b"] = ValveState.OPEN
    world.set_human_zone(HumanZoneState.OCCUPIED)  # Hard safety violation present

    failing_provider = TavilyKnowledgeProvider(api_key="tvly-mock-key", transport=mock_failing_transport)
    knowledge_service = KnowledgeRetrievalService(provider=failing_provider)

    runtime = MotionFenceRuntime(
        world=world,
        proposal_provider=LocalDeterministicProvider(),
        knowledge_service=knowledge_service,
        constraint_extractor=LocalConstraintExtractor(),
    )

    result = runtime.run_cycle(intent="Close valve_b")
    # Knowledge failure must NOT bypass policy or cause ALLOW
    assert result.policy_decision.is_denied
    assert result.ticket is None
    assert world.get_state().valves["valve_b"] == ValveState.OPEN


# ==============================================================================
# 2. CANDIDATE CONSTRAINT EXTRACTION & VALIDATION TESTS
# ==============================================================================

def test_valid_constraint_extraction():
    """Verify local extractor parses prohibition and procedure into distinct candidate constraints."""
    provider = LocalKnowledgeProvider()
    extractor = LocalConstraintExtractor()
    fixtures = provider.fixtures

    candidates = extractor.extract(fixtures)
    assert len(candidates) >= 3

    # Rule 1: Must be PROHIBITION on valve_b
    prohibition = next((c for c in candidates if c.constraint_type == ConstraintType.PROHIBITION), None)
    assert prohibition is not None
    assert prohibition.action == ActionType.CLOSE_VALVE
    assert prohibition.target == "valve_b"
    assert prohibition.condition.get("pump_p1") == "ACTIVE"
    assert prohibition.source_evidence_id == "kb_fixture_001"

    # Rule 2: Ordinary procedure must be INFORMATIONAL / INSPECT (NOT prohibition)
    procedure = next((c for c in candidates if c.constraint_type == ConstraintType.INFORMATIONAL), None)
    assert procedure is not None
    assert procedure.action == ActionType.INSPECT
    assert procedure.target == "valve_b"


def test_harmless_procedure_never_promotes_to_active_prohibition():
    """Verify harmless procedure candidate cannot become an ACTIVE prohibition."""
    provider = LocalKnowledgeProvider()
    extractor = LocalConstraintExtractor()
    service = KnowledgeRetrievalService(provider=provider)
    evidence = service.query("routine maintenance")

    candidates = extractor.extract(evidence)
    procedure = next(c for c in candidates if c.constraint_type == ConstraintType.INFORMATIONAL)

    promoted = ConstraintValidator.promote_to_active(procedure, service._evidence_registry)
    # Status remains VALIDATED or CANDIDATE, NOT ACTIVE
    assert promoted.status != ConstraintStatus.ACTIVE
    assert promoted.is_active is False


def test_unknown_evidence_reference_rejected():
    """Verify ConstraintValidator strictly rejects candidate constraints citing unknown evidence IDs."""
    fake_constraint = CandidateConstraint(
        constraint_id="cst_hallucinated_01",
        constraint_type=ConstraintType.PROHIBITION,
        action=ActionType.CLOSE_VALVE,
        target="valve_b",
        condition={"pump_p1": "ACTIVE"},
        source_evidence_id="kb_hallucinated_999",  # Does NOT exist
        confidence=0.95,
        created_at=time.time(),
        status=ConstraintStatus.CANDIDATE,
    )

    registry: Dict[str, KnowledgeEvidence] = {}
    is_valid = ConstraintValidator.validate(fake_constraint, registry)
    assert is_valid is False
    assert fake_constraint.status == ConstraintStatus.REJECTED
    assert any("Unknown source evidence reference" in note for note in fake_constraint.validation_notes)


def test_invalid_confidence_rejected():
    """Verify validator and schema reject candidate constraints with confidence out of bounds."""
    ev = KnowledgeEvidence(
        id="kb_test_01",
        query="test",
        title="Test Doc",
        source_url="local://test",
        content="prohibition test",
        retrieved_at=time.time(),
        source_metadata={},
        provenance="test_provenance",
        confidence=0.9,
        trust_status=TrustStatus.VALIDATED,
    )
    registry = {ev.id: ev}

    # Pydantic schema rejection for confidence > 1.0
    with pytest.raises(Exception):
        CandidateConstraint(
            constraint_id="cst_bad_conf",
            constraint_type=ConstraintType.PROHIBITION,
            action=ActionType.CLOSE_VALVE,
            target="valve_b",
            condition={},
            source_evidence_id=ev.id,
            confidence=1.5,  # Out of bounds!
            created_at=time.time(),
            status=ConstraintStatus.CANDIDATE,
        )


def test_malformed_condition_rejected():
    """Verify validator rejects non-dictionary conditions."""
    ev = KnowledgeEvidence(
        id="kb_test_02",
        query="test",
        title="Test Doc",
        source_url="local://test",
        content="prohibition test",
        retrieved_at=time.time(),
        source_metadata={},
        provenance="test_provenance",
        confidence=0.9,
        trust_status=TrustStatus.VALIDATED,
    )
    registry = {ev.id: ev}

    # Pass an invalid condition type via object creation
    with pytest.raises(Exception):
        CandidateConstraint(
            constraint_id="cst_bad_cond",
            constraint_type=ConstraintType.PROHIBITION,
            action=ActionType.CLOSE_VALVE,
            target="valve_b",
            condition="not_a_dictionary",  # type: ignore
            source_evidence_id=ev.id,
            confidence=0.9,
            created_at=time.time(),
            status=ConstraintStatus.CANDIDATE,
        )


def test_stale_evidence_sets_constraint_stale():
    """Verify constraints referencing stale evidence are marked STALE and cannot promote to ACTIVE."""
    stale_ev = KnowledgeEvidence(
        id="kb_stale_01",
        query="cooling",
        title="Archived Spec",
        source_url="local://archived",
        content="Must verify thermal purge",
        retrieved_at=time.time() - (86400.0 * 60.0),  # 60 days old
        source_metadata={},
        provenance="legacy_archive",
        confidence=0.8,
        trust_status=TrustStatus.STALE,
    )
    registry = {stale_ev.id: stale_ev}

    cst = CandidateConstraint(
        constraint_id="cst_stale",
        constraint_type=ConstraintType.REQUIREMENT,
        action=ActionType.CLOSE_VALVE,
        target="valve_b",
        condition={"purge": True},
        source_evidence_id=stale_ev.id,
        confidence=0.8,
        created_at=time.time(),
        status=ConstraintStatus.CANDIDATE,
    )

    promoted = ConstraintValidator.promote_to_active(cst, registry, max_age_seconds=86400.0)
    assert promoted.status == ConstraintStatus.STALE
    assert promoted.is_active is False


# ==============================================================================
# 3. CONSTRAINT CONFLICT DETECTION TESTS
# ==============================================================================

def test_conflicting_sources_detected_as_high_severity():
    """Verify conflicting rules (Rule 1 prohibition vs Rule 3 permission) produce a HIGH conflict."""
    provider = LocalKnowledgeProvider()
    extractor = LocalConstraintExtractor()
    fixtures = provider.fixtures

    candidates = extractor.extract(fixtures)
    prohibition = next(c for c in candidates if c.constraint_type == ConstraintType.PROHIBITION and c.target == "valve_b")
    permission = next(c for c in candidates if c.constraint_type == ConstraintType.PRECONDITION and c.target == "valve_b")

    conflicts = ConstraintConflictDetector.detect_conflicts([prohibition, permission])
    assert len(conflicts) == 1
    assert conflicts[0].conflict is True
    assert conflicts[0].severity == "HIGH"
    assert prohibition.status == ConstraintStatus.CONFLICTED
    assert permission.status == ConstraintStatus.CONFLICTED


def test_harmless_non_conflict_between_procedure_and_prohibition():
    """Verify procedure and prohibition on the same valve do not trigger a false conflict."""
    provider = LocalKnowledgeProvider()
    extractor = LocalConstraintExtractor()
    fixtures = provider.fixtures

    candidates = extractor.extract(fixtures)
    prohibition = next(c for c in candidates if c.constraint_type == ConstraintType.PROHIBITION)
    procedure = next(c for c in candidates if c.constraint_type == ConstraintType.INFORMATIONAL)

    conflicts = ConstraintConflictDetector.detect_conflicts([prohibition, procedure])
    assert len(conflicts) == 0
    assert prohibition.status != ConstraintStatus.CONFLICTED
    assert procedure.status != ConstraintStatus.CONFLICTED


# ==============================================================================
# 4. INTEGRATION & MANDATORY DEMONSTRATION SCENARIOS
# ==============================================================================

def test_scenario_3_knowledge_derived_prohibition_blocks_action():
    """MANDATORY SCENARIO:

    Initial World:
      Valve B = OPEN
      Pump P1 = ACTIVE
      Cooling = ACTIVE
      Human Zone = CLEAR
    Proposal:
      CLOSE_VALVE valve_b
    Knowledge Evidence:
      "Valve B must not be closed while Pump P1 is active."
    Result:
      PolicyEngine DENY
      No ticket minted
      No actuator execution
      Valve B remains OPEN
    """
    # 1. Setup World with Pump P1 active
    world = PhysicalWorld()
    world.set_pump_state("pump_p1", "ACTIVE")
    world.valves["valve_b"] = ValveState.OPEN
    world.cooling = CoolingState.ACTIVE
    world.human_zone = HumanZoneState.CLEAR

    initial_state = world.get_state()
    assert initial_state.valves["valve_b"] == ValveState.OPEN
    assert initial_state.pumps["pump_p1"] == "ACTIVE"

    # 2. Knowledge Provider with only Rule 1 (prohibition)
    rule1_fixture = LocalKnowledgeProvider._build_default_fixtures()[0]
    provider = LocalKnowledgeProvider(custom_fixtures=[rule1_fixture])
    knowledge_service = KnowledgeRetrievalService(provider=provider)
    extractor = LocalConstraintExtractor()

    # 3. Create Runtime with deterministic proposal to close valve_b
    runtime = MotionFenceRuntime(
        world=world,
        proposal_provider=LocalDeterministicProvider(),
        knowledge_service=knowledge_service,
        constraint_extractor=extractor,
    )

    # 4. Run cycle with high confidence evidence
    target_evidence = world.generate_targeted_evidence("valve_b")
    result = runtime.run_cycle(
        intent="Emergency shut off valve_b to isolate line",
        initial_evidence=target_evidence,
        knowledge_query="Valve B operating restrictions while Pump P1 is active",
    )

    # 5. Assertions: Must DENY due to active knowledge prohibition
    assert result.policy_decision.decision == DecisionType.DENY
    assert result.ticket is None
    assert result.execution_result is None
    # World state must remain UNCHANGED
    post_state = world.get_state()
    assert post_state.valves["valve_b"] == ValveState.OPEN
    assert any("knowledge_prohibition" in r.constraint for r in result.policy_decision.reasons if r.status == "failed")


def test_scenario_2_valid_action_with_pump_inactive_allowed():
    """Verify that when Pump P1 is INACTIVE, the knowledge prohibition condition does NOT hold,

    allowing the action to proceed to ACT and VERIFY.
    """
    world = PhysicalWorld()
    world.set_pump_state("pump_p1", "INACTIVE")
    world.valves["valve_b"] = ValveState.OPEN
    world.cooling = CoolingState.ACTIVE
    world.human_zone = HumanZoneState.CLEAR

    rule1_fixture = LocalKnowledgeProvider._build_default_fixtures()[0]
    provider = LocalKnowledgeProvider(custom_fixtures=[rule1_fixture])
    knowledge_service = KnowledgeRetrievalService(provider=provider)
    extractor = LocalConstraintExtractor()

    runtime = MotionFenceRuntime(
        world=world,
        proposal_provider=LocalDeterministicProvider(),
        knowledge_service=knowledge_service,
        constraint_extractor=extractor,
    )

    target_evidence = world.generate_targeted_evidence("valve_b")
    result = runtime.run_cycle(
        intent="Safely isolate valve_b with pump stopped",
        initial_evidence=target_evidence,
        knowledge_query="Valve B operational restrictions",
    )

    assert result.policy_decision.decision == DecisionType.ALLOW
    assert result.ticket is not None
    assert result.execution_result is not None
    assert result.execution_result.success is True
    assert result.verification_result is not None
    assert result.verification_result.is_verified is True
    assert world.get_state().valves["valve_b"] == ValveState.CLOSED


def test_scenario_harmless_procedure_does_not_block_action():
    """Verify harmless procedure ("Visual inspection should be performed") does not block CLOSE_VALVE."""
    world = PhysicalWorld()
    world.set_pump_state("pump_p1", "INACTIVE")
    world.valves["valve_b"] = ValveState.OPEN
    world.cooling = CoolingState.ACTIVE
    world.human_zone = HumanZoneState.CLEAR

    # Only load Fixture 2 (procedure)
    rule2_fixture = LocalKnowledgeProvider._build_default_fixtures()[1]
    provider = LocalKnowledgeProvider(custom_fixtures=[rule2_fixture])
    knowledge_service = KnowledgeRetrievalService(provider=provider)
    extractor = LocalConstraintExtractor()

    runtime = MotionFenceRuntime(
        world=world,
        proposal_provider=LocalDeterministicProvider(),
        knowledge_service=knowledge_service,
        constraint_extractor=extractor,
    )

    target_evidence = world.generate_targeted_evidence("valve_b")
    result = runtime.run_cycle(
        intent="Routine shutdown of valve_b",
        initial_evidence=target_evidence,
        knowledge_query="routine maintenance inspection for valve_b",
    )

    # Must be allowed! Procedure does not block
    assert result.policy_decision.decision == DecisionType.ALLOW
    assert world.get_state().valves["valve_b"] == ValveState.CLOSED


def test_scenario_conflicting_knowledge_blocks_action():
    """SCENARIO 4: Conflicting sources produce CONFLICTED state and block authorization."""
    world = PhysicalWorld()
    world.valves["valve_b"] = ValveState.OPEN

    # Load Fixture 1 (Prohibition) AND Fixture 3 (Contradictory exception)
    fixtures = [
        LocalKnowledgeProvider._build_default_fixtures()[0],
        LocalKnowledgeProvider._build_default_fixtures()[2],
    ]
    provider = LocalKnowledgeProvider(custom_fixtures=fixtures)
    knowledge_service = KnowledgeRetrievalService(provider=provider)
    extractor = LocalConstraintExtractor()

    runtime = MotionFenceRuntime(
        world=world,
        proposal_provider=LocalDeterministicProvider(),
        knowledge_service=knowledge_service,
        constraint_extractor=extractor,
    )

    target_evidence = world.generate_targeted_evidence("valve_b")
    result = runtime.run_cycle(
        intent="Close valve_b during conflicting guidance",
        initial_evidence=target_evidence,
        knowledge_query="Valve B emergency guidelines",
    )

    # Must DENY or block due to unresolved conflict
    assert result.policy_decision.decision == DecisionType.DENY
    assert len(result.constraint_conflicts) > 0
    assert result.ticket is None
    assert world.get_state().valves["valve_b"] == ValveState.OPEN


def test_scenario_stale_knowledge_triggers_need_more_evidence():
    """SCENARIO 5: Stale operational guidance triggers NEED_MORE_EVIDENCE."""
    world = PhysicalWorld()
    world.valves["valve_b"] = ValveState.OPEN

    # Load Fixture 4 (Stale source, 90 days old)
    stale_fixture = LocalKnowledgeProvider._build_default_fixtures()[3]
    provider = LocalKnowledgeProvider(custom_fixtures=[stale_fixture])
    knowledge_service = KnowledgeRetrievalService(provider=provider)
    extractor = LocalConstraintExtractor()

    runtime = MotionFenceRuntime(
        world=world,
        proposal_provider=LocalDeterministicProvider(),
        knowledge_service=knowledge_service,
        constraint_extractor=extractor,
    )

    target_evidence = world.generate_targeted_evidence("valve_b")
    result = runtime.run_cycle(
        intent="Operate valve_b under archived guidance",
        initial_evidence=target_evidence,
        knowledge_query="Legacy cooling specification",
    )

    assert result.policy_decision.decision == DecisionType.NEED_MORE_EVIDENCE
    assert result.ticket is None
    assert world.get_state().valves["valve_b"] == ValveState.OPEN


# ==============================================================================
# 5. SECURITY INVARIANTS & AUTHORITY BOUNDARY TESTS
# ==============================================================================

def test_candidate_constraint_cannot_directly_mutate_world():
    """INVARIANT: CandidateConstraint has no execution interface and cannot mutate PhysicalWorld."""
    world = PhysicalWorld()
    world.valves["valve_b"] = ValveState.OPEN

    cst = CandidateConstraint(
        constraint_id="cst_malicious",
        constraint_type=ConstraintType.PROHIBITION,
        action=ActionType.CLOSE_VALVE,
        target="valve_b",
        condition={},
        source_evidence_id="kb_01",
        confidence=0.99,
        created_at=time.time(),
        status=ConstraintStatus.ACTIVE,
    )

    assert not hasattr(cst, "execute")
    assert not hasattr(cst, "mutate")
    assert world.get_state().valves["valve_b"] == ValveState.OPEN


def test_knowledge_evidence_cannot_mint_authorization_ticket():
    """INVARIANT: KnowledgeEvidence cannot be passed to TicketAuthority to mint an AuthorizationTicket."""
    authority = TicketAuthority(secret_key="test_secret")
    ev = KnowledgeEvidence(
        id="kb_test",
        query="test",
        title="Test",
        source_url="local://test",
        content="test",
        retrieved_at=time.time(),
        source_metadata={},
        provenance="test",
        confidence=1.0,
        trust_status=TrustStatus.LOCAL_FIXTURE,
    )

    with pytest.raises(Exception):
        authority.mint_ticket(proposal=ev)  # type: ignore


def test_external_provider_cannot_bypass_policy_engine():
    """INVARIANT: Retrieved knowledge cannot bypass the deterministic PolicyEngine."""
    world = PhysicalWorld()
    actuator = PhysicalActuator(world=world)

    # An attacker attempts to create a proposal with an invalid ticket
    proposal = ActionProposal(
        id="prop_bypass",
        action_type=ActionType.CLOSE_VALVE,
        target="valve_b",
        supporting_evidence_ids=["ev_1"],
        model_confidence=0.99,
        rationale="Bypassing policy engine directly to actuator",
        timestamp=time.time(),
    )

    # Actuator execution without valid signed ticket MUST raise ValueError
    fake_ticket = AuthorizationTicket(
        ticket_id="fake_tkt",
        proposal_id="prop_bypass",
        action_type=ActionType.CLOSE_VALVE,
        target="valve_b",
        issued_at=time.time(),
        expires_at=time.time() + 60,
        signature="invalid_signature_bits",
    )

    with pytest.raises(UnauthorizedActionError) as exc:
        actuator.execute(proposal=proposal, ticket=fake_ticket)
    assert "Invalid ticket signature" in str(exc.value)
    assert world.get_state().valves["valve_b"] == ValveState.OPEN
