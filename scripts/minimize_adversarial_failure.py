#!/usr/bin/env python3
"""CLI script to automatically shrink failing compound adversarial scenarios (Phase 2H).

Demonstrates delta-debugging minimization: reducing a complex multi-fault scenario
(e.g., 5 simultaneous disturbances) down to the minimal essential fault set required
to trigger the safety condition, producing an understandable, auditable counterexample.
"""

import argparse
import json
import os
import sys

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from motionfence.adversarial.corpus import get_scenario
from motionfence.adversarial.models import (
    FaultCategory,
    FaultSeverity,
    FaultTiming,
    FaultType,
    ScenarioOutcome,
)
from motionfence.adversarial.reporting import AutomaticShrinker
from motionfence.adversarial.scenarios import ScenarioBuilder, scenario_from_json


def create_deliberate_compound_scenario() -> ScenarioBuilder:
    """Constructs a test-only compound scenario with 5 simultaneous disturbances."""
    return (
        ScenarioBuilder("DELIBERATE_COMPOUND_FAILURE")
        .with_description("Compound multi-fault disturbance: 5 faults injected across lifecycle")
        .with_seed(42)
        .expect_outcome(ScenarioOutcome.SAFE_REVALIDATION_BLOCK)
        .add_fault(
            fault_type=FaultType.SENSOR_NOISE,
            category=FaultCategory.SENSOR,
            timing=FaultTiming.AFTER_OBSERVATION,
            severity=FaultSeverity.LOW,
            parameters={"noise_std": 0.01},
            description="Superficial sensor noise (non-blocking)",
        )
        .add_fault(
            fault_type=FaultType.SENSOR_BIAS,
            category=FaultCategory.SENSOR,
            timing=FaultTiming.AFTER_OBSERVATION,
            severity=FaultSeverity.LOW,
            parameters={"bias_psi": 0.1},
            description="Negligible pressure bias (+0.1 psi)",
        )
        .add_fault(
            fault_type=FaultType.HUMAN_ENTERS_ZONE,
            category=FaultCategory.HUMAN,
            timing=FaultTiming.BEFORE_EXECUTION,
            severity=FaultSeverity.CRITICAL,
            description="Critical invariant breach: human enters valve zone right before execution",
        )
        .add_fault(
            fault_type=FaultType.VALVE_JAM,
            category=FaultCategory.EQUIPMENT,
            timing=FaultTiming.DURING_EXECUTION,
            severity=FaultSeverity.HIGH,
            description="Secondary mechanical jam downstream",
        )
        .add_fault(
            fault_type=FaultType.ACTUATOR_DELAY,
            category=FaultCategory.EQUIPMENT,
            timing=FaultTiming.DURING_EXECUTION,
            severity=FaultSeverity.LOW,
            description="Minor pneumatic delay during stroke",
        )
        .build()
    )


def main() -> int:
    parser = argparse.ArgumentParser(description="Delta-Debugging Fault Minimizer for Adversarial Scenarios")
    parser.add_argument("scenario_id", nargs="?", default="DELIBERATE_COMPOUND_FAILURE", help="Scenario ID or JSON file to minimize")
    parser.add_argument("--output-dir", type=str, default=".adversarial/counterexamples", help="Directory for minimal counterexample")
    args = parser.parse_args()

    target = args.scenario_id
    scenario = None

    if target == "DELIBERATE_COMPOUND_FAILURE":
        scenario = create_deliberate_compound_scenario()
    else:
        scenario = get_scenario(target)
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
                print(f"[ERROR] Failed to load scenario from '{target}': {e}")
                return 1

    if scenario is None:
        print(f"[ERROR] Could not resolve scenario '{target}'.")
        return 1

    print("=" * 72)
    print(" AUTOMATIC DELTA-DEBUGGING ADVERSARIAL SHRINKER (PHASE 2H)")
    print("=" * 72)
    print(f"Scenario ID:         {scenario.scenario_id}")
    print(f"Initial Fault Count: {len(scenario.fault_schedule)}")
    print(f"Initial Faults:")
    for sf in scenario.fault_schedule:
        print(f"  - [{sf.timing.value}] {sf.fault.fault_type.value}: {sf.fault.description}")
    print("-" * 72)

    shrinker = AutomaticShrinker()
    target_outcome = scenario.expected_outcome or ScenarioOutcome.SAFE_REVALIDATION_BLOCK
    failure_predicate = lambda res: res.outcome == target_outcome

    print(f"[SHRINKING] Minimizing fault schedule towards condition '{target_outcome.value}'...")
    counterexample = shrinker.shrink(
        failing_scenario=scenario,
        failure_predicate=failure_predicate,
    )

    print("\n" + "=" * 72)
    print(" MINIMIZED COUNTEREXAMPLE RESULT")
    print("=" * 72)
    print(f"Counterexample ID:   {counterexample.counterexample_id}")
    print(f"Shrunk Status:       {counterexample.shrunk}")
    print(f"Initial Faults:      {len(scenario.fault_schedule)}")
    print(f"Minimal Faults:      {counterexample.minimal_fault_count}")
    print(f"Active Faults Retained:")
    for f in counterexample.faults:
        print(f"  * {f}")

    os.makedirs(args.output_dir, exist_ok=True)
    out_path = os.path.join(args.output_dir, f"minimized_{counterexample.scenario_id}.json")
    with open(out_path, "w", encoding="utf-8") as f:
        f.write(counterexample.model_dump_json(indent=2))

    print(f"\n[OK] Minimized counterexample artifact written to: {out_path}")
    print("=" * 72)
    return 0


if __name__ == "__main__":
    sys.exit(main())
