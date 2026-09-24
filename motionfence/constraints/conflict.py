"""Conflict detection across operational constraints, sources, and safety policies."""

from typing import Any, List, Optional
import time

from motionfence.constraints.models import (
    CandidateConstraint,
    ConstraintType,
    ConstraintStatus,
    ConstraintConflictReport,
    ConflictCategory,
    Applicability,
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
        policy: Optional[Any] = None,
    ) -> List[ConstraintConflictReport]:
        """Examine constraints for source, policy, applicability, and freshness contradictions."""
        conflicts: List[ConstraintConflictReport] = []

        # 1. Pairwise Constraint Conflict Evaluation
        for i in range(len(constraints)):
            for j in range(i + 1, len(constraints)):
                c1 = constraints[i]
                c2 = constraints[j]

                same_target = c1.target == c2.target
                same_action = c1.action == c2.action and c1.action is not None

                if same_target and same_action:
                    # Source Conflict: Direct operational opposition (PROHIBITION vs PRECONDITION/REQUIREMENT)
                    is_opposed = (
                        (c1.constraint_type == ConstraintType.PROHIBITION and c2.constraint_type in (ConstraintType.PRECONDITION, ConstraintType.REQUIREMENT))
                        or (c2.constraint_type == ConstraintType.PROHIBITION and c1.constraint_type in (ConstraintType.PRECONDITION, ConstraintType.REQUIREMENT))
                    )

                    shared_conditions = set(c1.condition.keys()).intersection(set(c2.condition.keys()))

                    if is_opposed and (shared_conditions or not c1.condition or not c2.condition):
                        # Determine category: Freshness conflict if one is stale and one is fresh
                        category = ConflictCategory.SOURCE_CONFLICT
                        if (c1.status == ConstraintStatus.STALE and c2.status != ConstraintStatus.STALE) or \
                           (c2.status == ConstraintStatus.STALE and c1.status != ConstraintStatus.STALE):
                            category = ConflictCategory.FRESHNESS_CONFLICT

                        report = ConstraintConflictReport(
                            conflict=True,
                            constraint_a_id=c1.constraint_id,
                            constraint_b_id=c2.constraint_id,
                            conflict_category=category,
                            severity="HIGH",
                            details=(
                                f"Direct operational conflict on {c1.target} ({c1.action.value}): "
                                f"Constraint '{c1.constraint_id}' ({c1.constraint_type.value}) opposes "
                                f"Constraint '{c2.constraint_id}' ({c2.constraint_type.value}) [{category.value}]."
                            ),
                            timestamp=time.time(),
                        )
                        conflicts.append(report)
                        c1.status = ConstraintStatus.CONFLICTED
                        c2.status = ConstraintStatus.CONFLICTED

                        if event_bus:
                            event_bus.emit(
                                EventType.CONSTRAINT_CONFLICT,
                                f"High-severity constraint conflict detected: {report.details}",
                                payload=report.model_dump(),
                            )

                    # Applicability Conflict: Both constraints claim authority but have mismatched applicability
                    elif c1.applicability != c2.applicability and {c1.applicability, c2.applicability} == {Applicability.DIRECT, Applicability.MISMATCH}:
                        report = ConstraintConflictReport(
                            conflict=True,
                            constraint_a_id=c1.constraint_id,
                            constraint_b_id=c2.constraint_id,
                            conflict_category=ConflictCategory.APPLICABILITY_CONFLICT,
                            severity="HIGH",
                            details=(
                                f"Applicability conflict on {c1.target}: Constraint '{c1.constraint_id}' ({c1.applicability.value}) "
                                f"conflicts with context of Constraint '{c2.constraint_id}' ({c2.applicability.value})."
                            ),
                            timestamp=time.time(),
                        )
                        conflicts.append(report)
                        c1.status = ConstraintStatus.CONFLICTED
                        c2.status = ConstraintStatus.CONFLICTED

                        if event_bus:
                            event_bus.emit(
                                EventType.CONSTRAINT_CONFLICT,
                                f"Applicability conflict detected: {report.details}",
                                payload=report.model_dump(),
                            )

        # 2. Baseline Policy Conflict Evaluation (Policy vs Knowledge Constraint)
        if policy is not None:
            policy_conflicts = cls.detect_policy_conflicts(constraints, policy, event_bus)
            conflicts.extend(policy_conflicts)

        return conflicts

    @classmethod
    def detect_policy_conflicts(
        cls,
        constraints: List[CandidateConstraint],
        policy: Any,
        event_bus: Optional[EventBus] = None,
    ) -> List[ConstraintConflictReport]:
        """Detect direct contradictions between knowledge constraints and immutable safety policies."""
        reports: List[ConstraintConflictReport] = []

        allowed_targets = getattr(policy, "allowed_actuator_targets", ["valve_a", "valve_b", "pump_p1"])
        prohibited_actions = getattr(policy, "prohibited_actions", [])

        for cst in constraints:
            # Check A: Knowledge constraint attempts to permit/mandate an action that baseline policy strictly prohibits
            if cst.action is not None and cst.action in prohibited_actions and cst.constraint_type in (ConstraintType.REQUIREMENT, ConstraintType.PRECONDITION):
                rep = ConstraintConflictReport(
                    conflict=True,
                    constraint_a_id=cst.constraint_id,
                    constraint_b_id="base_policy_prohibited_actions",
                    conflict_category=ConflictCategory.POLICY_CONFLICT,
                    severity="HIGH",
                    details=f"Knowledge constraint '{cst.constraint_id}' requires prohibited action '{cst.action.value}'.",
                    timestamp=time.time(),
                )
                reports.append(rep)
                cst.status = ConstraintStatus.CONFLICTED
                if event_bus:
                    event_bus.emit(
                        EventType.CONSTRAINT_CONFLICT,
                        f"Policy conflict detected: {rep.details}",
                        payload=rep.model_dump(),
                    )

            # Check B: Knowledge constraint attempts to relax cooling or human zone invariants
            if "cooling" in cst.condition and cst.condition["cooling"] == "INACTIVE" and getattr(policy, "require_cooling_active", True):
                rep = ConstraintConflictReport(
                    conflict=True,
                    constraint_a_id=cst.constraint_id,
                    constraint_b_id="base_policy_cooling_invariant",
                    conflict_category=ConflictCategory.POLICY_CONFLICT,
                    severity="HIGH",
                    details=f"Knowledge constraint '{cst.constraint_id}' contradicts base policy cooling invariant.",
                    timestamp=time.time(),
                )
                reports.append(rep)
                cst.status = ConstraintStatus.CONFLICTED
                if event_bus:
                    event_bus.emit(
                        EventType.CONSTRAINT_CONFLICT,
                        f"Policy conflict detected: {rep.details}",
                        payload=rep.model_dump(),
                    )

        return reports

