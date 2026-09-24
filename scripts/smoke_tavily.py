#!/usr/bin/env python3
"""Live smoke test for Tavily Search Provider integration.

This script tests live connectivity, authentication, and retrieval of external
engineering documentation and operational knowledge using the Tavily Search API.

Requires:
    TAVILY_API_KEY environment variable.

Usage:
    export TAVILY_API_KEY="your-tavily-api-key"
    python scripts/smoke_tavily.py
"""

import os
import sys
import argparse

# Ensure motionfence package is on sys.path
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from motionfence.config.settings import settings
from motionfence.knowledge.tavily_provider import TavilyKnowledgeProvider
from motionfence.knowledge.provider import TavilyProviderError


def run_smoke_test(api_key: str, query: str, max_results: int) -> int:
    masked_key = f"{api_key[:6]}...{api_key[-4:]}" if len(api_key) > 10 else "***"
    print("=" * 70)
    print(" TAVILY SEARCH PROVIDER LIVE SMOKE TEST")
    print("=" * 70)
    print(f"API Key:       {masked_key}")
    print(f"Query:         '{query}'")
    print(f"Max Results:   {max_results}")
    print("-" * 70)

    print("[1] Initializing TavilyKnowledgeProvider...")
    provider = TavilyKnowledgeProvider(
        api_key=api_key,
        timeout=15.0,
        max_results=max_results,
    )

    print(f"[2] Executing search query against Tavily API: '{query}'...")
    try:
        evidence_list = provider.retrieve(query)
    except TavilyProviderError as e:
        print(f"\n[ERROR] Tavily Provider Error:\n    {e}")
        return 1
    except Exception as e:
        print(f"\n[ERROR] Unexpected error during retrieval:\n    {e}")
        return 2

    print(f"\n[3] Search Completed Successfully! Retrieved {len(evidence_list)} evidence item(s).")
    for idx, ev in enumerate(evidence_list, start=1):
        print(f"\n    --- Result #{idx} ---")
        print(f"    ID:          {ev.id}")
        print(f"    Title:       {ev.title}")
        print(f"    Source URL:  {ev.source_url}")
        print(f"    Provenance:  {ev.provenance}")
        print(f"    Confidence:  {ev.confidence:.2f}")
        print(f"    Trust State: {ev.trust_status.value}")
        snippet = ev.content[:140].replace("\n", " ") + ("..." if len(ev.content) > 140 else "")
        print(f"    Snippet:     {snippet}")

    print("\n" + "=" * 70)
    print(" SMOKE TEST RESULT: PASSED")
    print(f" Verified: Real Tavily API returned {len(evidence_list)} structured evidence item(s).")
    print("=" * 70)
    return 0


def main() -> int:
    parser = argparse.ArgumentParser(description="Live smoke test for Tavily Search Provider.")
    parser.add_argument("--api-key", default=None, help="Tavily API key (defaults to TAVILY_API_KEY env var)")
    parser.add_argument("--query", default="industrial centrifugal pump valve isolation procedure safety standards", help="Test query")
    parser.add_argument("--max-results", type=int, default=3, help="Max results to retrieve")
    args = parser.parse_args()

    api_key = args.api_key or os.getenv("TAVILY_API_KEY")
    # If no key or placeholder offline key is present, report skip and exit non-zero
    if not api_key or api_key == "placeholder_key_offline":
        print("=" * 70)
        print(" TAVILY SMOKE TEST: SKIPPED — no API key configured")
        print("=" * 70)
        print("To run the live smoke test against Tavily Search API:")
        print("  1. Obtain an API key from Tavily (https://tavily.com)")
        print("  2. export TAVILY_API_KEY='your-tavily-api-key'")
        print("  3. python scripts/smoke_tavily.py")
        print("=" * 70)
        return 1

    return run_smoke_test(api_key, args.query, args.max_results)


if __name__ == "__main__":
    sys.exit(main())
