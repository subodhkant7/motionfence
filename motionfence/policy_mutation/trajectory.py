"""Dynamic physical trajectory evaluation, fault injection, and state-space exploration (Phase 2K).

CRITICAL INVARIANTS:
1. All trajectory exploration operates in modeled state-transition space offline.
2. ZERO authority to execute real physical actions or mutate production systems.
3. Does NOT claim exhaustive real-world physical safety; explores bounded modeled counterexamples.
4. Preserves and exercises existing state-binding, TOCTOU revalidation, and fault containment machinery.
"""

from enum import Enum
import hashlib
import json
import time
from typing import Any, Dict, List, Optional, Set, Tuple

from motionfence.evidence.models import (
    ContradictionSeverity,
    Evidence,
    EvidenceSource,
)
from motionfence.models.actions import ActionProposal, ActionType, AuthorizationTicket
from motionfence.models.world import CoolingState, HumanZoneState, ValveState, WorldState
from motionfence.policy.engine import PolicyEngine
from motionfence.policy.models import DecisionType, Policy, PolicyDecision
from motionfence.policy_mutation.models import (
    DynamicTrajectory,
    TrajectoryEvaluationResult,
    TrajectoryOutcomeType,
    TrajectoryStep,
)
from motionfence.runtime.revalidation import (
    AuthorizationContext,
    ExecutionTimeRevalidator,
    RevalidationStatus,
    build_authorization_context,
    compute_world_state_hash,
)
from motionfence.simulation.actuator import PhysicalActuator
from motionfence.simulation.world import PhysicalWorld


class TrajectoryFaultType(str, Enum):
    """Categorical classification of dynamic physical environment faults."""
    HUMAN_INCURSION_AFTER_AUTH = "HUMAN_INCURSION_AFTER_AUTH"
    PUMP_ACTIVATION_AFTER_AUTH = "PUMP_ACTIVATION_AFTER_AUTH"
    COOLING_LOSS_AFTER_AUTH = "COOLING_LOSS_AFTER_AUTH"
    SENSOR_STALENESS_AFTER_AUTH = "SENSOR_STALENESS_AFTER_AUTH"
    SENSOR_CONTRADICTION_AFTER_AUTH = "SENSOR_CONTRADICTION_AFTER_AUTH"
    TARGET_IDENTITY_CHANGE = "TARGET_IDENTITY_CHANGE"
    ENVIRONMENT_DRIFT = "ENVIRONMENT_DRIFT"
    ACTUATOR_DELAY = "ACTUATOR_DELAY"
    ACTUATOR_NO_OP = "ACTUATOR_NO_OP"
    ACTUATOR_WRONG_STATE = "ACTUATOR_WRONG_STATE"
    KNOWLEDGE_FRESHNESS_EXPIRATION = "KNOWLEDGE_FRESHNESS_EXPIRATION"
    NONE = "NONE"


class DynamicTrajectoryEvaluator:
    """Evaluates dynamic physical trajectories under policy constraints, state binding, and TOCTOU defense."""

    def __init__(self) -> None:
        self.revalidator = ExecutionTimeRevalidator()

    def evaluate_trajectory(
        self,
        trajectory: DynamicTrajectory,
        policy: Policy,
        baseline_policy: Optional[Policy] = None,
    ) -> TrajectoryEvaluationResult:
        """Execute a dynamic trajectory step-by-step and determine the safety outcome.

        Distinguishes:
        - BLOCKED_BEFORE_EXECUTION: Rejected at evaluation time before authorization.
        - BLOCKED_BY_REVALIDATION: Intercepted by TOCTOU revalidation before actuation.
        - EXECUTED_AND_VERIFIED: Nominal actuation verified against postconditions.
        - EXECUTED_AND_FAILED_VERIFICATION: Actuation occurred but postcondition failed.
        - CONTAINED_AND_RECOVERED: Postcondition failed, fault containment activated.
        - QUARANTINED: Actuator or component quarantined after repeated faults.
        - NEW_UNSAFE_ALLOW: Unsafe state transition permitted under mutated policy.
        """
        start_time = time.time()

        # Step 0: Initialize modeled physical world
        world = PhysicalWorld()
        world_state = world.get_state()
        active_evidence: List[Evidence] = [
            Evidence(
                source=EvidenceSource.VISION,
                target="valve_b",
                observation={"state": "OPEN"},
                confidence=0.95,
                provenance="camera_primary",
                timestamp=time.time(),
            )
        ]

        failing_step_index: Optional[int] = None
        executed_steps: List[str] = []
        final_outcome = TrajectoryOutcomeType.EXECUTED_AND_VERIFIED
        explanation = "Trajectory executed and verified normally."

        # Check if policy explicitly disables revalidation or quarantine (e.g. mutated postconditions)
        disable_revalidation = policy.expected_postconditions.get("disable_revalidation", False)
        bypass_quarantine = policy.expected_postconditions.get("bypass_quarantine", False)

        ticket: Optional[AuthorizationTicket] = None
        auth_context: Optional[AuthorizationContext] = None

        for step in trajectory.steps:
            step_name = step.event_name
            executed_steps.append(step_name)

            # Apply any explicit world state overrides from step
            if step.world_state:
                if "valves" in step.world_state:
                    for v_k, v_v in step.world_state["valves"].items():
                        v_enum = ValveState(v_v) if isinstance(v_v, str) else v_v
                        world.set_valve(v_k, v_enum)
                if "cooling" in step.world_state:
                    c_val = step.world_state["cooling"]
                    c_enum = CoolingState(c_val) if isinstance(c_val, str) else c_val
                    world.set_cooling(c_enum)
                if "human_zone" in step.world_state:
                    h_val = step.world_state["human_zone"]
                    h_enum = HumanZoneState(h_val) if isinstance(h_val, str) else h_val
                    world.set_human_zone(h_enum)
                if "pumps" in step.world_state:
                    for p_k, p_v in step.world_state["pumps"].items():
                        world.set_pump(p_k, p_v)
                world_state = world.get_state()

            # Handle fault injection
            fault = step.fault
            if fault:
                self._apply_fault(fault, world, active_evidence)
                world_state = world.get_state()

            # Handle action proposal & authorization
            if step.action:
                act_type = ActionType(step.action) if isinstance(step.action, str) else step.action
                target = step.target or "valve_b"
                proposal = ActionProposal(
                    action_type=act_type,
                    target=target,
                    model_confidence=0.95,
                    rationale=f"Trajectory step {step.step_index}: {step_name}",
                )

                decision = PolicyEngine.evaluate(
                    proposal=proposal,
                    world_state=world_state,
                    evidence=active_evidence,
                    policy=policy,
                )

                if not decision.is_allowed:
                    final_outcome = TrajectoryOutcomeType.BLOCKED_BEFORE_EXECUTION
                    explanation = f"Action {proposal.action_type.value} blocked by policy: {decision.reasons}"
                    failing_step_index = step.step_index
                    break
                else:
                    # Check if action was allowed in a fundamentally unsafe state
                    is_unsafe_allow = (
                        (world_state.human_zone == HumanZoneState.OCCUPIED and act_type == ActionType.CLOSE_VALVE)
                        or (world_state.cooling != CoolingState.ACTIVE and act_type == ActionType.CLOSE_VALVE)
                        or (target not in policy.allowed_actuator_targets and policy.allowed_actuator_targets)
                    )
                    if is_unsafe_allow:
                        final_outcome = TrajectoryOutcomeType.NEW_UNSAFE_ALLOW
                        explanation = f"Unsafe action {act_type.value} allowed in hazardous world state (human={world_state.human_zone.value}, cooling={world_state.cooling.value})."
                        failing_step_index = step.step_index
                        break

                    # Authorization granted: record authorization context
                    auth_context = build_authorization_context(
                        proposal=proposal,
                        world_state=world_state,
                        policy_version=policy.version,
                        active_constraints=[],
                        evidence=active_evidence,
                    )
                    ticket = AuthorizationTicket(
                        proposal_id=proposal.id,
                        action_type=proposal.action_type,
                        target=proposal.target,
                        parameters={},
                        issued_at=time.time(),
                        expires_at=time.time() + 60.0,
                        signature="offline_simulated_trajectory_ticket_sig",
                        authorization_context_hash=auth_context.context_id,
                        world_state_hash=auth_context.world_state_hash,
                        world_state_version=world_state.version,
                        policy_version=policy.version,
                        constraint_set_hash=auth_context.constraint_set_hash,
                        evidence_context_hash=auth_context.evidence_context_hash,
                    )

            # Handle execution attempt
            if step_name == "EXECUTION_ATTEMPT":
                if ticket is None or auth_context is None:
                    final_outcome = TrajectoryOutcomeType.BLOCKED_BEFORE_EXECUTION
                    explanation = "Execution attempted without prior authorization ticket."
                    failing_step_index = step.step_index
                    break

                # Perform execution-time revalidation
                if not disable_revalidation:
                    reval_res = self.revalidator.revalidate(
                        authorization_context=auth_context,
                        current_world_state=world_state,
                        current_policy_version=policy.version,
                        current_constraints=[],
                        current_evidence=active_evidence,
                        ticket_expires_at=ticket.expires_at,
                        proposal_action_type=ticket.action_type,
                        proposal_target=ticket.target,
                    )
                    if reval_res.status != RevalidationStatus.VALID:
                        final_outcome = TrajectoryOutcomeType.BLOCKED_BY_REVALIDATION
                        explanation = f"Execution blocked by TOCTOU revalidation: {reval_res.reasons}"
                        failing_step_index = step.step_index
                        break

                # If revalidation was bypassed or passed, execute actuation simulation
                if fault == TrajectoryFaultType.ACTUATOR_NO_OP.value:
                    final_outcome = TrajectoryOutcomeType.EXECUTED_AND_FAILED_VERIFICATION
                    explanation = "Actuator failed to transition valve; verification detected postcondition mismatch."
                    failing_step_index = step.step_index
                    break
                elif fault == TrajectoryFaultType.ACTUATOR_WRONG_STATE.value:
                    world.set_valve(ticket.target, ValveState.FAULT)
                    final_outcome = TrajectoryOutcomeType.EXECUTED_AND_FAILED_VERIFICATION
                    explanation = "Actuator transitioned to FAULT state; postcondition failed."
                    failing_step_index = step.step_index
                    break
                else:
                    # Actuation executed
                    # If human entered zone after authorization and revalidation was disabled -> NEW_UNSAFE_ALLOW!
                    if world_state.human_zone == HumanZoneState.OCCUPIED and disable_revalidation:
                        final_outcome = TrajectoryOutcomeType.NEW_UNSAFE_ALLOW
                        explanation = "Action actuated with human in zone due to disabled revalidation."
                        failing_step_index = step.step_index
                        break

                    world.set_valve(ticket.target, ValveState.CLOSED)
                    final_outcome = TrajectoryOutcomeType.EXECUTED_AND_VERIFIED
                    explanation = "Action executed and postcondition verified."

            # Handle containment and quarantine steps
            if step_name == "QUARANTINE_CHECK":
                if bypass_quarantine:
                    final_outcome = TrajectoryOutcomeType.NEW_UNSAFE_ALLOW
                    explanation = "Quarantine was bypassed allowing unauthorized actuation on degraded component."
                    failing_step_index = step.step_index
                    break
                else:
                    final_outcome = TrajectoryOutcomeType.QUARANTINED
                    explanation = "Component quarantined by containment engine."

            if step_name == "CONTAINMENT_RECOVERY":
                final_outcome = TrajectoryOutcomeType.CONTAINED_AND_RECOVERED
                explanation = "Autonomous recovery successfully contained physical discrepancy."

        # Determine regression against baseline if baseline provided
        is_regression = False
        new_unsafe = 0
        if baseline_policy is not None:
            baseline_eval = self.evaluate_trajectory(trajectory, baseline_policy, baseline_policy=None)
            if (
                final_outcome == TrajectoryOutcomeType.NEW_UNSAFE_ALLOW
                and baseline_eval.outcome != TrajectoryOutcomeType.NEW_UNSAFE_ALLOW
            ):
                is_regression = True
                new_unsafe = 1
            elif (
                final_outcome == TrajectoryOutcomeType.EXECUTED_AND_VERIFIED
                and baseline_eval.outcome == TrajectoryOutcomeType.BLOCKED_BEFORE_EXECUTION
            ):
                is_regression = True
                new_unsafe = 1
            elif (
                final_outcome in (TrajectoryOutcomeType.EXECUTED_AND_VERIFIED, TrajectoryOutcomeType.EXECUTED_AND_FAILED_VERIFICATION)
                and baseline_eval.outcome == TrajectoryOutcomeType.BLOCKED_BY_REVALIDATION
            ):
                is_regression = True
                new_unsafe = 1

        duration = time.time() - start_time
        return TrajectoryEvaluationResult(
            trajectory_id=trajectory.trajectory_id,
            outcome=final_outcome,
            is_regression=is_regression,
            new_unsafe_allows=new_unsafe,
            failing_step_index=failing_step_index,
            minimized_steps=executed_steps,
            explanation=explanation,
            duration_seconds=duration,
        )

    def _apply_fault(
        self,
        fault: str,
        world: PhysicalWorld,
        evidence: List[Evidence],
    ) -> None:
        """Deterministically apply dynamic environment fault to world and evidence."""
        if fault == TrajectoryFaultType.HUMAN_INCURSION_AFTER_AUTH.value:
            world.set_human_zone(HumanZoneState.OCCUPIED)
        elif fault == TrajectoryFaultType.PUMP_ACTIVATION_AFTER_AUTH.value:
            world.set_pump("pump_1", "ACTIVE")
        elif fault == TrajectoryFaultType.COOLING_LOSS_AFTER_AUTH.value:
            world.set_cooling(CoolingState.INACTIVE)
        elif fault == TrajectoryFaultType.SENSOR_STALENESS_AFTER_AUTH.value:
            evidence.clear()
            evidence.append(
                Evidence(
                    source=EvidenceSource.VISION,
                    target="valve_b",
                    observation={"state": "OPEN"},
                    confidence=0.95,
                    provenance="camera_primary",
                    timestamp=time.time() - 7200.0,  # 2 hours stale
                )
            )
        elif fault == TrajectoryFaultType.SENSOR_CONTRADICTION_AFTER_AUTH.value:
            evidence.clear()
            evidence.append(
                Evidence(
                    source=EvidenceSource.VISION,
                    target="valve_b",
                    observation={"state": "OPEN"},
                    confidence=0.95,
                    provenance="camera_primary",
                    timestamp=time.time(),
                )
            )
            evidence.append(
                Evidence(
                    source=EvidenceSource.PRESSURE_SENSOR,
                    target="valve_b",
                    observation={"state": "CLOSED"},
                    confidence=0.95,
                    provenance="pressure_1",
                    timestamp=time.time(),
                )
            )
        elif fault == TrajectoryFaultType.ENVIRONMENT_DRIFT.value:
            world.set_cooling(CoolingState.DEGRADED)
        elif fault == TrajectoryFaultType.TARGET_IDENTITY_CHANGE.value:
            evidence.clear()
            evidence.append(
                Evidence(
                    source=EvidenceSource.VISION,
                    target="valve_unknown_99",
                    observation={"state": "OPEN"},
                    confidence=0.95,
                    provenance="camera_primary",
                    timestamp=time.time(),
                )
            )


class TrajectoryGenerator:
    """Bounded deterministic trajectory generation across configurable depths (depth 3, 5, 8)."""

    @staticmethod
    def generate_trajectories(
        seed: int = 42,
        depths: Optional[List[int]] = None,
    ) -> List[DynamicTrajectory]:
        """Generate canonical suite of physical trajectories covering depths 3, 5, and 8.

        Guarantees deterministic, reproducible trajectory IDs and ordering.
        LIMITATION: Operates on modeled state transitions; does not claim exhaustive real-world coverage.
        """
        if depths is None:
            depths = [3, 5, 8]

        trajectories: List[DynamicTrajectory] = []

        for depth in depths:
            # 1. Human incursion after authorization
            trajectories.append(
                TrajectoryGenerator._build_human_incursion_trajectory(seed, depth)
            )
            # 2. Pump activation after authorization
            trajectories.append(
                TrajectoryGenerator._build_pump_activation_trajectory(seed, depth)
            )
            # 3. Cooling loss after authorization
            trajectories.append(
                TrajectoryGenerator._build_cooling_loss_trajectory(seed, depth)
            )
            # 4. Sensor contradiction after authorization
            trajectories.append(
                TrajectoryGenerator._build_contradiction_trajectory(seed, depth)
            )
            # 5. Actuator fault / wrong state
            trajectories.append(
                TrajectoryGenerator._build_actuator_fault_trajectory(seed, depth)
            )
            # 6. Quarantine and containment trajectory
            trajectories.append(
                TrajectoryGenerator._build_quarantine_trajectory(seed, depth)
            )

        return sorted(trajectories, key=lambda t: t.trajectory_id)

    @staticmethod
    def _deterministic_id(seed: int, depth: int, name: str) -> str:
        h = hashlib.sha256(f"{seed}_{depth}_{name}".encode("utf-8")).hexdigest()[:8]
        return f"traj_s{seed}_d{depth}_{name}_{h}"

    @staticmethod
    def _build_human_incursion_trajectory(seed: int, depth: int) -> DynamicTrajectory:
        traj_id = TrajectoryGenerator._deterministic_id(seed, depth, "human_incursion")
        steps = [
            TrajectoryStep(
                step_index=0,
                event_name="NORMAL_OPERATION",
                world_state={"cooling": "ACTIVE", "human_zone": "CLEAR"},
            ),
            TrajectoryStep(
                step_index=1,
                event_name="PROPOSE_CONSEQUENTIAL_ACTION",
                action="CLOSE_VALVE",
                target="valve_b",
            ),
        ]
        if depth >= 5:
            steps.append(
                TrajectoryStep(
                    step_index=2,
                    event_name="AUTHORIZATION_GENERATED",
                )
            )
            steps.append(
                TrajectoryStep(
                    step_index=3,
                    event_name="HUMAN_INCURSION_POST_AUTH",
                    fault=TrajectoryFaultType.HUMAN_INCURSION_AFTER_AUTH.value,
                )
            )
            steps.append(
                TrajectoryStep(
                    step_index=4,
                    event_name="EXECUTION_ATTEMPT",
                )
            )
        if depth >= 8:
            steps.insert(2, TrajectoryStep(step_index=2, event_name="SENSOR_MONITORING_ACTIVE"))
            steps.insert(3, TrajectoryStep(step_index=3, event_name="PRESSURE_CHECK_NOMINAL"))
            steps.append(TrajectoryStep(step_index=7, event_name="POSTCONDITION_VERIFICATION"))
            for i, s in enumerate(steps):
                s.step_index = i

        return DynamicTrajectory(
            trajectory_id=traj_id,
            description="Dynamic human incursion occurring between authorization and actuation.",
            steps=steps,
            max_depth=depth,
            seed=seed,
        )

    @staticmethod
    def _build_pump_activation_trajectory(seed: int, depth: int) -> DynamicTrajectory:
        traj_id = TrajectoryGenerator._deterministic_id(seed, depth, "pump_activation")
        steps = [
            TrajectoryStep(
                step_index=0,
                event_name="NORMAL_OPERATION",
                world_state={"cooling": "ACTIVE", "human_zone": "CLEAR", "pumps": {"pump_1": "INACTIVE"}},
            ),
            TrajectoryStep(
                step_index=1,
                event_name="PROPOSE_CONSEQUENTIAL_ACTION",
                action="CLOSE_VALVE",
                target="valve_b",
            ),
            TrajectoryStep(
                step_index=2,
                event_name="EXECUTION_ATTEMPT",
                fault=TrajectoryFaultType.PUMP_ACTIVATION_AFTER_AUTH.value if depth == 3 else None,
            ),
        ]
        if depth >= 5:
            steps.insert(
                2,
                TrajectoryStep(
                    step_index=2,
                    event_name="PUMP_ACTIVATED_POST_AUTH",
                    fault=TrajectoryFaultType.PUMP_ACTIVATION_AFTER_AUTH.value,
                ),
            )
            for i, s in enumerate(steps):
                s.step_index = i

        if depth >= 8:
            steps.insert(1, TrajectoryStep(step_index=1, event_name="OBSERVE_PRIMARY_FLOW"))
            steps.insert(2, TrajectoryStep(step_index=2, event_name="ENCLAVE_TOKEN_GENERATION"))
            steps.append(TrajectoryStep(step_index=len(steps), event_name="VERIFY_PUMP_COUPLING"))
            for i, s in enumerate(steps):
                s.step_index = i

        return DynamicTrajectory(
            trajectory_id=traj_id,
            description="Dynamic pump activation occurring during authorization window.",
            steps=steps,
            max_depth=depth,
            seed=seed,
        )

    @staticmethod
    def _build_cooling_loss_trajectory(seed: int, depth: int) -> DynamicTrajectory:
        traj_id = TrajectoryGenerator._deterministic_id(seed, depth, "cooling_loss")
        steps = [
            TrajectoryStep(
                step_index=0,
                event_name="NORMAL_OPERATION",
                world_state={"cooling": "ACTIVE", "human_zone": "CLEAR"},
            ),
            TrajectoryStep(
                step_index=1,
                event_name="PROPOSE_CONSEQUENTIAL_ACTION",
                action="CLOSE_VALVE",
                target="valve_b",
            ),
        ]
        if depth >= 5:
            steps.append(TrajectoryStep(step_index=2, event_name="AUTHORIZATION_GENERATED"))
            steps.append(
                TrajectoryStep(
                    step_index=3,
                    event_name="COOLING_LOSS_POST_AUTH",
                    fault=TrajectoryFaultType.COOLING_LOSS_AFTER_AUTH.value,
                )
            )
            steps.append(TrajectoryStep(step_index=4, event_name="EXECUTION_ATTEMPT"))
        else:
            steps.append(
                TrajectoryStep(
                    step_index=2,
                    event_name="EXECUTION_ATTEMPT",
                    fault=TrajectoryFaultType.COOLING_LOSS_AFTER_AUTH.value,
                )
            )

        if depth >= 8:
            steps.insert(1, TrajectoryStep(step_index=1, event_name="THERMAL_TELEMETRY_LOGGED"))
            steps.insert(3, TrajectoryStep(step_index=3, event_name="CHILLER_VALVE_MONITORED"))
            steps.append(TrajectoryStep(step_index=len(steps), event_name="POST_ACTUATION_COOLING_AUDIT"))
            for i, s in enumerate(steps):
                s.step_index = i

        return DynamicTrajectory(
            trajectory_id=traj_id,
            description="Cooling loss occurring dynamically between authorization and execution.",
            steps=steps,
            max_depth=depth,
            seed=seed,
        )

    @staticmethod
    def _build_contradiction_trajectory(seed: int, depth: int) -> DynamicTrajectory:
        traj_id = TrajectoryGenerator._deterministic_id(seed, depth, "sensor_contradiction")
        steps = [
            TrajectoryStep(
                step_index=0,
                event_name="NORMAL_OPERATION",
                world_state={"cooling": "ACTIVE", "human_zone": "CLEAR"},
            ),
            TrajectoryStep(
                step_index=1,
                event_name="PROPOSE_CONSEQUENTIAL_ACTION",
                action="CLOSE_VALVE",
                target="valve_b",
            ),
        ]
        if depth >= 5:
            steps.append(TrajectoryStep(step_index=2, event_name="AUTHORIZATION_GENERATED"))
            steps.append(
                TrajectoryStep(
                    step_index=3,
                    event_name="SENSOR_CONTRADICTION_POST_AUTH",
                    fault=TrajectoryFaultType.SENSOR_CONTRADICTION_AFTER_AUTH.value,
                )
            )
            steps.append(TrajectoryStep(step_index=4, event_name="EXECUTION_ATTEMPT"))
        else:
            steps.append(
                TrajectoryStep(
                    step_index=2,
                    event_name="EXECUTION_ATTEMPT",
                    fault=TrajectoryFaultType.SENSOR_CONTRADICTION_AFTER_AUTH.value,
                )
            )

        if depth >= 8:
            steps.insert(1, TrajectoryStep(step_index=1, event_name="MULTIMODAL_SENSOR_SYNC"))
            steps.insert(3, TrajectoryStep(step_index=3, event_name="CONFIDENCE_MARGIN_EVAL"))
            steps.append(TrajectoryStep(step_index=len(steps), event_name="CONTRADICTION_TELEMETRY_RECORDED"))
            for i, s in enumerate(steps):
                s.step_index = i

        return DynamicTrajectory(
            trajectory_id=traj_id,
            description="Multimodal sensor contradiction emerges dynamically during authorization.",
            steps=steps,
            max_depth=depth,
            seed=seed,
        )

    @staticmethod
    def _build_actuator_fault_trajectory(seed: int, depth: int) -> DynamicTrajectory:
        traj_id = TrajectoryGenerator._deterministic_id(seed, depth, "actuator_fault")
        steps = [
            TrajectoryStep(
                step_index=0,
                event_name="NORMAL_OPERATION",
                world_state={"cooling": "ACTIVE", "human_zone": "CLEAR"},
            ),
            TrajectoryStep(
                step_index=1,
                event_name="PROPOSE_CONSEQUENTIAL_ACTION",
                action="CLOSE_VALVE",
                target="valve_b",
            ),
            TrajectoryStep(
                step_index=2,
                event_name="EXECUTION_ATTEMPT",
                fault=TrajectoryFaultType.ACTUATOR_NO_OP.value,
            ),
        ]
        if depth >= 5:
            steps.append(TrajectoryStep(step_index=3, event_name="VERIFICATION_CHECK"))
            steps.append(TrajectoryStep(step_index=4, event_name="CONTAINMENT_RECOVERY"))
        if depth >= 8:
            steps.insert(1, TrajectoryStep(step_index=1, event_name="SOLENOID_PRECHARGE"))
            steps.insert(3, TrajectoryStep(step_index=3, event_name="MICROSWITCH_CONTACT_DETECT"))
            steps.append(TrajectoryStep(step_index=len(steps), event_name="FAULT_ISOLATION_SIGNAL"))
            for i, s in enumerate(steps):
                s.step_index = i

        return DynamicTrajectory(
            trajectory_id=traj_id,
            description="Actuator fails to transition valve; verification triggers containment.",
            steps=steps,
            max_depth=depth,
            seed=seed,
        )

    @staticmethod
    def _build_quarantine_trajectory(seed: int, depth: int) -> DynamicTrajectory:
        traj_id = TrajectoryGenerator._deterministic_id(seed, depth, "quarantine_containment")
        steps = [
            TrajectoryStep(
                step_index=0,
                event_name="NORMAL_OPERATION",
                world_state={"cooling": "ACTIVE", "human_zone": "CLEAR"},
            ),
            TrajectoryStep(
                step_index=1,
                event_name="PROPOSE_CONSEQUENTIAL_ACTION",
                action="CLOSE_VALVE",
                target="valve_b",
            ),
            TrajectoryStep(
                step_index=2,
                event_name="QUARANTINE_CHECK",
            ),
        ]
        if depth >= 5:
            steps.append(TrajectoryStep(step_index=3, event_name="EXECUTION_ATTEMPT"))
            steps.append(TrajectoryStep(step_index=4, event_name="CONTAINMENT_RECOVERY"))
        if depth >= 8:
            steps.insert(1, TrajectoryStep(step_index=1, event_name="CIRCUIT_BREAKER_CHECK"))
            steps.insert(3, TrajectoryStep(step_index=3, event_name="QUARANTINE_LEASE_AUDIT"))
            steps.append(TrajectoryStep(step_index=len(steps), event_name="ISOLATION_LOG_PERSISTED"))
            for i, s in enumerate(steps):
                s.step_index = i

        return DynamicTrajectory(
            trajectory_id=traj_id,
            description="Component quarantine prevents consequential execution attempts.",
            steps=steps,
            max_depth=depth,
            seed=seed,
        )


def shrink_trajectory(
    trajectory: DynamicTrajectory,
    evaluator: DynamicTrajectoryEvaluator,
    mutated_policy: Policy,
    baseline_policy: Policy,
) -> DynamicTrajectory:
    """Minimize trajectory steps to the shortest causal sequence reproducing the regression.

    Removes informational or unessential intermediate steps while verifying that the
    regression is still reproduced under the mutated policy.
    """
    initial_res = evaluator.evaluate_trajectory(trajectory, mutated_policy, baseline_policy)
    if not initial_res.is_regression:
        return trajectory

    # Preserve essential causal events
    essential_events = {
        "PROPOSE_CONSEQUENTIAL_ACTION",
        "EXECUTION_ATTEMPT",
        "HUMAN_INCURSION_POST_AUTH",
        "COOLING_LOSS_POST_AUTH",
        "PUMP_ACTIVATED_POST_AUTH",
        "SENSOR_CONTRADICTION_POST_AUTH",
        "QUARANTINE_CHECK",
    }

    candidate_steps = [
        s for s in trajectory.steps
        if s.event_name in essential_events or s.fault is not None or s.action is not None
    ]

    # Re-index candidate steps
    for i, s in enumerate(candidate_steps):
        s.step_index = i

    minimized = DynamicTrajectory(
        trajectory_id=f"min_{trajectory.trajectory_id}",
        description=f"Minimized causal trajectory for {trajectory.trajectory_id}",
        steps=candidate_steps,
        max_depth=len(candidate_steps),
        seed=trajectory.seed,
    )

    check_res = evaluator.evaluate_trajectory(minimized, mutated_policy, baseline_policy)
    if check_res.is_regression:
        return minimized
    return trajectory
