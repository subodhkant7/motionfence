"""Immediate failure containment and ticket authority invalidation engine."""

from typing import Optional
import time

from motionfence.models.actions import AuthorizationTicket
from motionfence.models.events import EventType
from motionfence.runtime.events import EventBus
from motionfence.recovery.models import (
    ContainmentActionReport,
    FailureRecord,
    QuarantineStatus,
)
from motionfence.recovery.policies import ContainmentPolicy
from motionfence.recovery.quarantine import QuarantineManager


class ContainmentManager:
    """Executes immediate physical and cryptographic containment following a detected failure."""

    def __init__(
        self,
        policy: Optional[ContainmentPolicy] = None,
        event_bus: Optional[EventBus] = None,
    ) -> None:
        self.policy = policy or ContainmentPolicy()
        self.event_bus = event_bus

    def contain_failure(
        self,
        failure: FailureRecord,
        active_ticket: Optional[AuthorizationTicket] = None,
        quarantine_manager: Optional[QuarantineManager] = None,
    ) -> ContainmentActionReport:
        """Execute containment: invalidate ticket authority, isolate component, and emit audit logs.
        
        SECURITY INVARIANT (PROP_024):
        A verified action failure immediately invalidates the associated ticket.
        """
        if self.event_bus:
            self.event_bus.emit(
                EventType.CONTAINMENT_STARTED,
                f"Immediate containment initiated for failure '{failure.failure_id}' on component '{failure.target_component}'.",
                payload={"failure_id": failure.failure_id, "failure_class": failure.failure_class.value},
            )

        ticket_invalidated = False
        invalidated_id = None

        # 1. Cryptographic Authority Invalidation
        if active_ticket is not None:
            active_ticket.consumed = True
            ticket_invalidated = True
            invalidated_id = active_ticket.ticket_id
            if self.event_bus:
                self.event_bus.emit(
                    EventType.TICKET_INVALIDATED,
                    f"AuthorizationTicket '{active_ticket.ticket_id}' invalidated due to action failure.",
                    payload={"ticket_id": active_ticket.ticket_id, "failure_id": failure.failure_id},
                )

        # 2. Component Health Update & Scoped Quarantine
        comp_status = QuarantineStatus.SUSPECT
        if quarantine_manager is not None:
            rec = quarantine_manager.record_failure(failure)
            comp_status = rec.status
            if self.event_bus:
                if comp_status == QuarantineStatus.QUARANTINED:
                    self.event_bus.emit(
                        EventType.COMPONENT_QUARANTINED,
                        f"Component '{rec.component_id}' has reached {rec.consecutive_failures} failures and is QUARANTINED.",
                        payload={"component_id": rec.component_id, "consecutive_failures": rec.consecutive_failures},
                    )
                elif comp_status in (QuarantineStatus.SUSPECT, QuarantineStatus.RECOVERY_REQUIRED):
                    self.event_bus.emit(
                        EventType.COMPONENT_MARKED_SUSPECT,
                        f"Component '{rec.component_id}' marked as {comp_status.value}.",
                        payload={"component_id": rec.component_id, "status": comp_status.value},
                    )

        # 3. Determine frozen vs allowed actions
        frozen_actions = self.policy.get_actions_to_freeze(failure.failure_class, failure.target_component)
        allowed_actions = self.policy.get_actions_to_permit(failure.failure_class, failure.target_component)

        report = ContainmentActionReport(
            failure_id=failure.failure_id,
            target_component=failure.target_component,
            ticket_invalidated=ticket_invalidated,
            invalidated_ticket_id=invalidated_id,
            component_status=comp_status,
            frozen_actions=frozen_actions,
            allowed_actions=allowed_actions,
            message=(
                f"Containment applied: Ticket invalidated={ticket_invalidated}; "
                f"Component '{failure.target_component}' status={comp_status.value}; "
                f"Frozen consequential capabilities: {frozen_actions}."
            ),
        )
        return report
