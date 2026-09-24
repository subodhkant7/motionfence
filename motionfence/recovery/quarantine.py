"""Quarantine management registry enforcing scoped capability isolation and sensor evidence pruning."""

from typing import Dict, List, Optional, Set
import time

from motionfence.models.actions import ActionType, is_consequential_action
from motionfence.evidence.models import Evidence
from motionfence.recovery.models import ComponentType, FailureRecord, QuarantineRecord, QuarantineStatus
from motionfence.recovery.policies import QuarantinePolicy


class QuarantineManager:
    """Maintains component health records, enforces scoped capability isolation, and excludes bad telemetry."""

    def __init__(self, policy: Optional[QuarantinePolicy] = None) -> None:
        self.policy = policy or QuarantinePolicy()
        self._records: Dict[str, QuarantineRecord] = {}

    def get_record(self, component_id: str) -> Optional[QuarantineRecord]:
        """Retrieve quarantine audit record for a component."""
        return self._records.get(component_id)

    def is_quarantined(self, component_id: str) -> bool:
        """Check if a component is actively quarantined."""
        rec = self._records.get(component_id)
        return rec is not None and rec.status == QuarantineStatus.QUARANTINED

    def is_suspect(self, component_id: str) -> bool:
        """Check if a component is in suspect or recovery-required status."""
        rec = self._records.get(component_id)
        return rec is not None and rec.is_suspect

    def record_failure(
        self,
        failure: FailureRecord,
        custom_reason: str = "",
    ) -> QuarantineRecord:
        """Record an observed component failure and escalate quarantine status deterministically."""
        now = time.time()
        comp_id = failure.target_component
        comp_type = failure.component_type

        rec = self._records.get(comp_id)
        if rec is None:
            rec = QuarantineRecord(
                component_id=comp_id,
                component_type=comp_type,
                status=QuarantineStatus.HEALTHY,
                failure_count=0,
                consecutive_failures=0,
                first_failure_at=now,
                created_at=now,
                updated_at=now,
            )
            self._records[comp_id] = rec

        rec.failure_count += 1
        rec.consecutive_failures += 1
        rec.last_failure_at = now
        rec.updated_at = now
        if failure.evidence_ids:
            rec.evidence.extend(failure.evidence_ids)

        # Determine new status based on policy thresholds
        new_status = self.policy.determine_status(rec.consecutive_failures)
        rec.status = new_status
        rec.reason = custom_reason or failure.details

        # Apply scoped capabilities
        if new_status == QuarantineStatus.QUARANTINED:
            rec.quarantined_at = now
            rec.affected_capabilities = [a.value for a in self.policy.consequential_actuator_actions]
            rec.remaining_capabilities = [a.value for a in self.policy.permitted_diagnostic_actions]
        elif new_status in (QuarantineStatus.SUSPECT, QuarantineStatus.RECOVERY_REQUIRED):
            rec.affected_capabilities = [ActionType.CLOSE_VALVE.value]
            rec.remaining_capabilities = [a.value for a in self.policy.permitted_diagnostic_actions]
        else:
            rec.affected_capabilities = []
            rec.remaining_capabilities = [a.value for a in self.policy.permitted_diagnostic_actions] + [a.value for a in self.policy.consequential_actuator_actions]

        return rec

    def quarantine_component(
        self,
        component_id: str,
        reason: str,
        component_type: ComponentType = ComponentType.ACTUATOR,
        evidence_ids: Optional[List[str]] = None,
    ) -> QuarantineRecord:
        """Explicitly quarantine a component (e.g. from manual operator or emergency policy)."""
        now = time.time()
        rec = self._records.get(component_id)
        if rec is None:
            rec = QuarantineRecord(
                component_id=component_id,
                component_type=component_type,
                status=QuarantineStatus.QUARANTINED,
                reason=reason,
                evidence=evidence_ids or [],
                failure_count=1,
                consecutive_failures=self.policy.quarantine_threshold,
                first_failure_at=now,
                last_failure_at=now,
                quarantined_at=now,
                created_at=now,
                updated_at=now,
            )
            self._records[component_id] = rec
        else:
            rec.status = QuarantineStatus.QUARANTINED
            rec.reason = reason
            rec.quarantined_at = now
            rec.consecutive_failures = max(rec.consecutive_failures, self.policy.quarantine_threshold)
            rec.updated_at = now
            if evidence_ids:
                rec.evidence.extend(evidence_ids)

        rec.affected_capabilities = [a.value for a in self.policy.consequential_actuator_actions]
        rec.remaining_capabilities = [a.value for a in self.policy.permitted_diagnostic_actions]
        return rec

    def recertify_component(
        self,
        component_id: str,
        certification_evidence: List[str],
        rationale: str = "Empirically recertified through autonomous diagnostic testing.",
    ) -> QuarantineRecord:
        """Formally recertify a previously quarantined or suspect component with proof."""
        now = time.time()
        rec = self._records.get(component_id)
        if rec is None:
            rec = QuarantineRecord(
                component_id=component_id,
                component_type=ComponentType.ACTUATOR,
                status=QuarantineStatus.HEALTHY,
                reason=rationale,
                evidence=certification_evidence,
                created_at=now,
                updated_at=now,
            )
            self._records[component_id] = rec
        else:
            rec.status = QuarantineStatus.HEALTHY
            rec.reason = rationale
            rec.consecutive_failures = 0
            rec.evidence.extend(certification_evidence)
            rec.updated_at = now
            rec.affected_capabilities = []
            rec.remaining_capabilities = [a.value for a in self.policy.permitted_diagnostic_actions] + [a.value for a in self.policy.consequential_actuator_actions]

        return rec

    def is_action_permitted(self, action_type: ActionType, target: str) -> bool:
        """Enforce scoped quarantine: Consequential actions blocked on quarantined targets; diagnostics permitted."""
        rec = self._records.get(target)
        if rec is None:
            return True

        if rec.status == QuarantineStatus.QUARANTINED:
            # Consequential actions are strictly blocked
            if is_consequential_action(action_type):
                return False
            # Diagnostic informational actions remain permitted
            return action_type in self.policy.permitted_diagnostic_actions

        elif rec.status == QuarantineStatus.RECOVERY_REQUIRED:
            # Consequential retries blocked pending recovery
            if is_consequential_action(action_type):
                return False
            return True

        return True

    def filter_admissible_evidence(self, evidence_pool: List[Evidence]) -> List[Evidence]:
        """Prune safety-relevant evidence originating from quarantined or failed sensor components.
        
        SECURITY INVARIANT (PROP_028):
        Sensor quarantine removes untrusted evidence from the active authorization context.
        """
        filtered = []
        for ev in evidence_pool:
            # Check if sensor source or target is quarantined
            sensor_id = ev.provenance.split(":")[0] if ":" in ev.provenance else ev.provenance
            is_bad_sensor = self.is_quarantined(sensor_id) or self.is_quarantined(ev.target)
            if not is_bad_sensor:
                filtered.append(ev)
        return filtered

    def list_quarantined(self) -> List[QuarantineRecord]:
        """Return all currently quarantined components."""
        return [r for r in self._records.values() if r.status == QuarantineStatus.QUARANTINED]

    def reset(self) -> None:
        """Reset internal quarantine registry."""
        self._records.clear()
