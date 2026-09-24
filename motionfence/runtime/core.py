"""MotionFence Runtime Core: Deterministic control loop orchestrator."""

from typing import Any, Dict, List, Optional
import time
from pydantic import BaseModel, Field

from motionfence.models.actions import (
    ActionProposal,
    ActionType,
    AuthorizationTicket,
    ExecutionResult,
)
from motionfence.models.world import WorldState
from motionfence.models.events import EventType, RuntimeEvent
from motionfence.evidence.models import Evidence
from motionfence.policy.models import Policy, PolicyDecision, DecisionType
from motionfence.policy.engine import PolicyEngine
from motionfence.simulation.world import PhysicalWorld
from motionfence.simulation.actuator import PhysicalActuator
from motionfence.agent.provider import ActionProposalProvider, LocalDeterministicProvider
from motionfence.runtime.events import EventBus
from motionfence.runtime.ticket import TicketAuthority
from motionfence.runtime.verification import PostActionVerifier, VerificationResult, VerificationStatus
from motionfence.runtime.enclave import SafetyEnclave, EnclaveAuthorizationRequest
from motionfence.audit.models import DecisionRecord, DecisionCategory, ExecutionMode, SourceMode
from motionfence.audit.recorder import DecisionRecorder
from motionfence.runtime.revalidation import (
    ExecutionTimeRevalidator,
    RevalidationStatus,
    compute_world_state_hash,
)
from motionfence.hardware.models import (
    ActuatorType,
    HardwareExecutionRecord,
    HardwareExecutionStatus,
    HardwareFaultType,
)
from motionfence.hardware.mock import MockHardwareEndpoint
from motionfence.hardware.interface import HardwareEndpoint

# Knowledge and constraints integrations (Phase 2A)
from motionfence.knowledge.models import KnowledgeEvidence
from motionfence.knowledge.retrieval import KnowledgeRetrievalService
from motionfence.constraints.models import (
    CandidateConstraint,
    ConstraintConflictReport,
    ConstraintStatus,
    PlantContext,
)
from motionfence.constraints.extractor import ConstraintExtractor
from motionfence.constraints.validator import ConstraintValidator
from motionfence.constraints.conflict import ConstraintConflictDetector
from motionfence.knowledge.trust import (
    SourceTrustClassifier,
    CorroborationEngine,
    CorroborationStatus,
)
from motionfence.runtime.capabilities import (
    CapabilityEscalationError,
    CapabilityPolicy,
    create_planner_capability_policy,
)
from motionfence.runtime.evidence_actions import (
    EvidenceActionGateway,
    InformationAction,
    InformationGainLevel,
)
from motionfence.agent.evidence_planner import (
    BaseEvidencePlanner,
    LocalEvidencePlanner,
    EvidenceAcquisitionPlan,
)


class RuntimeCycleResult(BaseModel):
    """Auditable summary of an entire Observe-Propose-Authorize-Act-Verify cycle."""
    intent: str
    provider: str = Field(default="deterministic", description="Identifier of the proposal provider used.")
    model: Optional[str] = Field(default=None, description="Model identifier if an AI provider was used.")
    error: Optional[str] = Field(default=None, description="Error message if provider inference failed.")
    proposal: Optional[ActionProposal] = None
    policy_decision: Optional[PolicyDecision] = None
    ticket: Optional[AuthorizationTicket] = None
    execution_result: Optional[ExecutionResult] = None
    verification_result: Optional[VerificationResult] = None
    hardware_execution: Optional[HardwareExecutionRecord] = Field(
        default=None,
        description="Physical hardware endpoint execution record.",
    )
    pre_state: WorldState
    post_state: WorldState
    events: List[RuntimeEvent] = Field(default_factory=list)

    # Phase 2D: Immutable Hash-Linked Decision Record
    decision_record: Optional[DecisionRecord] = Field(
        default=None,
        description="Immutable, cryptographically hash-linked audit record of this cycle."
    )

    # Phase 2A Provenance Chain
    knowledge_evidence: List[KnowledgeEvidence] = Field(
        default_factory=list,
        description="Retrieved operational knowledge items."
    )
    candidate_constraints: List[CandidateConstraint] = Field(
        default_factory=list,
        description="Extracted candidate constraints."
    )
    active_constraints: List[CandidateConstraint] = Field(
        default_factory=list,
        description="Promoted active constraints enforced during evaluation."
    )
    constraint_conflicts: List[ConstraintConflictReport] = Field(
        default_factory=list,
        description="Detected mutual contradictions between operational rules."
    )

    # Phase 2G: Active Evidence Acquisition
    evidence_action_ids: List[str] = Field(
        default_factory=list,
        description="IDs of executed information-gathering actions.",
    )
    evidence_iterations: int = Field(
        default=0,
        description="Number of information-gathering iterations executed.",
    )
    predicted_information_gain: Optional[str] = Field(
        default=None,
        description="Predicted information gain level from planner.",
    )
    observed_information_gain: Optional[str] = Field(
        default=None,
        description="Observed empirical information gain level.",
    )

    @property
    def is_success(self) -> bool:
        """True if the cycle resulted in an authorized, executed, and verified outcome."""
        return (
            self.error is None
            and self.policy_decision is not None
            and self.policy_decision.is_allowed
            and self.verification_result is not None
            and self.verification_result.is_verified
        )


class MotionFenceRuntime:
    """The central runtime authorization layer governing physical AI actions.
    
    Coordinates the strictly ordered control loop:
    Knowledge → Observe → Propose → Evaluate Policy → Allow / Deny / Need Evidence → Act → Verify
    """

    def __init__(
        self,
        world: Optional[PhysicalWorld] = None,
        actuator: Optional[PhysicalActuator] = None,
        proposal_provider: Optional[ActionProposalProvider] = None,
        policy: Optional[Policy] = None,
        knowledge_service: Optional[KnowledgeRetrievalService] = None,
        constraint_extractor: Optional[ConstraintExtractor] = None,
        plant_context: Optional[PlantContext] = None,
        evidence_planner: Optional[BaseEvidencePlanner] = None,
        evidence_gateway: Optional[EvidenceActionGateway] = None,
        max_evidence_actions_per_cycle: int = 3,
        secret_key: str = "motionfence_runtime_kernel_secret",
        hardware_endpoint: Optional[HardwareEndpoint] = None,
    ) -> None:
        self.world = world or PhysicalWorld()
        self.event_bus = EventBus()
        self.actuator = actuator or PhysicalActuator(self.world, secret_key=secret_key)
        self.hardware_endpoint = hardware_endpoint or MockHardwareEndpoint(
            world=self.world,
            secret_key=secret_key,
            event_bus=self.event_bus,
            underlying_actuator=self.actuator,
        )
        self.proposal_provider = proposal_provider or LocalDeterministicProvider()
        self.policy = policy or Policy()
        self.knowledge_service = knowledge_service
        self.constraint_extractor = constraint_extractor
        self.plant_context = plant_context or PlantContext()
        self.safety_enclave = SafetyEnclave(secret_key=secret_key, event_bus=self.event_bus)
        self.ticket_authority = self.safety_enclave._ticket_authority
        self.recorder = DecisionRecorder(event_bus=self.event_bus)
        self.max_evidence_actions_per_cycle = max_evidence_actions_per_cycle
        self.evidence_gateway = evidence_gateway or EvidenceActionGateway(
            world=self.world,
            event_bus=self.event_bus,
        )
        self.evidence_planner = evidence_planner or LocalEvidencePlanner(
            capability_policy=self.evidence_gateway.capability_policy,
            event_bus=self.event_bus,
        )

        # Connect event bus to components if supported
        if hasattr(self.proposal_provider, "event_bus") and self.proposal_provider.event_bus is None:
            self.proposal_provider.event_bus = self.event_bus
        if self.knowledge_service and self.knowledge_service.event_bus is None:
            self.knowledge_service.event_bus = self.event_bus

    def run_cycle(
        self,
        intent: str,
        initial_evidence: Optional[List[Evidence]] = None,
        knowledge_query: Optional[str] = None,
        gather_additional_evidence_on_request: bool = False,
        auto_evidence_acquisition: Optional[bool] = None,
    ) -> RuntimeCycleResult:
        """Execute a single deterministic control loop."""
        if auto_evidence_acquisition is None:
            auto_evidence_acquisition = gather_additional_evidence_on_request
        cycle_events: List[RuntimeEvent] = []

        def track(evt: RuntimeEvent) -> None:
            cycle_events.append(evt)

        provider_name = getattr(self.proposal_provider, "provider_name", "deterministic")
        model_name = getattr(self.proposal_provider, "model", None)

        # 1. Intent Received
        evt_intent = self.event_bus.emit(
            EventType.INTENT_RECEIVED,
            f"Human intent received: '{intent}'",
            payload={"intent": intent},
        )
        track(evt_intent)

        # 2. Operational Knowledge Retrieval & Candidate Constraint Extraction (Phase 2A)
        retrieved_knowledge: List[KnowledgeEvidence] = []
        candidate_constraints: List[CandidateConstraint] = []
        active_constraints: List[CandidateConstraint] = list(self.policy.active_constraints)
        conflict_reports: List[ConstraintConflictReport] = []

        if self.knowledge_service is not None:
            q = knowledge_query or intent
            try:
                retrieved_knowledge = self.knowledge_service.query(q)
            except Exception as e:
                track(
                    self.event_bus.emit(
                        EventType.KNOWLEDGE_RESULT_REJECTED,
                        f"Knowledge provider query failed: {e}. Existing safety policy remains authoritative.",
                        payload={"query": q, "error": str(e)},
                    )
                )
                retrieved_knowledge = []

            if self.constraint_extractor is not None and retrieved_knowledge:
                evidence_reg = self.knowledge_service._evidence_registry

                # Step 2a: Assess source trust for each retrieved item
                assessments = {}
                for ev in retrieved_knowledge:
                    ass = SourceTrustClassifier.assess(ev, query=q)
                    assessments[ev.id] = ass
                    track(
                        self.event_bus.emit(
                            EventType.SOURCE_ASSESSED,
                            f"Assessed source '{ev.id}': category={ass.source_category.value}, role={ass.evidence_role.value}",
                            payload=ass.model_dump(),
                        )
                    )
                    track(
                        self.event_bus.emit(
                            EventType.EVIDENCE_CLASSIFIED,
                            f"Evidence '{ev.id}' classified as role={ass.evidence_role.value}",
                            payload={"evidence_id": ev.id, "role": ass.evidence_role.value},
                        )
                    )

                # Step 2b: Multi-source corroboration check
                corroboration_status, corroboration_notes = CorroborationEngine.evaluate_corroboration(
                    retrieved_knowledge, assessments
                )
                if corroboration_status == CorroborationStatus.CORROBORATED:
                    track(
                        self.event_bus.emit(
                            EventType.EVIDENCE_CORROBORATED,
                            f"Retrieved knowledge corroborated across independent sources: {corroboration_notes}",
                            payload={"status": corroboration_status.value},
                        )
                    )

                # Step 2c: Extract candidate constraints
                candidate_constraints = self.constraint_extractor.extract(retrieved_knowledge)
                for cst in candidate_constraints:
                    track(
                        self.event_bus.emit(
                            EventType.CONSTRAINT_EXTRACTED,
                            f"Extracted constraint '{cst.constraint_id}' ({cst.constraint_type.value}) for {cst.target}.",
                            payload=cst.model_dump(),
                        )
                    )
                    track(
                        self.event_bus.emit(
                            EventType.CONSTRAINT_CANDIDATE_CREATED,
                            f"Extracted candidate constraint '{cst.constraint_id}' ({cst.constraint_type.value}) for {cst.target}.",
                            payload=cst.model_dump(),
                        )
                    )

                    # Step 2d: Deterministic Validation, Admissibility, and Promotion
                    promoted = ConstraintValidator.promote_to_active(
                        cst,
                        evidence_reg,
                        self.event_bus,
                        plant_context=self.plant_context,
                        corroboration_status=corroboration_status,
                    )
                    if promoted.is_active or promoted.status == ConstraintStatus.STALE:
                        active_constraints.append(promoted)

                # Step 2e: Check for conflicts among all constraints and base policy
                conflict_reports = ConstraintConflictDetector.detect_conflicts(
                    candidate_constraints + active_constraints,
                    self.event_bus,
                    policy=self.policy,
                )
                for cst in candidate_constraints:
                    if cst.status == ConstraintStatus.CONFLICTED and cst not in active_constraints:
                        active_constraints.append(cst)

        # 3. Observe initial physical world state
        pre_state = self.world.get_state()
        evidence_pool = list(initial_evidence) if initial_evidence is not None else self.world.generate_initial_ambiguous_evidence()

        evt_obs = self.event_bus.emit(
            EventType.OBSERVATION_RECORDED,
            f"Recorded {len(evidence_pool)} physical sensor observations.",
            payload={"evidence_count": len(evidence_pool), "world_version": pre_state.version},
        )
        track(evt_obs)

        # Phase 2G Active Evidence Tracking variables
        evidence_action_ids: List[str] = []
        evidence_iterations: int = 0
        last_predicted_gain: Optional[str] = None
        last_observed_gain: Optional[str] = None

        # Helper to construct and finalize immutable DecisionRecord for every cycle outcome
        def _finalize_record(
            cat: DecisionCategory,
            pol_dec: Optional[PolicyDecision] = None,
            tkt: Optional[AuthorizationTicket] = None,
            exec_res: Optional[ExecutionResult] = None,
            verif_res: Optional[VerificationResult] = None,
            prop: Optional[ActionProposal] = None,
            reval_status: Optional[str] = None,
            reval_reasons: Optional[List[str]] = None,
            exec_version: Optional[int] = None,
            exec_hash: Optional[str] = None,
            evidence_act_ids: Optional[List[str]] = None,
            evidence_iters: Optional[int] = None,
            pred_gain: Optional[str] = None,
            obs_gain: Optional[str] = None,
            hw_rec: Optional[HardwareExecutionRecord] = None,
        ) -> DecisionRecord:
            certs = [c.support_certificate for c in active_constraints if c.support_certificate]
            source_assessments = [c.source_trust for c in active_constraints if c.source_trust]
            rec = self.recorder.create_record(
                intent=intent,
                world_state_snapshot=pre_state,
                policy_decision=cat,
                policy_reasons=[r.details if hasattr(r, "details") and r.details else f"{r.constraint}: {r.status}" for r in pol_dec.reasons] if pol_dec else [],
                action_proposal=prop,
                sensor_evidence=evidence_pool,
                knowledge_evidence=retrieved_knowledge,
                source_assessments=source_assessments,
                certificates=certs,
                candidate_constraints=candidate_constraints,
                active_constraints=active_constraints,
                authorization_ticket_id=tkt.ticket_id if tkt else None,
                execution_result=exec_res,
                verification_result=verif_res,
                provider_metadata={
                    "provider": provider_name,
                    "model": model_name,
                    "execution_mode": ExecutionMode.LIVE.value if provider_name != "deterministic" else ExecutionMode.FIXTURE.value,
                    "source_mode": SourceMode.LIVE_MODEL_RESPONSE.value if provider_name != "deterministic" else SourceMode.LOCAL_FIXTURE.value,
                },
                authorization_context_hash=tkt.authorization_context_hash if tkt else None,
                ticket_world_state_version=tkt.world_state_version if tkt else None,
                ticket_world_state_hash=tkt.world_state_hash if tkt else None,
                revalidation_status=reval_status,
                revalidation_reasons=reval_reasons or [],
                execution_context_version=exec_version,
                execution_context_hash=exec_hash,
                evidence_action_ids=evidence_act_ids if evidence_act_ids is not None else list(evidence_action_ids),
                evidence_acquisition_iterations=evidence_iters if evidence_iters is not None else evidence_iterations,
                evidence_budget=self.max_evidence_actions_per_cycle,
                predicted_information_gain=pred_gain if pred_gain is not None else last_predicted_gain,
                observed_information_gain=obs_gain if obs_gain is not None else last_observed_gain,
                hardware_execution_id=hw_rec.record_id if hw_rec else None,
                hardware_status=hw_rec.execution_status.value if hw_rec else None,
            )
            return self.recorder.finalize_record(rec)

        # 4. Propose action via agent provider
        try:
            proposal = self.proposal_provider.propose(
                intent=intent,
                world_state=pre_state,
                evidence=evidence_pool,
            )
        except Exception as e:
            err_msg = f"Proposal provider '{provider_name}' failed: {e}"
            evt_err = self.event_bus.emit(
                EventType.MODEL_PROVIDER_ERROR,
                err_msg,
                payload={"provider": provider_name, "model": model_name, "error": str(e)},
            )
            track(evt_err)
            rec = _finalize_record(DecisionCategory.DENY, pol_dec=None, prop=None)
            return RuntimeCycleResult(
                intent=intent,
                provider=provider_name,
                model=model_name,
                error=str(e),
                decision_record=rec,
                pre_state=pre_state,
                post_state=self.world.get_state(),
                events=cycle_events,
                knowledge_evidence=retrieved_knowledge,
                candidate_constraints=candidate_constraints,
                active_constraints=active_constraints,
                constraint_conflicts=conflict_reports,
                evidence_action_ids=evidence_action_ids,
                evidence_iterations=evidence_iterations,
                predicted_information_gain=last_predicted_gain,
                observed_information_gain=last_observed_gain,
            )

        evt_prop = self.event_bus.emit(
            EventType.ACTION_PROPOSED,
            f"Agent proposed {proposal.action_type.value} on {proposal.target} (conf={proposal.model_confidence:.2f})",
            payload=proposal.model_dump(),
        )
        track(evt_prop)

        # 5. Deterministic Policy Evaluation (Including Knowledge Constraints)
        decision = PolicyEngine.evaluate(
            proposal=proposal,
            world_state=pre_state,
            evidence=evidence_pool,
            policy=self.policy,
            active_constraints=active_constraints,
        )
        evt_pol = self.event_bus.emit(
            EventType.POLICY_EVALUATED,
            f"Policy evaluation verdict: {decision.decision.value}",
            payload=decision.model_dump(),
        )
        track(evt_pol)

        # Handle NEED_MORE_EVIDENCE with iterative active evidence acquisition
        if decision.needs_evidence:
            evt_need = self.event_bus.emit(
                EventType.MORE_EVIDENCE_REQUIRED,
                f"Action deferred: more evidence required for target '{proposal.target}'.",
                payload={"target": proposal.target, "reasons": [r.model_dump() for r in decision.reasons]},
            )
            track(evt_need)

            if auto_evidence_acquisition:
                track(
                    self.event_bus.emit(
                        EventType.EVIDENCE_ACQUISITION_STARTED,
                        f"Beginning active evidence acquisition (budget={self.max_evidence_actions_per_cycle} actions).",
                        payload={"budget": self.max_evidence_actions_per_cycle, "target": proposal.target},
                    )
                )

                while decision.needs_evidence and evidence_iterations < self.max_evidence_actions_per_cycle:
                    evidence_iterations += 1
                    try:
                        plan = self.evidence_planner.plan(
                            current_evidence=evidence_pool,
                            world_state=self.world.get_state(),
                            policy_decision=decision,
                            missing_requirements=[r.details for r in decision.reasons if r.details],
                        )
                    except CapabilityEscalationError as e:
                        track(
                            self.event_bus.emit(
                                EventType.EVIDENCE_ACTION_REJECTED,
                                f"SECURITY VIOLATION: Evidence planner escalation rejected: {e}",
                                payload={"error": str(e)},
                            )
                        )
                        break
                    except Exception as e:
                        track(
                            self.event_bus.emit(
                                EventType.EVIDENCE_ACTION_FAILED,
                                f"Evidence planning failed: {e}",
                                payload={"error": str(e)},
                            )
                        )
                        break

                    last_predicted_gain = plan.predicted_gain

                    info_action = InformationAction(
                        action_type=plan.action,
                        target=plan.target,
                        parameters=plan.parameters,
                        reason=plan.reason,
                        expected_gain=plan.predicted_gain,
                    )
                    exec_res = self.evidence_gateway.execute_action(info_action)
                    evidence_action_ids.append(exec_res.action_id)
                    last_observed_gain = exec_res.observed_gain

                    if exec_res.success and exec_res.new_evidence:
                        # Resampled sensor observations supersede prior readings from the same sensor/modality
                        if plan.action in (ActionType.RESAMPLE_SENSOR, ActionType.READ_SENSOR):
                            new_pairs = {(e.source, e.target) for e in exec_res.new_evidence}
                            evidence_pool = [e for e in evidence_pool if (e.source, e.target) not in new_pairs]
                        evidence_pool.extend(exec_res.new_evidence)
                        evt_more_obs = self.event_bus.emit(
                            EventType.OBSERVATION_RECORDED,
                            f"Gathered {len(exec_res.new_evidence)} new sensor observations via {plan.action.value} on {plan.target}.",
                            payload={"target": plan.target, "new_count": len(exec_res.new_evidence)},
                        )
                        track(evt_more_obs)

                        # Re-propose action with refined evidence
                        try:
                            proposal = self.proposal_provider.propose(
                                intent=intent,
                                world_state=pre_state,
                                evidence=evidence_pool,
                            )
                        except Exception as e:
                            err_msg = f"Proposal provider re-evaluation failed: {e}"
                            evt_err = self.event_bus.emit(
                                EventType.MODEL_PROVIDER_ERROR,
                                err_msg,
                                payload={"provider": provider_name, "model": model_name, "error": str(e)},
                            )
                            track(evt_err)
                            rec = _finalize_record(DecisionCategory.DENY, pol_dec=None, prop=None)
                            return RuntimeCycleResult(
                                intent=intent,
                                provider=provider_name,
                                model=model_name,
                                error=str(e),
                                decision_record=rec,
                                pre_state=pre_state,
                                post_state=self.world.get_state(),
                                events=cycle_events,
                                knowledge_evidence=retrieved_knowledge,
                                candidate_constraints=candidate_constraints,
                                active_constraints=active_constraints,
                                constraint_conflicts=conflict_reports,
                                evidence_action_ids=evidence_action_ids,
                                evidence_iterations=evidence_iterations,
                                predicted_information_gain=last_predicted_gain,
                                observed_information_gain=last_observed_gain,
                            )

                        decision = PolicyEngine.evaluate(
                            proposal=proposal,
                            world_state=pre_state,
                            evidence=evidence_pool,
                            policy=self.policy,
                            active_constraints=active_constraints,
                        )
                        evt_repol = self.event_bus.emit(
                            EventType.POLICY_EVALUATED,
                            f"Re-evaluation verdict with updated evidence: {decision.decision.value}",
                            payload=decision.model_dump(),
                        )
                        track(evt_repol)

                        if decision.is_allowed or decision.is_denied:
                            break
                    else:
                        break

                if decision.needs_evidence and evidence_iterations >= self.max_evidence_actions_per_cycle:
                    track(
                        self.event_bus.emit(
                            EventType.EVIDENCE_BUDGET_EXHAUSTED,
                            f"Evidence budget exhausted ({self.max_evidence_actions_per_cycle} iterations). Preserving safe NEED_MORE_EVIDENCE.",
                            payload={"budget": self.max_evidence_actions_per_cycle, "iterations": evidence_iterations},
                        )
                    )

                track(
                    self.event_bus.emit(
                        EventType.EVIDENCE_ACQUISITION_COMPLETED,
                        f"Evidence acquisition completed. Final verdict: {decision.decision.value}.",
                        payload={"verdict": decision.decision.value, "iterations": evidence_iterations},
                    )
                )

        # Handle DENY
        if decision.is_denied:
            evt_deny = self.event_bus.emit(
                EventType.ACTION_DENIED,
                f"Action {proposal.action_type.value} on {proposal.target} strictly DENIED by policy.",
                payload={"proposal_id": proposal.id, "reasons": [r.model_dump() for r in decision.reasons]},
            )
            track(evt_deny)
            rec = _finalize_record(DecisionCategory.DENY, pol_dec=decision, prop=proposal)
            return RuntimeCycleResult(
                intent=intent,
                provider=provider_name,
                model=model_name,
                proposal=proposal,
                policy_decision=decision,
                decision_record=rec,
                pre_state=pre_state,
                post_state=self.world.get_state(),
                events=cycle_events,
                knowledge_evidence=retrieved_knowledge,
                candidate_constraints=candidate_constraints,
                active_constraints=active_constraints,
                constraint_conflicts=conflict_reports,
                evidence_action_ids=evidence_action_ids,
                evidence_iterations=evidence_iterations,
                predicted_information_gain=last_predicted_gain,
                observed_information_gain=last_observed_gain,
            )

        # If still needing evidence, return without acting
        if decision.needs_evidence:
            rec = _finalize_record(DecisionCategory.NEED_MORE_EVIDENCE, pol_dec=decision, prop=proposal)
            return RuntimeCycleResult(
                intent=intent,
                provider=provider_name,
                model=model_name,
                proposal=proposal,
                policy_decision=decision,
                decision_record=rec,
                pre_state=pre_state,
                post_state=self.world.get_state(),
                events=cycle_events,
                knowledge_evidence=retrieved_knowledge,
                candidate_constraints=candidate_constraints,
                active_constraints=active_constraints,
                constraint_conflicts=conflict_reports,
                evidence_action_ids=evidence_action_ids,
                evidence_iterations=evidence_iterations,
                predicted_information_gain=last_predicted_gain,
                observed_information_gain=last_observed_gain,
            )

        # 6. Safety Enclave Evaluation & Authorization Ticket Minting (Only on ALLOW)
        enclave_req = EnclaveAuthorizationRequest(
            proposal=proposal,
            world_state=pre_state,
            evidence=evidence_pool,
            policy=self.policy,
            active_constraints=active_constraints,
        )
        enclave_result = self.safety_enclave.authorize(enclave_req)
        ticket = enclave_result.ticket
        if ticket:
            evt_auth = self.event_bus.emit(
                EventType.ACTION_AUTHORIZED,
                f"Action authorized! Safety Enclave minted ticket {ticket.ticket_id} for {proposal.target}.",
                payload=ticket.model_dump(),
            )
            track(evt_auth)

        # 7. Execution-Time Revalidation & Actuator Execution (Strictly requiring valid ticket)
        reval_status_val: Optional[str] = None
        reval_reasons_val: List[str] = []
        exec_version_val: int = self.world.get_state().version
        exec_hash_val: str = compute_world_state_hash(self.world.get_state())
        hw_record: Optional[HardwareExecutionRecord] = None

        if ticket and enclave_result.authorization_context:
            track(self.event_bus.emit(
                EventType.TICKET_REVALIDATION_STARTED,
                f"Starting execution-time revalidation for ticket {ticket.ticket_id}.",
                payload={"ticket_id": ticket.ticket_id, "expected_version": ticket.world_state_version, "observed_version": exec_version_val},
            ))

            current_ws = self.world.get_state()
            reval_res = ExecutionTimeRevalidator.revalidate(
                authorization_context=enclave_result.authorization_context,
                current_world_state=current_ws,
                current_policy_version=getattr(self.policy, "version", "1.0.0"),
                current_constraints=active_constraints,
                current_evidence=evidence_pool,
                ticket_expires_at=ticket.expires_at,
                proposal_action_type=proposal.action_type,
                proposal_target=proposal.target,
            )
            reval_status_val = reval_res.status.value
            reval_reasons_val = reval_res.reasons

            if reval_res.status == RevalidationStatus.VALID:
                track(self.event_bus.emit(
                    EventType.TICKET_REVALIDATION_PASSED,
                    f"Execution-time revalidation passed for ticket {ticket.ticket_id}.",
                    payload=reval_res.model_dump(),
                ))
                hw_record = self.hardware_endpoint.receive_and_actuate(proposal=proposal, ticket=ticket)
                execution = ExecutionResult(
                    success=(hw_record.execution_status == HardwareExecutionStatus.ACTUATED),
                    action_id=proposal.id,
                    ticket_id=ticket.ticket_id,
                    executed_action=proposal.action_type,
                    target=proposal.target,
                    message=hw_record.message,
                    state_version_before=exec_version_val,
                    state_version_after=self.world.version,
                    timestamp=hw_record.timestamp,
                )
            else:
                track(self.event_bus.emit(
                    EventType.TICKET_REVALIDATION_FAILED,
                    f"Execution-time revalidation failed ({reval_res.status.value}): {'; '.join(reval_res.reasons)}",
                    payload=reval_res.model_dump(),
                ))

                if reval_res.status == RevalidationStatus.WORLD_STATE_CHANGED:
                    track(self.event_bus.emit(
                        EventType.WORLD_STATE_DRIFT_DETECTED,
                        f"World state drift detected before execution: expected v{ticket.world_state_version}, observed v{exec_version_val}.",
                        payload=reval_res.model_dump(),
                    ))
                elif reval_res.status == RevalidationStatus.POLICY_CHANGED:
                    track(self.event_bus.emit(
                        EventType.POLICY_DRIFT_DETECTED,
                        "Policy drift detected before execution.",
                        payload=reval_res.model_dump(),
                    ))
                elif reval_res.status == RevalidationStatus.CONSTRAINT_CHANGED:
                    track(self.event_bus.emit(
                        EventType.CONSTRAINT_DRIFT_DETECTED,
                        "Constraint drift detected before execution.",
                        payload=reval_res.model_dump(),
                    ))
                elif reval_res.status == RevalidationStatus.EVIDENCE_CHANGED:
                    track(self.event_bus.emit(
                        EventType.EVIDENCE_DRIFT_DETECTED,
                        "Evidence drift detected before execution.",
                        payload=reval_res.model_dump(),
                    ))

                track(self.event_bus.emit(
                    EventType.TICKET_INVALIDATED,
                    f"Ticket {ticket.ticket_id} invalidated due to {reval_res.status.value}. Actuation aborted.",
                    payload={"ticket_id": ticket.ticket_id, "status": reval_res.status.value},
                ))

                # Do NOT execute physical actuation!
                execution = ExecutionResult(
                    success=False,
                    action_id=proposal.id,
                    ticket_id=ticket.ticket_id,
                    executed_action=proposal.action_type,
                    target=proposal.target,
                    message=f"Actuation aborted: Execution-time revalidation failed ({reval_res.status.value}).",
                    state_version_before=pre_state.version,
                    state_version_after=self.world.get_state().version,
                    timestamp=time.time(),
                )
        else:
            execution = self.actuator.execute(proposal=proposal, ticket=ticket)

        evt_exec = self.event_bus.emit(
            EventType.ACTION_EXECUTED,
            f"Actuator execution completed (success={execution.success}): {execution.message}",
            payload=execution.model_dump(),
        )
        track(evt_exec)

        # 8. Post-Action State Observation & Verification
        post_state = self.world.get_state()
        verification = PostActionVerifier.verify(
            proposal=proposal,
            execution=execution,
            pre_state=pre_state,
            post_state=post_state,
            expected_postconditions=self.policy.expected_postconditions,
        )

        if verification.is_verified:
            evt_ver = self.event_bus.emit(
                EventType.POSTCONDITION_VERIFIED,
                f"Physical postconditions verified successfully for {proposal.target}.",
                payload=verification.model_dump(),
            )
        else:
            evt_ver = self.event_bus.emit(
                EventType.POSTCONDITION_FAILED,
                f"Verification failed: {'; '.join(verification.discrepancies)}",
                payload=verification.model_dump(),
            )
        track(evt_ver)

        if not execution.success:
            verdict_cat = DecisionCategory.EXECUTION_FAILED
        elif not verification.is_verified:
            verdict_cat = DecisionCategory.VERIFICATION_FAILED
        else:
            verdict_cat = DecisionCategory.ALLOW

        rec = _finalize_record(
            cat=verdict_cat,
            pol_dec=decision,
            tkt=ticket,
            exec_res=execution,
            verif_res=verification,
            prop=proposal,
            reval_status=reval_status_val,
            reval_reasons=reval_reasons_val,
            exec_version=exec_version_val,
            exec_hash=exec_hash_val,
            hw_rec=hw_record,
        )

        return RuntimeCycleResult(
            intent=intent,
            provider=provider_name,
            model=model_name,
            proposal=proposal,
            policy_decision=decision,
            ticket=ticket,
            execution_result=execution,
            verification_result=verification,
            hardware_execution=hw_record,
            decision_record=rec,
            pre_state=pre_state,
            post_state=post_state,
            events=cycle_events,
            knowledge_evidence=retrieved_knowledge,
            candidate_constraints=candidate_constraints,
            active_constraints=active_constraints,
            constraint_conflicts=conflict_reports,
            evidence_action_ids=evidence_action_ids,
            evidence_iterations=evidence_iterations,
            predicted_information_gain=last_predicted_gain,
            observed_information_gain=last_observed_gain,
        )
