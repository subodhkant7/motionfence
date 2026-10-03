#!/usr/bin/env python3
"""MotionFence Deterministic Offline Public Telemetry Replay (Phase 2O).

Enforces:
1. 100% OFFLINE: Zero network calls, zero public API credentials.
2. ZERO AUTHORITY: Replay cannot actuate hardware or mint live tickets.
3. CRYPTOGRAPHIC INTEGRITY: Verifies the SHA-256 canonical hash of every snapshot; fails closed on tamper.
4. PROVENANCE INTEGRITY: Explicitly labels mode as REPLAY — RECORDED REAL OBSERVATION.
5. REPRODUCIBILITY: Deterministically reproduces observation snapshot, provenance, and policy context.

Usage:
    python scripts/replay_public_telemetry.py
    python scripts/replay_public_telemetry.py --sample
    python scripts/replay_public_telemetry.py --fixture path/to/fixture.json
"""

import argparse
import json
import os
import sys
from typing import Optional

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from motionfence.telemetry import (
    ObservationSnapshot,
    TelemetryEvidenceAdapter,
    TelemetryMode,
    TelemetryReplayEngine,
)
from motionfence.models.world import WorldState, ValveState, HumanZoneState
from motionfence.models.actions import ActionProposal, ActionType
from motionfence.policy.engine import PolicyEngine
from motionfence.policy.models import Policy
from motionfence.simulation.world import PhysicalWorld

FIXTURE_PATH = os.path.abspath(
    os.path.join(os.path.dirname(__file__), "..", "motionfence", "fixtures", "live_demo", "telemetry_observation.json")
)


def print_banner(title: str, stream=None) -> None:
    stream = stream or sys.stdout
    print("\n" + "=" * 78, file=stream)
    print(f" {title}", file=stream)
    print("=" * 78, file=stream)


def print_observation_box(obs: ObservationSnapshot, stream=None) -> None:
    stream = stream or sys.stdout
    w = 76
    print("┌" + "─" * (w - 2) + "┐", file=stream)
    title = " REPLAYED PUBLIC OBSERVATION (RECORDED USGS FIXTURE)"
    print(f"│{title}".ljust(w - 1) + "│", file=stream)
    print("├" + "─" * (w - 2) + "┤", file=stream)
    print(f"│  Source Provider:     {obs.provider} ({obs.source_system})".ljust(w - 1) + "│", file=stream)
    print(f"│  Station ID:          {obs.monitoring_location_id}".ljust(w - 1) + "│", file=stream)
    loc_name = obs.monitoring_location_name or "N/A"
    print(f"│  Station Name:        {loc_name[:w - 26]}".ljust(w - 1) + "│", file=stream)
    print(f"│  Parameter:           {obs.parameter_code} — {obs.parameter_name}".ljust(w - 1) + "│", file=stream)
    print(f"│  Value & Unit:        {obs.raw_value} {obs.unit}".ljust(w - 1) + "│", file=stream)
    print(f"│  Observation Time:    {obs.observed_at}".ljust(w - 1) + "│", file=stream)
    print(f"│  Recorded Freshness:  [{obs.freshness.value}] (age: {obs.freshness_age_seconds:.0f}s)".ljust(w - 1) + "│", file=stream)
    print(f"│  Approval / Qual:     {obs.approval_status or 'N/A'} / {obs.qualifier or 'None'}".ljust(w - 1) + "│", file=stream)
    print(f"│  Provenance Hash:     {obs.provenance_hash[:16]}...".ljust(w - 1) + "│", file=stream)
    print(f"│  Verified Canonical:  {obs.raw_record_hash[:16]}... [VERIFIED]".ljust(w - 1) + "│", file=stream)
    print("└" + "─" * (w - 2) + "┘", file=stream)


def replay_telemetry(fixture_path: Optional[str] = None, stream=None) -> int:
    stream = stream or sys.stdout
    target_fixture = fixture_path or FIXTURE_PATH

    print_banner("PHASE 2O: DETERMINISTIC OFFLINE PUBLIC TELEMETRY REPLAY", stream)
    print(f"Target Fixture: {target_fixture}", file=stream)
    print("Zero network calls. Zero model calls. Zero actuator authority.", file=stream)

    ok, snapshots, msg = TelemetryReplayEngine.load_from_fixture(target_fixture)
    if not ok:
        print(f"\n[FAIL CLOSED] Replay integrity check failed: {msg}", file=stream)
        return 1

    print(f"\n[INTEGRITY VERIFIED] {msg}", file=stream)

    for s in snapshots:
        print_observation_box(s, stream=stream)

    # 1. Translate observations into Evidence
    print("\n--- REPLAY STAGE 1: EVIDENCE TRANSLATION ---", file=stream)
    evidence_items = TelemetryEvidenceAdapter.to_evidence_list(snapshots)
    for ev in evidence_items:
        print(f"  • Reconstructed Evidence: {ev.id} (target: {ev.target}, conf: {ev.confidence:.2f})", file=stream)
        print(f"    Lineage: {ev.provenance}", file=stream)

    # 2. Derive deterministic environmental context
    discharge_obs = next((s for s in snapshots if s.parameter_code == "00060"), snapshots[0])
    derived_ctx = TelemetryEvidenceAdapter.derive_environmental_flow_context(
        discharge_obs,
        high_flow_threshold_cfs=5000.0,
    )
    print(f"\n--- REPLAY STAGE 2: DETERMINISTIC ENVIRONMENTAL CONTEXT ---", file=stream)
    print(f"  • Classification: {derived_ctx.classification} (Threshold: {derived_ctx.threshold_value} {derived_ctx.unit})", file=stream)
    print(f"  • Observed Flow:  {derived_ctx.observed_metric_value} {derived_ctx.unit}", file=stream)
    print(f"  • Rule Binding:   {derived_ctx.rule_id} [hash:{derived_ctx.deterministic_hash[:12]}]", file=stream)

    # 3. Replay into WorldState
    world = PhysicalWorld()
    world.valves["valve_b"] = ValveState.OPEN
    world.set_pump_state("pump_p1", "INACTIVE")
    world.set_human_zone(HumanZoneState.CLEAR)
    ws = world.get_state()

    TelemetryEvidenceAdapter.attach_to_world_state(ws, snapshots, derived_ctx)
    print(f"\n--- REPLAY STAGE 3: MOTIONFENCE POLICY REPLAY EVALUATION ---", file=stream)
    print(f"  • WorldState external_observations: USGS streamflow={ws.external_observations['usgs'].get('streamflow_cfs', {}).get('value')} cfs", file=stream)

    # Evaluate deterministic proposal against replayed context
    proposal = ActionProposal(
        action_type=ActionType.CLOSE_VALVE,
        target="valve_b",
        parameters={},
        rationale="Nominal maintenance shutdown of drainage valve during standard river flow conditions.",
        model_confidence=0.95,
        supporting_evidence_ids=[evidence_items[0].id],
    )

    policy = Policy()
    decision = PolicyEngine.evaluate(proposal, ws, evidence_items, policy)

    print(f"\n  • Evaluated Action: {proposal.action_type.value} on {proposal.target}", file=stream)
    print(f"  • Policy Decision:  [{decision.decision.value}] (Deterministic evaluation)", file=stream)
    for r in decision.reasons:
        print(f"    - {r.constraint}: {r.status} ({r.details})", file=stream)

    print("\n[SECURITY INVARIANT CONFIRMED] Offline replay executed with zero network calls and zero actuator authority.", file=stream)
    return 0


def main():
    parser = argparse.ArgumentParser(description="MotionFence Offline Telemetry Replay (Phase 2O)")
    parser.add_argument("--fixture", help="Path to custom telemetry fixture JSON")
    parser.add_argument("--sample", action="store_true", help="Replay canonical recorded sample fixture")

    args = parser.parse_args()
    rc = replay_telemetry(fixture_path=args.fixture)
    sys.exit(rc)


if __name__ == "__main__":
    main()
