"""Deterministic local constraint extractor analyzing knowledge text for operational rules."""

import re
import time
from typing import List

from motionfence.knowledge.models import KnowledgeEvidence
from motionfence.constraints.models import (
    CandidateConstraint,
    ConstraintType,
    ConstraintStatus,
)
from motionfence.models.actions import ActionType


class LocalConstraintExtractor:
    """Deterministic extractor converting knowledge evidence text into structured candidate constraints."""

    def extract(self, evidence_list: List[KnowledgeEvidence]) -> List[CandidateConstraint]:
        """Parse knowledge evidence items and generate structured CandidateConstraint objects."""
        constraints: List[CandidateConstraint] = []

        for ev in evidence_list:
            text = ev.content.lower()

            # Rule 1: Prohibition detection ("must not be closed", "do not close", "strictly prohibited")
            if any(p in text for p in ["must not be closed", "do not close", "closure prohibited", "never close"]):
                # Target extraction
                target = "valve_b" if "valve b" in text else ("valve_a" if "valve a" in text else "generic_valve")
                # Condition extraction
                condition = {}
                if "pump p1 is active" in text or "pump p1 running" in text or "under pump pressure" in text:
                    condition["pump_p1"] = "ACTIVE"

                constraints.append(
                    CandidateConstraint(
                        constraint_type=ConstraintType.PROHIBITION,
                        action=ActionType.CLOSE_VALVE,
                        target=target,
                        condition=condition,
                        source_evidence_id=ev.id,
                        confidence=ev.confidence,
                        created_at=time.time(),
                        status=ConstraintStatus.CANDIDATE,
                        description=f"Prohibition: {target} must not be closed when conditions {condition} are met.",
                    )
                )

            # Rule 2: Permissive / Contradictory exception ("may be closed while pump p1 is active")
            elif any(p in text for p in ["may be closed while pump p1 is active", "closure permitted", "may be closed"]):
                target = "valve_b" if "valve b" in text else ("valve_a" if "valve a" in text else "generic_valve")
                condition = {}
                if "pump p1 is active" in text or "emergency isolation" in text:
                    condition["pump_p1"] = "ACTIVE"

                constraints.append(
                    CandidateConstraint(
                        constraint_type=ConstraintType.PRECONDITION,  # Permissive exception condition
                        action=ActionType.CLOSE_VALVE,
                        target=target,
                        condition={"pump_p1": "ACTIVE", "emergency_bypass": "OPEN"},
                        source_evidence_id=ev.id,
                        confidence=ev.confidence,
                        created_at=time.time(),
                        status=ConstraintStatus.CANDIDATE,
                        description=f"Permissive Guidance: {target} may be closed during emergency with bypass.",
                    )
                )

            # Rule 3: Procedural / Informational guidance ("should be performed before", "routine procedure", "checklist")
            elif any(p in text for p in ["should be performed before", "routine procedure", "checklist", "inspection"]):
                target = "valve_b" if "valve b" in text else ("valve_a" if "valve a" in text else "system")
                # IMPORTANT: Harmless procedures must NOT become PROHIBITION!
                constraints.append(
                    CandidateConstraint(
                        constraint_type=ConstraintType.INFORMATIONAL,
                        action=ActionType.INSPECT,
                        target=target,
                        condition={},
                        source_evidence_id=ev.id,
                        confidence=ev.confidence,
                        created_at=time.time(),
                        status=ConstraintStatus.CANDIDATE,
                        description=f"Procedure: Routine visual check on {target} prior to maintenance.",
                    )
                )

            # Rule 4: Mandatory requirement ("requires", "must maintain")
            elif any(p in text for p in ["requires", "must maintain", "mandatory invariant"]):
                target = "valve_b" if "valve b" in text else ("valve_a" if "valve a" in text else "cooling")
                constraints.append(
                    CandidateConstraint(
                        constraint_type=ConstraintType.REQUIREMENT,
                        action=None,
                        target=target,
                        condition={"secondary_thermal_purge": True},
                        source_evidence_id=ev.id,
                        confidence=ev.confidence,
                        created_at=time.time(),
                        status=ConstraintStatus.CANDIDATE,
                        description=f"Requirement: Thermal purge verification mandatory for {target}.",
                    )
                )

        return constraints
