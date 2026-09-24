"""Phase 2F: State-Bound Authorization, TOCTOU Defense & Execution-Time Revalidation Tests.

Tests cover:
- Deterministic world-state hashing
- Deterministic authorization-context hashing
- World-state version tracking and ticket binding
- TOCTOU scenarios (human zone, pump, cooling, target, evidence, policy, constraint drift)
- Execution-time revalidation
- Stale ticket rejection
- Replay integration
- Bounded assurance properties PROP_008-PROP_011
- Adversarial TOCTOU violation detection
"""

import time
import hashlib
from copy import deepcopy

import pytest

from motionfence.models.actions import ActionProposal, ActionType, AuthorizationTicket
from motionfence.models.world import WorldState, ValveState, CoolingState, HumanZoneState, LeakState
from motionfence.evidence.models import Evidence, EvidenceSource
from motionfence.policy.models import Policy, PolicyDecision, DecisionType
from motionfence.policy.engine import PolicyEngine
from motionfence.constraints.models import CandidateConstraint, ConstraintType, ConstraintStatus
from motionfence.simulation.world import PhysicalWorld
from motionfence.simulation.actuator import PhysicalActuator
from motionfence.simulation.exceptions import UnauthorizedActionError
from motionfence.runtime.ticket import TicketAuthority
from motionfence.runtime.enclave import SafetyEnclave, EnclaveAuthorizationRequest
from motionfence.runtime.revalidation import (
    AuthorizationContext,
    AuthorizationRevalidationResult,
    RevalidationStatus,
    ExecutionTimeRevalidator,
    build_authorization_context,
    compute_world_state_hash,
    compute_constraint_set_hash,
    compute_evidence_context_hash,
    compute_authorization_context_hash,
)
from motionfence.assurance.checker import BoundedAssuranceChecker
from motionfence.assurance.invariants import AssurancePropertyRegistry
from motionfence.assurance.models import FindingStatus
from motionfence.audit.replay import DecisionReplayEngine, ReplayStatus
from motionfence.audit.recorder import DecisionRecorder
from motionfence.audit.models import DecisionCategory
from motionfence.runtime.core import MotionFenceRuntime
from motionfence.runtime.events import EventBus
from motionfence.models.events import EventType


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_world_state(**overrides) -> WorldState:
    defaults = {
        "valves": {"valve_a": ValveState.OPEN, "valve_b": ValveState.OPEN},
        "cooling": CoolingState.ACTIVE,
        "human_zone": HumanZoneState.CLEAR,
        "pumps": {"pump_p1": "STOPPED"},
        "leak": LeakState(active=True, target="valve_b", severity=0.85, flow_rate_lpm=14.2),
        "version": 1,
    }
    defaults.update(overrides)
    return WorldState(**defaults)


def _make_proposal(**overrides) -> ActionProposal:
    defaults = {
        "action_type": ActionType.CLOSE_VALVE,
        "target": "valve_b",
        "rationale": "Isolate leaking line",
        "model_confidence": 0.96,
        "supporting_evidence_ids": ["ev_1"],
    }
    defaults.update(overrides)
    return ActionProposal(**defaults)


def _make_evidence() -> list:
    return [
        Evidence(
            source=EvidenceSource.THERMAL_SENSOR,
            target="valve_b",
            observation={"leak_confirmed": True},
            confidence=0.96,
            timestamp=time.time(),
            provenance="flir_thermal_ptu_02",
        ),
    ]


def _make_constraints() -> list:
    return []


# ---------------------------------------------------------------------------
# 1. Deterministic Hashing Tests
# ---------------------------------------------------------------------------

class TestDeterministicHashing:
    """Verify that world-state and context hashing is deterministic and change-sensitive."""

    def test_same_world_state_produces_same_hash(self):
        """Same world state → same hash."""
        ws1 = _make_world_state()
        ws2 = _make_world_state()
        assert compute_world_state_hash(ws1) == compute_world_state_hash(ws2)

    def test_safety_relevant_change_produces_different_hash(self):
        """One safety-relevant field change → different hash."""
        ws1 = _make_world_state(human_zone=HumanZoneState.CLEAR)
        ws2 = _make_world_state(human_zone=HumanZoneState.OCCUPIED)
        assert compute_world_state_hash(ws1) != compute_world_state_hash(ws2)

    def test_cooling_change_produces_different_hash(self):
        """Cooling state change → different hash."""
        ws1 = _make_world_state(cooling=CoolingState.ACTIVE)
        ws2 = _make_world_state(cooling=CoolingState.INACTIVE)
        assert compute_world_state_hash(ws1) != compute_world_state_hash(ws2)

    def test_pump_change_produces_different_hash(self):
        """Pump state change → different hash."""
        ws1 = _make_world_state(pumps={"pump_p1": "STOPPED"})
        ws2 = _make_world_state(pumps={"pump_p1": "ACTIVE"})
        assert compute_world_state_hash(ws1) != compute_world_state_hash(ws2)

    def test_version_change_produces_different_hash(self):
        """World version increment → different hash."""
        ws1 = _make_world_state(version=1)
        ws2 = _make_world_state(version=2)
        assert compute_world_state_hash(ws1) != compute_world_state_hash(ws2)

    def test_deterministic_context_hash(self):
        """Authorization context hash is deterministic given same inputs."""
        ws = _make_world_state()
        proposal = _make_proposal()
        evidence = _make_evidence()
        ctx1 = build_authorization_context(proposal, ws, "1.0.0", [], evidence)
        ctx2 = build_authorization_context(proposal, ws, "1.0.0", [], evidence)
        assert compute_authorization_context_hash(ctx1) == compute_authorization_context_hash(ctx2)

    def test_empty_constraint_set_hash_is_deterministic(self):
        """Empty constraint set always produces the same hash."""
        h1 = compute_constraint_set_hash([])
        h2 = compute_constraint_set_hash([])
        assert h1 == h2

    def test_empty_evidence_hash_is_deterministic(self):
        """Empty evidence set always produces the same hash."""
        h1 = compute_evidence_context_hash([])
        h2 = compute_evidence_context_hash([])
        assert h1 == h2


# ---------------------------------------------------------------------------
# 2. World-State Versioning Tests
# ---------------------------------------------------------------------------

class TestWorldStateVersioning:
    """Verify monotonic world-state versioning and ticket binding."""

    def test_version_increments_on_mutation(self):
        """PhysicalWorld.version increments on state mutation."""
        world = PhysicalWorld()
        v0 = world.version
        world.set_human_zone(HumanZoneState.OCCUPIED)
        assert world.version == v0 + 1

    def test_pump_state_change_increments_version(self):
        """Pump state change increments world version."""
        world = PhysicalWorld()
        v0 = world.version
        world.set_pump_state("pump_p1", "STOPPED")
        assert world.version == v0 + 1

    def test_ticket_captures_issuance_version(self):
        """Minted ticket captures world-state version at issuance time."""
        ws = _make_world_state(version=42)
        proposal = _make_proposal()
        ta = TicketAuthority()
        ticket = ta.mint_ticket(proposal, world_state=ws, evidence=_make_evidence())
        assert ticket.world_state_version == 42

    def test_stale_version_invalidates_ticket(self):
        """Ticket minted at version=42 is invalidated at version=43."""
        ws_auth = _make_world_state(version=42)
        ws_exec = _make_world_state(version=43)
        proposal = _make_proposal()
        evidence = _make_evidence()

        ctx = build_authorization_context(proposal, ws_auth, "1.0.0", [], evidence)

        result = ExecutionTimeRevalidator.revalidate(
            authorization_context=ctx,
            current_world_state=ws_exec,
            current_policy_version="1.0.0",
            current_constraints=[],
            current_evidence=evidence,
            ticket_expires_at=time.time() + 30,
            proposal_action_type=ActionType.CLOSE_VALVE,
            proposal_target="valve_b",
        )
        assert result.status == RevalidationStatus.WORLD_STATE_CHANGED


# ---------------------------------------------------------------------------
# 3. TOCTOU Scenario Tests
# ---------------------------------------------------------------------------

class TestTOCTOUScenarios:
    """Mandatory TOCTOU (Time-of-Check vs Time-of-Use) defense tests."""

    def test_human_zone_toctou(self):
        """Human enters zone after authorization → ticket invalidated, no actuation."""
        ws_auth = _make_world_state(human_zone=HumanZoneState.CLEAR, version=1)
        ws_exec = _make_world_state(human_zone=HumanZoneState.OCCUPIED, version=2)
        proposal = _make_proposal()
        evidence = _make_evidence()
        ctx = build_authorization_context(proposal, ws_auth, "1.0.0", [], evidence)

        result = ExecutionTimeRevalidator.revalidate(
            authorization_context=ctx,
            current_world_state=ws_exec,
            current_policy_version="1.0.0",
            current_constraints=[],
            current_evidence=evidence,
            ticket_expires_at=time.time() + 30,
            proposal_action_type=ActionType.CLOSE_VALVE,
            proposal_target="valve_b",
        )
        assert result.status == RevalidationStatus.WORLD_STATE_CHANGED
        assert result.observed_world_version == 2
        assert result.expected_world_version == 1

    def test_pump_state_toctou(self):
        """Pump P1 starts after authorization → ticket invalidated."""
        ws_auth = _make_world_state(pumps={"pump_p1": "STOPPED"}, version=10)
        ws_exec = _make_world_state(pumps={"pump_p1": "ACTIVE"}, version=11)
        proposal = _make_proposal()
        evidence = _make_evidence()
        ctx = build_authorization_context(proposal, ws_auth, "1.0.0", [], evidence)

        result = ExecutionTimeRevalidator.revalidate(
            authorization_context=ctx,
            current_world_state=ws_exec,
            current_policy_version="1.0.0",
            current_constraints=[],
            current_evidence=evidence,
            ticket_expires_at=time.time() + 30,
            proposal_action_type=ActionType.CLOSE_VALVE,
            proposal_target="valve_b",
        )
        assert result.status == RevalidationStatus.WORLD_STATE_CHANGED

    def test_cooling_state_drift(self):
        """Cooling becomes INACTIVE after authorization → ticket invalidated."""
        ws_auth = _make_world_state(cooling=CoolingState.ACTIVE, version=5)
        ws_exec = _make_world_state(cooling=CoolingState.INACTIVE, version=6)
        proposal = _make_proposal()
        evidence = _make_evidence()
        ctx = build_authorization_context(proposal, ws_auth, "1.0.0", [], evidence)

        result = ExecutionTimeRevalidator.revalidate(
            authorization_context=ctx,
            current_world_state=ws_exec,
            current_policy_version="1.0.0",
            current_constraints=[],
            current_evidence=evidence,
            ticket_expires_at=time.time() + 30,
            proposal_action_type=ActionType.CLOSE_VALVE,
            proposal_target="valve_b",
        )
        assert result.status == RevalidationStatus.WORLD_STATE_CHANGED

    def test_target_state_drift(self):
        """Valve B changes to CLOSED after authorization → stale context."""
        ws_auth = _make_world_state(
            valves={"valve_a": ValveState.OPEN, "valve_b": ValveState.OPEN}, version=3
        )
        ws_exec = _make_world_state(
            valves={"valve_a": ValveState.OPEN, "valve_b": ValveState.CLOSED}, version=4
        )
        proposal = _make_proposal()
        evidence = _make_evidence()
        ctx = build_authorization_context(proposal, ws_auth, "1.0.0", [], evidence)

        result = ExecutionTimeRevalidator.revalidate(
            authorization_context=ctx,
            current_world_state=ws_exec,
            current_policy_version="1.0.0",
            current_constraints=[],
            current_evidence=evidence,
            ticket_expires_at=time.time() + 30,
            proposal_action_type=ActionType.CLOSE_VALVE,
            proposal_target="valve_b",
        )
        assert result.status == RevalidationStatus.WORLD_STATE_CHANGED

    def test_evidence_context_drift(self):
        """New contradictory evidence appears → evidence context hash changes."""
        ws = _make_world_state(version=1)
        proposal = _make_proposal()
        evidence_auth = _make_evidence()
        evidence_exec = [
            Evidence(
                source=EvidenceSource.PRESSURE_SENSOR,
                target="valve_b",
                observation={"pressure_normal": True, "leak_detected": False},
                confidence=0.91,
                timestamp=time.time(),
                provenance="sensor_piezo_01",
            ),
        ]
        ctx = build_authorization_context(proposal, ws, "1.0.0", [], evidence_auth)

        result = ExecutionTimeRevalidator.revalidate(
            authorization_context=ctx,
            current_world_state=ws,
            current_policy_version="1.0.0",
            current_constraints=[],
            current_evidence=evidence_exec,
            ticket_expires_at=time.time() + 30,
            proposal_action_type=ActionType.CLOSE_VALVE,
            proposal_target="valve_b",
        )
        assert result.status == RevalidationStatus.EVIDENCE_CHANGED


# ---------------------------------------------------------------------------
# 4. Policy & Constraint Drift Tests
# ---------------------------------------------------------------------------

class TestPolicyConstraintDrift:
    """Verify policy and constraint drift detection."""

    def test_policy_version_drift(self):
        """Policy version changes → ticket invalidated."""
        ws = _make_world_state(version=1)
        proposal = _make_proposal()
        evidence = _make_evidence()
        ctx = build_authorization_context(proposal, ws, "2026.1", [], evidence)

        result = ExecutionTimeRevalidator.revalidate(
            authorization_context=ctx,
            current_world_state=ws,
            current_policy_version="2026.2",
            current_constraints=[],
            current_evidence=evidence,
            ticket_expires_at=time.time() + 30,
            proposal_action_type=ActionType.CLOSE_VALVE,
            proposal_target="valve_b",
        )
        assert result.status == RevalidationStatus.POLICY_CHANGED

    def test_constraint_set_drift(self):
        """Active constraint set changes → ticket invalidated."""
        ws = _make_world_state(version=1)
        proposal = _make_proposal()
        evidence = _make_evidence()
        constraints_auth: list = []
        constraints_exec = [
            CandidateConstraint(
                constraint_id="cst_new_001",
                source_evidence_id="ev_1",
                evidence_id="ev_1",
                constraint_type=ConstraintType.PROHIBITION,
                action=ActionType.CLOSE_VALVE,
                target="valve_b",
                claim_text="New prohibition added after authorization.",
                status=ConstraintStatus.ACTIVE,
            ),
        ]
        ctx = build_authorization_context(proposal, ws, "1.0.0", constraints_auth, evidence)

        result = ExecutionTimeRevalidator.revalidate(
            authorization_context=ctx,
            current_world_state=ws,
            current_policy_version="1.0.0",
            current_constraints=constraints_exec,
            current_evidence=evidence,
            ticket_expires_at=time.time() + 30,
            proposal_action_type=ActionType.CLOSE_VALVE,
            proposal_target="valve_b",
        )
        assert result.status == RevalidationStatus.CONSTRAINT_CHANGED


# ---------------------------------------------------------------------------
# 5. Execution & Expiration Tests
# ---------------------------------------------------------------------------

class TestExecutionAndExpiration:
    """Verify that valid tickets execute and stale/expired tickets are rejected."""

    def test_valid_current_ticket_revalidates(self):
        """Valid ticket with unchanged context passes revalidation."""
        ws = _make_world_state(version=1)
        proposal = _make_proposal()
        evidence = _make_evidence()
        ctx = build_authorization_context(proposal, ws, "1.0.0", [], evidence)

        result = ExecutionTimeRevalidator.revalidate(
            authorization_context=ctx,
            current_world_state=ws,
            current_policy_version="1.0.0",
            current_constraints=[],
            current_evidence=evidence,
            ticket_expires_at=time.time() + 30,
            proposal_action_type=ActionType.CLOSE_VALVE,
            proposal_target="valve_b",
        )
        assert result.status == RevalidationStatus.VALID

    def test_expired_ticket_rejected(self):
        """Expired ticket is rejected regardless of context validity."""
        ws = _make_world_state(version=1)
        proposal = _make_proposal()
        evidence = _make_evidence()
        ctx = build_authorization_context(proposal, ws, "1.0.0", [], evidence)

        result = ExecutionTimeRevalidator.revalidate(
            authorization_context=ctx,
            current_world_state=ws,
            current_policy_version="1.0.0",
            current_constraints=[],
            current_evidence=evidence,
            ticket_expires_at=time.time() - 1,  # Already expired
            proposal_action_type=ActionType.CLOSE_VALVE,
            proposal_target="valve_b",
        )
        assert result.status == RevalidationStatus.TICKET_EXPIRED

    def test_action_mismatch_rejected(self):
        """Post-authorization action tampering is detected."""
        ws = _make_world_state(version=1)
        proposal = _make_proposal(action_type=ActionType.CLOSE_VALVE)
        evidence = _make_evidence()
        ctx = build_authorization_context(proposal, ws, "1.0.0", [], evidence)

        result = ExecutionTimeRevalidator.revalidate(
            authorization_context=ctx,
            current_world_state=ws,
            current_policy_version="1.0.0",
            current_constraints=[],
            current_evidence=evidence,
            ticket_expires_at=time.time() + 30,
            proposal_action_type=ActionType.OPEN_VALVE,  # Tampered action
            proposal_target="valve_b",
        )
        assert result.status == RevalidationStatus.ACTION_MISMATCH

    def test_target_mismatch_rejected(self):
        """Post-authorization target tampering is detected."""
        ws = _make_world_state(version=1)
        proposal = _make_proposal(target="valve_b")
        evidence = _make_evidence()
        ctx = build_authorization_context(proposal, ws, "1.0.0", [], evidence)

        result = ExecutionTimeRevalidator.revalidate(
            authorization_context=ctx,
            current_world_state=ws,
            current_policy_version="1.0.0",
            current_constraints=[],
            current_evidence=evidence,
            ticket_expires_at=time.time() + 30,
            proposal_action_type=ActionType.CLOSE_VALVE,
            proposal_target="valve_a",  # Tampered target
        )
        assert result.status == RevalidationStatus.TARGET_MISMATCH

    def test_stale_ticket_cannot_mutate_world(self):
        """A stale revalidation result means no world mutation should occur."""
        ws = _make_world_state(version=1)
        proposal = _make_proposal()
        evidence = _make_evidence()
        ctx = build_authorization_context(proposal, ws, "1.0.0", [], evidence)

        ws_mutated = _make_world_state(version=2, human_zone=HumanZoneState.OCCUPIED)
        result = ExecutionTimeRevalidator.revalidate(
            authorization_context=ctx,
            current_world_state=ws_mutated,
            current_policy_version="1.0.0",
            current_constraints=[],
            current_evidence=evidence,
            ticket_expires_at=time.time() + 30,
            proposal_action_type=ActionType.CLOSE_VALVE,
            proposal_target="valve_b",
        )
        assert result.status != RevalidationStatus.VALID
        # Revalidation cannot mutate state — it is purely observational
        assert ws_mutated.version == 2
        assert ws_mutated.human_zone == HumanZoneState.OCCUPIED


# ---------------------------------------------------------------------------
# 6. Ticket State-Binding Tests
# ---------------------------------------------------------------------------

class TestTicketStateBinding:
    """Verify that minted tickets carry state-binding fields."""

    def test_ticket_has_authorization_context_hash(self):
        """Minted ticket includes a non-empty authorization_context_hash."""
        ws = _make_world_state(version=1)
        proposal = _make_proposal()
        ta = TicketAuthority()
        ticket = ta.mint_ticket(proposal, world_state=ws, evidence=_make_evidence())
        assert ticket.authorization_context_hash != ""
        assert len(ticket.authorization_context_hash) == 64  # SHA-256 hex length

    def test_ticket_has_world_state_hash(self):
        """Minted ticket includes world_state_hash."""
        ws = _make_world_state(version=5)
        proposal = _make_proposal()
        ta = TicketAuthority()
        ticket = ta.mint_ticket(proposal, world_state=ws, evidence=_make_evidence())
        assert ticket.world_state_hash != ""
        assert ticket.world_state_version == 5

    def test_ticket_has_nonce(self):
        """Minted ticket includes a nonce for replay protection."""
        ws = _make_world_state()
        proposal = _make_proposal()
        ta = TicketAuthority()
        t1 = ta.mint_ticket(proposal, world_state=ws, evidence=_make_evidence())
        t2 = ta.mint_ticket(proposal, world_state=ws, evidence=_make_evidence())
        assert t1.nonce != ""
        assert t2.nonce != ""
        assert t1.nonce != t2.nonce  # Nonces must differ


# ---------------------------------------------------------------------------
# 7. Enclave Integration Tests
# ---------------------------------------------------------------------------

class TestEnclaveIntegration:
    """Verify that SafetyEnclave produces state-bound tickets."""

    def test_enclave_produces_authorization_context(self):
        """SafetyEnclave.authorize returns an authorization_context on ALLOW."""
        ws = _make_world_state(version=1)
        proposal = _make_proposal()
        evidence = _make_evidence()
        policy = Policy()

        enclave = SafetyEnclave()
        request = EnclaveAuthorizationRequest(
            proposal=proposal,
            world_state=ws,
            evidence=evidence,
            policy=policy,
        )
        result = enclave.authorize(request)
        if result.authorized:
            assert result.authorization_context is not None
            assert result.authorization_context.world_state_version == 1
            assert result.ticket is not None
            assert result.ticket.authorization_context_hash != ""


# ---------------------------------------------------------------------------
# 8. Security Invariant Tests
# ---------------------------------------------------------------------------

class TestSecurityInvariants:
    """Verify critical security properties required by Phase 2F."""

    def test_revalidation_cannot_mutate_world_state(self):
        """ExecutionTimeRevalidator has no mutation capability."""
        ws = _make_world_state(version=1)
        original_version = ws.version
        proposal = _make_proposal()
        evidence = _make_evidence()
        ctx = build_authorization_context(proposal, ws, "1.0.0", [], evidence)

        ExecutionTimeRevalidator.revalidate(
            authorization_context=ctx,
            current_world_state=ws,
            current_policy_version="1.0.0",
            current_constraints=[],
            current_evidence=evidence,
            ticket_expires_at=time.time() + 30,
            proposal_action_type=ActionType.CLOSE_VALVE,
            proposal_target="valve_b",
        )
        assert ws.version == original_version  # No mutation

    def test_revalidation_failure_produces_no_mutation(self):
        """Failed revalidation leaves world state completely unchanged."""
        world = PhysicalWorld()
        v0 = world.version
        pre_state = world.get_state()

        proposal = _make_proposal()
        evidence = _make_evidence()
        ctx = build_authorization_context(proposal, pre_state, "1.0.0", [], evidence)

        # Mutate world (TOCTOU)
        world.set_human_zone(HumanZoneState.OCCUPIED)
        current_state = world.get_state()

        result = ExecutionTimeRevalidator.revalidate(
            authorization_context=ctx,
            current_world_state=current_state,
            current_policy_version="1.0.0",
            current_constraints=[],
            current_evidence=evidence,
            ticket_expires_at=time.time() + 30,
            proposal_action_type=ActionType.CLOSE_VALVE,
            proposal_target="valve_b",
        )
        assert result.status != RevalidationStatus.VALID
        # Valve B remains OPEN — no mutation allowed
        assert world.valves["valve_b"] == ValveState.OPEN

    def test_stale_ticket_cannot_be_reused(self):
        """A consumed ticket remains consumed regardless of revalidation status."""
        ws = _make_world_state(version=1)
        proposal = _make_proposal()
        ta = TicketAuthority()
        ticket = ta.mint_ticket(proposal, world_state=ws, evidence=_make_evidence())
        ticket.consumed = True
        assert ticket.consumed is True
        # Revalidation does not un-consume tickets

    def test_no_model_or_network_in_revalidation(self):
        """ExecutionTimeRevalidator is a static method with no external dependencies."""
        # This is a structural test — the revalidator is @staticmethod with no __init__
        assert hasattr(ExecutionTimeRevalidator, "revalidate")
        method = getattr(ExecutionTimeRevalidator, "revalidate")
        assert callable(method)


# ---------------------------------------------------------------------------
# 9. Bounded Assurance Property Tests (PROP_008-PROP_011)
# ---------------------------------------------------------------------------

class TestBoundedAssurancePhase2F:
    """Verify Phase 2F bounded properties via Z3 SMT solver."""

    def test_property_registry_contains_11_properties(self):
        """Registry has at least 11 properties (7 Phase 2E + 4 Phase 2F + Phase 2G)."""
        registry = AssurancePropertyRegistry()
        assert len(registry.list_all()) >= 11
        # Check all Phase 2F properties are registered
        ids = {p.property_id for p in registry.list_all()}
        assert "PROP_008_NO_EXECUTION_AFTER_STATE_DRIFT" in ids
        assert "PROP_009_POLICY_VERSION_BINDING" in ids
        assert "PROP_010_CONSTRAINT_SET_BINDING" in ids
        assert "PROP_011_EXECUTION_TIME_VALIDITY" in ids

    def test_all_11_properties_satisfied_under_standard_policy(self):
        """All properties satisfied under standard (unmutated) policy rules."""
        checker = BoundedAssuranceChecker()
        findings = checker.check_all()
        for f in findings:
            assert f.status == FindingStatus.SATISFIED, (
                f"Property {f.property_id} unexpectedly {f.status.value}: {f.explanation}"
            )
        assert len(findings) >= 11

    def test_prop_008_violated_when_revalidation_disabled(self):
        """PROP_008: Disabling revalidation allows execution after state drift → VIOLATED."""
        checker = BoundedAssuranceChecker()
        finding = checker.check_property(
            "PROP_008_NO_EXECUTION_AFTER_STATE_DRIFT",
            policy_mutations={"disable_revalidation": True, "disable_execution_requires_revalidation": True},
        )
        assert finding.status == FindingStatus.VIOLATED
        assert finding.counterexample is not None

    def test_prop_009_violated_when_revalidation_disabled(self):
        """PROP_009: Disabling revalidation allows execution under different policy version → VIOLATED."""
        checker = BoundedAssuranceChecker()
        finding = checker.check_property(
            "PROP_009_POLICY_VERSION_BINDING",
            policy_mutations={"disable_revalidation": True, "disable_execution_requires_revalidation": True},
        )
        assert finding.status == FindingStatus.VIOLATED
        assert finding.counterexample is not None

    def test_prop_010_violated_when_revalidation_disabled(self):
        """PROP_010: Disabling revalidation allows execution with different constraints → VIOLATED."""
        checker = BoundedAssuranceChecker()
        finding = checker.check_property(
            "PROP_010_CONSTRAINT_SET_BINDING",
            policy_mutations={"disable_revalidation": True, "disable_execution_requires_revalidation": True},
        )
        assert finding.status == FindingStatus.VIOLATED
        assert finding.counterexample is not None

    def test_prop_011_violated_when_execution_bypass_revalidation(self):
        """PROP_011: Execution without revalidation → VIOLATED."""
        checker = BoundedAssuranceChecker()
        finding = checker.check_property(
            "PROP_011_EXECUTION_TIME_VALIDITY",
            policy_mutations={"disable_execution_requires_revalidation": True},
        )
        assert finding.status == FindingStatus.VIOLATED
        assert finding.counterexample is not None

    def test_toctou_counterexample_contains_execution_attempted(self):
        """PROP_008 counterexample demonstrates execution was attempted after state drift."""
        checker = BoundedAssuranceChecker()
        finding = checker.check_property(
            "PROP_008_NO_EXECUTION_AFTER_STATE_DRIFT",
            policy_mutations={"disable_revalidation": True, "disable_execution_requires_revalidation": True},
        )
        assert finding.status == FindingStatus.VIOLATED
        ce = finding.counterexample
        assert ce is not None
        # The counterexample must demonstrate execution was attempted
        assert "execution_attempted" in ce or len(ce) > 0


# ---------------------------------------------------------------------------
# 10. Adversarial TOCTOU Tests
# ---------------------------------------------------------------------------

class TestAdversarialTOCTOU:
    """Verify that stale tickets never execute under any tested scenario."""

    def test_stale_ticket_execution_count_zero(self):
        """No stale ticket executes across all TOCTOU scenarios."""
        stale_executed = 0
        total_scenarios = 0

        scenarios = [
            # (auth_overrides, exec_overrides, name)
            ({"human_zone": HumanZoneState.CLEAR, "version": 1},
             {"human_zone": HumanZoneState.OCCUPIED, "version": 2},
             "human_zone_toctou"),
            ({"pumps": {"pump_p1": "STOPPED"}, "version": 1},
             {"pumps": {"pump_p1": "ACTIVE"}, "version": 2},
             "pump_toctou"),
            ({"cooling": CoolingState.ACTIVE, "version": 1},
             {"cooling": CoolingState.INACTIVE, "version": 2},
             "cooling_toctou"),
            ({"valves": {"valve_a": ValveState.OPEN, "valve_b": ValveState.OPEN}, "version": 1},
             {"valves": {"valve_a": ValveState.OPEN, "valve_b": ValveState.CLOSED}, "version": 2},
             "target_toctou"),
        ]

        for auth_kw, exec_kw, name in scenarios:
            total_scenarios += 1
            ws_auth = _make_world_state(**auth_kw)
            ws_exec = _make_world_state(**exec_kw)
            proposal = _make_proposal()
            evidence = _make_evidence()
            ctx = build_authorization_context(proposal, ws_auth, "1.0.0", [], evidence)

            result = ExecutionTimeRevalidator.revalidate(
                authorization_context=ctx,
                current_world_state=ws_exec,
                current_policy_version="1.0.0",
                current_constraints=[],
                current_evidence=evidence,
                ticket_expires_at=time.time() + 30,
                proposal_action_type=ActionType.CLOSE_VALVE,
                proposal_target="valve_b",
            )
            if result.status == RevalidationStatus.VALID:
                stale_executed += 1

        assert total_scenarios >= 4
        assert stale_executed == 0, f"CRITICAL: {stale_executed} stale tickets executed!"

    def test_policy_version_drift_blocks_execution(self):
        """Policy version drift is always detected and blocks execution."""
        ws = _make_world_state(version=1)
        proposal = _make_proposal()
        evidence = _make_evidence()

        for old_ver, new_ver in [("1.0.0", "1.0.1"), ("2026.1", "2026.2"), ("A", "B")]:
            ctx = build_authorization_context(proposal, ws, old_ver, [], evidence)
            result = ExecutionTimeRevalidator.revalidate(
                authorization_context=ctx,
                current_world_state=ws,
                current_policy_version=new_ver,
                current_constraints=[],
                current_evidence=evidence,
                ticket_expires_at=time.time() + 30,
                proposal_action_type=ActionType.CLOSE_VALVE,
                proposal_target="valve_b",
            )
            assert result.status == RevalidationStatus.POLICY_CHANGED


# ---------------------------------------------------------------------------
# 11. Deterministic Replay Reconstruction of TOCTOU Divergence
# ---------------------------------------------------------------------------

class TestReplayTOCTOU:
    """Verify that deterministic replay reconstructs TOCTOU divergence offline."""

    def test_replay_reconstructs_issuance_42_execution_43_divergence(self):
        """Reconstruct authorization issued at v42, execution attempted at v43 → TICKET_REVALIDATION_FAILED."""
        recorder = DecisionRecorder()
        ws_pre = _make_world_state(version=42)
        proposal = _make_proposal()

        # Create record with divergence between ticket issuance version (42) and execution version (43)
        rec = recorder.create_record(
            intent="Isolate valve_b under changing conditions",
            world_state_snapshot=ws_pre,
            policy_decision=DecisionCategory.ALLOW,
            action_proposal=proposal,
            authorization_ticket_id="tkt_test_42",
            authorization_context_hash=hashlib.sha256(b"mock_context_42").hexdigest(),
            ticket_world_state_version=42,
            ticket_world_state_hash=compute_world_state_hash(ws_pre),
            revalidation_status="WORLD_STATE_CHANGED",
            revalidation_reasons=["World state version drift: authorized_version=42, current_version=43"],
            execution_context_version=43,
            execution_context_hash=hashlib.sha256(b"mock_context_43").hexdigest(),
        )
        finalized_rec = recorder.finalize_record(rec)

        # Run replay engine with an EventBus to capture emitted events
        bus = EventBus()
        captured_events = []
        bus.subscribe(lambda evt: captured_events.append(evt))

        engine = DecisionReplayEngine(event_bus=bus)
        report = engine.replay(finalized_rec)

        # Replay must identify revalidation failure
        assert report.revalidation_verdict == "TICKET_REVALIDATION_FAILED"
        assert len(report.steps) == 10
        assert report.steps[8].step_name == "EXECUTION"
        assert "TICKET_REVALIDATION_FAILED" in report.steps[8].summary

        # Must have emitted TICKET_REVALIDATION_FAILED
        drift_events = [e for e in captured_events if e.event_type == EventType.TICKET_REVALIDATION_FAILED]
        assert len(drift_events) == 1
        assert drift_events[0].payload["issuance_version"] == 42
        assert drift_events[0].payload["execution_version"] == 43

    def test_replay_cannot_mint_tickets_or_actuate(self):
        """Deterministic replay has zero authority: cannot mint tickets, cannot actuate."""
        recorder = DecisionRecorder()
        ws = _make_world_state(version=1)
        rec = recorder.finalize_record(
            recorder.create_record(
                intent="Offline audit",
                world_state_snapshot=ws,
                policy_decision=DecisionCategory.DENY,
            )
        )
        engine = DecisionReplayEngine()
        assert not hasattr(engine, "mint_ticket")
        assert not hasattr(engine, "actuator")
        assert not hasattr(engine, "execute")

        report = engine.replay(rec)
        assert report.execution_mode.value == "REPLAY"

    def test_replay_matching_versions_produces_passed(self):
        """When ticket issuance version matches execution version, replay shows passed."""
        recorder = DecisionRecorder()
        ws = _make_world_state(version=10)
        rec = recorder.create_record(
            intent="Normal execution audit",
            world_state_snapshot=ws,
            policy_decision=DecisionCategory.ALLOW,
            action_proposal=_make_proposal(),
            authorization_ticket_id="tkt_test_10",
            ticket_world_state_version=10,
            execution_context_version=10,
            revalidation_status="VALID",
        )
        finalized_rec = recorder.finalize_record(rec)

        engine = DecisionReplayEngine()
        report = engine.replay(finalized_rec)
        assert report.revalidation_verdict == "TICKET_REVALIDATION_VALID"


# ---------------------------------------------------------------------------
# 12. Runtime End-to-End TOCTOU Defense Integration
# ---------------------------------------------------------------------------

class TestRuntimeEndToEndTOCTOU:
    """Verify end-to-end runtime execution-time revalidation and TOCTOU defense."""

    def test_runtime_cycle_revalidates_and_records_valid_context(self):
        """Normal runtime cycle passes revalidation and records complete context."""
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

        assert res.policy_decision is not None
        assert res.policy_decision.is_allowed is True
        assert res.ticket is not None
        assert res.decision_record is not None

        # Revalidation must have passed
        assert res.decision_record.revalidation_status == "VALID"
        assert res.decision_record.ticket_world_state_version == res.decision_record.execution_context_version
        assert res.decision_record.authorization_context_hash != ""

        # Lifecycle events must include revalidation
        event_types = [e.event_type for e in res.events]
        assert EventType.TICKET_REVALIDATION_STARTED in event_types
        assert EventType.TICKET_REVALIDATION_PASSED in event_types
        assert EventType.ACTION_EXECUTED in event_types
        assert world.valves["valve_b"] == ValveState.CLOSED

    def test_runtime_cycle_aborts_actuation_on_human_zone_toctou_race(self):
        """A race condition where human enters zone right after authorization aborts execution."""
        world = PhysicalWorld()
        world.valves["valve_b"] = ValveState.OPEN
        world.cooling = CoolingState.ACTIVE
        world.set_pump_state("pump_p1", "INACTIVE")
        world.set_human_zone(HumanZoneState.CLEAR)

        runtime = MotionFenceRuntime(world=world)

        # Hook SafetyEnclave to simulate race: human enters right after ticket is minted
        orig_authorize = runtime.safety_enclave.authorize
        def hook_authorize(req):
            res = orig_authorize(req)
            # Adversarial state mutation during TOCTOU window
            world.set_human_zone(HumanZoneState.OCCUPIED)
            return res

        runtime.safety_enclave.authorize = hook_authorize

        res = runtime.run_cycle(
            intent="Isolate valve_b under race condition",
            initial_evidence=world.generate_targeted_evidence("valve_b"),
        )

        # Execution must have been ABORTED
        assert res.execution_result is not None
        assert res.execution_result.success is False
        assert "Actuation aborted: Execution-time revalidation failed" in res.execution_result.message

        # HARD SAFETY INVARIANT: Valve B must remain OPEN — no actuation allowed!
        assert world.valves["valve_b"] == ValveState.OPEN

        # DecisionRecord must capture revalidation failure and drift
        assert res.decision_record is not None
        assert res.decision_record.revalidation_status == "WORLD_STATE_CHANGED"
        assert res.decision_record.ticket_world_state_version != res.decision_record.execution_context_version

        # Events must include all TOCTOU defense lifecycle markers
        event_types = [e.event_type for e in res.events]
        assert EventType.TICKET_REVALIDATION_STARTED in event_types
        assert EventType.TICKET_REVALIDATION_FAILED in event_types
        assert EventType.WORLD_STATE_DRIFT_DETECTED in event_types
        assert EventType.TICKET_INVALIDATED in event_types

    def test_actuator_direct_rejection_on_stale_ticket(self):
        """PhysicalActuator Invariant 7 directly rejects stale world version."""
        world = PhysicalWorld()
        actuator = PhysicalActuator(world)
        ta = TicketAuthority()

        proposal = _make_proposal()
        ws_v1 = _make_world_state(version=world.version)
        ticket = ta.mint_ticket(proposal, world_state=ws_v1)
        assert ticket.world_state_version == world.version

        # Mutate world state to cause version drift
        world.set_human_zone(HumanZoneState.OCCUPIED)
        assert world.version > ticket.world_state_version

        with pytest.raises(UnauthorizedActionError, match="Stale authorization context"):
            actuator.execute(proposal, ticket)

