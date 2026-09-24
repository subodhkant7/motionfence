#!/usr/bin/env python3
"""Live smoke test for Nebius Token Factory and NVIDIA Nemotron integration (Request 1).

Tests live connectivity, authentication, and basic completion against the real
Nebius Token Factory OpenAI-compatible API using a deliberately minimal prompt
to strictly cap credit consumption.

SECURITY INVARIANTS:
- NEVER logs, prints, or exposes API credentials.
- Strictly cost-bounded with max_tokens cap.

Usage:
    python scripts/smoke_nebius.py
"""

import os
import sys
import time
import argparse
from openai import OpenAI

# Ensure motionfence package is on sys.path
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from motionfence.config.settings import settings


def run_smoke_test(api_key: str, base_url: str, model: str) -> int:
    print("=" * 70)
    print(" NEBIUS TOKEN FACTORY + NVIDIA NEMOTRON SMOKE TEST (REQUEST 1)")
    print("=" * 70)
    print("API Key:   [CONFIGURED]")
    print(f"Base URL:  {base_url}")
    print(f"Model:     {model}")
    print("-" * 70)

    print(f"[1] Connecting to Nebius Token Factory...")
    client = OpenAI(
        api_key=api_key,
        base_url=base_url,
        timeout=settings.nebius.timeout_seconds,
    )

    minimal_prompt = "Ping. Respond with 'MOTIONFENCE_ONLINE'."
    print(f"[2] Dispatching minimal connectivity prompt (max_tokens=50) to {model}...")

    t0 = time.time()
    try:
        response = client.chat.completions.create(
            model=model,
            messages=[{"role": "user", "content": minimal_prompt}],
            temperature=0.0,
            max_tokens=50,
            timeout=settings.nebius.timeout_seconds,
        )
        latency_ms = (time.time() - t0) * 1000.0
    except Exception as e:
        print(f"\n[ERROR] Nebius Token Factory Connection/API Error:\n    {e}")
        return 1

    if not response.choices or not response.choices[0].message.content:
        print("\n[ERROR] Received empty response from model.")
        return 2

    raw_content = response.choices[0].message.content.strip()

    # Capture token usage metadata safely
    usage_info = {}
    if getattr(response, "usage", None):
        usage_info = {
            "prompt_tokens": getattr(response.usage, "prompt_tokens", None),
            "completion_tokens": getattr(response.usage, "completion_tokens", None),
            "total_tokens": getattr(response.usage, "total_tokens", None),
        }

    print(f"\n[3] Model Response Received Successfully!")
    print(f"    - Response text:   {raw_content}")
    print(f"    - Finish reason:   {response.choices[0].finish_reason}")
    print(f"    - Latency:         {latency_ms:.1f}ms")
    print(f"    - Prompt Tokens:   {usage_info.get('prompt_tokens', 'N/A')}")
    print(f"    - Response Tokens: {usage_info.get('completion_tokens', 'N/A')}")
    print(f"    - Total Tokens:    {usage_info.get('total_tokens', 'N/A')}")

    print("\n" + "=" * 70)
    print(" SMOKE TEST RESULT: PASSED")
    print(f" Verified: Real Token Factory connectivity confirmed for model {model}")
    print("=" * 70)
    return 0


def main() -> int:
    parser = argparse.ArgumentParser(description="Live connectivity smoke test for Nebius Token Factory.")
    parser.add_argument("--api-key", default=None, help="Nebius API key (defaults to NEBIUS_API_KEY env var)")
    parser.add_argument("--base-url", default=None, help="Nebius base URL (defaults to NEBIUS_BASE_URL env var)")
    parser.add_argument("--model", default=None, help="Model name (defaults to NEBIUS_MODEL env var)")
    args = parser.parse_args()

    api_key = args.api_key or settings.nebius.api_key
    if not api_key or api_key == "placeholder_key_offline":
        print("=" * 70)
        print(" NEBIUS SMOKE TEST: SKIPPED (No API Key)")
        print("=" * 70)
        print("Status: NEBIUS_API_KEY configured = NO")
        return 1

    base_url = args.base_url or settings.nebius.base_url
    model = args.model or settings.nebius.model

    return run_smoke_test(api_key, base_url, model)


if __name__ == "__main__":
    sys.exit(main())
