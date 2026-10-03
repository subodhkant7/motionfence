#!/usr/bin/env python3
"""MotionFence Live Public Telemetry CLI Runner (Phase 2O).

Acquires real-world physical observations from the modern USGS Water Data OGC API,
normalizes them with cryptographic provenance and freshness checks,
injects them as Evidence into MotionFence WorldState, and optionally runs
a live AI ActionProposal evaluation.

SECURITY INVARIANTS:
1. Public telemetry is strictly an OBSERVATION source; it has ZERO actuation authority.
2. Fails closed on any network, schema, or semantic failure.
3. Observes rate limits: single explicit fetch by default; zero aggressive polling.
4. Preserves semantic honesty: real river telemetry != internal pump/actuator state.

Usage:
    python scripts/live_public_telemetry.py
    python scripts/live_public_telemetry.py --location USGS-01646500
    python scripts/live_public_telemetry.py --live-ai
"""

import argparse
from datetime import datetime, timezone
import json
import os
import sys
import time
from typing import Optional

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from motionfence.telemetry import (
    ObservationFreshness,
    ObservationSnapshot,
    TelemetryConfig,
    TelemetryEvidenceAdapter,
    TelemetryMode,
    TelemetryStatus,
    USGSOgcTelemetryProvider,
)
from motionfence.models.world import WorldState, ValveState, CoolingState, HumanZoneState
from motionfence.models.actions import ActionProposal, ActionType
from motionfence.policy.engine import PolicyEngine
from motionfence.policy.models import Policy
from motionfence.simulation.world import PhysicalWorld
from motionfence.agent.nebius_provider import NebiusNemotronProvider
from motionfence.config.settings import settings


def print_banner(title: str, stream=None) -> None:
    stream = stream or sys.stdout
    print("\n" + "=" * 78, file=stream)
    print(f" {title}", file=stream)
    print("=" * 78, file=stream)


def print_observation_box(obs: ObservationSnapshot, mode: str = "LIVE", stream=None) -> None:
    stream = stream or sys.stdout
    w = 76
    print("┌" + "─" * (w - 2) + "┐", file=stream)
    title = f" REAL-WORLD PUBLIC OBSERVATION ({mode})"
    print(f"│{title}".ljust(w - 1) + "│", file=stream)
    print("├" + "─" * (w - 2) + "┤", file=stream)
    print(f"│  Source Provider:     {obs.provider} ({obs.source_system})".ljust(w - 1) + "│", file=stream)
    print(f"│  Station ID:          {obs.monitoring_location_id}".ljust(w - 1) + "│", file=stream)
    loc_name = obs.monitoring_location_name or "N/A"
    print(f"│  Station Name:        {loc_name[:w - 26]}".ljust(w - 1) + "│", file=stream)
    print(f"│  Parameter:           {obs.parameter_code} — {obs.parameter_name}".ljust(w - 1) + "│", file=stream)
    print(f"│  Value & Unit:        {obs.raw_value} {obs.unit}".ljust(w - 1) + "│", file=stream)
    print(f"│  Observation Time:    {obs.observed_at}".ljust(w - 1) + "│", file=stream)
    print(f"│  Freshness:           [{obs.freshness.value}] (age: {obs.freshness_age_seconds:.0f}s)".ljust(w - 1) + "│", file=stream)
    print(f"│  Approval / Qual:     {obs.approval_status or 'N/A'} / {obs.qualifier or 'None'}".ljust(w - 1) + "│", file=stream)
    print(f"│  Provenance Hash:     {obs.provenance_hash[:16]}...".ljust(w - 1) + "│", file=stream)
    print(f"│  Canonical Hash:      {obs.raw_record_hash[:16]}...".ljust(w - 1) + "│", file=stream)
    print("└" + "─" * (w - 2) + "┘", file=stream)


def run_live_public_telemetry(
    location_id: Optional[str] = None,
    run_live_ai: bool = False,
    save_fixture: bool = True,
    stream=None,
) -> int:
    stream = stream or sys.stdout

    config = TelemetryConfig()
    if location_id:
        config.monitoring_location_id = location_id

    print_banner(f"PHASE 2O: REAL-WORLD PUBLIC TELEMETRY ACQUISITION ({config.monitoring_location_id})", stream)
    print(f"Calling modern USGS OGC API: {config.base_url}/collections/latest-continuous/items", file=stream)

    provider = USGSOgcTelemetryProvider(config=config)
    start_time = time.time()
    snapshots = provider.fetch_latest_observations()
    elapsed = time.time() - start_time

    status = provider.get_last_status()
    details = provider.get_status_details()

    if status != TelemetryStatus.SUCCESS or not snapshots:
        print(f"\n[FAIL CLOSED] Telemetry acquisition failed: {status.value}", file=stream)
        print(f"Details: {json.dumps(details, indent=2)}", file=stream)
        print("\nSECURITY INVARIANT ENFORCED: Missing observation fails closed; zero authorization granted.", file=stream)
        return 1

    print(f"\n[SUCCESS] Retrieved {len(snapshots)} observation(s) in {elapsed:.2f}s (Status: {status.value})", file=stream)

    for s in snapshots:
        print_observation_box(s, mode="LIVE", stream=stream)

    # 1. Translate observations into Evidence
    print("\n--- STAGE 1: EVIDENCE TRANSLATION & FRESHNESS GATING ---", file=stream)
    evidence_items = TelemetryEvidenceAdapter.to_evidence_list(snapshots)
    for ev in evidence_items:
        print(f"  • Ingested Evidence: {ev.id} (target: {ev.target}, conf: {ev.confidence:.2f})", file=stream)
        print(f"    Lineage: {ev.provenance}", file=stream)

    # 2. Derive deterministic environmental context
    discharge_obs = next((s for s in snapshots if s.parameter_code == "00060"), snapshots[0])
    derived_ctx = TelemetryEvidenceAdapter.derive_environmental_flow_context(
        discharge_obs,
        high_flow_threshold_cfs=5000.0,
    )
    print(f"\n--- STAGE 2: DETERMINISTIC ENVIRONMENTAL CONTEXT DERIVATION ---", file=stream)
    print(f"  • Context Name:   {derived_ctx.context_name}", file=stream)
    print(f"  • Classification: {derived_ctx.classification} (Threshold: {derived_ctx.threshold_value} {derived_ctx.unit})", file=stream)
    print(f"  • Observed Flow:  {derived_ctx.observed_metric_value} {derived_ctx.unit}", file=stream)
    print(f"  • Derivation ID:  {derived_ctx.rule_id} [hash:{derived_ctx.deterministic_hash[:12]}]", file=stream)

    # 3. Inject into WorldState
    world = PhysicalWorld()
    world.set_pump_state("pump_p1", "INACTIVE")
    world.set_human_zone(HumanZoneState.CLEAR)
    world.valves["valve_b"] = ValveState.OPEN

    ws = world.get_state()
    TelemetryEvidenceAdapter.attach_to_world_state(ws, snapshots, derived_ctx)
    print(f"\n--- STAGE 3: MOTIONFENCE WORLDSTATE NAMESPACE ATTACHMENT ---", file=stream)
    print(f"  • Modeled Plant:        PUMP P1={ws.pumps.get('pump_p1')} | VALVE B={ws.valves.get('valve_b').value} | HUMAN ZONE={ws.human_zone.value}", file=stream)
    print(f"  • External Observation: USGS streamflow={ws.external_observations['usgs'].get('streamflow_cfs', {}).get('value')} cfs", file=stream)
    print(f"  • Env Classification:   {ws.external_observations.get('environmental_context', {}).get('classification')}", file=stream)
    print("  • Semantic Distinction: Real river measurement is strictly separated from internal plant state.", file=stream)

    # 4. Optional Live Nemotron proposal
    if run_live_ai:
        print_banner("OPTIONAL: LIVE NEMOTRON PROPOSAL OVER CONTEXT", stream)
        provider_llm = NebiusNemotronProvider()
        intent = (
            f"River streamflow at {discharge_obs.monitoring_location_name} is currently {discharge_obs.raw_value} {discharge_obs.unit} "
            f"({derived_ctx.classification}). Propose an action for valve_b to ensure proper drainage while human zone is CLEAR."
        )
        print(f"Intent Prompt: {intent}", file=stream)
        proposal = provider_llm.generate_action_proposal(intent, ws, evidence_items)
        print(f"\nGenerated Proposal: {proposal.action_type.value} on target='{proposal.target}'", file=stream)
        print(f"Confidence: {proposal.model_confidence:.2f} | Rationale: {proposal.rationale}", file=stream)

        # 5. Deterministic Policy Evaluation
        print("\n--- STAGE 5: MOTIONFENCE DETERMINISTIC POLICY GATE ---", file=stream)
        policy = Policy()
        decision = PolicyEngine.evaluate(proposal, ws, evidence_items, policy)
        print(f"Decision: [{decision.decision.value}] (Proposal: {proposal.action_type.value})", file=stream)
        for r in decision.reasons:
            print(f"  • {r.constraint}: {r.status} — {r.details}", file=stream)

    # 6. Save replay artifact if requested
    if save_fixture:
        out_path = os.path.abspath(
            os.path.join(os.path.dirname(__file__), "..", "motionfence", "fixtures", "live_demo", "telemetry_observation.json")
        )
        os.makedirs(os.path.dirname(out_path), exist_ok=True)
        rec_data = {
            "record_id": f"rec_usgs_{int(time.time())}",
            "mode": TelemetryMode.REPLAYED_OBSERVATION.value,
            "recorded_at": datetime.now(timezone.utc).isoformat(),
            "context_metadata": {
                "provider": "USGS",
                "station_id": config.monitoring_location_id,
                "station_name": config.monitoring_location_name,
                "api_endpoint": f"{config.base_url}/collections/latest-continuous/items",
                "derived_context": derived_ctx.model_dump(),
            },
            "snapshots": [s.model_dump() for s in snapshots],
        }
        with open(out_path, "w", encoding="utf-8") as f:
            json.dump(rec_data, f, indent=2)
        print(f"\n[ARTIFACT] Saved verified telemetry replay fixture to: {out_path}", file=stream)

    print("\nPhase 2O public telemetry execution completed successfully.", file=stream)
    return 0


def main():
    parser = argparse.ArgumentParser(description="MotionFence Live Public Telemetry CLI (Phase 2O)")
    parser.add_argument("--location", default="USGS-01646500", help="USGS Monitoring Location ID (default: USGS-01646500)")
    parser.add_argument("--live-ai", action="store_true", help="Optionally query live Nemotron model using the observation context")
    parser.add_argument("--no-save", action="store_true", help="Do not overwrite canonical telemetry fixture")

    args = parser.parse_args()
    rc = run_live_public_telemetry(
        location_id=args.location,
        run_live_ai=args.live_ai,
        save_fixture=not args.no_save,
    )
    sys.exit(rc)


if __name__ == "__main__":
    main()
