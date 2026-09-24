"""DecisionReplayEngine: Offline, deterministic replay and divergence verification."""

from enum import Enum
from typing import Any, Dict, List, Optional
from pydantic import BaseModel, Field

from motionfence.audit.models import DecisionRecord, DecisionCategory, ExecutionMode
from motionfence.models.actions import ActionProposal
from motionfence.evidence.models import Evidence
from motionfence.constraints.models import CandidateConstraint
from motionfence.policy.models import Policy, PolicyDecision, DecisionType
from motionfence.policy.engine import PolicyEngine
from motionfence.runtime.events import EventBus
from motionfence.models.events import EventType


class ReplayStatus(str, Enum):
    """Result of comparing replayed deterministic policy evaluation against historical record."""
    REPLAY_MATCH = "REPLAY_MATCH"              # Replayed policy verdict matches recorded verdict
    REPLAY_DIVERGENCE = "REPLAY_DIVERGENCE"    # Replayed evaluation diverged from recorded verdict
    REPLAY_ERROR = "REPLAY_ERROR"              # Replay execution failed due to invalid data


class ReplayStep(BaseModel):
    """Individual reconstructed lifecycle phase in the 10-step authorization control loop."""
    step_number: int
    step_name: str
    summary: str
    details: Dict[str, Any] = Field(default_factory=dict)


class ReplayReport(BaseModel):
    """Complete diagnostic result of a deterministic replay evaluation."""
    decision_id: str
    status: ReplayStatus
    recorded_verdict: str
    replayed_verdict: str
    steps: List[ReplayStep] = Field(default_factory=list)
    replayed_decision: Optional[PolicyDecision] = None
    divergence_reasons: List[str] = Field(default_factory=list)
    revalidation_verdict: Optional[str] = None
    execution_mode: ExecutionMode = ExecutionMode.REPLAY

    @property
    def is_match(self) -> bool:
        return self.status == ReplayStatus.REPLAY_MATCH


class DecisionReplayEngine:
    """Offline, deterministic replay engine for MotionFence authorization decisions.
    
    SECURITY INVARIANTS:
    1. Replay can mutate WorldState = NO
    2. Replay can mint AuthorizationTicket = NO
    3. Replay can call actuator = NO
    4. Replay can call Tavily = NO
    5. Replay can call Nemotron = NO
    6. Operates strictly from recorded data; 100% offline.
    """

    def __init__(self, event_bus: Optional[EventBus] = None) -> None:
        self.event_bus = event_bus

    def replay(
        self,
        record: DecisionRecord,
        custom_policy: Optional[Policy] = None,
    ) -> ReplayReport:
        """Replay a recorded decision from its immutable snapshot and verify deterministic convergence."""
        if self.event_bus:
            self.event_bus.emit(
                EventType.DECISION_REPLAYED,
                f"Initiating offline deterministic replay of decision '{record.decision_id}'.",
                payload={"decision_id": record.decision_id},
            )

        steps: List[ReplayStep] = []
        snaps = record.snapshots or {}

        # [01] INTENT
        steps.append(
            ReplayStep(
                step_number=1,
                step_name="INTENT",
                summary=record.intent,
                details={"intent": record.intent},
            )
        )

        # [02] WORLD STATE
        steps.append(
            ReplayStep(
                step_number=2,
                step_name="WORLD STATE",
                summary=f"Cooling={record.world_state_snapshot.cooling.value}, Leak={record.world_state_snapshot.leak.active}, Human={record.world_state_snapshot.human_zone.value}",
                details=record.world_state_snapshot.model_dump(),
            )
        )

        # [03] EVIDENCE
        ev_list: List[Evidence] = []
        for e in snaps.get("evidence", []):
            try:
                ev_list.append(Evidence.model_validate(e))
            except Exception:
                continue
        ev_summary = f"{len(ev_list)} physical sensor observation(s) reconstructed."
        if record.evidence_acquisition_iterations > 0:
            ev_summary += f" ({record.evidence_acquisition_iterations} active information action(s) executed: {', '.join(record.evidence_action_ids)})."

        steps.append(
            ReplayStep(
                step_number=3,
                step_name="EVIDENCE",
                summary=ev_summary,
                details={
                    "evidence": [e.model_dump() for e in ev_list],
                    "evidence_action_ids": record.evidence_action_ids,
                    "iterations": record.evidence_acquisition_iterations,
                    "budget": record.evidence_budget,
                    "predicted_gain": record.predicted_information_gain,
                    "observed_gain": record.observed_information_gain,
                },
            )
        )

        # [04] SOURCE TRUST
        source_ass = snaps.get("source_assessments", [])
        steps.append(
            ReplayStep(
                step_number=4,
                step_name="SOURCE TRUST",
                summary=f"{len(source_ass)} source assessment(s) replayed.",
                details={"assessments": source_ass},
            )
        )

        # [05] CLAIM GROUNDING
        certs = snaps.get("certificates", [])
        cert_types = [c.get("support_type") for c in certs if isinstance(c, dict)]
        steps.append(
            ReplayStep(
                step_number=5,
                step_name="CLAIM GROUNDING",
                summary=f"{len(certs)} certificate(s) replayed (types={cert_types}).",
                details={"certificates": certs},
            )
        )

        # [06] CONSTRAINTS
        active_constraints: List[CandidateConstraint] = []
        for c in snaps.get("active_constraints", []):
            try:
                active_constraints.append(CandidateConstraint.model_validate(c))
            except Exception:
                continue
        steps.append(
            ReplayStep(
                step_number=6,
                step_name="CONSTRAINTS",
                summary=f"{len(active_constraints)} active operational constraint(s) replayed.",
                details={"active_constraints": [c.model_dump() for c in active_constraints]},
            )
        )

        # [07] POLICY EVALUATION (Deterministic Re-Execution)
        eval_policy = custom_policy or Policy()
        replayed_decision: Optional[PolicyDecision] = None
        divergence_reasons: List[str] = []

        if record.action_proposal is not None:
            # Re-evaluate policy deterministically WITHOUT calling any LLM or network
            replayed_decision = PolicyEngine.evaluate(
                proposal=record.action_proposal,
                world_state=record.world_state_snapshot,
                evidence=ev_list,
                policy=eval_policy,
                active_constraints=active_constraints,
            )
            replayed_verdict_str = replayed_decision.decision.value
        else:
            replayed_verdict_str = record.policy_decision.value

        steps.append(
            ReplayStep(
                step_number=7,
                step_name="POLICY",
                summary=f"Replayed policy verdict: {replayed_verdict_str}",
                details=replayed_decision.model_dump() if replayed_decision else {},
            )
        )

        # [08] AUTHORIZATION
        steps.append(
            ReplayStep(
                step_number=8,
                step_name="AUTHORIZATION",
                summary=f"Ticket: {record.authorization_ticket_id or 'NOT CREATED'} (Replay mints 0 tickets).",
                details={"authorization_ticket_id": record.authorization_ticket_id},
            )
        )

        # [09] EXECUTION & REVALIDATION RECONSTRUCTION
        reval_verdict: Optional[str] = None
        if record.ticket_world_state_version is not None and record.execution_context_version is not None:
            if record.ticket_world_state_version != record.execution_context_version:
                reval_verdict = "TICKET_REVALIDATION_FAILED"
                if self.event_bus:
                    self.event_bus.emit(
                        EventType.TICKET_REVALIDATION_FAILED,
                        f"Replay detected TOCTOU drift for decision '{record.decision_id}': "
                        f"issuance v{record.ticket_world_state_version} != execution v{record.execution_context_version}.",
                        payload={
                            "decision_id": record.decision_id,
                            "issuance_version": record.ticket_world_state_version,
                            "execution_version": record.execution_context_version,
                        },
                    )
            elif record.revalidation_status:
                reval_verdict = f"TICKET_REVALIDATION_{record.revalidation_status}"
            else:
                reval_verdict = "TICKET_REVALIDATION_PASSED"
        elif record.revalidation_status:
            reval_verdict = f"TICKET_REVALIDATION_{record.revalidation_status}"

        steps.append(
            ReplayStep(
                step_number=9,
                step_name="EXECUTION",
                summary=(
                    f"Execution recorded: {record.execution_result.success if record.execution_result else 'NOT APPLICABLE'}"
                    + (f" | Revalidation: {reval_verdict}" if reval_verdict else "")
                    + " (Replay acts on 0 physical systems)."
                ),
                details={
                    "execution_result": record.execution_result.model_dump() if record.execution_result else {},
                    "revalidation_status": record.revalidation_status,
                    "revalidation_verdict": reval_verdict,
                    "ticket_world_state_version": record.ticket_world_state_version,
                    "execution_context_version": record.execution_context_version,
                },
            )
        )

        # [10] VERIFICATION
        steps.append(
            ReplayStep(
                step_number=10,
                step_name="VERIFICATION",
                summary=f"Verification recorded: {record.verification_result.is_verified if record.verification_result else 'NOT APPLICABLE'}",
                details=record.verification_result.model_dump() if record.verification_result else {},
            )
        )

        # Compare Replayed vs Recorded
        recorded_val = record.policy_decision.value
        if replayed_verdict_str == recorded_val:
            status = ReplayStatus.REPLAY_MATCH
            if self.event_bus:
                self.event_bus.emit(
                    EventType.REPLAY_MATCH,
                    f"Replay MATCH for decision '{record.decision_id}': verdict={recorded_val}.",
                    payload={"decision_id": record.decision_id, "verdict": recorded_val},
                )
        else:
            status = ReplayStatus.REPLAY_DIVERGENCE
            divergence_reasons.append(
                f"Replay verdict '{replayed_verdict_str}' diverged from recorded '{recorded_val}'."
            )
            if self.event_bus:
                self.event_bus.emit(
                    EventType.REPLAY_DIVERGENCE,
                    f"Replay DIVERGENCE for decision '{record.decision_id}': recorded={recorded_val}, replayed={replayed_verdict_str}.",
                    payload={"decision_id": record.decision_id, "recorded": recorded_val, "replayed": replayed_verdict_str},
                )

        return ReplayReport(
            decision_id=record.decision_id,
            status=status,
            recorded_verdict=recorded_val,
            replayed_verdict=replayed_verdict_str,
            steps=steps,
            replayed_decision=replayed_decision,
            divergence_reasons=divergence_reasons,
            revalidation_verdict=reval_verdict,
            execution_mode=ExecutionMode.REPLAY,
        )
