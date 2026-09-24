#!/usr/bin/env python3
"""CLI utility to manage, inspect, quarantine, and recertify plant components (Phase 2I).

Usage:
    python scripts/quarantine_component.py --list
    python scripts/quarantine_component.py --status valve_b
    python scripts/quarantine_component.py --quarantine valve_b --reason "Excessive friction detected"
    python scripts/quarantine_component.py --recertify valve_b --evidence "ev_repaired_01"
"""

import argparse
import os
import sys

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from motionfence.recovery.models import ComponentType, QuarantineStatus
from motionfence.recovery.quarantine import QuarantineManager


def main():
    parser = argparse.ArgumentParser(description="MotionFence Component Quarantine Registry Manager")
    parser.add_argument("--list", action="store_true", help="List all quarantined/suspect components")
    parser.add_argument("--status", type=str, help="Show quarantine status and capability permissions for component")
    parser.add_argument("--quarantine", type=str, help="Component ID to explicitly quarantine")
    parser.add_argument("--recertify", type=str, help="Component ID to recertify with evidence")
    parser.add_argument("--reason", type=str, default="Manual administrative quarantine command", help="Quarantine reason")
    parser.add_argument("--evidence", type=str, default="", help="Certification evidence identifier")
    parser.add_argument("--type", choices=["ACTUATOR", "SENSOR", "ZONE", "CONTROLLER"], default="ACTUATOR", help="Component type")

    args = parser.parse_args()
    qm = QuarantineManager()

    if args.quarantine:
        comp_type = getattr(ComponentType, args.type, ComponentType.ACTUATOR)
        rec = qm.quarantine_component(
            component_id=args.quarantine,
            reason=args.reason,
            component_type=comp_type,
        )
        print(f"[QUARANTINE RECORD CREATED]")
        print(f"Component:      {rec.component_id} ({rec.component_type.value})")
        print(f"Status:         {rec.status.value}")
        print(f"Reason:         {rec.reason}")
        print(f"Blocked Actions:{rec.affected_capabilities}")
        print(f"Allowed Actions:{rec.remaining_capabilities}")

    elif args.recertify:
        evidence = [args.evidence] if args.evidence else ["ev_manual_inspection_passed"]
        rec = qm.recertify_component(
            component_id=args.recertify,
            certification_evidence=evidence,
            rationale="Recertified by authorized physical inspection.",
        )
        print(f"[COMPONENT RECERTIFIED]")
        print(f"Component:      {rec.component_id}")
        print(f"Status:         {rec.status.value}")
        print(f"Evidence:       {rec.evidence}")
        print(f"Remaining Caps: {rec.remaining_capabilities}")

    elif args.status:
        rec = qm.get_record(args.status)
        if not rec:
            print(f"Component '{args.status}' is currently HEALTHY (unregistered, 0 faults).")
        else:
            print(f"Component:      {rec.component_id} ({rec.component_type.value})")
            print(f"Status:         {rec.status.value}")
            print(f"Failures:       {rec.failure_count} (consecutive: {rec.consecutive_failures})")
            print(f"Reason:         {rec.reason}")
            print(f"Blocked Actions:{rec.affected_capabilities}")
            print(f"Allowed Actions:{rec.remaining_capabilities}")

    elif args.list:
        quarantined = qm.list_quarantined()
        print(f"QUARANTINED COMPONENTS COUNT: {len(quarantined)}")
        for r in quarantined:
            print(f"  * {r.component_id} ({r.component_type.value}): {r.reason}")

    else:
        parser.print_help()


if __name__ == "__main__":
    main()
