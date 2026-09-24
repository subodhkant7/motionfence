"""MotionFence Configuration Module."""

import os
from typing import Optional
from pydantic import BaseModel, Field


class PolicySettings(BaseModel):
    """Configurable thresholds for deterministic policy evaluation."""
    min_target_confidence: float = Field(
        default=0.90,
        description="Minimum confidence required in target identification to allow actuation."
    )
    require_multi_source_evidence: bool = Field(
        default=False,
        description="Whether multiple independent sensor sources are required for actuation."
    )
    contradiction_severity_threshold: str = Field(
        default="HIGH",
        description="Contradiction severity level that triggers immediate blockage."
    )
    knowledge_freshness_max_age_seconds: float = Field(
        default=86400.0 * 30.0,  # 30 days
        description="Maximum age in seconds before knowledge evidence/constraints are considered stale."
    )


class NebiusSettings(BaseModel):
    """Configuration for Nebius Token Factory and NVIDIA Nemotron models."""
    api_key: Optional[str] = Field(
        default_factory=lambda: os.getenv("NEBIUS_API_KEY"),
        description="API key for Nebius Token Factory (loaded strictly from environment)."
    )
    base_url: str = Field(
        default_factory=lambda: os.getenv("NEBIUS_BASE_URL", "https://api.tokenfactory.nebius.com/v1/"),
        description="OpenAI-compatible base URL for Nebius Token Factory."
    )
    model: str = Field(
        default_factory=lambda: os.getenv("NEBIUS_MODEL", "nvidia/nemotron-3-super-120b-a12b"),
        description="NVIDIA Nemotron model identifier."
    )
    timeout_seconds: float = Field(
        default_factory=lambda: float(os.getenv("NEBIUS_TIMEOUT_SECONDS", "30.0")),
        description="Timeout in seconds for model inference requests."
    )
    max_retries: int = Field(
        default_factory=lambda: int(os.getenv("NEBIUS_MAX_RETRIES", "3")),
        description="Maximum retry attempts for transient API errors."
    )


class TavilySettings(BaseModel):
    """Configuration for Tavily Search API."""
    api_key: Optional[str] = Field(
        default_factory=lambda: os.getenv("TAVILY_API_KEY"),
        description="API key for Tavily search (loaded strictly from environment)."
    )
    timeout_seconds: float = Field(
        default_factory=lambda: float(os.getenv("TAVILY_TIMEOUT_SECONDS", "15.0")),
        description="Timeout in seconds for Tavily retrieval requests."
    )
    max_results: int = Field(
        default_factory=lambda: int(os.getenv("TAVILY_MAX_RESULTS", "5")),
        description="Maximum search results to retrieve."
    )


class Settings(BaseModel):
    """Global MotionFence application settings."""
    app_name: str = "MotionFence"
    version: str = "0.1.0"
    environment: str = "simulation"
    policy: PolicySettings = Field(default_factory=PolicySettings)
    nebius: NebiusSettings = Field(default_factory=NebiusSettings)
    tavily: TavilySettings = Field(default_factory=TavilySettings)
    log_level: str = "INFO"


# Default singleton instance
settings = Settings()
