"""Deterministic validator and promotion gate for candidate operational constraints."""

from typing import Dict, List, Optional
import time

from motionfence.constraints.models import (
    CandidateConstraint,
    ConstraintType,
    ConstraintStatus,
)
from motionfence.constraints.extractor import ConstraintValidationError
from motionfence.knowledge.models import KnowledgeEvidence, TrustStatus, FreshnessStatus
from motionfence.models.actions import ActionType
from motionfence.models.events import EventType
from motionfence.runtime.events import EventBus
from motionfence.config.settings import settings


class ConstraintValidator:
    """Deterministically verifies candidate constraint schemas, evidence links, and provenance."""

    @classmethod
    def validate(
        cls,
        constraint: CandidateConstraint,
        evidence_registry: Dict[str, KnowledgeEvidence],
        event_bus: Optional[EventBus] = None,
        max_age_seconds: Optional[float] = None,
    ) -> bool:
        """Independently verify candidate constraint against structural rules and evidence registry."""
        notes: List[str] = []
        is_valid = True

        # 1. Structural Schema Verification
        if not isinstance(constraint.constraint_type, ConstraintType):
            notes.append(f"Unknown constraint type: {constraint.constraint_type}")
            is_valid = False

        if constraint.action is not None and not isinstance(constraint.action, ActionType):
            notes.append(f"Unknown action: {constraint.action}")
            is_valid = False

        if not constraint.target or not isinstance(constraint.target, str):
            notes.append("Target must be a non-empty string.")
            is_valid = False

        if not isinstance(constraint.condition, dict):
            notes.append("Condition must be a dictionary.")
            is_valid = False

        if not (0.0 <= constraint.confidence <= 1.0):
            notes.append(f"Confidence {constraint.confidence} out of bounds [0.0, 1.0].")
            is_valid = False

        # 2. Strict Evidence Discipline & Provenance Verification
        source_ev = evidence_registry.get(constraint.source_evidence_id)
        if source_ev is None:
            notes.append(
                f"Unknown source evidence reference '{constraint.source_evidence_id}'. "
                "Every constraint must resolve to registered KnowledgeEvidence."
            )
            is_valid = False
        else:
            if not source_ev.provenance:
                notes.append("Referenced knowledge evidence is missing provenance attribution.")
                is_valid = False

            if source_ev.trust_status == TrustStatus.REJECTED:
                notes.append("Referenced knowledge evidence has trust_status=REJECTED.")
                is_valid = False

            # 3. Freshness Verification
            max_age = max_age_seconds or settings.policy.knowledge_freshness_max_age_seconds
            if source_ev.is_stale(max_age):
                notes.append(f"Referenced knowledge evidence is STALE (age > {max_age}s).")
                constraint.status = ConstraintStatus.STALE
                if event_bus:
                    event_bus.emit(
                        EventType.CONSTRAINT_STALE,
                        f"Constraint '{constraint.constraint_id}' marked STALE from evidence '{source_ev.id}'.",
                        payload={"constraint_id": constraint.constraint_id, "evidence_id": source_ev.id},
                    )

        constraint.validation_notes = notes

        if not is_valid:
            constraint.status = ConstraintStatus.REJECTED
            if event_bus:
                event_bus.emit(
                    EventType.CONSTRAINT_REJECTED,
                    f"Constraint '{constraint.constraint_id}' REJECTED: {'; '.join(notes)}",
                    payload={"constraint_id": constraint.constraint_id, "notes": notes},
                )
            return False

        if constraint.status != ConstraintStatus.STALE:
            constraint.status = ConstraintStatus.VALIDATED

        if event_bus:
            event_bus.emit(
                EventType.CONSTRAINT_VALIDATED,
                f"Constraint '{constraint.constraint_id}' validated successfully.",
                payload={"constraint_id": constraint.constraint_id, "type": constraint.constraint_type.value},
            )

        return True

    @classmethod
    def promote_to_active(
        cls,
        constraint: CandidateConstraint,
        evidence_registry: Dict[str, KnowledgeEvidence],
        event_bus: Optional[EventBus] = None,
        max_age_seconds: Optional[float] = None,
    ) -> CandidateConstraint:
        """Validate and deterministically promote a candidate constraint to ACTIVE status."""
        valid = cls.validate(constraint, evidence_registry, event_bus, max_age_seconds)
        if not valid:
            raise ConstraintValidationError(
                f"Cannot promote invalid constraint '{constraint.constraint_id}': {'; '.join(constraint.validation_notes)}"
            )

        if constraint.status == ConstraintStatus.STALE:
            # Stale constraints cannot become unconditionally ACTIVE
            return constraint

        if constraint.constraint_type == ConstraintType.INFORMATIONAL:
            # Informational procedures do not become active prohibitions
            return constraint

        constraint.status = ConstraintStatus.ACTIVE

        if event_bus:
            event_bus.emit(
                EventType.CONSTRAINT_ACTIVATED,
                f"Operational constraint '{constraint.constraint_id}' promoted to ACTIVE status: {constraint.description}",
                payload={
                    "constraint_id": constraint.constraint_id,
                    "target": constraint.target,
                    "action": constraint.action.value if constraint.action else None,
                    "condition": constraint.condition,
                },
            )

        return constraint
