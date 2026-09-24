"""Agent Proposal Provider protocols and local deterministic implementation.

PLANNED INTEGRATIONS:
- NebiusNemotronProvider: Will query NVIDIA Nemotron on Nebius Token Factory.
- TavilyKnowledgeProvider: Will retrieve engineering procedures and manuals via Tavily.
"""

from typing import Any, Dict, List, Protocol, runtime_checkable
import time
import uuid

from motionfence.models.actions import ActionProposal, ActionType
from motionfence.models.world import WorldState
from motionfence.evidence.models import Evidence


@runtime_checkable
class ActionProposalProvider(Protocol):
    """Protocol for AI agent systems that propose physical actions from observations and intent."""

    def propose(
        self,
        intent: str,
        world_state: WorldState,
        evidence: List[Evidence],
    ) -> ActionProposal:
        """Formulate an ActionProposal given human intent, world observations, and evidence."""
        ...


@runtime_checkable
class KnowledgeProvider(Protocol):
    """Protocol for external engineering manual / SOP retrieval."""

    def retrieve(self, query: str) -> List[Dict[str, Any]]:
        """Retrieve contextual safety protocols or operating procedures."""
        ...


class LocalDeterministicProvider(ActionProposalProvider):
    """Deterministic proposal generator modeling an embodied agent's cognitive loop.
    
    Used for local testing and deterministic scenario validation.
    DOES NOT call an external LLM.
    """

    def propose(
        self,
        intent: str,
        world_state: WorldState,
        evidence: List[Evidence],
    ) -> ActionProposal:
        """Evaluate observations and generate an ActionProposal based on best available evidence."""
        # Find highest-confidence leak observation across evidence
        leak_candidates: Dict[str, float] = {}

        for ev in evidence:
            obs = ev.observation
            is_leak = (
                obs.get("leak_detected") is True
                or obs.get("visual_vapor_detected") is True
                or obs.get("leak_confirmed") is True
                or obs.get("gasket_failure_visible") is True
            )
            if is_leak and ev.target in ("valve_a", "valve_b"):
                if ev.target not in leak_candidates or ev.confidence > leak_candidates[ev.target]:
                    leak_candidates[ev.target] = ev.confidence

        if not leak_candidates:
            # No evidence of leak; propose inspection
            return ActionProposal(
                action_type=ActionType.INSPECT,
                target="valve_a",
                rationale="No leak source confirmed in evidence; proposing visual inspection.",
                model_confidence=0.50,
                supporting_evidence_ids=[e.id for e in evidence],
            )

        # Pick candidate with highest confidence
        best_target = max(leak_candidates, key=leak_candidates.get)
        best_conf = leak_candidates[best_target]

        supporting_ids = [e.id for e in evidence if e.target == best_target]

        return ActionProposal(
            action_type=ActionType.CLOSE_VALVE,
            target=best_target,
            parameters={"target": best_target, "force_mode": "gradual"},
            rationale=(
                f"Agent observed leak signs on {best_target} with confidence {best_conf:.2f}. "
                f"Proposing valve closure to satisfy intent: '{intent}'."
            ),
            model_confidence=best_conf,
            supporting_evidence_ids=supporting_ids,
        )


class LocalMockKnowledgeProvider(KnowledgeProvider):
    """Deterministic local repository of plant safety procedures (SOPs)."""

    def retrieve(self, query: str) -> List[Dict[str, Any]]:
        return [
            {
                "id": "SOP-MECH-402",
                "title": "Hazardous Fluid Leak Isolation Procedure",
                "rule": "Never actuate isolation valves when safety zone is occupied. Maintain active cooling.",
                "relevance": 0.95,
            }
        ]
