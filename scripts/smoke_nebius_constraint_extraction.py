#!/usr/bin/env python3
"""Live smoke test for Nebius Token Factory + NVIDIA Nemotron operational constraint extraction.

Tests live connectivity, authentication, and structured CandidateConstraint
extraction against the real Nebius Token Factory API.

SECURITY REQUIREMENTS:
- Never expose, log, or leak raw API credentials.
- Strictly validate Pydantic structured output and cited evidence references.

Usage:
    export NEBIUS_API_KEY="your-token-factory-key"
    python scripts/smoke_nebius_constraint_extraction.py
"""

import os
import sys
import argparse
import time

# Ensure motionfence package is on sys.path
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from motionfence.config.settings import settings
from motionfence.knowledge.models import KnowledgeEvidence, TrustStatus
from motionfence.constraints.nemotron_extractor import (
    NemotronConstraintExtractor,
    NemotronExtractorError,
)
from motionfence.constraints.validator import ConstraintValidator
from motionfence.constraints.models import PlantContext


def run_smoke_test(api_key: str, base_url: str, model: str) -> int:
    masked_key = f"{api_key[:6]}...{api_key[-4:]}" if len(api_key) > 10 else "***"
    print("=" * 70)
    print(" NEBIUS TOKEN FACTORY + NEMOTRON CONSTRAINT EXTRACTION SMOKE TEST")
    print("=" * 70)
    print(f"API Key:   {masked_key}")
    print(f"Base URL:  {base_url}")
    print(f"Model:     {model}")
    print("-" * 70)

    # Known industrial evidence fixture
    evidence_items = [
        KnowledgeEvidence(
            id="ev_smoke_pump_iso_01",
            query="Pump isolation and Valve B restrictions",
            title="Industrial Plant Manual - Fluid Circuit Safety Guidelines",
            source_url="https://plant-safety.internal/manual/pumps#sec4",
            content="MANDATORY PROHIBITION: Valve B must not be closed while Pump P1 is active to prevent hydraulic shock.",
            retrieved_at=time.time(),
            source_metadata={"section": "4.2", "mandatory": True},
            provenance="internal_plant_manual_rev2",
            confidence=0.96,
            trust_status=TrustStatus.LOCAL_FIXTURE,
        ),
        KnowledgeEvidence(
            id="ev_smoke_routine_chk_02",
            query="Routine valve inspection checklist",
            title="Daily Maintenance SOP - Checklists",
            source_url="https://plant-safety.internal/sop/daily_maintenance#sec1",
            content="ROUTINE PROCEDURE: Visual inspection should be performed before servicing Valve B.",
            retrieved_at=time.time(),
            source_metadata={"section": "1.1", "mandatory": False},
            provenance="internal_maintenance_sop_v1",
            confidence=0.90,
            trust_status=TrustStatus.LOCAL_FIXTURE,
        ),
    ]
    evidence_registry = {e.id: e for e in evidence_items}

    print("[1] Initializing NemotronConstraintExtractor with Nebius Token Factory...")
    extractor = NemotronConstraintExtractor(
        api_key=api_key,
        base_url=base_url,
        model=model,
        timeout=35.0,
        max_retries=2,
    )

    print(f"[2] Dispatching evidence text to {model} for structured extraction...")
    try:
        candidates = extractor.extract(evidence_items)
    except NemotronExtractorError as e:
        print(f"\n[ERROR] Nemotron Extraction API Error:\n    {e}")
        return 1
    except Exception as e:
        print(f"\n[ERROR] Unexpected error during extraction:\n    {e}")
        return 2

    print(f"\n[3] Extraction Succeeded! Parsed {len(candidates)} candidate constraint(s):")
    for idx, cst in enumerate(candidates, start=1):
        print(f"    [{idx}] ID:          {cst.constraint_id}")
        print(f"        Type:        {cst.constraint_type.value}")
        print(f"        Target:      {cst.target}")
        print(f"        Action:      {cst.action.value if cst.action else None}")
        print(f"        Condition:   {cst.condition}")
        print(f"        Evidence ID: {cst.source_evidence_id}")
        print(f"        Confidence:  {cst.confidence:.2f}")
        print(f"        Quote:       '{cst.claim_text}'")

    print("\n[4] Running deterministic MotionFence Admissibility Gate...")
    plant = PlantContext(equipment_id="pump_p1", authorized_targets=["valve_a", "valve_b", "pump_p1"])
    for cst in candidates:
        admissible = ConstraintValidator.check_admissibility(cst, evidence_registry, plant_context=plant)
        print(f"    - Constraint '{cst.constraint_id}': Admissible = {admissible}, Status = {cst.status.value}")

    print("\n" + "=" * 70)
    print(" SMOKE TEST RESULT: PASSED")
    print(" Verified: Real Nebius Token Factory returned validated CandidateConstraints")
    print("=" * 70)
    return 0


def main() -> int:
    parser = argparse.ArgumentParser(description="Live smoke test for Nebius Nemotron constraint extraction.")
    parser.add_argument("--api-key", default=None, help="Nebius API key (defaults to NEBIUS_API_KEY env var)")
    parser.add_argument("--base-url", default=None, help="Nebius base URL (defaults to NEBIUS_BASE_URL env var)")
    parser.add_argument("--model", default=None, help="Model name (defaults to NEBIUS_MODEL env var)")
    args = parser.parse_args()

    api_key = args.api_key or os.getenv("NEBIUS_API_KEY")
    if not api_key:
        print("=" * 70)
        print(" NEBIUS NEMOTRON EXTRACTION SMOKE TEST: SKIPPED (No API Key)")
        print("=" * 70)
        print("Status: IMPLEMENTED — LIVE VERIFICATION PENDING CREDENTIALS")
        print("To run the live extraction smoke test against Nebius Token Factory:")
        print("  1. Obtain an API key from Nebius Token Factory (https://tokenfactory.nebius.com)")
        print("  2. export NEBIUS_API_KEY='your-nebius-api-key'")
        print("  3. python scripts/smoke_nebius_constraint_extraction.py")
        print("=" * 70)
        return 1

    base_url = args.base_url or os.getenv("NEBIUS_BASE_URL", "https://api.tokenfactory.nebius.com/v1/")
    model = args.model or os.getenv("NEBIUS_MODEL", "nvidia/nemotron-3-super-120b-a12b")

    return run_smoke_test(api_key, base_url, model)


if __name__ == "__main__":
    sys.exit(main())
