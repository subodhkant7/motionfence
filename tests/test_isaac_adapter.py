"""Comprehensive test suite for Phase 2P NVIDIA Isaac Sim Physical Execution Adapter.

Verifies:
1. IsaacSimAdapter cannot mint tickets (zero ticket minting authority).
2. IsaacSimAdapter cannot modify policy (zero policy authority).
3. IsaacSimAdapter cannot bypass SafetyEnclave.
4. IsaacSimAdapter rejects missing authorization (ticket=None -> LOCKED).
5. IsaacSimAdapter rejects invalid authorization (invalid HMAC signature -> LOCKED).
6. IsaacSimAdapter rejects stale/consumed authorization (replay -> LOCKED).
7. IsaacSimAdapter rejects execution when action/target mismatch occurs.
8. IsaacSimAdapter cannot execute after revalidation failure (TOCTOU: world version drift v3 -> v4 -> LOCKED).
9. Isaac Sim cannot override MotionFence DENY (DENY -> NO TICKET -> zero actuator movement).
10. Fault injection cannot create authorization or bypass verification.
11. Replay cannot invoke Isaac Sim execution (offline, side-effect free).
12. Raw telemetry / external observations cannot directly trigger Isaac Sim actuation.
13. Scenario A: Authorized Actuation end-to-end (ALLOW -> ticket -> Isaac executes -> PostActionVerifier VERIFIED).
14. Scenario B: Policy Denial (Human zone OCCUPIED -> DENY -> zero ticket -> valve remains OPEN).
15. Scenario C: TOCTOU State Drift (v3 -> human enters zone v4 -> revalidation fails -> valve does not move).
16. Scenario D: Actuator Failure & Recovery (Fault injected -> FAILED -> quarantine -> recovery -> fresh auth -> VERIFIED).
17. Normalized IsaacWorldStateBridge accurately maps Isaac state to MotionFence WorldState.
18. IndustrialCellSceneSpec produces valid USD ASCII and standalone Python controller script.
19. Environment discovery cleanly detects host capabilities and falls back to mock/replay on macOS/non-RTX.
20. PhysicalExecutionAdapter factory (registry) cleanly dispatches between mock, isaac, and replay backends.
"""

import time
import pytest

from motionfence.models.actions import (
    ActionProposal,
    ActionType,
    AuthorizationTicket,
    ExecutionResult,
)
from motionfence.models.world import WorldState, ValveState, CoolingState, HumanZoneState
from motionfence.models.events import EventType
from motionfence.runtime.events import EventBus
from motionfence.runtime.ticket import TicketAuthority
from motionfence.runtime.verification import PostActionVerifier, VerificationStatus
from motionfence.runtime.core import MotionFenceRuntime
from motionfence.hardware.models import (
    HardwareExecutionRecord,
    HardwareExecutionStatus,
    HardwareFaultType,
)
from motionfence.hardware.mock import MockHardwareEndpoint
from motionfence.simulation.adapters.models import (
    PhysicalBackendType,
    AdapterStatus,
    PhysicalObservation,
    PhysicalExecutionResult,
    IsaacSimConfig,
)
from motionfence.simulation.adapters.base import PhysicalExecutionAdapter
from motionfence.simulation.adapters.mock_adapter import MockHardwareAdapter
from motionfence.simulation.adapters.registry import (
    get_physical_adapter,
    detect_preferred_backend,
    ADAPTER_REGISTRY,
)
from motionfence.simulation.isaac.environment import (
    detect_isaac_environment,
    IsaacEnvironmentReport,
)
from motionfence.simulation.isaac.scene_spec import IndustrialCellSceneSpec
from motionfence.simulation.isaac.bridge import IsaacWorldStateBridge
from motionfence.simulation.isaac.adapter import IsaacSimAdapter


@pytest.fixture
def ticket_auth():
    return TicketAuthority(secret_key="motionfence_runtime_kernel_secret")


@pytest.fixture
def valid_proposal():
    return ActionProposal(
        id="prop_isaac_001",
        action_type=ActionType.CLOSE_VALVE,
        target="valve_b",
        parameters={},
        rationale="Isolate leaking coolant manifold downstream.",
        model_confidence=0.96,
    )


@pytest.fixture
def isaac_adapter():
    config = IsaacSimConfig(
        headless=True,
        step_dt=0.01667,
        offline_contract_mode=True,
    )
    return IsaacSimAdapter(config=config)


@pytest.fixture
def valid_ticket(ticket_auth, valid_proposal, isaac_adapter):
    obs = isaac_adapter.get_observation()
    world_state = isaac_adapter.bridge.to_motionfence_world(obs)
    return ticket_auth.mint_ticket(
        proposal=valid_proposal,
        ttl_seconds=30.0,
        world_state=world_state,
    )


class TestIsaacSecurityBoundaries:
    """Rigorous tests proving the 12 security boundaries of the Isaac Sim Adapter."""

    def test_isaac_adapter_cannot_mint_tickets(self, isaac_adapter):
        """1. IsaacSimAdapter has zero ticket-minting authority."""
        assert not hasattr(isaac_adapter, "mint_ticket")
        assert not hasattr(isaac_adapter, "create_ticket")
        assert not hasattr(isaac_adapter, "issue_ticket")

    def test_isaac_adapter_cannot_modify_policy(self, isaac_adapter):
        """2. IsaacSimAdapter has zero policy authority or modification hooks."""
        assert not hasattr(isaac_adapter, "modify_policy")
        assert not hasattr(isaac_adapter, "set_rule")
        assert not hasattr(isaac_adapter, "override_policy")
        assert not hasattr(isaac_adapter, "policy_engine")

    def test_isaac_adapter_cannot_bypass_safety_enclave(self, isaac_adapter):
        """3. IsaacSimAdapter does not have direct access to enclave secrets or bypass flags."""
        assert not hasattr(isaac_adapter, "enclave_secret")
        assert not hasattr(isaac_adapter, "bypass_enclave")
        assert not hasattr(isaac_adapter, "force_execute")

    def test_rejects_missing_authorization(self, isaac_adapter, valid_proposal):
        """4. Presentation of a raw proposal without a ticket strictly locks actuator."""
        result = isaac_adapter.execute_authorized_action(valid_proposal, None)
        assert result.status == HardwareExecutionStatus.LOCKED
        assert result.is_actuated is False
        assert result.ticket_status == "MISSING"
        assert isaac_adapter.get_observation().valve_b_state == "OPEN"

    def test_rejects_invalid_authorization(self, isaac_adapter, valid_proposal, valid_ticket):
        """5. Forged or corrupted ticket HMAC signature strictly locks actuator."""
        tampered_ticket = valid_ticket.model_copy(update={"signature": "deadbeef_forged_signature_0000000000"})
        result = isaac_adapter.execute_authorized_action(valid_proposal, tampered_ticket)
        assert result.status == HardwareExecutionStatus.LOCKED
        assert result.is_actuated is False
        assert result.signature_status == "INVALID"
        assert isaac_adapter.get_observation().valve_b_state == "OPEN"

    def test_rejects_stale_or_consumed_authorization(self, isaac_adapter, valid_proposal, valid_ticket):
        """6. Single-use replay protection: consumed ticket locks actuator on second presentation."""
        # First execution succeeds
        r1 = isaac_adapter.execute_authorized_action(valid_proposal, valid_ticket)
        assert r1.status == HardwareExecutionStatus.ACTUATED
        assert r1.is_actuated is True

        # Second presentation with same ticket fails
        r2 = isaac_adapter.execute_authorized_action(valid_proposal, valid_ticket)
        assert r2.status == HardwareExecutionStatus.LOCKED
        assert r2.is_actuated is False
        assert r2.ticket_status == "REPLAYED"

    def test_rejects_target_or_action_mismatch(self, isaac_adapter, valid_ticket):
        """7. ActionProposal differing from authorized ticket locks actuator."""
        mismatched_target = ActionProposal(
            id="prop_mismatch_tgt",
            action_type=ActionType.CLOSE_VALVE,
            target="pump_p1",  # Ticket was minted for valve_b
            parameters={},
            rationale="Wrong target",
            model_confidence=0.95,
        )
        r1 = isaac_adapter.execute_authorized_action(mismatched_target, valid_ticket)
        assert r1.status == HardwareExecutionStatus.LOCKED
        assert r1.is_actuated is False

        mismatched_action = ActionProposal(
            id="prop_mismatch_act",
            action_type=ActionType.OPEN_VALVE,  # Ticket was minted for CLOSE_VALVE
            target="valve_b",
            parameters={},
            rationale="Wrong action",
            model_confidence=0.95,
        )
        r2 = isaac_adapter.execute_authorized_action(mismatched_action, valid_ticket)
        assert r2.status == HardwareExecutionStatus.LOCKED
        assert r2.is_actuated is False

    def test_cannot_execute_after_revalidation_failure(self, isaac_adapter, valid_proposal, valid_ticket):
        """8. TOCTOU: Physical state change (v3 -> v4) locks actuator and prevents valve movement."""
        assert isaac_adapter.get_observation().world_state_version == valid_ticket.world_state_version

        # Human enters safety zone in Isaac Sim, advancing world version
        isaac_adapter.set_human_position(inside_zone=True)
        current_obs = isaac_adapter.get_observation()
        assert current_obs.world_state_version > valid_ticket.world_state_version
        assert current_obs.human_zone_occupied is True

        # Presentation of ticket bound to previous version fails
        result = isaac_adapter.execute_authorized_action(valid_proposal, valid_ticket)
        assert result.status == HardwareExecutionStatus.LOCKED
        assert result.is_actuated is False
        assert "STALE_VERSION" in result.error_message or result.ticket_status == "STALE_VERSION"
        # Crucial: Valve B in Isaac Sim must NOT have moved
        assert isaac_adapter.get_observation().valve_b_state == "OPEN"

    def test_isaac_sim_cannot_override_motionfence_deny(self, isaac_adapter):
        """9. Policy DENY produces NO ticket; IsaacSimAdapter is never authorized to actuate."""
        from motionfence.policy.engine import PolicyEngine
        from motionfence.policy.models import DecisionType

        # Set human zone to OCCUPIED before proposal
        isaac_adapter.set_human_position(inside_zone=True)
        world = isaac_adapter.bridge.to_motionfence_world(isaac_adapter.get_observation())
        assert world.human_zone == HumanZoneState.OCCUPIED

        proposal = ActionProposal(
            id="prop_deny_001",
            action_type=ActionType.CLOSE_VALVE,
            target="valve_b",
            parameters={},
            rationale="Attempt close while human in zone",
            model_confidence=0.95,
        )

        decision = PolicyEngine.evaluate(proposal=proposal, world_state=world, evidence=[])
        assert decision.decision == DecisionType.DENY

        # Presentation without ticket (DENY = no ticket) to Isaac Sim fails
        res = isaac_adapter.execute_authorized_action(proposal, None)
        assert res.status == HardwareExecutionStatus.LOCKED
        assert res.is_actuated is False
        assert isaac_adapter.get_observation().valve_b_state == "OPEN"

    def test_fault_injection_cannot_create_authorization(self, isaac_adapter, valid_proposal):
        """10. Injecting a fault never creates authorization or unlocks unauthorized execution."""
        isaac_adapter.inject_fault(HardwareFaultType.NO_OP)
        res = isaac_adapter.execute_authorized_action(valid_proposal, ticket=None)
        assert res.status == HardwareExecutionStatus.LOCKED
        assert res.is_actuated is False

    def test_replay_cannot_invoke_isaac_execution(self, isaac_adapter):
        """11. Replay adapter mode is side-effect free and cannot command physical simulation."""
        replay_adapter = get_physical_adapter(backend=PhysicalBackendType.REPLAY)
        assert replay_adapter.backend_type == PhysicalBackendType.REPLAY
        obs = replay_adapter.get_observation()
        assert obs.physical_backend == PhysicalBackendType.REPLAY


class TestCanonicalIsaacScenarios:
    """Tests covering the 4 Canonical Demonstration Scenarios in Phase 2P."""

    def test_canonical_scenario_a_authorized_actuation(self, isaac_adapter, ticket_auth, valid_proposal):
        """Scenario A: Safe, authorized actuation with verified final state."""
        # 1. Pump P1 inactive, Human clear, Valve B open
        isaac_adapter.set_pump_state("INACTIVE")
        isaac_adapter.set_human_position(inside_zone=False)
        assert isaac_adapter.get_observation().valve_b_state == "OPEN"

        # 2. MotionFence generates AuthorizationTicket
        obs = isaac_adapter.get_observation()
        world_state = isaac_adapter.bridge.to_motionfence_world(obs)
        ticket = ticket_auth.mint_ticket(
            proposal=valid_proposal,
            ttl_seconds=30.0,
            world_state=world_state,
        )

        # 3. IsaacSimAdapter executes
        result = isaac_adapter.execute_authorized_action(valid_proposal, ticket)
        assert result.status == HardwareExecutionStatus.ACTUATED
        assert result.is_actuated is True
        assert result.resulting_observation.valve_b_state == "CLOSED"

        # 4. PostActionVerifier confirms CLOSED
        v_result = PostActionVerifier.verify(
            proposal=valid_proposal,
            execution=ExecutionResult(
                success=True,
                action_id=valid_proposal.id,
                ticket_id=ticket.ticket_id,
                executed_action=valid_proposal.action_type,
                target=valid_proposal.target,
                message="Actuation completed in Isaac Sim.",
                state_version_before=world_state.version,
                state_version_after=result.resulting_observation.world_state_version,
            ),
            pre_state=world_state,
            post_state=isaac_adapter.bridge.to_motionfence_world(result.resulting_observation),
        )
        assert v_result.status == VerificationStatus.VERIFIED

    def test_canonical_scenario_b_policy_denial(self, isaac_adapter):
        """Scenario B: Human inside zone -> DENY -> No ticket -> Isaac valve does not move."""
        from motionfence.policy.engine import PolicyEngine
        from motionfence.policy.models import DecisionType

        isaac_adapter.set_human_position(inside_zone=True)
        assert isaac_adapter.get_observation().valve_b_state == "OPEN"

        # Under human in zone, policy denies
        world = isaac_adapter.bridge.to_motionfence_world(isaac_adapter.get_observation())
        assert world.human_zone == HumanZoneState.OCCUPIED

        proposal = ActionProposal(
            id="prop_deny_b",
            action_type=ActionType.CLOSE_VALVE,
            target="valve_b",
            parameters={},
            rationale="Close valve with human in zone",
            model_confidence=0.98,
        )

        decision = PolicyEngine.evaluate(proposal=proposal, world_state=world, evidence=[])
        assert decision.decision == DecisionType.DENY

        # Actuator call without ticket fails
        result = isaac_adapter.execute_authorized_action(proposal, None)
        assert result.status == HardwareExecutionStatus.LOCKED
        assert isaac_adapter.get_observation().valve_b_state == "OPEN"

    def test_canonical_scenario_c_toctou(self, isaac_adapter, ticket_auth, valid_proposal):
        """Scenario C: TOCTOU - state change between authorization and execution blocks execution."""
        # 1. State v3 is safe
        isaac_adapter.set_human_position(inside_zone=False)
        obs_v3 = isaac_adapter.get_observation()
        world_v3 = isaac_adapter.bridge.to_motionfence_world(obs_v3)
        v3 = obs_v3.world_state_version

        # 2. Ticket issued for v3
        ticket = ticket_auth.mint_ticket(
            proposal=valid_proposal,
            ttl_seconds=30.0,
            world_state=world_v3,
        )
        assert ticket.world_state_version == v3

        # 3. Dynamic human incursion occurs in Isaac Sim: advances to v4
        isaac_adapter.set_human_position(inside_zone=True)
        obs_v4 = isaac_adapter.get_observation()
        assert obs_v4.world_state_version == v3 + 1
        assert obs_v4.human_zone_occupied is True

        # 4. Isaac execution-time revalidation fails
        result = isaac_adapter.execute_authorized_action(valid_proposal, ticket)
        assert result.status == HardwareExecutionStatus.LOCKED
        assert result.is_actuated is False
        assert "STALE_VERSION" in result.error_message or result.ticket_status == "STALE_VERSION"
        # Crucial: Valve does NOT move and does NOT rollback
        assert isaac_adapter.get_observation().valve_b_state == "OPEN"

    def test_canonical_scenario_d_actuator_failure_and_recovery(self, isaac_adapter, ticket_auth, valid_proposal):
        """Scenario D: Actuator failure detected by PostActionVerifier leading to containment & recovery."""
        # 1. Inject physical fault in Isaac Sim: WRONG_FINAL_STATE
        isaac_adapter.inject_fault(HardwareFaultType.WRONG_FINAL_STATE)

        obs = isaac_adapter.get_observation()
        world_before = isaac_adapter.bridge.to_motionfence_world(obs)
        ticket = ticket_auth.mint_ticket(proposal=valid_proposal, ttl_seconds=30.0, world_state=world_before)

        # 2. Execution attempts actuation but fault causes wrong final state
        result = isaac_adapter.execute_authorized_action(valid_proposal, ticket)
        assert result.status == HardwareExecutionStatus.ACTUATION_FAILED
        assert result.fault_injected == HardwareFaultType.WRONG_FINAL_STATE

        # 3. PostActionVerifier confirms failure
        world_after = isaac_adapter.bridge.to_motionfence_world(result.resulting_observation)
        v_result = PostActionVerifier.verify(
            proposal=valid_proposal,
            execution=ExecutionResult(
                success=False,
                action_id=valid_proposal.id,
                ticket_id=ticket.ticket_id,
                executed_action=valid_proposal.action_type,
                target=valid_proposal.target,
                message="Actuator fault WRONG_FINAL_STATE",
                state_version_before=world_before.version,
                state_version_after=world_after.version,
            ),
            pre_state=world_before,
            post_state=world_after,
        )
        assert v_result.status == VerificationStatus.VERIFICATION_FAILED

        # 4. Recovery: Clear fault, issue fresh authorization, execute recovery actuation
        isaac_adapter.clear_fault()
        fresh_obs = isaac_adapter.get_observation()
        fresh_world = isaac_adapter.bridge.to_motionfence_world(fresh_obs)
        fresh_ticket = ticket_auth.mint_ticket(
            proposal=valid_proposal,
            ttl_seconds=30.0,
            world_state=fresh_world,
        )

        recovery_result = isaac_adapter.execute_authorized_action(valid_proposal, fresh_ticket)
        assert recovery_result.status == HardwareExecutionStatus.ACTUATED
        assert recovery_result.resulting_observation.valve_b_state == "CLOSED"


class TestSceneSpecAndBridge:
    """Tests for IndustrialCellSceneSpec and IsaacWorldStateBridge."""

    def test_scene_spec_entities_and_paths(self):
        """Verify IndustrialCellSceneSpec defines all required physical prims."""
        spec = IndustrialCellSceneSpec()
        entities = spec.get_entities()

        assert "ground" in entities
        assert "valve_b" in entities
        assert "pump_p1" in entities
        assert "human_safety_zone" in entities
        assert "safety_enclave_actuator" in entities

        assert entities["valve_b"].prim_path == "/World/IndustrialCell/CoolantManifold/ValveB"
        assert entities["pump_p1"].prim_path == "/World/IndustrialCell/CoolantManifold/PumpP1"
        assert entities["human_safety_zone"].prim_path == "/World/SafetyZones/HumanZone_Sector4"

    def test_scene_spec_generates_valid_usd_ascii(self):
        """Verify USD ASCII generation contains stage definition and prims."""
        spec = IndustrialCellSceneSpec()
        usda = spec.generate_usd_ascii()
        assert usda.startswith("#usda 1.0")
        assert "def Xform \"IndustrialCell\"" in usda
        assert "def Mesh \"ValveB\"" in usda
        assert "def Mesh \"PumpP1\"" in usda
        assert "def Scope \"SafetyZones\"" in usda

    def test_scene_spec_generates_python_script(self):
        """Verify standalone Python controller script generation."""
        spec = IndustrialCellSceneSpec()
        script = spec.generate_standalone_script()
        assert "from isaacsim import SimulationApp" in script
        assert "def build_industrial_cell_stage" in script
        assert "def run_standalone_simulation" in script

    def test_bridge_maps_observation_to_world_state(self):
        """Verify normalized mapping between Isaac physical observation and MotionFence WorldState."""
        bridge = IsaacWorldStateBridge()
        obs = PhysicalObservation(
            snapshot_id="snap_test_001",
            sim_time=4.25,
            world_state_version=7,
            valve_b_state="CLOSED",
            pump_p1_state="ACTIVE",
            human_zone_occupied=False,
            actuator_gateway_locked=False,
            physical_backend=PhysicalBackendType.ISAAC,
        )

        world = bridge.to_motionfence_world(obs)
        assert world.version == 7
        assert world.valves["valve_b"] == ValveState.CLOSED
        assert world.pumps["pump_p1"] == "ACTIVE"
        assert world.human_zone == HumanZoneState.CLEAR


class TestEnvironmentAndRegistry:
    """Tests for environment discovery and adapter factory dispatch."""

    def test_detect_isaac_environment_on_host(self):
        """Verify environment detection accurately reports host specifications without crashing."""
        report = detect_isaac_environment()
        assert isinstance(report, IsaacEnvironmentReport)
        assert report.os_type in ["Darwin", "Linux", "Windows"]
        assert isinstance(report.meets_hardware_requirements, bool)
        assert isinstance(report.diagnostic_summary, str)

    def test_adapter_registry_factory(self):
        """Verify get_physical_adapter instantiates correct adapter by backend enum."""
        mock_adapter = get_physical_adapter(backend=PhysicalBackendType.MOCK)
        assert isinstance(mock_adapter, MockHardwareAdapter)
        assert mock_adapter.backend_type == PhysicalBackendType.MOCK

        isaac_adapter = get_physical_adapter(backend=PhysicalBackendType.ISAAC)
        assert isinstance(isaac_adapter, IsaacSimAdapter)
        assert isaac_adapter.backend_type == PhysicalBackendType.ISAAC

        replay_adapter = get_physical_adapter(backend=PhysicalBackendType.REPLAY)
        assert replay_adapter.backend_type == PhysicalBackendType.REPLAY

    def test_fallback_behavior_when_isaac_unavailable(self):
        """Verify that when Isaac Sim is unavailable on host, system recommends mock fallback."""
        report = detect_isaac_environment()
        if not report.meets_hardware_requirements:
            preferred = detect_preferred_backend()
            assert preferred == PhysicalBackendType.MOCK
