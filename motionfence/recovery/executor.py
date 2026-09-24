"""Autonomous recovery execution engine orchestrating containment, diagnostics, and fresh authorization."""

from typing import Any, Dict, List, Optional, Tuple
import copy
import time

from motionfence.models.actions import (
    ActionProposal,
    ActionType,
    AuthorizationTicket,
    ExecutionResult,
)
from motionfence.models.events import EventType
from motionfence.models.world import WorldState
from motionfence.evidence.models import Evidence
from motionfence.policy.engine import PolicyEngine
from motionfence.policy.models import DecisionType, Policy, PolicyDecision
from motionfence.runtime.capabilities import CapabilityPolicy, create_planner_capability_policy
from motionfence.runtime.enclave import EnclaveAuthorizationRequest, SafetyEnclave
from motionfence.runtime.events import EventBus
from motionfence.runtime.evidence_actions import EvidenceActionGateway, InformationAction
from motionfence.runtime.revalidation import (
    AuthorizationRevalidationResult,
    ExecutionTimeRevalidator,
    RevalidationStatus,
)
from motionfence.runtime.verification import PostActionVerifier, VerificationResult, VerificationStatus
from motionfence.simulation.actuator import PhysicalActuator
from motionfence.simulation.exceptions import UnauthorizedActionError
from motionfence.simulation.world import PhysicalWorld
from motionfence.recovery.classifier import FailureClassifier
from motionfence.recovery.containment import ContainmentManager
from motionfence.recovery.models import (
    FailureClass,
    FailureRecord,
    QuarantineRecord,
    QuarantineStatus,
    RecoveryExecutionResult,
    RecoveryOutcome,
    RecoveryPlan,
    RecoveryStrategy,
)
from motionfence.recovery.planner import RecoveryPlanner
from motionfence.recovery.policies import ContainmentPolicy, QuarantinePolicy, RecoveryBudget
from motionfence.recovery.quarantine import QuarantineManager


class RecoveryExecutor:
    """Executes the deterministic fault containment and autonomous recovery lifecycle.
    
    SECURITY INVARIANTS:
    1. A failed action CANNOT silently reuse its previous ticket (PROP_024, PROP_026).
    2. Every consequential retry requires a completely fresh authorization cycle (PROP_027).
    3. Quarantined components cannot execute blocked capabilities (PROP_025).
    4. Sensor quarantine excludes untrusted telemetry from the active authorization context (PROP_028).
    5. Recovery attempts are strictly bounded by finite budgets (PROP_029).
    6. Informational recovery steps cannot escalate into consequential actuation (PROP_030).
    """

    def __init__(
        self,
        world: Optional[PhysicalWorld] = None,
        quarantine_manager: Optional[QuarantineManager] = None,
        containment_manager: Optional[ContainmentManager] = None,
        recovery_planner: Optional[RecoveryPlanner] = None,
        recovery_budget: Optional[RecoveryBudget] = None,
        event_bus: Optional[EventBus] = None,
        secret_key: str = "motionfence_runtime_kernel_secret",
    ) -> None:
        self.world = world or PhysicalWorld()
        self.quarantine_manager = quarantine_manager or QuarantineManager()
        self.containment_manager = containment_manager or ContainmentManager(event_bus=event_bus)
        self.recovery_planner = recovery_planner or RecoveryPlanner(budget=recovery_budget)
        self.recovery_budget = recovery_budget or RecoveryBudget()
        self.event_bus = event_bus
        self.secret_key = secret_key

    def handle_failure_and_recover(
        self,
        failed_proposal: ActionProposal,
        failed_execution: Optional[ExecutionResult] = None,
        failed_verification: Optional[VerificationResult] = None,
        failed_revalidation: Optional[AuthorizationRevalidationResult] = None,
        initial_ticket: Optional[AuthorizationTicket] = None,
        current_evidence: Optional[List[Evidence]] = None,
        policy: Optional[Policy] = None,
        max_attempts: Optional[int] = None,
    ) -> RecoveryExecutionResult:
        """Run the complete containment, quarantine, recovery planning, and fresh authorization workflow."""
        start_time = time.time()
        policy = policy or Policy()
        evidence_pool = list(current_evidence) if current_evidence is not None else self.world.generate_targeted_evidence(failed_proposal.target)
        max_allowed_attempts = max_attempts or self.recovery_budget.max_recovery_attempts
        executed_steps_log: List[Dict[str, Any]] = []
        new_evidence_collected: List[Evidence] = []
        unsafe_retries = 0

        # Step 1: Detect and Classify Failure
        if self.event_bus:
            self.event_bus.emit(
                EventType.ACTION_FAILURE_DETECTED,
                f"Action failure detected for proposal '{failed_proposal.id}' on target '{failed_proposal.target}'.",
                payload={"proposal_id": failed_proposal.id, "target": failed_proposal.target},
            )

        failure_record = FailureClassifier.classify(
            proposal=failed_proposal,
            execution=failed_execution,
            verification=failed_verification,
            revalidation=failed_revalidation,
            world_state=self.world.get_state(),
            evidence=evidence_pool,
        )

        if self.event_bus:
            self.event_bus.emit(
                EventType.FAILURE_CLASSIFIED,
                f"Failure classified as '{failure_record.failure_class.value}': {failure_record.details}",
                payload={"failure_id": failure_record.failure_id, "failure_class": failure_record.failure_class.value},
            )

        # Step 2: Immediate Containment & Cryptographic Authority Invalidation
        containment_report = self.containment_manager.contain_failure(
            failure=failure_record,
            active_ticket=initial_ticket,
            quarantine_manager=self.quarantine_manager,
        )

        # Check if component has reached QUARANTINED status
        target_rec = self.quarantine_manager.get_record(failed_proposal.target)
        if target_rec is not None and target_rec.is_quarantined:
            duration = time.time() - start_time
            dummy_plan = RecoveryPlan(
                failure_id=failure_record.failure_id,
                strategy=RecoveryStrategy.ABORT_AND_QUARANTINE,
                rationale=f"Component '{failed_proposal.target}' reached quarantine threshold. Consequential actuation halted.",
            )
            return RecoveryExecutionResult(
                failure_record=failure_record,
                recovery_plan=dummy_plan,
                outcome=RecoveryOutcome.QUARANTINED,
                iterations_used=0,
                max_iterations_allowed=max_allowed_attempts,
                quarantine_records={target_rec.component_id: target_rec},
                fresh_authorization_required=True,
                unsafe_retries=0,
                duration_seconds=duration,
                message=f"Component '{failed_proposal.target}' is QUARANTINED. All consequential commands strictly refused.",
            )

        # Step 3: Multi-Attempt Autonomous Recovery Loop
        attempt = 0
        gateway = EvidenceActionGateway(
            world=self.world,
            capability_policy=create_planner_capability_policy(),
            event_bus=self.event_bus,
        )

        last_plan = None
        while attempt < max_allowed_attempts:
            attempt += 1

            # 3a. Formulate Recovery Plan
            plan = self.recovery_planner.plan_recovery(
                failure=failure_record,
                world_state=self.world.get_state(),
                evidence_pool=evidence_pool,
                quarantine_manager=self.quarantine_manager,
                attempt_number=attempt,
            )
            last_plan = plan

            if self.event_bus:
                self.event_bus.emit(
                    EventType.RECOVERY_PLANNED,
                    f"Recovery plan '{plan.plan_id}' formulated with strategy '{plan.strategy.value}'.",
                    payload={"plan_id": plan.plan_id, "strategy": plan.strategy.value},
                )

            # If strategy is ABORT_AND_QUARANTINE
            if plan.strategy == RecoveryStrategy.ABORT_AND_QUARANTINE:
                self.quarantine_manager.quarantine_component(
                    component_id=failed_proposal.target,
                    reason=plan.rationale,
                )
                break

            # 3b. Execute Informational Recovery Steps (Diagnostic perception, resampling, waiting)
            for step in plan.steps:
                # Security check: Steps must remain non-consequential
                if step.is_consequential:
                    unsafe_retries += 1
                    raise UnauthorizedActionError(
                        f"SECURITY INVARIANT VIOLATION: Recovery plan attempted to invoke consequential action "
                        f"'{step.action_type.value}' directly without fresh SafetyEnclave authorization!"
                    )

                if self.event_bus:
                    self.event_bus.emit(
                        EventType.RECOVERY_ACTION_PROPOSED,
                        f"Executing recovery step '{step.action_type.value}' on target '{step.target}'.",
                        payload={"step_id": step.step_id, "action_type": step.action_type.value},
                    )

                info_action = InformationAction(
                    action_type=step.action_type,
                    target=step.target,
                    parameters=step.parameters,
                    reason=step.description,
                    expected_gain=step.expected_gain,
                )
                res = gateway.execute_action(info_action)
                executed_steps_log.append({
                    "step_id": step.step_id,
                    "action_type": step.action_type.value,
                    "target": step.target,
                    "success": res.success,
                    "message": res.message,
                })

                if res.success and res.new_evidence:
                    new_evidence_collected.extend(res.new_evidence)
                    # Replace/update evidence pool
                    new_pairs = {(e.source, e.target) for e in res.new_evidence}
                    evidence_pool = [e for e in evidence_pool if (e.source, e.target) not in new_pairs]
                    evidence_pool.extend(res.new_evidence)

            # 3c. Filter Evidence: Prune quarantined/failed sensor telemetry (PROP_028)
            admissible_evidence = self.quarantine_manager.filter_admissible_evidence(evidence_pool)

            # 3d. Check Scoped Quarantine on Proposal Target (PROP_025)
            candidate_proposal = plan.suggested_alternate_proposal if plan.suggested_alternate_proposal else failed_proposal
            if not self.quarantine_manager.is_action_permitted(candidate_proposal.action_type, candidate_proposal.target):
                self.quarantine_manager.record_failure(
                    failure_record,
                    custom_reason=f"Attempted action '{candidate_proposal.action_type.value}' blocked by scoped quarantine on '{candidate_proposal.target}'.",
                )
                continue

            # 3e. Deterministic Policy Re-evaluation (Fresh cycle)
            fresh_decision = PolicyEngine.evaluate(
                proposal=candidate_proposal,
                world_state=self.world.get_state(),
                evidence=admissible_evidence,
                policy=policy,
            )

            # If policy allows, initiate FRESH authorization cycle
            if fresh_decision.is_allowed:
                if self.event_bus:
                    self.event_bus.emit(
                        EventType.FRESH_AUTHORIZATION_REQUIRED,
                        f"Policy re-evaluation ALLOWED proposal '{candidate_proposal.id}'. Requesting fresh Safety Enclave ticket.",
                        payload={"proposal_id": candidate_proposal.id},
                    )

                enclave = SafetyEnclave(secret_key=self.secret_key, event_bus=self.event_bus)
                enclave_req = EnclaveAuthorizationRequest(
                    proposal=candidate_proposal,
                    world_state=self.world.get_state(),
                    evidence=admissible_evidence,
                    policy=policy,
                )
                auth_res = enclave.authorize(enclave_req)

                if auth_res.is_authorized and auth_res.ticket is not None:
                    fresh_ticket = auth_res.ticket

                    # Security Verification: Ticket must NOT be the initial failed ticket
                    if initial_ticket and fresh_ticket.ticket_id == initial_ticket.ticket_id:
                        unsafe_retries += 1
                        raise UnauthorizedActionError("CRITICAL INVARIANT VIOLATION: Reused stale authorization ticket!")

                    # Pre-Execution Revalidation Gate
                    reval_result = ExecutionTimeRevalidator.revalidate(
                        authorization_context=auth_res.authorization_context,
                        current_world_state=self.world.get_state(),
                        current_policy_version=getattr(policy, "version", "1.0.0"),
                        current_constraints=[],
                        current_evidence=admissible_evidence,
                        ticket_expires_at=fresh_ticket.expires_at,
                        proposal_action_type=candidate_proposal.action_type,
                        proposal_target=candidate_proposal.target,
                    )

                    if reval_result.status != RevalidationStatus.VALID:
                        # Revalidation drift blocked execution
                        continue

                    # Execute Physical Actuation
                    actuator = PhysicalActuator(world=self.world, secret_key=self.secret_key)
                    pre_state = self.world.get_state()
                    try:
                        retry_exec = actuator.execute(candidate_proposal, fresh_ticket)
                    except UnauthorizedActionError as err:
                        retry_exec = ExecutionResult(
                            success=False,
                            action_id=candidate_proposal.id,
                            ticket_id=fresh_ticket.ticket_id,
                            executed_action=candidate_proposal.action_type,
                            target=candidate_proposal.target,
                            message=str(err),
                            state_version_before=pre_state.version,
                            state_version_after=self.world.version,
                        )

                    post_state = self.world.get_state()
                    retry_verif = PostActionVerifier.verify(
                        proposal=candidate_proposal,
                        execution=retry_exec,
                        pre_state=pre_state,
                        post_state=post_state,
                    )

                    if retry_verif.is_verified:
                        # Success: Recertify component if previously suspect
                        self.quarantine_manager.recertify_component(
                            component_id=candidate_proposal.target,
                            certification_evidence=[e.id for e in admissible_evidence],
                            rationale="Autonomous recovery cycle succeeded and was independently verified.",
                        )
                        if self.event_bus:
                            self.event_bus.emit(
                                EventType.RECOVERY_COMPLETED,
                                f"Autonomous recovery succeeded for '{candidate_proposal.target}'. Physical outcome verified.",
                                payload={"target": candidate_proposal.target, "iterations": attempt},
                            )

                        duration = time.time() - start_time
                        return RecoveryExecutionResult(
                            failure_record=failure_record,
                            recovery_plan=plan,
                            outcome=RecoveryOutcome.SUCCESS,
                            iterations_used=attempt,
                            max_iterations_allowed=max_allowed_attempts,
                            executed_steps=executed_steps_log,
                            new_evidence_gathered=new_evidence_collected,
                            quarantine_records=dict(self.quarantine_manager._records),
                            fresh_authorization_required=True,
                            fresh_policy_decision=fresh_decision,
                            fresh_ticket=fresh_ticket,
                            retry_execution_result=retry_exec,
                            retry_verification_result=retry_verif,
                            unsafe_retries=0,
                            duration_seconds=duration,
                            message=f"Autonomous recovery succeeded on attempt #{attempt}: physical postconditions verified.",
                        )
                    else:
                        # Retry failed post-action verification: escalate failure count
                        self.quarantine_manager.record_failure(failure_record)
                else:
                    # Enclave denied authorization
                    pass
            else:
                # Policy still denies or needs more evidence
                pass

        # Step 4: Terminal Exit on Budget Exhaustion or Permanent Quarantine
        duration = time.time() - start_time
        if attempt >= max_allowed_attempts:
            if self.event_bus:
                self.event_bus.emit(
                    EventType.RECOVERY_BUDGET_EXHAUSTED,
                    f"Recovery budget exhausted ({attempt}/{max_allowed_attempts}) for component '{failed_proposal.target}'.",
                    payload={"target": failed_proposal.target, "attempts": attempt},
                )
            # Escalate to QUARANTINED
            self.quarantine_manager.quarantine_component(
                component_id=failed_proposal.target,
                reason=f"Autonomous recovery budget exhausted ({attempt} failed attempts).",
            )
            outcome = RecoveryOutcome.BUDGET_EXHAUSTED
            msg = f"Recovery budget exhausted ({attempt}/{max_allowed_attempts}); component '{failed_proposal.target}' quarantined."
        else:
            outcome = RecoveryOutcome.FAILED
            msg = f"Autonomous recovery could not establish safe conditions; component '{failed_proposal.target}' isolated."

        return RecoveryExecutionResult(
            failure_record=failure_record,
            recovery_plan=last_plan or RecoveryPlan(failure_id=failure_record.failure_id, strategy=RecoveryStrategy.ABORT_AND_QUARANTINE),
            outcome=outcome,
            iterations_used=attempt,
            max_iterations_allowed=max_allowed_attempts,
            executed_steps=executed_steps_log,
            new_evidence_gathered=new_evidence_collected,
            quarantine_records=dict(self.quarantine_manager._records),
            fresh_authorization_required=True,
            unsafe_retries=unsafe_retries,
            duration_seconds=duration,
            message=msg,
        )
