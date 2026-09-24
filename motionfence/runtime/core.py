"""MotionFence Runtime Core: Deterministic control loop orchestrator."""

from typing import Any, Dict, List, Optional
import time
from pydantic import BaseModel, Field

from motionfence.models.actions import (
    ActionProposal,
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

# Knowledge and constraints integrations (Phase 2A)
from motionfence.knowledge.models import KnowledgeEvidence
from motionfence.knowledge.retrieval import KnowledgeRetrievalService
from motionfence.constraints.models import CandidateConstraint, ConstraintConflictReport, ConstraintStatus
from motionfence.constraints.extractor import ConstraintExtractor
from motionfence.constraints.validator import ConstraintValidator
from motionfence.constraints.conflict import ConstraintConflictDetector


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
    pre_state: WorldState
    post_state: WorldState
    events: List[RuntimeEvent] = Field(default_factory=list)

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
        secret_key: str = "motionfence_runtime_kernel_secret",
    ) -> None:
        self.world = world or PhysicalWorld()
        self.actuator = actuator or PhysicalActuator(self.world, secret_key=secret_key)
        self.proposal_provider = proposal_provider or LocalDeterministicProvider()
        self.policy = policy or Policy()
        self.knowledge_service = knowledge_service
        self.constraint_extractor = constraint_extractor
        self.ticket_authority = TicketAuthority(secret_key=secret_key)
        self.event_bus = EventBus()

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
    ) -> RuntimeCycleResult:
        """Execute a single deterministic control loop."""
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
                candidate_constraints = self.constraint_extractor.extract(retrieved_knowledge)
                for cst in candidate_constraints:
                    track(
                        self.event_bus.emit(
                            EventType.CONSTRAINT_CANDIDATE_CREATED,
                            f"Extracted candidate constraint '{cst.constraint_id}' ({cst.constraint_type.value}) for {cst.target}.",
                            payload=cst.model_dump(),
                        )
                    )

                    # Deterministic Validation and Promotion
                    evidence_reg = self.knowledge_service._evidence_registry
                    promoted = ConstraintValidator.promote_to_active(cst, evidence_reg, self.event_bus)
                    if promoted.is_active or promoted.status == ConstraintStatus.STALE:
                        active_constraints.append(promoted)

                # Check for conflicts among all constraints
                conflict_reports = ConstraintConflictDetector.detect_conflicts(
                    candidate_constraints + active_constraints,
                    self.event_bus
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
            return RuntimeCycleResult(
                intent=intent,
                provider=provider_name,
                model=model_name,
                error=str(e),
                pre_state=pre_state,
                post_state=self.world.get_state(),
                events=cycle_events,
                knowledge_evidence=retrieved_knowledge,
                candidate_constraints=candidate_constraints,
                active_constraints=active_constraints,
                constraint_conflicts=conflict_reports,
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

        # Handle NEED_MORE_EVIDENCE with optional iterative evidence gathering
        if decision.needs_evidence:
            evt_need = self.event_bus.emit(
                EventType.MORE_EVIDENCE_REQUIRED,
                f"Action deferred: more evidence required for target '{proposal.target}'.",
                payload={"target": proposal.target, "reasons": [r.model_dump() for r in decision.reasons]},
            )
            track(evt_need)

            if gather_additional_evidence_on_request:
                # Targeted inspection triggered deterministically
                targeted_evidence = self.world.generate_targeted_evidence(proposal.target)
                evidence_pool.extend(targeted_evidence)

                evt_more_obs = self.event_bus.emit(
                    EventType.OBSERVATION_RECORDED,
                    f"Gathered {len(targeted_evidence)} targeted sensor observations for {proposal.target}.",
                    payload={"target": proposal.target, "additional_count": len(targeted_evidence)},
                )
                track(evt_more_obs)

                # Re-propose with refined evidence
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
                    return RuntimeCycleResult(
                        intent=intent,
                        provider=provider_name,
                        model=model_name,
                        error=str(e),
                        pre_state=pre_state,
                        post_state=self.world.get_state(),
                        events=cycle_events,
                        knowledge_evidence=retrieved_knowledge,
                        candidate_constraints=candidate_constraints,
                        active_constraints=active_constraints,
                        constraint_conflicts=conflict_reports,
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

        # Handle DENY
        if decision.is_denied:
            evt_deny = self.event_bus.emit(
                EventType.ACTION_DENIED,
                f"Action {proposal.action_type.value} on {proposal.target} strictly DENIED by policy.",
                payload={"proposal_id": proposal.id, "reasons": [r.model_dump() for r in decision.reasons]},
            )
            track(evt_deny)
            return RuntimeCycleResult(
                intent=intent,
                provider=provider_name,
                model=model_name,
                proposal=proposal,
                policy_decision=decision,
                pre_state=pre_state,
                post_state=self.world.get_state(),
                events=cycle_events,
                knowledge_evidence=retrieved_knowledge,
                candidate_constraints=candidate_constraints,
                active_constraints=active_constraints,
                constraint_conflicts=conflict_reports,
            )

        # If still needing evidence, return without acting
        if decision.needs_evidence:
            return RuntimeCycleResult(
                intent=intent,
                provider=provider_name,
                model=model_name,
                proposal=proposal,
                policy_decision=decision,
                pre_state=pre_state,
                post_state=self.world.get_state(),
                events=cycle_events,
                knowledge_evidence=retrieved_knowledge,
                candidate_constraints=candidate_constraints,
                active_constraints=active_constraints,
                constraint_conflicts=conflict_reports,
            )

        # 6. Authorization Ticket Minting (Only on ALLOW)
        ticket = self.ticket_authority.mint_ticket(proposal=proposal)
        evt_auth = self.event_bus.emit(
            EventType.ACTION_AUTHORIZED,
            f"Action authorized! Minted ticket {ticket.ticket_id} for {proposal.target}.",
            payload=ticket.model_dump(),
        )
        track(evt_auth)

        # 7. Actuator Execution (Strictly requiring ticket)
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

        return RuntimeCycleResult(
            intent=intent,
            provider=provider_name,
            model=model_name,
            proposal=proposal,
            policy_decision=decision,
            ticket=ticket,
            execution_result=execution,
            verification_result=verification,
            pre_state=pre_state,
            post_state=post_state,
            events=cycle_events,
            knowledge_evidence=retrieved_knowledge,
            candidate_constraints=candidate_constraints,
            active_constraints=active_constraints,
            constraint_conflicts=conflict_reports,
        )
