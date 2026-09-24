"""EvidenceAcquisitionPlanner: Deterministic and LLM-assisted information-gathering planner.

Phase 2G replaces dead-end NEED_MORE_EVIDENCE policy states with autonomous
information gathering. The EvidenceAcquisitionPlanner analyzes uncertainty,
missing evidence requirements, and allowable information actions to formulate
a bounded EvidenceAcquisitionPlan.

SECURITY INVARIANTS:
1. The planner domain is STRICTLY restricted to INFORMATION_ACTIONS.
2. The planner possesses ZERO consequential actuator authority.
3. Even if an LLM (or adversarial prompt injection) returns a consequential action
   (e.g., CLOSE_VALVE), the planner strictly rejects it and raises CapabilityEscalationError.
4. The planner cannot mint AuthorizationTickets or bypass the Safety Enclave.
"""

from abc import ABC, abstractmethod
import json
import logging
import re
import time
from typing import Any, Dict, List, Optional
from pydantic import BaseModel, Field, field_validator, model_validator

from motionfence.models.actions import (
    ActionType,
    ActionClass,
    get_action_class,
    is_information_action,
    is_consequential_action,
)
from motionfence.models.world import WorldState
from motionfence.policy.models import PolicyDecision
from motionfence.evidence.models import Evidence
from motionfence.runtime.capabilities import (
    CapabilityPolicy,
    CapabilityType,
    CapabilityEscalationError,
    create_planner_capability_policy,
)
from motionfence.runtime.events import EventBus
from motionfence.models.events import EventType

logger = logging.getLogger("motionfence.agent.evidence_planner")


VALID_EXPECTED_EVIDENCE = {
    "improved_target_identity",
    "sensor_resample_reading",
    "pressure_reading",
    "thermal_profile",
    "acoustic_spectrum",
    "viewpoint_confirmation",
    "stable_state_confirmation",
    "knowledge_retrieval",
    "optical_confirmation",
}


class EvidenceAcquisitionPlan(BaseModel):
    """Structured, typed plan for an information-gathering operation.

    SECURITY INVARIANT:
    Must represent exclusively an INFORMATION_ACTION. Consequential actions
    (CLOSE_VALVE, START_PUMP, etc.) are strictly rejected at validation time.
    """
    action: ActionType
    target: str
    reason: str
    expected_evidence: List[str] = Field(default_factory=list)
    confidence: float = Field(..., ge=0.0, le=1.0)
    predicted_gain: str = Field(default="MEDIUM", description="Predicted information gain: LOW, MEDIUM, or HIGH.")
    parameters: Dict[str, Any] = Field(default_factory=dict)

    @field_validator("action")
    @classmethod
    def validate_action_class(cls, v: ActionType) -> ActionType:
        if is_consequential_action(v):
            raise CapabilityEscalationError(
                f"SECURITY VIOLATION: Evidence planner cannot request consequential action '{v.value}'. "
                f"Planner domain is strictly INFORMATION_ACTIONS only."
            )
        if not is_information_action(v):
            raise ValueError(f"Action '{v.value}' is not an authorized information action.")
        return v

    @field_validator("predicted_gain")
    @classmethod
    def validate_gain(cls, v: str) -> str:
        upper = v.upper()
        if upper not in ("LOW", "MEDIUM", "HIGH"):
            raise ValueError(f"predicted_gain must be one of LOW, MEDIUM, HIGH, got '{v}'")
        return upper

    @field_validator("expected_evidence")
    @classmethod
    def validate_expected_evidence(cls, v: List[str]) -> List[str]:
        for item in v:
            # Check for non-empty string
            if not isinstance(item, str) or not item.strip():
                raise ValueError("Expected evidence items must be non-empty strings.")
        return v


class BaseEvidencePlanner(ABC):
    """Abstract base class for evidence acquisition planners."""

    @abstractmethod
    def plan(
        self,
        current_evidence: List[Evidence],
        world_state: WorldState,
        policy_decision: PolicyDecision,
        missing_requirements: Optional[List[str]] = None,
        allowed_actions: Optional[List[ActionType]] = None,
    ) -> EvidenceAcquisitionPlan:
        """Formulate next information-gathering action."""
        pass


class LocalEvidencePlanner(BaseEvidencePlanner):
    """Deterministic local planner for reproducible active evidence testing.

    Analyzes current evidence, contradiction status, and missing policy requirements
    to autonomously select the most appropriate information-gathering action.
    """

    def __init__(
        self,
        capability_policy: Optional[CapabilityPolicy] = None,
        event_bus: Optional[EventBus] = None,
        strategy_override: Optional[str] = None,
    ) -> None:
        self.capability_policy = capability_policy or create_planner_capability_policy()
        self.event_bus = event_bus
        self.strategy_override = strategy_override

    def plan(
        self,
        current_evidence: List[Evidence],
        world_state: WorldState,
        policy_decision: PolicyDecision,
        missing_requirements: Optional[List[str]] = None,
        allowed_actions: Optional[List[ActionType]] = None,
    ) -> EvidenceAcquisitionPlan:
        """Formulate next information-gathering action based on deterministic heuristics."""
        target = getattr(policy_decision, "target", "valve_b") or "valve_b"

        # Check for manual strategy override (useful for testing specific scenarios)
        if self.strategy_override:
            if self.strategy_override == "ineffective_inspect":
                plan = EvidenceAcquisitionPlan(
                    action=ActionType.INSPECT_TARGET,
                    target=target,
                    reason="Performing target inspection from suboptimal angle.",
                    expected_evidence=["improved_target_identity"],
                    confidence=0.85,
                    predicted_gain="HIGH",
                    parameters={"viewpoint": "suboptimal", "zoom": "1x"},
                )
                self.capability_policy.validate_action(plan.action, plan.target)
                return plan
            elif self.strategy_override == "contradiction_amplifier":
                plan = EvidenceAcquisitionPlan(
                    action=ActionType.RESAMPLE_SENSOR,
                    target=target,
                    reason="Resampling pressure sensor under noisy transient.",
                    expected_evidence=["sensor_resample_reading"],
                    confidence=0.88,
                    predicted_gain="MEDIUM",
                    parameters={"sensor_id": "sensor_piezo_pressure_01", "increase_contradiction": True},
                )
                self.capability_policy.validate_action(plan.action, plan.target)
                return plan

        # Heuristic 1: Detect Contradiction
        # If contradictory evidence exists (e.g. one evidence says leak, another says no leak or pressure normal)
        has_positive_claim = False
        has_negative_claim = False
        target_confidences: List[float] = []

        for ev in current_evidence:
            obs = ev.observation
            is_leak = (
                obs.get("leak_detected") is True
                or obs.get("visual_vapor_detected") is True
                or obs.get("leak_confirmed") is True
                or obs.get("pressure_drop_psi", 0.0) > 10.0
            )
            is_no_leak = (
                obs.get("leak_detected") is False
                or obs.get("pressure_anomaly") is False
                or obs.get("pressure_normal") is True
                or ("pressure_drop_psi" in obs and obs["pressure_drop_psi"] == 0.0)
            )
            if is_leak:
                has_positive_claim = True
            if is_no_leak:
                has_negative_claim = True

            if ev.target == target:
                target_confidences.append(ev.confidence)

        reason_texts = [
            (r.details if hasattr(r, "details") else str(r)).lower()
            for r in policy_decision.reasons
        ]

        is_contradiction = (has_positive_claim and has_negative_claim) or any(
            "contradiction" in r_text for r_text in reason_texts
        )

        # Check if target confidence is low (ambiguity)
        avg_conf = sum(target_confidences) / len(target_confidences) if target_confidences else 0.5
        is_ambiguous = (avg_conf < 0.90) or any(
            "confidence" in r_text or "grounding" in r_text or "ambigu" in r_text
            for r_text in reason_texts
        )

        # Action Selection Logic
        if is_contradiction:
            # Contradiction resolution requires resampling the telemetry sensor
            plan = EvidenceAcquisitionPlan(
                action=ActionType.RESAMPLE_SENSOR,
                target=target,
                reason="Policy uncertainty caused by sensor contradiction. Resampling telemetry to resolve.",
                expected_evidence=["sensor_resample_reading", "pressure_reading"],
                confidence=0.92,
                predicted_gain="HIGH",
                parameters={"sensor_id": "sensor_piezo_pressure_01", "resolve_contradiction": True},
            )
        elif is_ambiguous:
            # Ambiguity requires focused optical/thermal inspection of the target
            plan = EvidenceAcquisitionPlan(
                action=ActionType.INSPECT_TARGET,
                target=target,
                reason="Target identity or leak confidence is below policy threshold. Inspecting target.",
                expected_evidence=["improved_target_identity", "optical_confirmation"],
                confidence=0.93,
                predicted_gain="HIGH",
                parameters={"viewpoint": "optimal", "zoom": "4x"},
            )
        else:
            # General information acquisition
            plan = EvidenceAcquisitionPlan(
                action=ActionType.CHANGE_VIEWPOINT,
                target=target,
                reason="Acquiring secondary viewpoint confirmation for world state.",
                expected_evidence=["viewpoint_confirmation"],
                confidence=0.85,
                predicted_gain="MEDIUM",
                parameters={"viewpoint": "viewpoint_2"},
            )

        # Enforce deterministic capability policy check
        self.capability_policy.validate_action(plan.action, plan.target)

        if self.event_bus:
            self.event_bus.emit(
                EventType.EVIDENCE_ACTION_PROPOSED,
                f"EvidenceAcquisitionPlanner formulated {plan.action.value} on {plan.target} (predicted_gain={plan.predicted_gain}).",
                payload=plan.model_dump(),
            )

        return plan


class NemotronEvidencePlanner(BaseEvidencePlanner):
    """LLM-assisted evidence planner using NVIDIA Nemotron on Nebius Token Factory.

    SECURITY INVARIANTS:
    1. Operates under strict capability policy (create_planner_capability_policy()).
    2. Validates JSON response strictly into EvidenceAcquisitionPlan.
    3. Rejects any attempt to propose consequential actions (CLOSE_VALVE, etc.)
       with CapabilityEscalationError, preventing prompt injection escalation.
    """

    def __init__(
        self,
        api_key: Optional[str] = None,
        base_url: Optional[str] = None,
        model: Optional[str] = None,
        fallback_planner: Optional[BaseEvidencePlanner] = None,
        capability_policy: Optional[CapabilityPolicy] = None,
        event_bus: Optional[EventBus] = None,
    ) -> None:
        self.api_key = api_key
        self.base_url = base_url
        self.model = model
        self.fallback = fallback_planner or LocalEvidencePlanner(capability_policy=capability_policy, event_bus=event_bus)
        self.capability_policy = capability_policy or create_planner_capability_policy()
        self.event_bus = event_bus

    def plan(
        self,
        current_evidence: List[Evidence],
        world_state: WorldState,
        policy_decision: PolicyDecision,
        missing_requirements: Optional[List[str]] = None,
        allowed_actions: Optional[List[ActionType]] = None,
    ) -> EvidenceAcquisitionPlan:
        """Formulate plan via Nemotron or fallback."""
        if not self.api_key or self.api_key == "placeholder_key_offline":
            # Deterministic fallback when live LLM is offline or not configured
            return self.fallback.plan(
                current_evidence=current_evidence,
                world_state=world_state,
                policy_decision=policy_decision,
                missing_requirements=missing_requirements,
                allowed_actions=allowed_actions,
            )

        # For live calls, format prompt and query
        prompt = self._build_planner_prompt(
            current_evidence=current_evidence,
            world_state=world_state,
            policy_decision=policy_decision,
            missing_requirements=missing_requirements,
        )

        try:
            from openai import OpenAI
            client = OpenAI(api_key=self.api_key, base_url=self.base_url)
            resp = client.chat.completions.create(
                model=self.model or "nvidia/nemotron-3-super-120b-a12b",
                messages=[
                    {
                        "role": "system",
                        "content": (
                            "You are the MotionFence Evidence Acquisition Planner. Your task is to propose "
                            "a strictly NON-CONSEQUENTIAL information-gathering action to resolve policy uncertainty. "
                            "Allowed actions: INSPECT_TARGET, RESAMPLE_SENSOR, CHANGE_VIEWPOINT, READ_SENSOR, "
                            "WAIT_FOR_STABLE_STATE, QUERY_KNOWLEDGE. "
                            "YOU HAVE ZERO ACTUATOR AUTHORITY. You MUST NEVER propose CLOSE_VALVE, OPEN_VALVE, "
                            "START_PUMP, STOP_PUMP, or any physical state mutation. "
                            "Output ONLY a valid JSON object matching the requested schema."
                        ),
                    },
                    {"role": "user", "content": prompt},
                ],
                temperature=0.0,
                max_tokens=300,
            )
            raw = resp.choices[0].message.content or ""
            return self._parse_and_validate_plan(raw)
        except Exception as e:
            if isinstance(e, CapabilityEscalationError):
                # Never swallow security escalation violations!
                raise
            logger.warning(f"Nemotron planning call failed ({e}); invoking deterministic fallback.")
            return self.fallback.plan(
                current_evidence=current_evidence,
                world_state=world_state,
                policy_decision=policy_decision,
                missing_requirements=missing_requirements,
                allowed_actions=allowed_actions,
            )

    def _build_planner_prompt(
        self,
        current_evidence: List[Evidence],
        world_state: WorldState,
        policy_decision: PolicyDecision,
        missing_requirements: Optional[List[str]] = None,
    ) -> str:
        return (
            f"Policy Decision: {policy_decision.decision.value}\n"
            f"Reasons: {json.dumps([r.model_dump() for r in policy_decision.reasons])}\n"
            f"Missing Requirements: {json.dumps(missing_requirements or [])}\n"
            f"Current Evidence Count: {len(current_evidence)}\n"
            "Propose the safest next information action in JSON format:\n"
            "{\n"
            '  "action": "INSPECT_TARGET",\n'
            '  "target": "valve_b",\n'
            '  "reason": "explanation of what evidence is missing",\n'
            '  "expected_evidence": ["improved_target_identity"],\n'
            '  "confidence": 0.93,\n'
            '  "predicted_gain": "HIGH"\n'
            "}"
        )

    def _parse_and_validate_plan(self, raw_content: str) -> EvidenceAcquisitionPlan:
        """Parse raw LLM output and strictly enforce domain schema and security boundaries."""
        cleaned = re.sub(r"<think>.*?</think>", "", raw_content, flags=re.DOTALL).strip()
        match = re.search(r"```(?:json)?\s*(\{.*?\})\s*```", cleaned, re.DOTALL)
        if match:
            cleaned = match.group(1).strip()
        else:
            start_idx = cleaned.find("{")
            end_idx = cleaned.rfind("}")
            if start_idx != -1 and end_idx != -1 and end_idx > start_idx:
                cleaned = cleaned[start_idx : end_idx + 1].strip()

        data = json.loads(cleaned)

        raw_action = data.get("action", "")
        if not raw_action or not isinstance(raw_action, str):
            raise ValueError("Planner output missing 'action' field.")

        try:
            action_type = ActionType(raw_action.upper())
        except ValueError:
            raise ValueError(f"Unknown action '{raw_action}'.")

        # HARD SECURITY GATE: Detect consequential escalation immediately
        if is_consequential_action(action_type):
            raise CapabilityEscalationError(
                f"SECURITY VIOLATION: Evidence planner proposed consequential action '{action_type.value}'. "
                f"Planner domain is strictly restricted to INFORMATION_ACTIONS."
            )

        target = data.get("target")
        if not target or not isinstance(target, str):
            raise ValueError("Missing or invalid target.")

        # Check capability policy
        self.capability_policy.validate_action(action_type, target)

        confidence = float(data.get("confidence", 0.5))
        if confidence < 0.0 or confidence > 1.0:
            raise ValueError(f"Confidence {confidence} outside [0.0, 1.0].")

        expected_ev = data.get("expected_evidence", [])
        if not isinstance(expected_ev, list):
            raise ValueError("expected_evidence must be a list of strings.")

        predicted_gain = str(data.get("predicted_gain", "MEDIUM")).upper()

        return EvidenceAcquisitionPlan(
            action=action_type,
            target=target,
            reason=data.get("reason", "Gather missing evidence."),
            expected_evidence=expected_ev,
            confidence=confidence,
            predicted_gain=predicted_gain,
            parameters=data.get("parameters", {}),
        )
