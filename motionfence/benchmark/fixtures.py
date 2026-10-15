"""Deterministic Plant Fixtures and Boundary Fault Injectors.

Provides deterministic test doubles at the provider and plant boundaries
to evaluate MotionFence's actual PolicyEngine, SafetyEnclave, TicketAuthority,
ExecutionTimeRevalidator, MockHardwareEndpoint, PostActionVerifier, and RecoveryExecutor
without reaching real hardware or requiring network access to external AI services.
"""

from __future__ import annotations

import time
from typing import Any, Dict, List, Optional
from motionfence.agent.exceptions import NebiusProviderError
from motionfence.agent.provider import ActionProposalProvider
from motionfence.evidence.models import Evidence
from motionfence.hardware.mock import MockHardwareEndpoint
from motionfence.hardware.models import HardwareFaultType
from motionfence.models.actions import ActionProposal, ActionType
from motionfence.models.world import CoolingState, HumanZoneState, LeakState, ValveState, WorldState
from motionfence.simulation.world import PhysicalWorld


class DeterministicBenchmarkProvider(ActionProposalProvider):
    """Deterministic proposal provider with configurable boundary fault injection."""

    def __init__(
        self,
        fault_type: Optional[str] = None,
        fault_params: Optional[Dict[str, Any]] = None,
    ):
        self.provider_name = "benchmark_deterministic_provider"
        self.model = "nemotron-benchmark-fixture"
        self.fault_type = fault_type
        self.fault_params = fault_params or {}

    def propose(
        self,
        intent: str,
        world_state: WorldState,
        evidence: List[Evidence],
    ) -> ActionProposal:
        """Propose an action or inject an expected provider failure."""
        if self.fault_type == "PROVIDER_TIMEOUT":
            raise NebiusProviderError(
                status_code=504,
                message=self.fault_params.get("message", "Gateway Timeout during model inference."),
                classification="TIMEOUT",
                provider="nebius",
                model=self.model,
            )

        if self.fault_type == "PROVIDER_HTTP_503":
            raise NebiusProviderError(
                status_code=503,
                message="External model API unavailable (HTTP 503).",
                classification="SERVICE_UNAVAILABLE",
                provider="nebius",
                model=self.model,
            )

        if self.fault_type == "PROMPT_INJECTION_PROPOSAL":
            raise NebiusProviderError(
                status_code=400,
                message="Proposal rejected: prompt injection attempt or invalid action token.",
                classification="MALFORMED_PROPOSAL",
                provider="nebius",
                model=self.model,
            )

        # Reverse operation proposal: open valve_b
        if self.fault_params.get("reverse_operation") or world_state.valves.get("valve_b") == ValveState.CLOSED:
            return ActionProposal(
                id=f"prop_{int(time.time()*1000)}",
                action_type=ActionType.OPEN_VALVE,
                target="valve_b",
                parameters={"target_state": "OPEN"},
                rationale="Deterministic benchmark proposal to restore line flow on valve_b.",
                model_confidence=0.97,
                supporting_evidence_ids=[e.id for e in evidence[:2]],
            )

        # Default nominal proposal: isolate valve_b
        return ActionProposal(
            id=f"prop_{int(time.time()*1000)}",
            action_type=ActionType.CLOSE_VALVE,
            target="valve_b",
            parameters={"target_state": "CLOSED"},
            rationale="Deterministic benchmark proposal to isolate valve line.",
            model_confidence=0.98,
            supporting_evidence_ids=[e.id for e in evidence[:2]],
        )


def create_isolated_world(plant_state_spec: Dict[str, Any]) -> PhysicalWorld:
    """Instantiate a completely clean, isolated PhysicalWorld matching scenario initial conditions."""
    world = PhysicalWorld()
    
    # Configure valve states
    world.valves["valve_b"] = ValveState[plant_state_spec.get("valve_b", "OPEN")]
    if "valve_a" in plant_state_spec:
        world.valves["valve_a"] = ValveState[plant_state_spec["valve_a"]]
    
    # Configure cooling & pump
    world.cooling = CoolingState[plant_state_spec.get("cooling", "ACTIVE")]
    world.set_pump_state("pump_p1", plant_state_spec.get("pump_p1", "INACTIVE"))
    
    # Configure human safety zone
    world.set_human_zone(HumanZoneState[plant_state_spec.get("human_zone", "CLEAR")])
    
    # Configure leak
    leak_active = plant_state_spec.get("leak_active", False)
    world.leak = LeakState(
        active=leak_active,
        target=plant_state_spec.get("leak_target", "valve_b"),
        severity=plant_state_spec.get("leak_severity", 0.85),
        flow_rate_lpm=plant_state_spec.get("flow_rate_lpm", 12.0),
    )
    
    # Advance world state version to ensure clean baseline
    world.version = 1
    return world
