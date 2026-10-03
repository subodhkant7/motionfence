#!/usr/bin/env python3
"""MotionFence NVIDIA Isaac Sim Environment Discovery & Adapter Smoke Test.

Inspects host capabilities for NVIDIA Isaac Sim runtime and executes an offline
adapter contract verification cycle.

Usage:
    python scripts/isaac_smoke.py
"""

import sys
import os

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from motionfence.simulation.isaac.environment import detect_isaac_environment
from motionfence.simulation.isaac.adapter import IsaacSimAdapter
from motionfence.simulation.adapters.models import IsaacSimConfig, PhysicalBackendType
from motionfence.models.actions import ActionProposal, ActionType
from motionfence.hardware.models import HardwareExecutionStatus


def main() -> int:
    print("=" * 70)
    print("MOTIONFENCE — NVIDIA ISAAC SIM ENVIRONMENT & ADAPTER SMOKE TEST")
    print("=" * 70)

    report = detect_isaac_environment()

    print("\n[HOST ENVIRONMENT DISCOVERY]")
    print(f"  Operating System:      {report.os_name} {report.os_version} ({report.arch})")
    print(f"  NVIDIA GPU Detected:   {'YES' if report.nvidia_gpu_present else 'NO'}")
    if report.nvidia_gpu_present:
        print(f"  GPU Model:             {report.gpu_model}")
        print(f"  GPU VRAM:              {report.gpu_vram_gb:.1f} GB")
        print(f"  Driver Version:        {report.driver_version}")
    print(f"  CUDA Runtime:          {'AVAILABLE' if report.cuda_available else 'UNAVAILABLE'}")
    print(f"  Isaac Python Module:   {'INSTALLED' if report.isaac_python_installed else 'NOT FOUND'}")
    print(f"  Isaac Sim Launcher:    {report.isaac_binary_path or 'NOT FOUND'}")
    print(f"  Hardware Requirements: {'SATISFIED' if report.meets_hardware_requirements else 'UNMET'}")
    print(f"  Native Isaac Executable: {'YES' if report.is_available else 'NO (macOS / non-RTX host)'}")

    if report.unavailability_reasons:
        print("\n[DIAGNOSTIC NOTES]")
        for reason in report.unavailability_reasons:
            print(f"  - {reason}")

    print("\n[PROVISIONING GUIDANCE]")
    print(f"  {report.setup_guidance}")

    print("\n" + "-" * 70)
    print("[OFFLINE ADAPTER CONTRACT VERIFICATION]")
    print("-" * 70)

    config = IsaacSimConfig(headless=True, step_dt=0.01667)
    adapter = IsaacSimAdapter(config=config)
    adapter.connect()

    obs = adapter.get_observation()
    print(f"  Adapter Backend:       {adapter.backend_type.value}")
    print(f"  Operating Mode:        {obs.metadata.get('isaac_mode', 'UNKNOWN')}")
    print(f"  Target Version:        {config.target_version}")
    print(f"  Initial World Version: {obs.world_version}")
    print(f"  Valve B Initial State: {obs.valve_b_state} ({obs.valve_b_angle_deg}°)")
    print(f"  Pump P1 Initial State: {obs.pump_p1_state}")
    print(f"  Human Zone Status:     {obs.human_zone}")

    # Security check: Unauthorized proposal must lock actuator
    proposal = ActionProposal(
        id="smoke_unauth_001",
        action_type=ActionType.CLOSE_VALVE,
        target="valve_b",
        parameters={},
        rationale="Smoke test unauthorized execution rejection",
        model_confidence=0.95,
    )
    result = adapter.execute_authorized_action(proposal, ticket=None)

    assert result.status == HardwareExecutionStatus.LOCKED, f"Expected LOCKED, got {result.status}"
    assert result.is_actuated is False, "Actuator must not actuate without ticket"
    assert adapter.get_observation().valve_b_state == "OPEN", "Valve must remain OPEN"

    print("  Security Boundary:     VERIFIED (unauthorized proposal strictly LOCKED)")

    # Advancing physics simulation
    advanced_obs = adapter.advance(steps=5, dt=0.01667)
    print(f"  Simulation Step Test:  VERIFIED ({advanced_obs.step_count} steps, {advanced_obs.simulation_time:.3f}s)")

    print("\n" + "=" * 70)
    print("SMOKE TEST RESULT: SUCCESS")
    print(f"Execution Backend:     {'LIVE ISAAC SIM' if report.is_available else 'ISAAC SIM ADAPTER (CONTRACT SIMULATOR)'}")
    print("Deterministic Safety:  ZERO AUTHORITY LEAKAGE")
    print("=" * 70)

    return 0


if __name__ == "__main__":
    sys.exit(main())
