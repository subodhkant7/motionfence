#!/usr/bin/env python3
"""CLI script to deterministically replay an adversarial scenario offline (Phase 2H).

Replay Guarantees:
- Requires ZERO network connection.
- Calls ZERO LLMs or model APIs (local deterministic execution).
- Calls ZERO web retrieval (no Tavily).
- Mutates ZERO production state (runs in simulated sandbox).
- Mints no production tickets.
- Dispatches no real hardware signals.
"""

import argparse
import json
import os
import sys

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from motionfence.adversarial.corpus import get_scenario
from motionfence.adversarial.executor import AdversarialScenarioExecutor
from motionfence.adversarial.scenarios import scenario_from_json


def main() -> int:
    parser = argparse.ArgumentParser(description="Deterministic Offline Replay of Adversarial Physical Scenarios")
    parser.add_argument("scenario_id", type=str, help="Scenario identifier (e.g. SCENARIO_A_HUMAN_TOCTOU) or JSON file path")
    parser.add_argument("--seed", type=int, default=42, help="Deterministic seed for execution")
    args = parser.parse_args()

    scenario = None
    target = args.scenario_id

    # 1. Attempt to resolve from standard corpus
    scenario = get_scenario(target)

    # 2. If not in corpus, check if target is a file path
    if scenario is None and os.path.isfile(target):
        try:
            with open(target, "r", encoding="utf-8") as f:
                content = f.read()
                data = json.loads(content)
                if "scenario" in data and isinstance(data["scenario"], dict):
                    scenario = scenario_from_json(json.dumps(data["scenario"]))
                else:
                    scenario = scenario_from_json(content)
        except Exception as e:
            print(f"[ERROR] Failed to load scenario from file '{target}': {e}")
            return 1

    if scenario is None:
        print(f"[ERROR] Could not find scenario with ID '{target}' in corpus or filesystem.")
        print("Available corpus scenarios:")
        from motionfence.adversarial.corpus import list_corpus_scenarios
        for s in list_corpus_scenarios():
            print(f"  - {s.scenario_id}")
        return 1

    print("=" * 72)
    print(f" REPLAYING ADVERSARIAL SCENARIO: {scenario.scenario_id}")
    print("=" * 72)
    print(f"Description:        {scenario.description}")
    print(f"Seed:               {args.seed}")
    print(f"Scheduled Faults:   {len(scenario.fault_schedule)}")
    print(f"Expected Outcome:   {scenario.expected_outcome.value if scenario.expected_outcome else 'N/A'}")
    print("Guarantees:         Offline / Zero LLM / Zero Network / Non-mutating")
    print("-" * 72)

    for i, sf in enumerate(scenario.fault_schedule, 1):
        print(f"  Fault #{i:<2}: [{sf.timing.value:<28}] ({sf.fault.category.value}) {sf.fault.fault_type.value}")
        if sf.fault.description:
            print(f"            Description: {sf.fault.description}")

    print("-" * 72)
    print("[EXECUTION] Executing scenario through deterministic MotionFence control loop...")

    executor = AdversarialScenarioExecutor(seed=args.seed)
    result = executor.execute(scenario)

    print("\n" + "=" * 72)
    print(" REPLAY EXECUTION RESULT")
    print("=" * 72)
    print(f"Scenario ID:           {result.scenario_id}")
    print(f"Outcome:               {result.outcome.value}")
    print(f"Baseline Decision:     {result.baseline_decision.value if result.baseline_decision else 'N/A'}")
    print(f"Adversarial Decision:  {result.adversarial_decision.value if result.adversarial_decision else 'N/A'}")
    print(f"Revalidation Status:   {result.revalidation_status or 'N/A'}")
    print(f"Actuator Success:      {result.execution_success}")
    print(f"Verification Status:   {result.verification_status.value if result.verification_status else 'N/A'}")
    print(f"Critical Unsafe ALLOW: {result.unsafe_allow}")
    print(f"False Denial:          {result.false_denial}")
    print(f"Execution Duration:    {result.duration_seconds * 1000:.2f} ms")
    print(f"State Versions:        Pre-exec v{result.pre_state_version} -> Post-exec v{result.post_state_version}")

    print(f"\nApplied Faults ({len(result.faults_applied)}):")
    for af in result.faults_applied:
        print(f"  * {af}")

    print(f"\nMessage: {result.message}")
    print("=" * 72)

    if scenario.expected_outcome and result.outcome != scenario.expected_outcome:
        print(f"\n[WARNING] Outcome '{result.outcome.value}' diverged from expected '{scenario.expected_outcome.value}'.")
        return 1

    print("\n[SUCCESS] Scenario replayed deterministically matching expected safety properties.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
