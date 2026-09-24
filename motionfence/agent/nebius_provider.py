"""NVIDIA Nemotron proposal provider integrated with Nebius Token Factory."""

import json
import logging
import random
import re
import time
from typing import Any, Dict, List, Optional

from openai import (
    OpenAI,
    APIConnectionError,
    APITimeoutError,
    RateLimitError,
    InternalServerError,
    AuthenticationError,
    BadRequestError,
    NotFoundError,
)

from motionfence.models.actions import ActionProposal, ActionType
from motionfence.models.world import WorldState
from motionfence.models.events import EventType
from motionfence.evidence.models import Evidence
from motionfence.config.settings import settings
from motionfence.agent.prompt import build_system_prompt, build_context_prompt
from motionfence.agent.exceptions import (
    NebiusProviderError,
    ModelProposalValidationError,
)
from motionfence.runtime.events import EventBus

logger = logging.getLogger("motionfence.agent.nebius")


class NebiusNemotronProvider:
    """ActionProposalProvider implementation connecting to Nebius Token Factory.
    
    SECURITY INVARIANT:
    This provider operates strictly as an unprivileged proposal generator.
    It possesses ZERO execution authority, holds no actuator handles,
    and has no access to ticket-signing secrets.
    """

    provider_name: str = "nebius"

    def __init__(
        self,
        api_key: Optional[str] = None,
        base_url: Optional[str] = None,
        model: Optional[str] = None,
        timeout: Optional[float] = None,
        max_retries: Optional[int] = None,
        client: Optional[OpenAI] = None,
        event_bus: Optional[EventBus] = None,
    ) -> None:
        self.api_key = api_key or settings.nebius.api_key
        self.base_url = base_url or settings.nebius.base_url
        self.model = model or settings.nebius.model
        self.timeout = timeout if timeout is not None else settings.nebius.timeout_seconds
        self.max_retries = max_retries if max_retries is not None else settings.nebius.max_retries
        self.event_bus = event_bus

        if client is not None:
            self.client = client
        else:
            # We defer strict key check to request time to allow instantiation in offline setups
            self.client = OpenAI(
                api_key=self.api_key or "placeholder_key_offline",
                base_url=self.base_url,
                timeout=self.timeout,
            )

    def propose(
        self,
        intent: str,
        world_state: WorldState,
        evidence: List[Evidence],
    ) -> ActionProposal:
        """Formulate an ActionProposal by querying NVIDIA Nemotron on Nebius Token Factory."""
        if not self.api_key or self.api_key == "placeholder_key_offline":
            msg = "NEBIUS_API_KEY environment variable is not configured."
            if self.event_bus:
                self.event_bus.emit(
                    EventType.MODEL_PROVIDER_ERROR,
                    msg,
                    payload={"provider": self.provider_name, "error": "MissingCredentials"},
                )
            raise NebiusProviderError(msg)

        system_prompt = build_system_prompt()
        context_prompt = build_context_prompt(intent, world_state, evidence)

        if self.event_bus:
            self.event_bus.emit(
                EventType.MODEL_REQUESTED,
                f"Querying {self.model} on Nebius Token Factory for proposal.",
                payload={
                    "provider": self.provider_name,
                    "model": self.model,
                    "evidence_count": len(evidence),
                },
            )

        # Call with bounded exponential backoff
        raw_content = self._call_model_with_retry(system_prompt, context_prompt)

        # Parse and strictly validate proposal
        proposal = self._parse_and_validate_proposal(raw_content, evidence)

        if self.event_bus:
            self.event_bus.emit(
                EventType.ACTION_PROPOSAL_VALIDATED,
                f"Validated {proposal.action_type.value} proposal on {proposal.target} (conf={proposal.model_confidence:.2f}).",
                payload=proposal.model_dump(),
            )

        return proposal

    def _call_model_with_retry(self, system_prompt: str, context_prompt: str) -> str:
        """Execute chat completion with bounded retries for transient errors."""
        attempt = 0
        t_start = time.time()

        while attempt <= self.max_retries:
            try:
                t_req = time.time()
                response = self.client.chat.completions.create(
                    model=self.model,
                    messages=[
                        {"role": "system", "content": system_prompt},
                        {"role": "user", "content": context_prompt},
                    ],
                    temperature=0.0,
                    timeout=self.timeout,
                )
                latency_ms = (time.time() - t_req) * 1000.0

                if not response.choices or not response.choices[0].message.content:
                    raise NebiusProviderError("Model returned empty response content.")

                content = response.choices[0].message.content.strip()

                if self.event_bus:
                    self.event_bus.emit(
                        EventType.MODEL_RESPONSE_RECEIVED,
                        f"Received response from {self.model} in {latency_ms:.1f}ms.",
                        payload={
                            "provider": self.provider_name,
                            "model": self.model,
                            "latency_ms": round(latency_ms, 2),
                            "finish_reason": response.choices[0].finish_reason,
                        },
                    )

                return content

            except (RateLimitError, APIConnectionError, APITimeoutError, InternalServerError) as e:
                attempt += 1
                if attempt > self.max_retries:
                    err_msg = f"Nebius inference request failed after {self.max_retries} retries: {type(e).__name__} - {e}"
                    if self.event_bus:
                        self.event_bus.emit(
                            EventType.MODEL_PROVIDER_ERROR,
                            err_msg,
                            payload={"provider": self.provider_name, "error": str(e)},
                        )
                    raise NebiusProviderError(err_msg) from e

                # Exponential backoff with jitter
                delay = (0.5 * (2 ** (attempt - 1))) + (random.uniform(0.05, 0.2))
                logger.warning(f"Transient error querying Nebius ({type(e).__name__}); retrying in {delay:.2f}s...")
                time.sleep(delay)

            except (AuthenticationError, BadRequestError, NotFoundError) as e:
                # Non-retryable
                err_msg = f"Non-retryable Nebius API error: {type(e).__name__} - {e}"
                if self.event_bus:
                    self.event_bus.emit(
                        EventType.MODEL_PROVIDER_ERROR,
                        err_msg,
                        payload={"provider": self.provider_name, "error": str(e)},
                    )
                raise NebiusProviderError(err_msg) from e

            except Exception as e:
                err_msg = f"Unexpected error during model inference: {e}"
                if self.event_bus:
                    self.event_bus.emit(
                        EventType.MODEL_PROVIDER_ERROR,
                        err_msg,
                        payload={"provider": self.provider_name, "error": str(e)},
                    )
                raise NebiusProviderError(err_msg) from e

        raise NebiusProviderError("Exceeded maximum retries without a valid response.")

    def _parse_and_validate_proposal(
        self,
        raw_content: str,
        available_evidence: List[Evidence],
    ) -> ActionProposal:
        """Parse raw model output and strictly enforce domain schema and evidence discipline."""
        # 1. Strip markdown code fence if model wrapped output in ```json ... ```
        cleaned = raw_content
        match = re.search(r"```(?:json)?\s*(\{.*?\})\s*```", raw_content, re.DOTALL)
        if match:
            cleaned = match.group(1)

        try:
            data = json.loads(cleaned)
        except json.JSONDecodeError as e:
            err = f"Model output is not valid JSON: {e}"
            if self.event_bus:
                self.event_bus.emit(EventType.MODEL_RESPONSE_REJECTED, err, payload={"raw_content": raw_content[:200]})
            raise ModelProposalValidationError(err) from e

        if not isinstance(data, dict):
            err = f"Model output JSON root must be an object, got {type(data).__name__}"
            if self.event_bus:
                self.event_bus.emit(EventType.MODEL_RESPONSE_REJECTED, err)
            raise ModelProposalValidationError(err)

        # 2. Validate Action Type
        raw_action = data.get("action")
        if not raw_action or not isinstance(raw_action, str):
            err = "Model proposal missing required 'action' field."
            if self.event_bus:
                self.event_bus.emit(EventType.MODEL_RESPONSE_REJECTED, err)
            raise ModelProposalValidationError(err)

        try:
            action_type = ActionType(raw_action.upper())
        except ValueError:
            err = f"Unknown action '{raw_action}'. Permitted actions: {[a.value for a in ActionType]}."
            if self.event_bus:
                self.event_bus.emit(EventType.MODEL_RESPONSE_REJECTED, err)
            raise ModelProposalValidationError(err)

        # 3. Validate Target
        target = data.get("target")
        if not target or not isinstance(target, str):
            err = "Model proposal missing or invalid 'target' string."
            if self.event_bus:
                self.event_bus.emit(EventType.MODEL_RESPONSE_REJECTED, err)
            raise ModelProposalValidationError(err)

        # 4. Validate Confidence
        raw_conf = data.get("confidence")
        if raw_conf is None or not isinstance(raw_conf, (int, float)):
            err = "Model proposal missing or invalid 'confidence' number."
            if self.event_bus:
                self.event_bus.emit(EventType.MODEL_RESPONSE_REJECTED, err)
            raise ModelProposalValidationError(err)

        confidence = float(raw_conf)
        if confidence < 0.0 or confidence > 1.0:
            err = f"Model confidence {confidence} is outside permissible range [0.0, 1.0]."
            if self.event_bus:
                self.event_bus.emit(EventType.MODEL_RESPONSE_REJECTED, err)
            raise ModelProposalValidationError(err)

        # 5. Validate Rationale
        rationale = data.get("rationale")
        if not rationale or not isinstance(rationale, str):
            err = "Model proposal missing required 'rationale' explanation."
            if self.event_bus:
                self.event_bus.emit(EventType.MODEL_RESPONSE_REJECTED, err)
            raise ModelProposalValidationError(err)

        # 6. Strict Evidence Discipline
        evidence_refs = data.get("evidence_refs", [])
        if not isinstance(evidence_refs, list):
            err = "'evidence_refs' must be a list of evidence IDs."
            if self.event_bus:
                self.event_bus.emit(EventType.MODEL_RESPONSE_REJECTED, err)
            raise ModelProposalValidationError(err)

        available_ids = {e.id for e in available_evidence}
        for ref in evidence_refs:
            if ref not in available_ids:
                err = f"Unknown evidence reference '{ref}'. Every cited reference must exist in runtime context."
                if self.event_bus:
                    self.event_bus.emit(
                        EventType.MODEL_RESPONSE_REJECTED,
                        err,
                        payload={"unknown_ref": ref, "available_ids": sorted(list(available_ids))},
                    )
                raise ModelProposalValidationError(err)

        return ActionProposal(
            action_type=action_type,
            target=target,
            rationale=rationale,
            model_confidence=confidence,
            supporting_evidence_ids=evidence_refs,
        )
