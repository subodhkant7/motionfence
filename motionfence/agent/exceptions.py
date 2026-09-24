"""Exceptions for model providers and proposal validation."""


class ProviderError(Exception):
    """Base exception for all agent proposal providers."""
    pass


class NebiusProviderError(ProviderError):
    """Raised when an error occurs communicating with Nebius Token Factory."""
    pass


class ModelProposalValidationError(ProviderError):
    """Raised when model output fails structural or semantic validation."""
    pass
