"""NVIDIA Nemotron proposal provider integrated with Nebius Token Factory."""

import json
import logging
import random
import re
import time
import uuid
from typing import Any, Dict, List, Optional
from urllib.parse import urlparse

from openai import (
    OpenAI,
    APIConnectionError,
    APITimeoutError,
    RateLimitError,
    InternalServerError,
    AuthenticationError,
    PermissionDeniedError,
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
    NebiusConfigurationError,
    NebiusAuthenticationError,
    NebiusAuthorizationError,
    NebiusInvalidModelOrRequestError,
    NebiusRateLimitError,
    NebiusUpstreamServerError,
    NebiusTimeoutError,
    NebiusTransportError,
    NebiusMalformedResponseError,
    ModelProposalValidationError,
)
from motionfence.runtime.events import EventBus

logger = logging.getLogger("motionfence.agent.nebius")


def _sanitize_url(url: str) -> str:
    """Safely sanitize base URL by stripping query strings, userinfo, and fragments."""
    try:
        p = urlparse(url)
        return f"{p.scheme}://{p.netloc}{p.path}"
    except Exception:
        return "https://api.tokenfactory.nebius.com/v1/"


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
        max_tokens: Optional[int] = None,
        client: Optional[OpenAI] = None,
        event_bus: Optional[EventBus] = None,
    ) -> None:
        if api_key is not None and not api_key.strip():
            raise NebiusConfigurationError("Nebius API key cannot be empty or whitespace.", failure_stage="CONFIGURATION_VALIDATION")
        if model is not None and not model.strip():
            raise NebiusConfigurationError("Nebius model name cannot be empty.", failure_stage="CONFIGURATION_VALIDATION")
        if base_url is not None and not base_url.strip():
            raise NebiusConfigurationError("Nebius base URL cannot be empty.", failure_stage="CONFIGURATION_VALIDATION")

        self.api_key = api_key if api_key is not None else settings.nebius.api_key
        self.base_url = base_url or settings.nebius.base_url
        self.model = model or settings.nebius.model
        self.timeout = timeout if timeout is not None else settings.nebius.timeout_seconds
        self.max_retries = max_retries if max_retries is not None else settings.nebius.max_retries
        self.max_tokens = max_tokens if max_tokens is not None else settings.nebius.max_output_tokens
        self.event_bus = event_bus
        self.last_usage: Dict[str, Any] = {}
        self.sanitized_endpoint: str = _sanitize_url(self.base_url)

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
        correlation_id = f"corr_{uuid.uuid4().hex[:12]}"
        t_start = time.time()

        if not self.api_key or self.api_key == "placeholder_key_offline":
            msg = "NEBIUS_API_KEY environment variable is not configured or placeholder."
            if self.event_bus:
                self.event_bus.emit(
                    EventType.MODEL_PROVIDER_ERROR,
                    msg,
                    payload={
                        "provider": self.provider_name,
                        "error": "MissingCredentials",
                        "correlation_id": correlation_id,
                    },
                )
            raise NebiusConfigurationError(
                msg,
                provider=self.provider_name,
                model=self.model,
                sanitized_endpoint=self.sanitized_endpoint,
                correlation_id=correlation_id,
                elapsed_ms=(time.time() - t_start) * 1000.0,
            )

        system_prompt = build_system_prompt()
        context_prompt = build_context_prompt(intent, world_state, evidence)

        if self.event_bus:
            self.event_bus.emit(
                EventType.MODEL_REQUESTED,
                f"Querying {self.model} on Nebius Token Factory for proposal (corr={correlation_id}).",
                payload={
                    "provider": self.provider_name,
                    "model": self.model,
                    "evidence_count": len(evidence),
                    "correlation_id": correlation_id,
                },
            )

        # Call with bounded exponential backoff
        raw_content = self._call_model_with_retry(system_prompt, context_prompt, correlation_id)

        # Parse and strictly validate proposal
        proposal = self._parse_and_validate_proposal(raw_content, evidence)

        if self.event_bus:
            self.event_bus.emit(
                EventType.ACTION_PROPOSAL_VALIDATED,
                f"Validated {proposal.action_type.value} proposal on {proposal.target} (conf={proposal.model_confidence:.2f}, corr={correlation_id}).",
                payload=proposal.model_dump(),
            )

        return proposal

    def _call_model_with_retry(
        self,
        system_prompt: str,
        context_prompt: str,
        correlation_id: Optional[str] = None,
    ) -> str:
        """Execute chat completion with bounded retries for transient errors."""
        corr_id = correlation_id or f"corr_{uuid.uuid4().hex[:12]}"
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
                    max_tokens=self.max_tokens,
                    timeout=self.timeout,
                )
                latency_ms = (time.time() - t_req) * 1000.0

                if not response.choices or not response.choices[0].message.content or not response.choices[0].message.content.strip():
                    raise NebiusMalformedResponseError(
                        "Model returned empty response content from Nebius Token Factory.",
                        provider=self.provider_name,
                        model=self.model,
                        sanitized_endpoint=self.sanitized_endpoint,
                        correlation_id=corr_id,
                        elapsed_ms=(time.time() - t_start) * 1000.0,
                    )

                content = response.choices[0].message.content.strip()

                usage_info: Dict[str, Any] = {}
                if getattr(response, "usage", None):
                    usage_info = {
                        "prompt_tokens": getattr(response.usage, "prompt_tokens", None),
                        "completion_tokens": getattr(response.usage, "completion_tokens", None),
                        "total_tokens": getattr(response.usage, "total_tokens", None),
                    }
                self.last_usage = usage_info

                if self.event_bus:
                    self.event_bus.emit(
                        EventType.MODEL_RESPONSE_RECEIVED,
                        f"Received response from {self.model} in {latency_ms:.1f}ms (corr={corr_id}).",
                        payload={
                            "provider": self.provider_name,
                            "model": self.model,
                            "latency_ms": round(latency_ms, 2),
                            "finish_reason": response.choices[0].finish_reason,
                            "usage": usage_info,
                            "correlation_id": corr_id,
                        },
                    )

                return content

            except PermissionDeniedError as e:
                # HTTP 403 - Permission Denied / Policy Invalidation
                elapsed = (time.time() - t_start) * 1000.0
                err_msg = f"Nebius permission denied: Request to {self.sanitized_endpoint} rejected by upstream policy ({getattr(e, 'message', str(e))[:140]})."
                exc = NebiusAuthorizationError(
                    err_msg,
                    provider=self.provider_name,
                    model=self.model,
                    sanitized_endpoint=self.sanitized_endpoint,
                    status_code=403,
                    provider_code=getattr(e, "code", "permission_denied"),
                    correlation_id=corr_id,
                    elapsed_ms=elapsed,
                )
                if self.event_bus:
                    self.event_bus.emit(
                        EventType.MODEL_PROVIDER_ERROR,
                        err_msg,
                        payload=exc.to_diagnostic_dict(),
                    )
                raise exc from e

            except AuthenticationError as e:
                # HTTP 401 - Authentication rejection
                elapsed = (time.time() - t_start) * 1000.0
                err_msg = f"Nebius authentication rejected: Invalid or expired API credentials ({getattr(e, 'message', str(e))[:140]})."
                exc = NebiusAuthenticationError(
                    err_msg,
                    provider=self.provider_name,
                    model=self.model,
                    sanitized_endpoint=self.sanitized_endpoint,
                    status_code=401,
                    provider_code=getattr(e, "code", "unauthorized"),
                    correlation_id=corr_id,
                    elapsed_ms=elapsed,
                )
                if self.event_bus:
                    self.event_bus.emit(
                        EventType.MODEL_PROVIDER_ERROR,
                        err_msg,
                        payload=exc.to_diagnostic_dict(),
                    )
                raise exc from e

            except (NotFoundError, BadRequestError) as e:
                # HTTP 404 or HTTP 400 - Invalid model or request schema
                elapsed = (time.time() - t_start) * 1000.0
                st_code = getattr(e, "status_code", 400 if isinstance(e, BadRequestError) else 404)
                err_msg = f"Nebius request error ({type(e).__name__}): {getattr(e, 'message', str(e))[:140]}."
                exc = NebiusInvalidModelOrRequestError(
                    err_msg,
                    provider=self.provider_name,
                    model=self.model,
                    sanitized_endpoint=self.sanitized_endpoint,
                    status_code=st_code,
                    provider_code=getattr(e, "code", "invalid_request"),
                    correlation_id=corr_id,
                    elapsed_ms=elapsed,
                )
                if self.event_bus:
                    self.event_bus.emit(
                        EventType.MODEL_PROVIDER_ERROR,
                        err_msg,
                        payload=exc.to_diagnostic_dict(),
                    )
                raise exc from e

            except RateLimitError as e:
                # HTTP 429 - Rate limit with bounded backoff
                attempt += 1
                elapsed = (time.time() - t_start) * 1000.0
                if attempt > self.max_retries:
                    err_msg = f"Nebius rate limit exceeded after {self.max_retries} retries ({getattr(e, 'message', str(e))[:140]})."
                    exc = NebiusRateLimitError(
                        err_msg,
                        provider=self.provider_name,
                        model=self.model,
                        sanitized_endpoint=self.sanitized_endpoint,
                        status_code=429,
                        provider_code=getattr(e, "code", "rate_limit_exceeded"),
                        correlation_id=corr_id,
                        elapsed_ms=elapsed,
                    )
                    if self.event_bus:
                        self.event_bus.emit(
                            EventType.MODEL_PROVIDER_ERROR,
                            err_msg,
                            payload=exc.to_diagnostic_dict(),
                        )
                    raise exc from e

                delay = (0.5 * (2 ** (attempt - 1))) + random.uniform(0.05, 0.2)
                logger.warning(
                    "Rate limit querying Nebius (%s); retrying %d/%d in %.2fs (corr=%s)...",
                    type(e).__name__,
                    attempt,
                    self.max_retries,
                    delay,
                    corr_id,
                )
                time.sleep(delay)

            except APITimeoutError as e:
                # Timeout error with bounded backoff
                attempt += 1
                elapsed = (time.time() - t_start) * 1000.0
                if attempt > self.max_retries:
                    err_msg = f"Nebius request timed out after {self.max_retries} retries (timeout={self.timeout}s)."
                    exc = NebiusTimeoutError(
                        err_msg,
                        provider=self.provider_name,
                        model=self.model,
                        sanitized_endpoint=self.sanitized_endpoint,
                        correlation_id=corr_id,
                        elapsed_ms=elapsed,
                    )
                    if self.event_bus:
                        self.event_bus.emit(
                            EventType.MODEL_PROVIDER_ERROR,
                            err_msg,
                            payload=exc.to_diagnostic_dict(),
                        )
                    raise exc from e

                delay = (0.5 * (2 ** (attempt - 1))) + random.uniform(0.05, 0.2)
                logger.warning(
                    "Timeout querying Nebius (%s); retrying %d/%d in %.2fs (corr=%s)...",
                    type(e).__name__,
                    attempt,
                    self.max_retries,
                    delay,
                    corr_id,
                )
                time.sleep(delay)

            except APIConnectionError as e:
                # Network transport error with bounded backoff
                attempt += 1
                elapsed = (time.time() - t_start) * 1000.0
                if attempt > self.max_retries:
                    err_msg = f"Nebius transport connection failed after {self.max_retries} retries: {str(e)[:140]}."
                    exc = NebiusTransportError(
                        err_msg,
                        provider=self.provider_name,
                        model=self.model,
                        sanitized_endpoint=self.sanitized_endpoint,
                        correlation_id=corr_id,
                        elapsed_ms=elapsed,
                    )
                    if self.event_bus:
                        self.event_bus.emit(
                            EventType.MODEL_PROVIDER_ERROR,
                            err_msg,
                            payload=exc.to_diagnostic_dict(),
                        )
                    raise exc from e

                delay = (0.5 * (2 ** (attempt - 1))) + random.uniform(0.05, 0.2)
                logger.warning(
                    "Connection error querying Nebius (%s); retrying %d/%d in %.2fs (corr=%s)...",
                    type(e).__name__,
                    attempt,
                    self.max_retries,
                    delay,
                    corr_id,
                )
                time.sleep(delay)

            except InternalServerError as e:
                # HTTP 500, 502, 503, 504 - Upstream server error with bounded backoff
                attempt += 1
                elapsed = (time.time() - t_start) * 1000.0
                st_code = getattr(e, "status_code", 500)
                if attempt > self.max_retries:
                    err_msg = f"Nebius upstream server error ({st_code}) after {self.max_retries} retries: {getattr(e, 'message', str(e))[:140]}."
                    exc = NebiusUpstreamServerError(
                        err_msg,
                        provider=self.provider_name,
                        model=self.model,
                        sanitized_endpoint=self.sanitized_endpoint,
                        status_code=st_code,
                        provider_code=getattr(e, "code", "internal_server_error"),
                        correlation_id=corr_id,
                        elapsed_ms=elapsed,
                    )
                    if self.event_bus:
                        self.event_bus.emit(
                            EventType.MODEL_PROVIDER_ERROR,
                            err_msg,
                            payload=exc.to_diagnostic_dict(),
                        )
                    raise exc from e

                delay = (0.5 * (2 ** (attempt - 1))) + random.uniform(0.05, 0.2)
                logger.warning(
                    "Upstream server error querying Nebius (%s); retrying %d/%d in %.2fs (corr=%s)...",
                    type(e).__name__,
                    attempt,
                    self.max_retries,
                    delay,
                    corr_id,
                )
                time.sleep(delay)

            except NebiusProviderError:
                # Re-raise already classified provider errors directly
                raise

            except Exception as e:
                elapsed = (time.time() - t_start) * 1000.0
                err_msg = f"Unexpected error during Nebius model inference: {type(e).__name__} - {str(e)[:140]}"
                exc = NebiusProviderError(
                    err_msg,
                    classification="UNEXPECTED_ERROR",
                    provider=self.provider_name,
                    model=self.model,
                    sanitized_endpoint=self.sanitized_endpoint,
                    correlation_id=corr_id,
                    elapsed_ms=elapsed,
                )
                if self.event_bus:
                    self.event_bus.emit(
                        EventType.MODEL_PROVIDER_ERROR,
                        err_msg,
                        payload=exc.to_diagnostic_dict(),
                    )
                raise exc from e

        raise NebiusTimeoutError(
            f"Exceeded maximum retries ({self.max_retries}) without a valid response.",
            provider=self.provider_name,
            model=self.model,
            sanitized_endpoint=self.sanitized_endpoint,
            correlation_id=corr_id,
            elapsed_ms=(time.time() - t_start) * 1000.0,
        )

    def _parse_and_validate_proposal(
        self,
        raw_content: str,
        available_evidence: List[Evidence],
    ) -> ActionProposal:
        """Parse raw model output and strictly enforce domain schema and evidence discipline."""
        # 1. Strip reasoning/think tags if emitted by model
        cleaned = re.sub(r"<think>.*?</think>", "", raw_content, flags=re.DOTALL).strip()

        # 2. Strip markdown code fence if model wrapped output in ```json ... ```
        match = re.search(r"```(?:json)?\s*(\{.*?\})\s*```", cleaned, re.DOTALL)
        if match:
            cleaned = match.group(1).strip()
        else:
            # Fallback: extract substring from outermost { to }
            start_idx = cleaned.find("{")
            end_idx = cleaned.rfind("}")
            if start_idx != -1 and end_idx != -1 and end_idx > start_idx:
                cleaned = cleaned[start_idx : end_idx + 1].strip()

        try:
            data = json.loads(cleaned)
        except json.JSONDecodeError as e:
            err = f"Model output is not valid JSON: {e}"
            if self.event_bus:
                self.event_bus.emit(
                    EventType.MODEL_RESPONSE_REJECTED,
                    err,
                    payload={"raw_content": raw_content[:200]},
                )
            raise ModelProposalValidationError(err) from e

        if not isinstance(data, dict):
            err = f"Model output must be a JSON object, got {type(data).__name__}"
            if self.event_bus:
                self.event_bus.emit(EventType.MODEL_RESPONSE_REJECTED, err)
            raise ModelProposalValidationError(err)

        # 3. Field validation
        action_str = data.get("action")
        target = data.get("target")
        confidence = data.get("confidence")
        rationale = data.get("rationale")
        evidence_refs = data.get("evidence_refs", [])

        if not action_str or not isinstance(action_str, str):
            raise ModelProposalValidationError("Model proposal missing 'action' field.")

        try:
            action_type = ActionType(action_str)
        except ValueError as e:
            raise ModelProposalValidationError(f"Unknown action '{action_str}' proposed by model.") from e

        if not target or not isinstance(target, str):
            raise ModelProposalValidationError("Model proposal missing valid 'target' field.")

        if confidence is None or not isinstance(confidence, (int, float)):
            raise ModelProposalValidationError("Model proposal missing numeric 'confidence' field.")

        confidence_val = float(confidence)
        if not (0.0 <= confidence_val <= 1.0):
            raise ModelProposalValidationError(
                f"Model confidence {confidence_val} is outside permissible range [0.0, 1.0]."
            )

        if not rationale or not isinstance(rationale, str):
            raise ModelProposalValidationError("Model proposal missing 'rationale' explanation.")

        # 4. Strict Evidence Discipline: all cited evidence must exist in available_evidence
        valid_evidence_ids = {e.id for e in available_evidence}
        if not isinstance(evidence_refs, list):
            raise ModelProposalValidationError("'evidence_refs' must be a list of evidence IDs.")

        for ref in evidence_refs:
            if ref not in valid_evidence_ids:
                err = f"Unknown evidence reference '{ref}' cited in proposal. Hallucinated evidence is strictly forbidden."
                if self.event_bus:
                    self.event_bus.emit(
                        EventType.MODEL_RESPONSE_REJECTED,
                        err,
                        payload={"hallucinated_ref": ref},
                    )
                raise ModelProposalValidationError(err)

        return ActionProposal(
            action_type=action_type,
            target=target,
            model_confidence=confidence_val,
            rationale=rationale,
            supporting_evidence_ids=evidence_refs,
            raw_model_output=raw_content,
        )
