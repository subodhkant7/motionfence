"""AI-assisted operational constraint extraction using NVIDIA Nemotron on Nebius Token Factory."""

import json
import logging
import os
import re
import time
from typing import Any, Callable, Dict, List, Optional
from pydantic import BaseModel, Field

from motionfence.knowledge.models import KnowledgeEvidence
from motionfence.constraints.models import (
    CandidateConstraint,
    ConstraintType,
    ConstraintStatus,
    Applicability,
)
from motionfence.constraints.extractor import ConstraintExtractor, ConstraintValidationError
from motionfence.models.actions import ActionType
from motionfence.config.settings import settings

logger = logging.getLogger("motionfence.constraints.nemotron")


class NemotronExtractorError(Exception):
    """Raised when Nemotron extraction fails or encounters unrecoverable API errors."""
    pass


class NemotronExtractedItem(BaseModel):
    """Structured Pydantic schema for individual constraint output from Nemotron."""
    constraint_type: str = Field(..., description="PROHIBITION, REQUIREMENT, PRECONDITION, POSTCONDITION, INFORMATIONAL")
    action: Optional[str] = Field(default=None, description="ActionType or None")
    target: str = Field(..., description="Target physical component or subsystem")
    condition: Dict[str, Any] = Field(default_factory=dict, description="State conditions for activation")
    source_evidence_id: str = Field(..., description="Exact ID of cited KnowledgeEvidence")
    confidence: float = Field(default=1.0, ge=0.0, le=1.0, description="Model extraction confidence score")
    claim_text: str = Field(default="", description="Exact quote from source text supporting this claim")
    rationale: str = Field(default="", description="Explanation of why this rule was extracted")


class NemotronConstraintExtractor:
    """Extracts machine-readable operational constraints using NVIDIA Nemotron via Nebius Token Factory.
    
    SECURITY INVARIANTS:
    1. Nemotron extracts claims and proposes candidate constraints only.
    2. Nemotron CANNOT activate constraints or decide legal/institutional source authority.
    3. Nemotron confidence is strictly recorded as model_confidence, separate from source trust.
    4. Hallucinated evidence references are strictly rejected before policy evaluation.
    """

    SYSTEM_PROMPT = """You are an industrial safety knowledge extraction engine for MotionFence.
Your job is to read operational engineering documentation and extract machine-readable operational constraints.

CRITICAL INSTRUCTIONS:
1. You possess ZERO physical actuation authority. You only interpret text claims.
2. For each operational rule found in the text, extract:
   - constraint_type: PROHIBITION (must not do X), REQUIREMENT (must do Y), PRECONDITION (must do before Z), POSTCONDITION (invariant after), INFORMATIONAL (general procedure)
   - action: CLOSE_VALVE, OPEN_VALVE, INSPECT, ADJUST_COOLING, or null
   - target: physical component name (e.g. 'valve_b', 'valve_a', 'pump_p1')
   - condition: object with physical conditions (e.g. {"pump_p1": "ACTIVE"})
   - source_evidence_id: MUST BE the exact evidence ID provided in the prompt
   - confidence: float between 0.0 and 1.0 representing extraction confidence
   - claim_text: exact supporting quote from document
   - rationale: brief explanation of why this was extracted
3. Distinguish routine maintenance checklists (INFORMATIONAL) from mandatory prohibitions (PROHIBITION).
4. Return ONLY valid JSON as an array of objects matching this schema. Do not include markdown codeblocks or conversational text."""

    def __init__(
        self,
        api_key: Optional[str] = None,
        base_url: Optional[str] = None,
        model: Optional[str] = None,
        timeout: Optional[float] = None,
        max_retries: int = 2,
        max_tokens: Optional[int] = None,
        client: Optional[Any] = None,
        transport: Optional[Callable[[List[Dict[str, str]]], str]] = None,
    ) -> None:
        self.api_key = api_key if api_key is not None else settings.nebius.api_key
        self.base_url = base_url or settings.nebius.base_url
        self.model = model or settings.nebius.model
        self.timeout = timeout if timeout is not None else settings.nebius.timeout_seconds
        self.max_retries = max_retries
        self.max_tokens = max_tokens if max_tokens is not None else settings.nebius.max_output_tokens
        self._client = client
        self._transport = transport
        self.last_usage: Dict[str, Any] = {}

    def extract(self, evidence_list: List[KnowledgeEvidence]) -> List[CandidateConstraint]:
        """Extract structured CandidateConstraint objects from provided evidence items."""
        if not evidence_list:
            return []

        # Build prompt containing known evidence registry
        valid_ids = {ev.id for ev in evidence_list}
        prompt_content = self._build_user_prompt(evidence_list)

        raw_response = self._call_model(prompt_content)
        return self._parse_and_validate(raw_response, valid_ids)

    def _build_user_prompt(self, evidence_list: List[KnowledgeEvidence]) -> str:
        parts = ["Analyze the following industrial plant documentation items and extract all operational constraints:\n"]
        for idx, ev in enumerate(evidence_list, start=1):
            parts.append(
                f"--- EVIDENCE ITEM #{idx} ---\n"
                f"ID: {ev.id}\n"
                f"Title: {ev.title}\n"
                f"Source URL: {ev.source_url}\n"
                f"Content: \"\"\"{ev.content}\"\"\"\n"
            )
        parts.append("\nReturn JSON array of extracted operational constraints:")
        return "\n".join(parts)

    def _call_model(self, prompt: str) -> str:
        """Dispatch prompt via custom transport or OpenAI client to Nebius Token Factory."""
        messages = [
            {"role": "system", "content": self.SYSTEM_PROMPT},
            {"role": "user", "content": prompt},
        ]

        if self._transport is not None:
            return self._transport(messages)

        if not self.api_key or self.api_key == "placeholder_key_offline":
            raise NemotronExtractorError("NEBIUS_API_KEY is not configured for Nemotron extraction.")

        if self._client is None:
            try:
                from openai import OpenAI
                self._client = OpenAI(base_url=self.base_url, api_key=self.api_key, timeout=self.timeout)
            except Exception as e:
                raise NemotronExtractorError(f"Failed to initialize OpenAI client for Nebius Token Factory: {e}") from e

        try:
            response = self._client.chat.completions.create(
                model=self.model,
                messages=messages,
                temperature=0.1,
                max_tokens=self.max_tokens,
            )
            usage_dict: Dict[str, Any] = {}
            if getattr(response, "usage", None):
                usage_dict = {
                    "prompt_tokens": getattr(response.usage, "prompt_tokens", None),
                    "completion_tokens": getattr(response.usage, "completion_tokens", None),
                    "total_tokens": getattr(response.usage, "total_tokens", None),
                }
            self.last_usage = usage_dict
            return response.choices[0].message.content or "[]"
        except Exception as e:
            raise NemotronExtractorError(f"Nebius Token Factory request failed: {e}") from e

    def _parse_and_validate(self, raw_json: str, valid_evidence_ids: set) -> List[CandidateConstraint]:
        """Parse raw model JSON and strictly validate constraints and evidence links."""
        text = raw_json.strip()
        text = re.sub(r"<think>.*?</think>", "", text, flags=re.DOTALL).strip()
        if text.startswith("```json"):
            text = text[7:]
        if text.startswith("```"):
            text = text[3:]
        if text.endswith("```"):
            text = text[:-3]
        text = text.strip()

        try:
            parsed = json.loads(text)
        except json.JSONDecodeError:
            # Fallback: attempt to find JSON array or object substring
            start_bracket = text.find("[")
            end_bracket = text.rfind("]")
            if start_bracket != -1 and end_bracket != -1 and end_bracket > start_bracket:
                try:
                    parsed = json.loads(text[start_bracket : end_bracket + 1])
                except json.JSONDecodeError as e:
                    raise NemotronExtractorError(f"Nemotron returned malformed JSON: {e}\nRaw output: {raw_json[:200]}") from e
            else:
                start_brace = text.find("{")
                end_brace = text.rfind("}")
                if start_brace != -1 and end_brace != -1 and end_brace > start_brace:
                    try:
                        parsed = json.loads(text[start_brace : end_brace + 1])
                    except json.JSONDecodeError as e:
                        raise NemotronExtractorError(f"Nemotron returned malformed JSON: {e}\nRaw output: {raw_json[:200]}") from e
                else:
                    raise NemotronExtractorError(f"Nemotron returned malformed JSON\nRaw output: {raw_json[:200]}")

        if not isinstance(parsed, list):
            if isinstance(parsed, dict) and "constraints" in parsed and isinstance(parsed["constraints"], list):
                parsed = parsed["constraints"]
            else:
                raise NemotronExtractorError(f"Nemotron response root must be a JSON array, got: {type(parsed)}")

        extracted: List[CandidateConstraint] = []
        now = time.time()

        for item in parsed:
            try:
                model_item = NemotronExtractedItem.model_validate(item)
            except Exception as e:
                logger.warning(f"Discarding invalid extracted item schema: {e}")
                continue

            # Strict Evidence Discipline: Evidence reference MUST exist
            if model_item.source_evidence_id not in valid_evidence_ids:
                logger.warning(
                    f"Discarding constraint citing hallucinated evidence ID: {model_item.source_evidence_id}"
                )
                continue

            # Action mapping
            action_obj = None
            if model_item.action:
                try:
                    action_obj = ActionType(model_item.action.upper())
                except ValueError:
                    action_obj = None

            # Constraint type mapping
            try:
                cst_type = ConstraintType(model_item.constraint_type.upper())
            except ValueError:
                cst_type = ConstraintType.INFORMATIONAL

            cst = CandidateConstraint(
                constraint_type=cst_type,
                action=action_obj,
                target=model_item.target.lower().strip(),
                condition=model_item.condition if isinstance(model_item.condition, dict) else {},
                source_evidence_id=model_item.source_evidence_id,
                confidence=model_item.confidence,
                created_at=now,
                status=ConstraintStatus.CANDIDATE,
                description=f"{cst_type.value}: {model_item.claim_text or model_item.rationale}",
                claim_text=model_item.claim_text,
                extraction_rationale=model_item.rationale,
            )
            extracted.append(cst)

        return extracted
