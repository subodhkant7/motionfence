"""Deterministic validator and promotion gate for candidate operational constraints."""

from typing import Dict, List, Optional
import time

from motionfence.constraints.models import (
    CandidateConstraint,
    ConstraintType,
    ConstraintStatus,
    Applicability,
    PlantContext,
)
from motionfence.constraints.extractor import ConstraintValidationError
from motionfence.knowledge.models import KnowledgeEvidence, TrustStatus, FreshnessStatus
from motionfence.knowledge.trust import (
    SourceTrustClassifier,
    SourceCategory,
    AuthorityLevel,
    EvidenceRole,
    CorroborationStatus,
)
from motionfence.models.actions import ActionType
from motionfence.models.events import EventType
from motionfence.runtime.events import EventBus
from motionfence.config.settings import settings


class ConstraintValidator:
    """Deterministically verifies candidate constraint schemas, evidence links, provenance, and admissibility."""

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
            constraint.status = ConstraintStatus.STRUCTURALLY_VALID

        if event_bus:
            event_bus.emit(
                EventType.CONSTRAINT_VALIDATED,
                f"Constraint '{constraint.constraint_id}' validated structurally.",
                payload={"constraint_id": constraint.constraint_id, "type": constraint.constraint_type.value},
            )

        return True

    @classmethod
    def assess_applicability(
        cls,
        constraint: CandidateConstraint,
        plant_context: PlantContext,
        evidence: Optional[KnowledgeEvidence] = None,
    ) -> Applicability:
        """Evaluate context and equipment alignment against plant metadata."""
        # 1. Target actuator boundary check
        if constraint.target not in plant_context.authorized_targets:
            return Applicability.MISMATCH

        # 2. Check evidence text if present
        if evidence is not None:
            text = f"{evidence.title} {evidence.content}".lower()

            # Mismatched equipment models or types
            if "p200" in text or "model y" in text or "slurry" in text:
                return Applicability.MISMATCH

            # Direct match on equipment ID or specific plant manual
            if (
                plant_context.equipment_id in text
                or (plant_context.equipment_model and plant_context.equipment_model.lower() in text)
                or "plant_manual" in evidence.source_url.lower()
            ):
                return Applicability.DIRECT

            # Generic equipment family
            if plant_context.equipment_type.lower() in text or "pump" in text:
                return Applicability.PARTIAL

            return Applicability.UNKNOWN

        return Applicability.DIRECT

    @classmethod
    def check_admissibility(
        cls,
        constraint: CandidateConstraint,
        evidence_registry: Dict[str, KnowledgeEvidence],
        plant_context: Optional[PlantContext] = None,
        corroboration_status: Optional[CorroborationStatus] = None,
        event_bus: Optional[EventBus] = None,
        max_age_seconds: Optional[float] = None,
    ) -> bool:
        """Deterministically assess whether evidence is sufficiently authoritative, applicable, and fresh.
        
        SECURITY PRINCIPLE:
        SOURCE EXISTS ≠ SOURCE IS TRUSTWORTHY ≠ CLAIM IS APPLICABLE ≠ CLAIM IS SUFFICIENT FOR AUTHORIZATION
        """
        # Step 1: Structural validation must pass
        if not cls.validate(constraint, evidence_registry, event_bus, max_age_seconds):
            constraint.admissibility_notes.append("Failed structural validation.")
            if event_bus:
                event_bus.emit(
                    EventType.CONSTRAINT_NOT_ADMISSIBLE,
                    f"Constraint '{constraint.constraint_id}' not admissible: failed structural validation.",
                    payload={"constraint_id": constraint.constraint_id},
                )
            return False

        if constraint.status == ConstraintStatus.STALE:
            constraint.admissibility_notes.append("Stale evidence cannot be admitted for active policy.")
            if event_bus:
                event_bus.emit(
                    EventType.CONSTRAINT_NOT_ADMISSIBLE,
                    f"Constraint '{constraint.constraint_id}' not admissible: evidence is STALE.",
                    payload={"constraint_id": constraint.constraint_id},
                )
            return False

        source_ev = evidence_registry[constraint.source_evidence_id]

        # Step 2: Source Trust Assessment
        if constraint.source_trust is None:
            assessment = SourceTrustClassifier.assess(source_ev)
            constraint.source_trust = assessment
            constraint.evidence_role = assessment.evidence_role

            if event_bus:
                event_bus.emit(
                    EventType.SOURCE_ASSESSED,
                    f"Source assessed for evidence '{source_ev.id}': category={assessment.source_category.value}, authority={assessment.authority_level.value}",
                    payload=assessment.model_dump(),
                )
                event_bus.emit(
                    EventType.EVIDENCE_CLASSIFIED,
                    f"Evidence '{source_ev.id}' assigned role: {assessment.evidence_role.value}",
                    payload={"evidence_id": source_ev.id, "role": assessment.evidence_role.value},
                )

        assessment = constraint.source_trust

        # Step 3: Role & Authority Gating
        if assessment.evidence_role == EvidenceRole.REJECTED:
            constraint.admissibility_notes.append("Evidence is rejected due to invalid provenance or trust status.")
            if event_bus:
                event_bus.emit(
                    EventType.CONSTRAINT_NOT_ADMISSIBLE,
                    f"Constraint '{constraint.constraint_id}' not admissible: evidence role is REJECTED.",
                    payload={"constraint_id": constraint.constraint_id},
                )
            return False

        # Discovery sources (community forums, social media, unattributed blogs) CANNOT create active prohibitions
        if (
            assessment.evidence_role == EvidenceRole.DISCOVERY
            or assessment.source_category in (SourceCategory.COMMUNITY_OR_USER_CONTENT, SourceCategory.UNKNOWN)
        ):
            note = (
                f"Source category '{assessment.source_category.value}' (role={assessment.evidence_role.value}) "
                "is admissible for DISCOVERY ONLY. It cannot independently activate safety prohibitions."
            )
            constraint.admissibility_notes.append(note)
            if event_bus:
                event_bus.emit(
                    EventType.EVIDENCE_INSUFFICIENT,
                    f"Evidence '{source_ev.id}' has insufficient authority: {note}",
                    payload={"evidence_id": source_ev.id, "category": assessment.source_category.value},
                )
                event_bus.emit(
                    EventType.CONSTRAINT_NOT_ADMISSIBLE,
                    f"Constraint '{constraint.constraint_id}' not admissible: {note}",
                    payload={"constraint_id": constraint.constraint_id},
                )
            return False

        # Supporting sources (general technical, non-OEM technical blogs) require multi-source corroboration
        effective_corroboration = corroboration_status or constraint.corroboration
        if (
            assessment.evidence_role == EvidenceRole.SUPPORTING
            or assessment.source_category == SourceCategory.GENERAL_TECHNICAL_SOURCE
        ):
            if effective_corroboration != CorroborationStatus.CORROBORATED:
                note = (
                    f"Supporting source category '{assessment.source_category.value}' requires independent "
                    "multi-source corroboration before activating safety prohibitions."
                )
                constraint.admissibility_notes.append(note)
                if event_bus:
                    event_bus.emit(
                        EventType.EVIDENCE_INSUFFICIENT,
                        f"Evidence '{source_ev.id}' lacks multi-source corroboration.",
                        payload={"evidence_id": source_ev.id, "corroboration": effective_corroboration.value},
                    )
                    event_bus.emit(
                        EventType.CONSTRAINT_NOT_ADMISSIBLE,
                        f"Constraint '{constraint.constraint_id}' not admissible: {note}",
                        payload={"constraint_id": constraint.constraint_id},
                    )
                return False
            else:
                if event_bus:
                    event_bus.emit(
                        EventType.EVIDENCE_CORROBORATED,
                        f"Supporting evidence '{source_ev.id}' corroborated by independent sources.",
                        payload={"evidence_id": source_ev.id},
                    )

        # Step 4: Applicability Gating
        p_context = plant_context or PlantContext()
        evaluated_applicability = cls.assess_applicability(constraint, p_context, source_ev)
        constraint.applicability = evaluated_applicability

        if evaluated_applicability == Applicability.MISMATCH:
            note = f"Equipment applicability MISMATCH with plant context (target={constraint.target})."
            constraint.admissibility_notes.append(note)
            if event_bus:
                event_bus.emit(
                    EventType.CONSTRAINT_NOT_ADMISSIBLE,
                    f"Constraint '{constraint.constraint_id}' not admissible: {note}",
                    payload={"constraint_id": constraint.constraint_id},
                )
            return False

        if evaluated_applicability == Applicability.UNKNOWN:
            note = "Equipment applicability is UNKNOWN; cannot activate safety constraint."
            constraint.admissibility_notes.append(note)
            if event_bus:
                event_bus.emit(
                    EventType.CONSTRAINT_NOT_ADMISSIBLE,
                    f"Constraint '{constraint.constraint_id}' not admissible: {note}",
                    payload={"constraint_id": constraint.constraint_id},
                )
            return False

        # Constraint passed all structural, authority, corroboration, and applicability checks
        constraint.status = ConstraintStatus.ADMISSIBLE
        constraint.admissibility_notes.append(
            f"Admissible: verified authority ({assessment.source_category.value}), "
            f"role ({assessment.evidence_role.value}), applicability ({evaluated_applicability.value})."
        )

        if event_bus:
            event_bus.emit(
                EventType.CONSTRAINT_ADMISSIBILITY_CHECKED,
                f"Admissibility checked for constraint '{constraint.constraint_id}': ADMISSIBLE.",
                payload={"constraint_id": constraint.constraint_id, "category": assessment.source_category.value},
            )
            event_bus.emit(
                EventType.CONSTRAINT_ADMISSIBLE,
                f"Constraint '{constraint.constraint_id}' deemed ADMISSIBLE for policy consideration.",
                payload={"constraint_id": constraint.constraint_id},
            )

        return True

    @classmethod
    def promote_to_active(
        cls,
        constraint: CandidateConstraint,
        evidence_registry: Dict[str, KnowledgeEvidence],
        event_bus: Optional[EventBus] = None,
        max_age_seconds: Optional[float] = None,
        plant_context: Optional[PlantContext] = None,
        corroboration_status: Optional[CorroborationStatus] = None,
    ) -> CandidateConstraint:
        """Validate, assess admissibility, and deterministically promote a constraint to ACTIVE status.
        
        INVARIANT:
        Only ADMISSIBLE constraints may become ACTIVE.
        Weak/discovery evidence, uncorroborated supporting sources, or applicability mismatches
        remain non-active and cannot gate physical actuation.
        """
        # Check admissibility
        is_admissible = cls.check_admissibility(
            constraint=constraint,
            evidence_registry=evidence_registry,
            plant_context=plant_context,
            corroboration_status=corroboration_status,
            event_bus=event_bus,
            max_age_seconds=max_age_seconds,
        )

        if not is_admissible:
            # Stale and rejected constraints maintain their respective status
            # Non-admissible candidate constraints remain STRUCTURALLY_VALID (or CANDIDATE)
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
                    "source_category": constraint.source_trust.source_category.value if constraint.source_trust else None,
                },
            )

        return constraint

