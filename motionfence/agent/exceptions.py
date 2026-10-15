"""Exceptions for model providers and proposal validation."""

from typing import Optional, Dict, Any


class ProviderError(Exception):
    """Base exception for all agent proposal providers."""
    pass


class NebiusProviderError(ProviderError):
    """Raised when an error occurs communicating with Nebius Token Factory.

    Encapsulates structured, sanitized diagnostic fields to enable actionable error reporting
    without leaking credentials, tokens, or private paths.
    """

    def __init__(
        self,
        message: str,
        *,
        classification: str = "UNEXPECTED_ERROR",
        status_code: Optional[int] = None,
        provider: str = "nebius",
        model: Optional[str] = None,
        sanitized_endpoint: Optional[str] = None,
        failure_stage: Optional[str] = None,
        provider_code: Optional[str] = None,
        is_retryable: bool = False,
        elapsed_ms: Optional[float] = None,
        correlation_id: Optional[str] = None,
    ) -> None:
        super().__init__(message)
        self.message = message
        self.classification = classification
        self.status_code = status_code
        self.provider = provider
        self.model = model
        self.sanitized_endpoint = sanitized_endpoint
        self.failure_stage = failure_stage
        self.provider_code = provider_code
        self.is_retryable = is_retryable
        self.elapsed_ms = elapsed_ms
        self.correlation_id = correlation_id

    def to_diagnostic_dict(self) -> Dict[str, Any]:
        """Return a safe, structured dictionary for diagnostic logging and API transport."""
        return {
            "classification": self.classification,
            "provider": self.provider,
            "model": self.model,
            "sanitized_endpoint": self.sanitized_endpoint,
            "status_code": self.status_code,
            "provider_code": self.provider_code,
            "is_retryable": self.is_retryable,
            "failure_stage": self.failure_stage,
            "elapsed_ms": round(self.elapsed_ms, 2) if self.elapsed_ms is not None else None,
            "correlation_id": self.correlation_id,
            "sanitized_message": self.message[:256],
        }


class NebiusConfigurationError(NebiusProviderError):
    """Raised when provider configuration or credentials are missing or invalid."""

    def __init__(self, message: str, **kwargs: Any) -> None:
        kwargs.setdefault("classification", "CONFIGURATION_ERROR")
        kwargs.setdefault("is_retryable", False)
        kwargs.setdefault("failure_stage", "CONFIGURATION_VALIDATION")
        super().__init__(message, **kwargs)


class NebiusAuthenticationError(NebiusProviderError):
    """Raised when authentication (HTTP 401) fails."""

    def __init__(self, message: str, **kwargs: Any) -> None:
        kwargs.setdefault("classification", "AUTHENTICATION_ERROR")
        kwargs.setdefault("status_code", 401)
        kwargs.setdefault("is_retryable", False)
        kwargs.setdefault("failure_stage", "AUTHENTICATION")
        super().__init__(message, **kwargs)


class NebiusAuthorizationError(NebiusProviderError):
    """Raised when permission/policy (HTTP 403) denies the request."""

    def __init__(self, message: str, **kwargs: Any) -> None:
        kwargs.setdefault("classification", "AUTHORIZATION_ERROR")
        kwargs.setdefault("status_code", 403)
        kwargs.setdefault("is_retryable", False)
        kwargs.setdefault("failure_stage", "AUTHORIZATION")
        super().__init__(message, **kwargs)


class NebiusInvalidModelOrRequestError(NebiusProviderError):
    """Raised when model or request schema is invalid (HTTP 400 or 404)."""

    def __init__(self, message: str, **kwargs: Any) -> None:
        kwargs.setdefault("classification", "INVALID_MODEL_OR_REQUEST")
        kwargs.setdefault("is_retryable", False)
        kwargs.setdefault("failure_stage", "REQUEST_DISPATCH")
        super().__init__(message, **kwargs)


class NebiusRateLimitError(NebiusProviderError):
    """Raised when provider rate limit is exceeded (HTTP 429)."""

    def __init__(self, message: str, **kwargs: Any) -> None:
        kwargs.setdefault("classification", "RATE_LIMIT_ERROR")
        kwargs.setdefault("status_code", 429)
        kwargs.setdefault("is_retryable", True)
        kwargs.setdefault("failure_stage", "RATE_LIMITING")
        super().__init__(message, **kwargs)


class NebiusUpstreamServerError(NebiusProviderError):
    """Raised when upstream Nebius server errors occur (HTTP 500, 502, 503, 504)."""

    def __init__(self, message: str, **kwargs: Any) -> None:
        kwargs.setdefault("classification", "UPSTREAM_SERVER_ERROR")
        kwargs.setdefault("is_retryable", True)
        kwargs.setdefault("failure_stage", "UPSTREAM_EXECUTION")
        super().__init__(message, **kwargs)


class NebiusTimeoutError(NebiusProviderError):
    """Raised when provider request times out."""

    def __init__(self, message: str, **kwargs: Any) -> None:
        kwargs.setdefault("classification", "TIMEOUT_ERROR")
        kwargs.setdefault("is_retryable", True)
        kwargs.setdefault("failure_stage", "REQUEST_TIMEOUT")
        super().__init__(message, **kwargs)


class NebiusTransportError(NebiusProviderError):
    """Raised on network connection errors."""

    def __init__(self, message: str, **kwargs: Any) -> None:
        kwargs.setdefault("classification", "NETWORK_TRANSPORT_ERROR")
        kwargs.setdefault("is_retryable", True)
        kwargs.setdefault("failure_stage", "TRANSPORT_CONNECTION")
        super().__init__(message, **kwargs)


class NebiusMalformedResponseError(NebiusProviderError):
    """Raised when model response is empty, unexpected, or structurally invalid."""

    def __init__(self, message: str, **kwargs: Any) -> None:
        kwargs.setdefault("classification", "MALFORMED_RESPONSE_ERROR")
        kwargs.setdefault("is_retryable", False)
        kwargs.setdefault("failure_stage", "RESPONSE_PARSING")
        super().__init__(message, **kwargs)


class ModelProposalValidationError(ProviderError):
    """Raised when model output fails structural or semantic validation."""
    pass
