"""MotionFence Configuration Module."""

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


class Settings(BaseModel):
    """Global MotionFence application settings."""
    app_name: str = "MotionFence"
    version: str = "0.1.0"
    environment: str = "simulation"
    policy: PolicySettings = Field(default_factory=PolicySettings)
    log_level: str = "INFO"


# Default singleton instance
settings = Settings()
