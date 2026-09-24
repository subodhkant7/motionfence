"""DecisionRecorder: Manages immutable, hash-linked DecisionRecord creation and chain persistence."""

import json
import os
from typing import Any, Dict, List, Optional
from pydantic import BaseModel

from motionfence.audit.models import DecisionRecord, DecisionCategory
from motionfence.audit.serialization import compute_record_hash
from motionfence.runtime.events import EventBus
from motionfence.models.events import EventType


class DecisionRecorder:
    """Manages the creation, cryptographic hashing, and persistence of DecisionRecords.
    
    SECURITY INVARIANTS:
    1. Every record is hash-linked to its predecessor: Hash(N) = SHA256(Record(N) + Hash(N-1)).
    2. Finalized records cannot be modified.
    3. Emits auditable runtime events throughout the lifecycle.
    """

    def __init__(
        self,
        event_bus: Optional[EventBus] = None,
        storage_dir: Optional[str] = None,
    ) -> None:
        self.event_bus = event_bus
        self.storage_dir = storage_dir
        self._chain: List[DecisionRecord] = []
        self._index: Dict[str, DecisionRecord] = {}

        if self.storage_dir:
            os.makedirs(self.storage_dir, exist_ok=True)
            self._load_from_storage()

    def get_latest_hash(self) -> Optional[str]:
        """Return the record_hash of the most recently finalized record in the chain."""
        if not self._chain:
            return None
        return self._chain[-1].record_hash

    def create_record(
        self,
        intent: str,
        world_state_snapshot: Any,
        policy_decision: DecisionCategory,
        policy_reasons: Optional[List[str]] = None,
        action_proposal: Optional[Any] = None,
        sensor_evidence: Optional[List[Any]] = None,
        knowledge_evidence: Optional[List[Any]] = None,
        source_assessments: Optional[List[Any]] = None,
        certificates: Optional[List[Any]] = None,
        candidate_constraints: Optional[List[Any]] = None,
        active_constraints: Optional[List[Any]] = None,
        authorization_ticket_id: Optional[str] = None,
        execution_result: Optional[Any] = None,
        verification_result: Optional[Any] = None,
        provider_metadata: Optional[Dict[str, Any]] = None,
        policy_version: str = "1.0.0",
        runtime_version: str = "2.4.0",
    ) -> DecisionRecord:
        """Construct an unfinalized DecisionRecord capturing the complete evaluation context."""
        sensor_evidence = sensor_evidence or []
        knowledge_evidence = knowledge_evidence or []
        source_assessments = source_assessments or []
        certificates = certificates or []
        candidate_constraints = candidate_constraints or []
        active_constraints = active_constraints or []

        # Snapshots enable 100% self-contained offline replay without external databases
        snapshots: Dict[str, Any] = {
            "evidence": [e.model_dump() if hasattr(e, "model_dump") else e for e in sensor_evidence],
            "knowledge": [k.model_dump() if hasattr(k, "model_dump") else k for k in knowledge_evidence],
            "source_assessments": [a.model_dump() if hasattr(a, "model_dump") else a for a in source_assessments],
            "certificates": [c.model_dump() if hasattr(c, "model_dump") else c for c in certificates],
            "candidate_constraints": [c.model_dump() if hasattr(c, "model_dump") else c for c in candidate_constraints],
            "active_constraints": [c.model_dump() if hasattr(c, "model_dump") else c for c in active_constraints],
        }

        record = DecisionRecord(
            sequence_number=len(self._chain),
            intent=intent,
            world_state_snapshot=world_state_snapshot,
            sensor_evidence_ids=[getattr(e, "id", str(idx)) for idx, e in enumerate(sensor_evidence)],
            knowledge_evidence_ids=[getattr(k, "id", str(idx)) for idx, k in enumerate(knowledge_evidence)],
            source_assessment_ids=[getattr(a, "evidence_id", str(idx)) for idx, a in enumerate(source_assessments)],
            claim_support_certificate_ids=[getattr(c, "certificate_id", str(idx)) for idx, c in enumerate(certificates)],
            candidate_constraint_ids=[getattr(c, "constraint_id", str(idx)) for idx, c in enumerate(candidate_constraints)],
            active_constraint_ids=[getattr(c, "constraint_id", str(idx)) for idx, c in enumerate(active_constraints)],
            action_proposal=action_proposal,
            policy_decision=policy_decision,
            policy_reasons=policy_reasons or [],
            authorization_ticket_id=authorization_ticket_id,
            execution_result=execution_result,
            verification_result=verification_result,
            runtime_version=runtime_version,
            policy_version=policy_version,
            provider_metadata=provider_metadata or {},
            snapshots=snapshots,
        )

        if self.event_bus:
            self.event_bus.emit(
                EventType.DECISION_CREATED,
                f"DecisionRecord '{record.decision_id}' created for intent '{intent[:40]}...'.",
                payload={"decision_id": record.decision_id, "verdict": policy_decision.value},
            )

        return record

    def finalize_record(self, record: DecisionRecord) -> DecisionRecord:
        """Cryptographically sign, link, and permanently store a DecisionRecord."""
        if record.is_finalized:
            return record

        prev_hash = self.get_latest_hash()
        record_hash = compute_record_hash(record.model_dump(mode="json"), prev_hash)
        record.mark_finalized(record_hash=record_hash, previous_record_hash=prev_hash)

        self._chain.append(record)
        self._index[record.decision_id] = record

        if self.event_bus:
            self.event_bus.emit(
                EventType.DECISION_HASHED,
                f"DecisionRecord '{record.decision_id}' hashed: {record_hash[:16]}... (prev={str(prev_hash)[:16]}).",
                payload={"decision_id": record.decision_id, "hash": record_hash, "prev_hash": prev_hash},
            )
            self.event_bus.emit(
                EventType.DECISION_FINALIZED,
                f"DecisionRecord '{record.decision_id}' finalized at sequence #{record.sequence_number}.",
                payload={"decision_id": record.decision_id, "sequence": record.sequence_number},
            )

        if self.storage_dir:
            self._save_record_to_storage(record)

        return record

    def get_record(self, decision_id: str) -> Optional[DecisionRecord]:
        """Lookup a finalized record by ID."""
        return self._index.get(decision_id)

    def get_all_records(self) -> List[DecisionRecord]:
        """Return the chronological audit chain."""
        return list(self._chain)

    def _save_record_to_storage(self, record: DecisionRecord) -> None:
        """Persist a single record as JSON in storage_dir."""
        if not self.storage_dir:
            return
        filename = f"{record.sequence_number:06d}_{record.decision_id}.json"
        filepath = os.path.join(self.storage_dir, filename)
        with open(filepath, "w", encoding="utf-8") as f:
            f.write(record.model_dump_json(indent=2))

    def _load_from_storage(self) -> None:
        """Load and index existing records from storage_dir."""
        if not self.storage_dir or not os.path.isdir(self.storage_dir):
            return
        files = sorted(f for f in os.listdir(self.storage_dir) if f.endswith(".json"))
        for fname in files:
            path = os.path.join(self.storage_dir, fname)
            try:
                with open(path, "r", encoding="utf-8") as f:
                    rec = DecisionRecord.model_validate_json(f.read())
                self._chain.append(rec)
                self._index[rec.decision_id] = rec
            except Exception:
                continue
