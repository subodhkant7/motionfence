#!/usr/bin/env python3
"""Live smoke test for Nebius Token Factory and NVIDIA Nemotron integration.

This script tests live connectivity, authentication, and structured ActionProposal
generation against the real Nebius Token Factory OpenAI-compatible API.

Requires:
    NEBIUS_API_KEY environment variable.

Usage:
    export NEBIUS_API_KEY="your-token-factory-key"
    python scripts/smoke_nebius.py
"""

import os
import sys
import argparse

# Ensure motionfence package is on sys.path
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from motionfence.config.settings import settings
from motionfence.agent.nebius_provider import NebiusNemotronProvider
from motionfence.models.world import WorldState, ValveState, CoolingState, HumanZoneState, LeakState
from motionfence.evidence.models import Evidence, EvidenceSource
from motionfence.agent.exceptions import NebiusProviderError, ModelProposalValidationError


def run_smoke_test(api_key: str, base_url: str, model: str) -> int:
    masked_key = f"{api_key[:6]}...{api_key[-4:]}" if len(api_key) > 10 else "***"
    print("=" * 70)
    print(" NEBIUS TOKEN FACTORY + NVIDIA NEMOTRON SMOKE TEST")
    print("=" * 70)
    print(f"API Key:   {masked_key}")
    print(f"Base URL:  {base_url}")
    print(f"Model:     {model}")
    print("-" * 70)

    # 1. Setup minimal test environment and evidence
    world = WorldState(
        valves={"valve_a": ValveState.OPEN, "valve_b": ValveState.OPEN},
        cooling=CoolingState.ACTIVE,
        leak=LeakState(active=True, target="valve_b", severity=0.85, flow_rate_lpm=12.0),
        human_zone=HumanZoneState.CLEAR,
    )

    evidence_registry = [
        Evidence(
            id="ev_smoke_vis_01",
            source=EvidenceSource.VISION,
            target="valve_b",
            observation={"visual_leak_detected": True, "condensation": True},
            confidence=0.92,
            provenance="camera_overhead_highres",
        ),
        Evidence(
            id="ev_smoke_therm_02",
            source=EvidenceSource.THERMAL_SENSOR,
            target="valve_b",
            observation={"thermal_gradient_c": 16.5, "leak_confirmed": True},
            confidence=0.95,
            provenance="flir_thermal_ptu_01",
        ),
    ]

    intent = "Isolate the leaking line while keeping cooling active."

    print(f"[1] Connecting to Nebius Token Factory...")
    provider = NebiusNemotronProvider(
        api_key=api_key,
        base_url=base_url,
        model=model,
        timeout=30.0,
        max_retries=2,
    )

    print(f"[2] Dispatching prompt to {model}...")
    try:
        proposal = provider.propose(
            intent=intent,
            world_state=world,
            evidence=evidence_registry,
        )
    except NebiusProviderError as e:
        print(f"\n[ERROR] Nebius Token Factory API Error:\n    {e}")
        return 1
    except ModelProposalValidationError as e:
        print(f"\n[ERROR] Model Proposal Validation Error:\n    {e}")
        return 2
    except Exception as e:
        print(f"\n[ERROR] Unexpected error:\n    {e}")
        return 3

    print(f"\n[3] Model Response Validated Successfully!")
    print(f"    - Action:                  {proposal.action_type.value}")
    print(f"    - Target:                  {proposal.target}")
    print(f"    - Model Confidence:        {proposal.model_confidence:.2f}")
    print(f"    - Rationale:               {proposal.rationale}")
    print(f"    - Supporting Evidence IDs: {proposal.supporting_evidence_ids}")

    print("\n" + "=" * 70)
    print(" SMOKE TEST RESULT: PASSED")
    print(" Verified: Real Nebius Token Factory returned a valid ActionProposal")
    print("=" * 70)
    return 0


def main() -> int:
    parser = argparse.ArgumentParser(description="Live smoke test for Nebius Token Factory integration.")
    parser.add_argument("--api-key", default=None, help="Nebius API key (defaults to NEBIUS_API_KEY env var)")
    parser.add_argument("--base-url", default=None, help="Nebius base URL (defaults to NEBIUS_BASE_URL env var)")
    parser.add_argument("--model", default=None, help="Model name (defaults to NEBIUS_MODEL env var)")
    args = parser.parse_args()

    api_key = args.api_key or os.getenv("NEBIUS_API_KEY")
    if not api_key:
        print("=" * 70)
        print(" NEBIUS SMOKE TEST: SKIPPED (No API Key)")
        print("=" * 70)
        print("To run the live smoke test against Nebius Token Factory:")
        print("  1. Obtain an API key from Nebius Token Factory (https://tokenfactory.nebius.com)")
        print("  2. export NEBIUS_API_KEY='your-nebius-api-key'")
        print("  3. python scripts/smoke_nebius.py")
        print("=" * 70)
        return 1

    base_url = args.base_url or os.getenv("NEBIUS_BASE_URL", "https://api.tokenfactory.nebius.com/v1/")
    model = args.model or os.getenv("NEBIUS_MODEL", "nvidia/nemotron-3-super-120b-a12b")

    return run_smoke_test(api_key, base_url, model)


if __name__ == "__main__":
    sys.exit(main())
