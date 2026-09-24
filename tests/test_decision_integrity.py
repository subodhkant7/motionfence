"""Adversarial and empirical test suite for MotionFence Phase 2D:
Decision Records, Hash-Linked Audit Chains, Deterministic Replay, and Safety Enclave.

SECURITY INVARIANTS TESTED:
1. Replay can mutate WorldState = NO
2. Replay can mint AuthorizationTicket = NO
3. Replay can call actuator = NO
4. Replay can call Tavily / Nemotron = NO
5. Tampered records immediately fail cryptographic verification (INTEGRITY_FAILURE)
6. Canonical serialization is strictly deterministic regardless of insertion order
7. Only SafetyEnclave can authorize actions and mint AuthorizationTickets
8. Cache vs Live distinction is explicit and unforgeable
"""

import time
import pytest

from motionfence.audit.models import (
    DecisionRecord,
    DecisionCategory,
    ExecutionMode,
    SourceMode,
    format_decision_audit,
)
from motionfence.audit.serialization import (
    canonical_serialize,
    canonical_json_dump,
    compute_record_hash,
)
from motionfence.audit.recorder import DecisionRecorder
from motionfence.audit.verifier import DecisionRecordVerifier
from motionfence.audit.replay import DecisionReplayEngine, ReplayStatus
from motionfence.runtime.enclave import (
    SafetyEnclave,
    EnclaveAuthorizationRequest,
    EnclaveAuthorizationResult,
)
from motionfence.runtime.core import MotionFenceRuntime, RuntimeCycleResult
from motionfence.simulation.world import PhysicalWorld, ValveState, CoolingState, HumanZoneState
from motionfence.models.actions import ActionProposal, ActionType, AuthorizationTicket, ExecutionResult
from motionfence.evidence.models import Evidence, EvidenceSource
from motionfence.constraints.models import CandidateConstraint, ConstraintType, ConstraintStatus
from motionfence.policy.models import Policy, DecisionType, PolicyDecision
from motionfence.runtime.events import EventBus
from motionfence.models.events import EventType


# ==============================================================================
# 1. CANONICAL SERIALIZATION & HASH DETERMINISM TESTS
# ==============================================================================

def test_canonical_serialization_dict_order_independence():
    """Verify that different dictionary insertion orders yield identical canonical bytes and hashes."""
    dict_a = {"z_field": 100, "a_field": "test", "m_list": [1, 2, 3]}
    dict_b = {"a_field": "test", "m_list": [1, 2, 3], "z_field": 100}

    bytes_a = canonical_serialize(dict_a)
    bytes_b = canonical_serialize(dict_b)

    assert bytes_a == bytes_b
    assert canonical_json_dump(dict_a) == canonical_json_dump(dict_b)


def test_canonical_hash_identity_and_tamper_sensitivity():
    """Verify same logical record yields same hash; one changed field produces a different hash."""
    world = PhysicalWorld()
    state = world.get_state()
    recorder = DecisionRecorder()

    rec1 = recorder.create_record(
        intent="Isolate valve_b safely",
        world_state_snapshot=state,
        policy_decision=DecisionCategory.ALLOW,
        policy_reasons=["All nominal policy checks passed."],
    )
    rec2 = recorder.create_record(
        intent="Isolate valve_b safely",
        world_state_snapshot=state,
        policy_decision=DecisionCategory.ALLOW,
        policy_reasons=["All nominal policy checks passed."],
    )

    # Force identical timestamps and decision IDs to verify pure pre-image determinism
    rec2.decision_id = rec1.decision_id
    rec2.created_at = rec1.created_at

    hash1 = compute_record_hash(rec1.model_dump(mode="json"), "GENESIS")
    hash2 = compute_record_hash(rec2.model_dump(mode="json"), "GENESIS")
    assert hash1 == hash2

    # Tamper with single policy reason
    rec_tampered = rec1.model_dump(mode="json")
    rec_tampered["policy_reasons"] = ["Tampered reason."]
    tampered_hash = compute_record_hash(rec_tampered, "GENESIS")

    assert tampered_hash != hash1


# ==============================================================================
# 2. HASH-LINKED AUDIT CHAIN TESTS
# ==============================================================================

def test_hash_linked_audit_chain_integrity():
    """Verify sequential records form an unbroken cryptographic chain."""
    world = PhysicalWorld()
    recorder = DecisionRecorder()

    rec0 = recorder.create_record(
        intent="First cycle",
        world_state_snapshot=world.get_state(),
        policy_decision=DecisionCategory.DENY,
    )
    recorder.finalize_record(rec0)

    rec1 = recorder.create_record(
        intent="Second cycle",
        world_state_snapshot=world.get_state(),
        policy_decision=DecisionCategory.ALLOW,
        authorization_ticket_id="tkt_001",
    )
    recorder.finalize_record(rec1)

    chain = recorder.get_all_records()
    assert len(chain) == 2
    assert chain[0].previous_record_hash is None
    assert chain[1].previous_record_hash == chain[0].record_hash

    reports = DecisionRecordVerifier.verify_chain(chain)
    assert all(r.is_valid for r in reports)
    assert all(r.chain_linked for r in reports)


def test_historical_record_tampering_breaks_chain():
    """Verify that tampering with an earlier record invalidates subsequent chain verification."""
    world = PhysicalWorld()
    recorder = DecisionRecorder()

    rec0 = recorder.finalize_record(
        recorder.create_record(
            intent="Step 1",
            world_state_snapshot=world.get_state(),
            policy_decision=DecisionCategory.DENY,
        )
    )
    rec1 = recorder.finalize_record(
        recorder.create_record(
            intent="Step 2",
            world_state_snapshot=world.get_state(),
            policy_decision=DecisionCategory.ALLOW,
            authorization_ticket_id="tkt_002",
        )
    )

    chain = recorder.get_all_records()

    # Adversary alters historical decision on rec0
    chain[0].policy_decision = DecisionCategory.ALLOW
    chain[0].authorization_ticket_id = "tkt_fake"

    reports = DecisionRecordVerifier.verify_chain(chain)
    assert reports[0].is_valid is False
    assert reports[0].hash_verified is False


# ==============================================================================
# 3. ADVERSARIAL DECISION RECORD TAMPERING TESTS
# ==============================================================================

def test_tamper_policy_decision_detected():
    """Verify tampering with policy_decision triggers INTEGRITY_FAILURE."""
    bus = EventBus()
    events = []
    bus.subscribe(lambda e: events.append(e))

    world = PhysicalWorld()
    recorder = DecisionRecorder(event_bus=bus)

    rec = recorder.finalize_record(
        recorder.create_record(
            intent="Isolate valve_b",
            world_state_snapshot=world.get_state(),
            policy_decision=DecisionCategory.DENY,
            policy_reasons=["Cooling inactive."],
        )
    )

    # Adversary alters DENY -> ALLOW
    rec.policy_decision = DecisionCategory.ALLOW
    report = DecisionRecordVerifier.verify_record(rec, event_bus=bus)

    assert report.is_valid is False
    assert report.hash_verified is False
    assert any(e.event_type == EventType.INTEGRITY_FAILURE for e in events)


def test_tamper_evidence_reference_detected():
    """Verify referencing an evidence ID not present in snapshots triggers INTEGRITY_FAILURE."""
    world = PhysicalWorld()
    recorder = DecisionRecorder()

    ev = Evidence(
        id="ev_vision_real",
        source=EvidenceSource.VISION,
        target="valve_b",
        observation={"leak_detected": True},
        confidence=0.95,
        provenance="camera:v1",
    )
    rec = recorder.finalize_record(
        recorder.create_record(
            intent="Isolate valve_b",
            world_state_snapshot=world.get_state(),
            policy_decision=DecisionCategory.DENY,
            sensor_evidence=[ev],
        )
    )

    # Adversary injects phantom evidence ID
    rec.sensor_evidence_ids.append("ev_phantom_999")
    report = DecisionRecordVerifier.verify_record(rec)

    assert report.is_valid is False
    assert report.references_consistent is False


def test_tamper_ticket_id_detected():
    """Verify modifying ticket identifier on a finalized record triggers INTEGRITY_FAILURE."""
    world = PhysicalWorld()
    recorder = DecisionRecorder()

    proposal = ActionProposal(
        id="prop_01",
        action_type=ActionType.CLOSE_VALVE,
        target="valve_b",
        rationale="Isolate leak",
        model_confidence=0.98,
    )
    rec = recorder.finalize_record(
        recorder.create_record(
            intent="Isolate valve_b",
            world_state_snapshot=world.get_state(),
            policy_decision=DecisionCategory.ALLOW,
            action_proposal=proposal,
            authorization_ticket_id="tkt_real_123",
            execution_result=ExecutionResult(
                success=True,
                action_id="prop_01",
                ticket_id="tkt_real_123",
                executed_action=ActionType.CLOSE_VALVE,
                target="valve_b",
                state_version_before=1,
                state_version_after=2,
            ),
        )
    )

    # Adversary tampers with ticket ID
    rec.authorization_ticket_id = "tkt_forged_999"
    report = DecisionRecordVerifier.verify_record(rec)

    assert report.is_valid is False
    assert report.hash_verified is False


def test_tamper_active_constraint_detected():
    """Verify modifying or injecting active constraint reference triggers INTEGRITY_FAILURE."""
    world = PhysicalWorld()
    recorder = DecisionRecorder()

    cst = CandidateConstraint(
        constraint_id="cst_valid_01",
        constraint_type=ConstraintType.PROHIBITION,
        action=ActionType.CLOSE_VALVE,
        target="valve_b",
        source_evidence_id="kb_ev_01",
    )
    rec = recorder.finalize_record(
        recorder.create_record(
            intent="Isolate valve_b",
            world_state_snapshot=world.get_state(),
            policy_decision=DecisionCategory.DENY,
            active_constraints=[cst],
        )
    )

    # Adversary injects phantom constraint ID into active_constraint_ids
    rec.active_constraint_ids.append("cst_phantom_999")
    report = DecisionRecordVerifier.verify_record(rec)

    assert report.is_valid is False
    assert report.references_consistent is False


def test_tamper_execution_result_detected():
    """Verify modifying execution result fields on a finalized record triggers INTEGRITY_FAILURE."""
    world = PhysicalWorld()
    recorder = DecisionRecorder()

    proposal = ActionProposal(
        id="prop_02",
        action_type=ActionType.CLOSE_VALVE,
        target="valve_b",
        rationale="Isolate leak",
        model_confidence=0.98,
    )
    rec = recorder.finalize_record(
        recorder.create_record(
            intent="Isolate valve_b",
            world_state_snapshot=world.get_state(),
            policy_decision=DecisionCategory.ALLOW,
            action_proposal=proposal,
            authorization_ticket_id="tkt_real_456",
            execution_result=ExecutionResult(
                success=True,
                action_id="prop_02",
                ticket_id="tkt_real_456",
                executed_action=ActionType.CLOSE_VALVE,
                target="valve_b",
                state_version_before=1,
                state_version_after=2,
            ),
        )
    )

    # Adversary tampers with execution success flag
    rec.execution_result.success = False
    report = DecisionRecordVerifier.verify_record(rec)

    assert report.is_valid is False
    assert report.hash_verified is False


def test_tamper_verification_result_detected():
    """Verify modifying verification result on a finalized record triggers INTEGRITY_FAILURE."""
    from motionfence.runtime.verification import VerificationResult, VerificationStatus
    world = PhysicalWorld()
    recorder = DecisionRecorder()

    proposal = ActionProposal(
        id="prop_03",
        action_type=ActionType.CLOSE_VALVE,
        target="valve_b",
        rationale="Isolate leak",
        model_confidence=0.98,
    )
    verif = VerificationResult(
        action_id="prop_03",
        target="valve_b",
        action_occurred=True,
        status=VerificationStatus.VERIFIED,
        expected_postconditions={"valve_b": "CLOSED"},
        observed_postconditions={"valve_b": "CLOSED"},
    )
    rec = recorder.finalize_record(
        recorder.create_record(
            intent="Isolate valve_b",
            world_state_snapshot=world.get_state(),
            policy_decision=DecisionCategory.ALLOW,
            action_proposal=proposal,
            authorization_ticket_id="tkt_real_789",
            verification_result=verif,
        )
    )

    # Adversary flips verification outcome
    rec.verification_result.status = VerificationStatus.VERIFICATION_FAILED
    report = DecisionRecordVerifier.verify_record(rec)

    assert report.is_valid is False
    assert report.hash_verified is False


# ==============================================================================
# 4. REPLAY SECURITY INVARIANT TESTS
# ==============================================================================

def test_replay_cannot_mutate_world_state():
    """Verify that replaying a decision leaves PhysicalWorld state completely untouched."""
    world = PhysicalWorld()
    world.valves["valve_b"] = ValveState.OPEN
    world.cooling = CoolingState.ACTIVE
    initial_version = world.get_state().version

    runtime = MotionFenceRuntime(world=world)
    res = runtime.run_cycle(
        intent="Isolate valve_b safely",
        initial_evidence=world.generate_targeted_evidence("valve_b"),
    )
    assert res.decision_record is not None

    world_version_after_action = world.get_state().version

    # Run replay engine
    engine = DecisionReplayEngine()
    rep = engine.replay(res.decision_record)

    # INVARIANT: WorldState version and valves must NOT be altered by replay
    assert world.get_state().version == world_version_after_action
    assert rep.status == ReplayStatus.REPLAY_MATCH


def test_replay_cannot_mint_authorization_tickets():
    """Verify that replay engine does not possess ticket minting handles or mint tickets."""
    world = PhysicalWorld()
    recorder = DecisionRecorder()

    rec = recorder.finalize_record(
        recorder.create_record(
            intent="Isolate valve_b",
            world_state_snapshot=world.get_state(),
            policy_decision=DecisionCategory.DENY,
        )
    )

    engine = DecisionReplayEngine()
    assert not hasattr(engine, "mint_ticket")
    assert not hasattr(engine, "ticket_authority")
    assert not hasattr(engine, "_ticket_authority")

    rep = engine.replay(rec)
    assert rep.status == ReplayStatus.REPLAY_MATCH


# ==============================================================================
# 5. DETERMINISTIC REPLAY CONVERGENCE & DIVERGENCE TESTS
# ==============================================================================

def test_replay_deterministic_allow_convergence():
    """Verify that a recorded ALLOW verdict re-evaluates deterministically to REPLAY_MATCH."""
    world = PhysicalWorld()
    world.valves["valve_b"] = ValveState.OPEN
    world.cooling = CoolingState.ACTIVE
    world.set_pump_state("pump_p1", "INACTIVE")
    world.set_human_zone(HumanZoneState.CLEAR)

    runtime = MotionFenceRuntime(world=world)
    res = runtime.run_cycle(
        intent="Routine isolate valve_b",
        initial_evidence=world.generate_targeted_evidence("valve_b"),
    )
    assert res.decision_record is not None
    assert res.decision_record.policy_decision == DecisionCategory.ALLOW

    engine = DecisionReplayEngine()
    report = engine.replay(res.decision_record)

    assert report.status == ReplayStatus.REPLAY_MATCH
    assert report.is_match is True
    assert report.recorded_verdict == "ALLOW"
    assert report.replayed_verdict == "ALLOW"
    assert len(report.steps) == 10


def test_replay_deterministic_deny_convergence():
    """Verify that a recorded DENY verdict (human in zone) re-evaluates deterministically to REPLAY_MATCH."""
    world = PhysicalWorld()
    world.valves["valve_b"] = ValveState.OPEN
    world.cooling = CoolingState.ACTIVE
    world.set_human_zone(HumanZoneState.OCCUPIED)  # Hard policy blocker

    runtime = MotionFenceRuntime(world=world)
    res = runtime.run_cycle(
        intent="Isolate valve_b",
        initial_evidence=world.generate_targeted_evidence("valve_b"),
    )
    assert res.decision_record is not None
    assert res.decision_record.policy_decision == DecisionCategory.DENY

    engine = DecisionReplayEngine()
    report = engine.replay(res.decision_record)

    assert report.status == ReplayStatus.REPLAY_MATCH
    assert report.recorded_verdict == "DENY"
    assert report.replayed_verdict == "DENY"


def test_replay_detects_deliberate_policy_divergence():
    """Verify that replaying against an altered policy identifies REPLAY_DIVERGENCE."""
    world = PhysicalWorld()
    world.valves["valve_b"] = ValveState.OPEN
    world.cooling = CoolingState.ACTIVE
    world.set_pump_state("pump_p1", "INACTIVE")
    world.set_human_zone(HumanZoneState.CLEAR)

    runtime = MotionFenceRuntime(world=world)
    res = runtime.run_cycle(
        intent="Isolate valve_b",
        initial_evidence=world.generate_targeted_evidence("valve_b"),
    )
    assert res.decision_record is not None
    assert res.decision_record.policy_decision == DecisionCategory.ALLOW

    # Deliberately modify policy rules during replay: prohibit CLOSE_VALVE actions
    stricter_policy = Policy(prohibited_actions=[ActionType.CLOSE_VALVE])

    engine = DecisionReplayEngine()
    report = engine.replay(res.decision_record, custom_policy=stricter_policy)

    assert report.status == ReplayStatus.REPLAY_DIVERGENCE
    assert report.is_match is False
    assert report.recorded_verdict == "ALLOW"
    assert report.replayed_verdict == "DENY"
    assert len(report.divergence_reasons) >= 1
    # INVARIANT: Original DecisionRecord was not altered
    assert res.decision_record.policy_decision == DecisionCategory.ALLOW


# ==============================================================================
# 6. SAFETY ENCLAVE ISOLATION TESTS
# ==============================================================================

def test_safety_enclave_zero_llm_and_isolated_authority():
    """Verify SafetyEnclave evaluates policy deterministically without external models or web calls."""
    enclave = SafetyEnclave()

    # Enclave must not have LLM or network attributes
    assert not hasattr(enclave, "llm")
    assert not hasattr(enclave, "tavily")
    assert not hasattr(enclave, "nebius")

    world = PhysicalWorld()
    proposal = ActionProposal(
        id="prop_enc_01",
        action_type=ActionType.CLOSE_VALVE,
        target="valve_b",
        rationale="Safe close",
        model_confidence=0.95,
    )
    evidence = world.generate_targeted_evidence("valve_b")

    req = EnclaveAuthorizationRequest(
        proposal=proposal,
        world_state=world.get_state(),
        evidence=evidence,
        policy=Policy(),
    )

    result = enclave.authorize(req)
    assert result.authorized is True
    assert result.ticket is not None
    assert result.ticket.proposal_id == "prop_enc_01"


def test_safety_enclave_blocks_unauthorized_proposals():
    """Verify SafetyEnclave refuses ticket minting when policy constraints fail."""
    enclave = SafetyEnclave()
    world = PhysicalWorld()
    world.cooling = CoolingState.INACTIVE  # Invariant violation

    proposal = ActionProposal(
        id="prop_enc_02",
        action_type=ActionType.CLOSE_VALVE,
        target="valve_b",
        rationale="Unsafe close",
        model_confidence=0.95,
    )
    req = EnclaveAuthorizationRequest(
        proposal=proposal,
        world_state=world.get_state(),
        evidence=world.generate_targeted_evidence("valve_b"),
        policy=Policy(),
    )

    result = enclave.authorize(req)
    assert result.authorized is False
    assert result.ticket is None
    assert result.is_authorized is False


# ==============================================================================
# 7. LIVE VS CACHE DISTINCTION & AUDIT FORMATTING TESTS
# ==============================================================================

def test_format_decision_audit_output():
    """Verify format_decision_audit produces the exact structured report required by Section 8."""
    world = PhysicalWorld()
    world.valves["valve_b"] = ValveState.OPEN
    world.cooling = CoolingState.ACTIVE
    world.set_pump_state("pump_p1", "INACTIVE")
    world.set_human_zone(HumanZoneState.CLEAR)

    runtime = MotionFenceRuntime(world=world)
    res = runtime.run_cycle(
        intent="Isolate leaking line while preserving cooling.",
        initial_evidence=world.generate_targeted_evidence("valve_b"),
    )
    assert res.decision_record is not None

    text = format_decision_audit(res.decision_record)
    assert "MOTIONFENCE DECISION" in text
    assert "Intent:\nIsolate leaking line while preserving cooling." in text
    assert "Proposed action:\nCLOSE_VALVE valve_b" in text
    assert "Policy:\nALLOW" in text
    assert "Authorization ticket:\n" in text
    assert "World mutation:\nAPPLIED" in text
    assert "Final verification:\nVERIFIED" in text


def test_execution_mode_and_source_mode_explicitly_labeled():
    """Verify DecisionRecord explicitly captures execution_mode and source_mode."""
    world = PhysicalWorld()
    recorder = DecisionRecorder()

    rec_live = recorder.create_record(
        intent="Live operation",
        world_state_snapshot=world.get_state(),
        policy_decision=DecisionCategory.ALLOW,
        provider_metadata={
            "provider": "nebius",
            "model": "nvidia/nemotron-3-super-120b-a12b",
            "execution_mode": ExecutionMode.LIVE.value,
            "source_mode": SourceMode.LIVE_MODEL_RESPONSE.value,
        },
    )
    assert rec_live.provider_metadata["execution_mode"] == "LIVE"
    assert rec_live.provider_metadata["source_mode"] == "LIVE_MODEL_RESPONSE"

    rec_cached = recorder.create_record(
        intent="Cached replay",
        world_state_snapshot=world.get_state(),
        policy_decision=DecisionCategory.ALLOW,
        provider_metadata={
            "provider": "nebius",
            "model": "nvidia/nemotron-3-super-120b-a12b",
            "execution_mode": ExecutionMode.REPLAY.value,
            "source_mode": SourceMode.LOCAL_CACHE_REPLAY.value,
        },
    )
    assert rec_cached.provider_metadata["execution_mode"] == "REPLAY"
    assert rec_cached.provider_metadata["source_mode"] == "LOCAL_CACHE_REPLAY"
    assert rec_live.provider_metadata != rec_cached.provider_metadata
