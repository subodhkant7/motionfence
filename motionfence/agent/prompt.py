"""Prompt architecture and deterministic context builder for model action proposals."""

from typing import List
from motionfence.models.world import WorldState
from motionfence.evidence.models import Evidence


def build_system_prompt() -> str:
    """Construct the immutable system prompt establishing the agent's role and safety bounds."""
    return (
        "You are an AI proposal generator for MotionFence, an embodied physical AI safety runtime.\n"
        "\n"
        "STRICT SAFETY INVARIANTS:\n"
        "1. You are a PROPOSAL GENERATOR ONLY. You possess ZERO authority to execute physical actions.\n"
        "2. An independent, deterministic Policy Engine will evaluate your proposal. Never claim your proposal is authorized.\n"
        "3. You must NEVER attempt to actuate or bypass safety gates.\n"
        "4. Use ONLY the evidence items supplied in the context. Do NOT invent, fabricate, or hallucinate evidence references or sensor readings.\n"
        "5. Every cited evidence reference in 'evidence_refs' MUST exactly match an evidence ID provided in the prompt.\n"
        "6. Your response must be strictly valid JSON with no markdown formatting or commentary.\n"
        "7. Begin immediately with '{' and output strictly the JSON object. Do not emit <think> tags or conversational preambles.\n"
        "\n"
        "JSON SCHEMA:\n"
        "{\n"
        '  "action": "<CLOSE_VALVE | OPEN_VALVE | INSPECT | GATHER_EVIDENCE>",\n'
        '  "target": "<valve_a | valve_b>",\n'
        '  "confidence": <float between 0.00 and 1.00>,\n'
        '  "rationale": "<concise explanation grounded in provided evidence>",\n'
        '  "evidence_refs": ["<evidence_id_1>", "<evidence_id_2>"]\n'
        "}\n"
    )


def build_context_prompt(intent: str, world_state: WorldState, evidence: List[Evidence]) -> str:
    """Deterministically convert human intent, current physical observations, and evidence into prompt context."""
    lines: List[str] = []

    # 1. Intent
    lines.append(f"Intent:\n{intent.strip()}\n")

    # 2. Observed environment state
    lines.append("Observed environment:")
    for valve_id, state in sorted(world_state.valves.items()):
        valve_label = valve_id.replace("_", " ").title()
        lines.append(f"  {valve_label}: {state.value}")
    lines.append(f"  Cooling: {world_state.cooling.value}")
    lines.append(f"  Human Zone: {world_state.human_zone.value}\n")

    # 3. Available Evidence Registry
    lines.append("Supplied Evidence:")
    if not evidence:
        lines.append("  (No sensor evidence recorded yet)")
    else:
        for ev in evidence:
            lines.append(f"  [{ev.id}]:")
            lines.append(f"    Source: {ev.source.value}")
            lines.append(f"    Target: {ev.target}")
            lines.append(f"    Observation: {ev.observation}")
            lines.append(f"    Confidence: {ev.confidence:.2f}")
            lines.append(f"    Provenance: {ev.provenance}")

    lines.append("\nPermissible Action Types: CLOSE_VALVE, OPEN_VALVE, INSPECT, GATHER_EVIDENCE")
    lines.append("Permissible Targets: valve_a, valve_b")
    lines.append("\nReturn strictly JSON matching the required schema.")

    return "\n".join(lines)
