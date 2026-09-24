"""DecisionRecordVerifier: Audits canonical hashes, chain integrity, and reference consistency."""

from typing import List, Optional
from pydantic import BaseModel, Field

from motionfence.audit.models import DecisionRecord, DecisionCategory
from motionfence.audit.serialization import compute_record_hash
from motionfence.runtime.events import EventBus
from motionfence.models.events import EventType


class IntegrityReport(BaseModel):
    """Auditable result of a decision integrity verification check."""
    decision_id: str
    is_valid: bool
    hash_verified: bool
    chain_linked: bool
    policy_consistent: bool
    references_consistent: bool
    issues: List[str] = Field(default_factory=list)


class DecisionRecordVerifier:
    """Independent auditor verifying cryptographic integrity and reference consistency.
    
    SECURITY INVARIANTS:
    1. If any field or hash is tampered with, flags INTEGRITY_FAILURE.
    2. Does NOT silently repair corrupted or tampered records.
    """

    @classmethod
    def verify_record(
        cls,
        record: DecisionRecord,
        expected_prev_hash: Optional[str] = None,
        event_bus: Optional[EventBus] = None,
    ) -> IntegrityReport:
        """Verify an individual DecisionRecord's internal cryptographic and logical integrity."""
        issues: List[str] = []

        if not record.is_finalized or not record.record_hash:
            issues.append("Record is not finalized or is missing record_hash.")

        # 1. Canonical Hash Verification
        rec_dict = record.model_dump(mode="json")
        expected_hash = compute_record_hash(rec_dict, record.previous_record_hash)
        hash_verified = (expected_hash == record.record_hash)
        if not hash_verified:
            issues.append(f"Cryptographic hash mismatch: recorded={record.record_hash}, calculated={expected_hash}.")

        # 2. Previous Record Hash Linkage Check
        chain_linked = True
        if expected_prev_hash is not None and record.previous_record_hash != expected_prev_hash:
            chain_linked = False
            issues.append(f"Chain linkage mismatch: recorded prev_hash={record.previous_record_hash}, expected={expected_prev_hash}.")

        # 3. Policy Decision & Ticket Association Consistency
        policy_consistent = True
        if record.policy_decision == DecisionCategory.ALLOW:
            # If allowed, authorization ticket should have been generated
            if not record.authorization_ticket_id:
                policy_consistent = False
                issues.append("Policy verdict is ALLOW but authorization_ticket_id is missing.")
        elif record.policy_decision in (DecisionCategory.DENY, DecisionCategory.NEED_MORE_EVIDENCE):
            # If denied or need more evidence, no ticket may exist
            if record.authorization_ticket_id is not None:
                policy_consistent = False
                issues.append(f"Policy verdict is {record.policy_decision.value} but authorization_ticket_id is present.")

        # If executed, verify proposal and ticket association
        if record.execution_result and record.action_proposal:
            exec_action_id = getattr(record.execution_result, "action_id", getattr(record.execution_result, "proposal_id", None))
            if exec_action_id != record.action_proposal.id:
                policy_consistent = False
                issues.append(f"Execution result action_id '{exec_action_id}' does not match action_proposal '{record.action_proposal.id}'.")
            if record.execution_result.ticket_id and record.execution_result.ticket_id != record.authorization_ticket_id:
                policy_consistent = False
                issues.append(f"Execution ticket_id '{record.execution_result.ticket_id}' does not match authorization_ticket_id '{record.authorization_ticket_id}'.")

        # 4. Reference Consistency against Snapshots
        references_consistent = True
        snaps = record.snapshots or {}

        if "evidence" in snaps:
            snap_ev_ids = {e.get("id") for e in snaps["evidence"] if isinstance(e, dict)}
            for ev_id in record.sensor_evidence_ids:
                if ev_id not in snap_ev_ids:
                    references_consistent = False
                    issues.append(f"Sensor evidence ID '{ev_id}' referenced in record is missing from snapshot.")

        if "active_constraints" in snaps:
            snap_cst_ids = {c.get("constraint_id") for c in snaps["active_constraints"] if isinstance(c, dict)}
            for cst_id in record.active_constraint_ids:
                if cst_id not in snap_cst_ids:
                    references_consistent = False
                    issues.append(f"Active constraint ID '{cst_id}' referenced in record is missing from snapshot.")

        is_valid = hash_verified and chain_linked and policy_consistent and references_consistent

        if not is_valid and event_bus:
            event_bus.emit(
                EventType.INTEGRITY_FAILURE,
                f"Integrity verification FAILED for decision '{record.decision_id}': {'; '.join(issues)}",
                payload={"decision_id": record.decision_id, "issues": issues},
            )

        return IntegrityReport(
            decision_id=record.decision_id,
            is_valid=is_valid,
            hash_verified=hash_verified,
            chain_linked=chain_linked,
            policy_consistent=policy_consistent,
            references_consistent=references_consistent,
            issues=issues,
        )

    @classmethod
    def verify_chain(
        cls,
        chain: List[DecisionRecord],
        event_bus: Optional[EventBus] = None,
    ) -> List[IntegrityReport]:
        """Verify the chronological audit chain of DecisionRecords from genesis to head."""
        reports: List[IntegrityReport] = []
        expected_prev_hash: Optional[str] = None

        for rec in chain:
            rep = cls.verify_record(rec, expected_prev_hash=expected_prev_hash, event_bus=event_bus)
            reports.append(rep)
            expected_prev_hash = rec.record_hash

        return reports
