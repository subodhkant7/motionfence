"""Conflict detection between operational constraints and safety policies."""

from typing import List, Optional
import time

from motionfence.constraints.models import (
    CandidateConstraint,
    ConstraintType,
    ConstraintStatus,
    ConstraintConflictReport,
)
from motionfence.models.events import EventType
from motionfence.runtime.events import EventBus


class ConstraintConflictDetector:
    """Identifies mutual contradictions between knowledge-derived constraints or safety policies."""

    @classmethod
    def detect_conflicts(
        cls,
        constraints: List[CandidateConstraint],
        event_bus: Optional[EventBus] = None,
    ) -> List[ConstraintConflictReport]:
        """Examine constraints for conflicting permissions, prohibitions, or preconditions."""
        conflicts: List[ConstraintConflictReport] = []

        for i in range(len(constraints)):
            for j in range(i + 1, len(constraints)):
                c1 = constraints[i]
                c2 = constraints[j]

                # Conflict Condition: Same target and action, but one is PROHIBITION and other is permissive/PRECONDITION
                same_target = c1.target == c2.target
                same_action = c1.action == c2.action and c1.action is not None

                if same_target and same_action:
                    is_opposed = (
                        (c1.constraint_type == ConstraintType.PROHIBITION and c2.constraint_type in (ConstraintType.PRECONDITION, ConstraintType.REQUIREMENT))
                        or (c2.constraint_type == ConstraintType.PROHIBITION and c1.constraint_type in (ConstraintType.PRECONDITION, ConstraintType.REQUIREMENT))
                    )

                    # Check for overlapping condition keys (e.g. pump_p1)
                    shared_conditions = set(c1.condition.keys()).intersection(set(c2.condition.keys()))

                    if is_opposed and (shared_conditions or not c1.condition or not c2.condition):
                        report = ConstraintConflictReport(
                            conflict=True,
                            constraint_a_id=c1.constraint_id,
                            constraint_b_id=c2.constraint_id,
                            severity="HIGH",
                            details=(
                                f"Direct operational conflict on {c1.target} ({c1.action.value}): "
                                f"Constraint '{c1.constraint_id}' ({c1.constraint_type.value}) opposes "
                                f"Constraint '{c2.constraint_id}' ({c2.constraint_type.value})."
                            ),
                            timestamp=time.time(),
                        )
                        conflicts.append(report)

                        # Update statuses to CONFLICTED
                        c1.status = ConstraintStatus.CONFLICTED
                        c2.status = ConstraintStatus.CONFLICTED

                        if event_bus:
                            event_bus.emit(
                                EventType.CONSTRAINT_CONFLICT,
                                f"High-severity constraint conflict detected: {report.details}",
                                payload=report.model_dump(),
                            )

        return conflicts
