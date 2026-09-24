"""Deterministic contradiction detector for physical sensor observations."""

from typing import List, Optional, Tuple
from motionfence.evidence.models import (
    Evidence,
    EvidenceSource,
    ContradictionReport,
    ContradictionSeverity,
)


class ContradictionDetector:
    """Evaluates multiple evidence items to detect physical discrepancies and sensor conflicts."""

    @classmethod
    def detect(cls, evidence_list: List[Evidence], target: Optional[str] = None) -> ContradictionReport:
        """Analyze evidence items for mutual contradictions on the specified target or system-wide."""
        relevant_evidence = [
            e for e in evidence_list
            if target is None or e.target == target or target in e.target or e.target == "global"
        ]

        if len(relevant_evidence) < 2:
            return ContradictionReport(contradiction=False, severity=ContradictionSeverity.NONE)

        conflicts: List[Tuple[Evidence, Evidence, str]] = []

        # Pairwise comparison
        for i in range(len(relevant_evidence)):
            for j in range(i + 1, len(relevant_evidence)):
                ev1 = relevant_evidence[i]
                ev2 = relevant_evidence[j]

                conflict_msg = cls._check_pair_conflict(ev1, ev2)
                if conflict_msg:
                    conflicts.append((ev1, ev2, conflict_msg))

        if not conflicts:
            return ContradictionReport(contradiction=False, severity=ContradictionSeverity.NONE)

        # Aggregate highest severity conflict
        max_severity = ContradictionSeverity.LOW
        conflicting_sources = set()
        conflicting_ids = set()
        details_list = []

        for ev1, ev2, msg in conflicts:
            conflicting_sources.add(ev1.source.value)
            conflicting_sources.add(ev2.source.value)
            conflicting_ids.add(ev1.id)
            conflicting_ids.add(ev2.id)
            details_list.append(msg)

            severity = cls._calculate_severity(ev1.confidence, ev2.confidence)
            if cls._severity_rank(severity) > cls._severity_rank(max_severity):
                max_severity = severity

        return ContradictionReport(
            contradiction=True,
            sources=sorted(list(conflicting_sources)),
            severity=max_severity,
            target=target,
            conflicting_evidence_ids=sorted(list(conflicting_ids)),
            details="; ".join(details_list),
        )

    @classmethod
    def _check_pair_conflict(cls, ev1: Evidence, ev2: Evidence) -> Optional[str]:
        """Check if two evidence items make conflicting physical claims."""
        obs1 = ev1.observation
        obs2 = ev2.observation

        # Case 1: Direct boolean conflict on leak_detected
        leak1 = obs1.get("leak_detected")
        leak2 = obs2.get("leak_detected")
        if leak1 is not None and leak2 is not None and leak1 != leak2:
            return (
                f"{ev1.source.value} reports leak_detected={leak1} "
                f"while {ev2.source.value} reports leak_detected={leak2}"
            )

        # Case 2: Vision reports leak, but pressure sensor reports no pressure anomaly
        if (ev1.source == EvidenceSource.VISION and ev2.source == EvidenceSource.PRESSURE_SENSOR) or (
            ev2.source == EvidenceSource.VISION and ev1.source == EvidenceSource.PRESSURE_SENSOR
        ):
            vis = ev1 if ev1.source == EvidenceSource.VISION else ev2
            press = ev2 if ev1.source == EvidenceSource.VISION else ev1

            vis_leak = vis.observation.get("leak_detected") or vis.observation.get("visual_leak_detected")
            press_anomaly = press.observation.get("pressure_anomaly")
            press_normal = press.observation.get("pressure_normal")

            if vis_leak is True and (press_anomaly is False or press_normal is True):
                return (
                    f"Vision reports leak on {vis.target} (conf={vis.confidence:.2f}) "
                    f"but pressure sensor reports nominal pressure with no anomaly (conf={press.confidence:.2f})"
                )

        # Case 3: Conflicting valve state
        vstate1 = obs1.get("valve_state") or obs1.get("state")
        vstate2 = obs2.get("valve_state") or obs2.get("state")
        if vstate1 is not None and vstate2 is not None and vstate1 != vstate2:
            return (
                f"{ev1.source.value} reports state={vstate1} "
                f"while {ev2.source.value} reports state={vstate2}"
            )

        # Case 4: Flow detected while reported closed
        if (obs1.get("valve_state") == "CLOSED" and obs2.get("flow_detected") is True) or (
            obs2.get("valve_state") == "CLOSED" and obs1.get("flow_detected") is True
        ):
            return "Conflicting observations: Valve reported closed but active fluid flow detected"

        return None

    @classmethod
    def _calculate_severity(cls, conf1: float, conf2: float) -> ContradictionSeverity:
        """Assign severity based on sensor confidence levels."""
        if conf1 >= 0.80 and conf2 >= 0.80:
            return ContradictionSeverity.HIGH
        if (conf1 >= 0.80 and conf2 >= 0.60) or (conf2 >= 0.80 and conf1 >= 0.60):
            return ContradictionSeverity.MEDIUM
        return ContradictionSeverity.LOW

    @classmethod
    def _severity_rank(cls, severity: ContradictionSeverity) -> int:
        ranks = {
            ContradictionSeverity.NONE: 0,
            ContradictionSeverity.LOW: 1,
            ContradictionSeverity.MEDIUM: 2,
            ContradictionSeverity.HIGH: 3,
        }
        return ranks.get(severity, 0)
