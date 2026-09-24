#!/usr/bin/env python3
"""CLI utility for deterministic, offline replay of dynamic physical trajectories (Phase 2K).

SECURITY INVARIANTS:
1. Replay is 100% offline and side-effect free.
2. ZERO ticket minting and ZERO actuator authority.
3. CANNOT alter production policies or live plant world state.
4. Identical canonical results for identical inputs.

Usage:
    python scripts/replay_trajectory.py <trajectory_id_or_file> [--seed <int>]
"""

import argparse
import json
import os
import sys

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from motionfence.policy.models import Policy
from motionfence.policy_mutation.models import DynamicTrajectory
from motionfence.policy_mutation.trajectory import DynamicTrajectoryEvaluator, TrajectoryGenerator


def replay_trajectory(trajectory_id_or_file: str, seed: int = 42) -> int:
    """Load and deterministically replay a physical trajectory."""
    traj: DynamicTrajectory

    if os.path.exists(trajectory_id_or_file):
        with open(trajectory_id_or_file, "r", encoding="utf-8") as f:
            data = json.load(f)
        traj = DynamicTrajectory(**data)
    else:
        # Search canonical generated trajectories
        canonical = TrajectoryGenerator.generate_trajectories(seed=seed, depths=[3, 5, 8])
        matched = [t for t in canonical if t.trajectory_id == trajectory_id_or_file or trajectory_id_or_file in t.trajectory_id]
        if not matched:
            print(f"Error: Trajectory '{trajectory_id_or_file}' not found in canonical corpus or file.", file=sys.stderr)
            return 1
        traj = matched[0]

    evaluator = DynamicTrajectoryEvaluator()
    policy = Policy()

    print("=" * 70)
    print(" MOTIONFENCE DETERMINISTIC TRAJECTORY REPLAY (PHASE 2K)")
    print("=" * 70)
    print(f"Trajectory ID:   {traj.trajectory_id}")
    print(f"Description:     {traj.description}")
    print(f"Step Count:      {len(traj.steps)}")
    print(f"Max Depth:       {traj.max_depth}")
    print(f"Replay Mode:     100% OFFLINE, ZERO NETWORK, ZERO ACTUATION")
    print("-" * 70)
    print("Steps Replayed:")
    for s in traj.steps:
        fault_tag = f" [FAULT: {s.fault}]" if s.fault else ""
        act_tag = f" [ACTION: {s.action}]" if s.action else ""
        print(f"  t{s.step_index}: {s.event_name}{act_tag}{fault_tag}")

    result = evaluator.evaluate_trajectory(traj, policy, baseline_policy=policy)
    print("-" * 70)
    print(f"Evaluated Outcome: {result.outcome.value}")
    print(f"Is Regression:     {result.is_regression}")
    print(f"New Unsafe ALLOWs: {result.new_unsafe_allows}")
    print(f"Explanation:       {result.explanation}")
    print("=" * 70)

    return 0


def main() -> int:
    parser = argparse.ArgumentParser(description="Replay a MotionFence dynamic physical trajectory")
    parser.add_argument("trajectory_id", help="Trajectory ID (e.g. traj_s42_d5_human_incursion_...) or JSON file path")
    parser.add_argument("--seed", type=int, default=42, help="Deterministic generation seed")
    args = parser.parse_args()
    return replay_trajectory(args.trajectory_id, args.seed)


if __name__ == "__main__":
    sys.exit(main())
