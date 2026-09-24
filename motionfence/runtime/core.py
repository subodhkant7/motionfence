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


class RuntimeCycleResult(BaseModel):
    """Auditable summary of an entire Observe-Propose-Authorize-Act-Verify cycle."""
    intent: str
    proposal: Optional[ActionProposal] = None
    policy_decision: Optional[PolicyDecision] = None
    ticket: Optional[AuthorizationTicket] = None
    execution_result: Optional[ExecutionResult] = None
    verification_result: Optional[VerificationResult] = None
    pre_state: WorldState
    post_state: WorldState
    events: List[RuntimeEvent] = Field(default_factory=list)

    @property
    def is_success(self) -> bool:
        """True if the cycle resulted in an authorized, executed, and verified outcome."""
        return (
            self.policy_decision is not None
            and self.policy_decision.is_allowed
            and self.verification_result is not None
            and self.verification_result.is_verified
        )


class MotionFenceRuntime:
    """The central runtime authorization layer governing physical AI actions.
    
    Coordinates the strictly ordered control loop:
    Observe → Propose → Evaluate Policy → Allow / Deny / Need Evidence → Act → Verify
    """

    def __init__(
        self,
        world: Optional[PhysicalWorld] = None,
        actuator: Optional[PhysicalActuator] = None,
        proposal_provider: Optional[ActionProposalProvider] = None,
        policy: Optional[Policy] = None,
        secret_key: str = "motionfence_runtime_kernel_secret",
    ) -> None:
        self.world = world or PhysicalWorld()
        self.actuator = actuator or PhysicalActuator(self.world, secret_key=secret_key)
        self.proposal_provider = proposal_provider or LocalDeterministicProvider()
        self.policy = policy or Policy()
        self.ticket_authority = TicketAuthority(secret_key=secret_key)
        self.event_bus = EventBus()

    def run_cycle(
        self,
        intent: str,
        initial_evidence: Optional[List[Evidence]] = None,
        gather_additional_evidence_on_request: bool = False,
    ) -> RuntimeCycleResult:
        """Execute a single deterministic control loop."""
        cycle_events: List[RuntimeEvent] = []

        def track(evt: RuntimeEvent) -> None:
            cycle_events.append(evt)

        # 1. Intent Received
        evt_intent = self.event_bus.emit(
            EventType.INTENT_RECEIVED,
            f"Human intent received: '{intent}'",
            payload={"intent": intent},
        )
        track(evt_intent)

        # 2. Observe initial physical world state
        pre_state = self.world.get_state()
        evidence_pool = list(initial_evidence) if initial_evidence is not None else self.world.generate_initial_ambiguous_evidence()

        evt_obs = self.event_bus.emit(
            EventType.OBSERVATION_RECORDED,
            f"Recorded {len(evidence_pool)} physical sensor observations.",
            payload={"evidence_count": len(evidence_pool), "world_version": pre_state.version},
        )
        track(evt_obs)

        # 3. Propose action via agent provider
        proposal = self.proposal_provider.propose(
            intent=intent,
            world_state=pre_state,
            evidence=evidence_pool,
        )
        evt_prop = self.event_bus.emit(
            EventType.ACTION_PROPOSED,
            f"Agent proposed {proposal.action_type.value} on {proposal.target} (conf={proposal.model_confidence:.2f})",
            payload=proposal.model_dump(),
        )
        track(evt_prop)

        # 4. Deterministic Policy Evaluation
        decision = PolicyEngine.evaluate(
            proposal=proposal,
            world_state=pre_state,
            evidence=evidence_pool,
            policy=self.policy,
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
                proposal = self.proposal_provider.propose(
                    intent=intent,
                    world_state=pre_state,
                    evidence=evidence_pool,
                )
                decision = PolicyEngine.evaluate(
                    proposal=proposal,
                    world_state=pre_state,
                    evidence=evidence_pool,
                    policy=self.policy,
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
                proposal=proposal,
                policy_decision=decision,
                pre_state=pre_state,
                post_state=self.world.get_state(),
                events=cycle_events,
            )

        # If still needing evidence, return without acting
        if decision.needs_evidence:
            return RuntimeCycleResult(
                intent=intent,
                proposal=proposal,
                policy_decision=decision,
                pre_state=pre_state,
                post_state=self.world.get_state(),
                events=cycle_events,
            )

        # 5. Authorization Ticket Minting (Only on ALLOW)
        ticket = self.ticket_authority.mint_ticket(proposal=proposal)
        evt_auth = self.event_bus.emit(
            EventType.ACTION_AUTHORIZED,
            f"Action authorized! Minted ticket {ticket.ticket_id} for {proposal.target}.",
            payload=ticket.model_dump(),
        )
        track(evt_auth)

        # 6. Actuator Execution (Strictly requiring ticket)
        execution = self.actuator.execute(proposal=proposal, ticket=ticket)
        evt_exec = self.event_bus.emit(
            EventType.ACTION_EXECUTED,
            f"Actuator execution completed (success={execution.success}): {execution.message}",
            payload=execution.model_dump(),
        )
        track(evt_exec)

        # 7. Post-Action State Observation & Verification
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
            proposal=proposal,
            policy_decision=decision,
            ticket=ticket,
            execution_result=execution,
            verification_result=verification,
            pre_state=pre_state,
            post_state=post_state,
            events=cycle_events,
        )
