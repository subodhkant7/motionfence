"""MotionFence Configuration Module."""

import os
from typing import Optional
from pydantic import BaseModel, Field


def _load_env_file() -> None:
    """Safely load .env file into os.environ if present without external dependencies."""
    candidates = [
        os.path.join(os.getcwd(), ".env"),
        os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..", ".env")),
    ]
    for env_path in candidates:
        if os.path.isfile(env_path):
            try:
                with open(env_path, "r", encoding="utf-8") as f:
                    for line in f:
                        line = line.strip()
                        if not line or line.startswith("#") or "=" not in line:
                            continue
                        key, val = line.split("=", 1)
                        key = key.strip()
                        val = val.strip()
                        if (val.startswith('"') and val.endswith('"')) or (val.startswith("'") and val.endswith("'")):
                            val = val[1:-1]
                        if key and key not in os.environ and val != "":
                            os.environ[key] = val
                break
            except Exception:
                pass


_load_env_file()


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
    max_output_tokens: int = Field(
        default_factory=lambda: int(os.getenv("NEBIUS_MAX_OUTPUT_TOKENS", "600")),
        description="Maximum output tokens for model inference to strictly cap credit consumption."
    )
    allow_public_live: bool = Field(
        default_factory=lambda: os.getenv("MOTIONFENCE_ALLOW_PUBLIC_LIVE", "").strip().lower() in ("1", "true", "yes"),
        description="Whether to permit live external model inference from public demo requests. Defaults to False to prevent unapproved spending."
    )

    @property
    def is_configured(self) -> bool:
        """Safe check whether Nebius API key is configured without exposing secret."""
        return bool(self.api_key and self.api_key != "placeholder_key_offline")


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

    @property
    def is_configured(self) -> bool:
        """Safe check whether Tavily API key is configured without exposing secret."""
        return bool(self.api_key and self.api_key != "placeholder_key_offline")


class SecuritySettings(BaseModel):
    """Cryptographic and trust-boundary security settings."""
    kernel_secret: str = Field(
        default_factory=lambda: os.getenv("MOTIONFENCE_KERNEL_SECRET", "motionfence_runtime_kernel_secret"),
        description="HMAC key used for signing and validating AuthorizationTickets.",
    )
    allow_insecure_tls: bool = Field(
        default_factory=lambda: os.getenv("MOTIONFENCE_ALLOW_INSECURE_TLS", "").strip().lower() in ("1", "true", "yes"),
        description="Explicit test-only opt-in to permit unverified TLS contexts. Forbidden in production.",
    )
    trusted_proxies: str = Field(
        default_factory=lambda: os.getenv("MOTIONFENCE_TRUSTED_PROXIES", ""),
        description="Comma-separated IP addresses of trusted reverse proxies allowed to set X-Forwarded-For.",
    )
    cors_origin: str = Field(
        default_factory=lambda: os.getenv("MOTIONFENCE_CORS_ORIGIN", ""),
        description="Allowed CORS origin. In production, must be the exact deployed Judge Console origin. Wildcard '*' is forbidden.",
    )

    def validate_for_production(self, environment: str) -> None:
        """Enforce strict production cryptographic boundaries."""
        is_prod = environment.lower() in ("production", "prod")
        if not is_prod:
            return

        # 1. Insecure TLS forbidden in production
        if self.allow_insecure_tls:
            raise RuntimeError(
                "PRODUCTION SECURITY VIOLATION: MOTIONFENCE_ALLOW_INSECURE_TLS cannot be enabled in production."
            )

        # 2. Kernel secret must be strong, high-entropy, and non-default
        fallback_secrets = {
            "motionfence_runtime_kernel_secret",
            "motionfence_dev_test_kernel_secret",
            "default",
            "secret",
        }
        if (
            not self.kernel_secret
            or self.kernel_secret in fallback_secrets
            or len(self.kernel_secret) < 32
        ):
            raise RuntimeError(
                "PRODUCTION SECURITY VIOLATION: In production mode, MOTIONFENCE_KERNEL_SECRET must be set to "
                "a high-entropy secret of at least 32 characters. Refusing to start with missing or default test secret."
            )

        # 3. Wildcard CORS origin is forbidden in production
        if self.cors_origin.strip() == "*":
            raise RuntimeError(
                "PRODUCTION SECURITY VIOLATION: Wildcard CORS origin ('*') is strictly prohibited in production. "
                "Specify an exact deployed HTTPS origin via MOTIONFENCE_CORS_ORIGIN, or leave empty for same-origin only."
            )


class Settings(BaseModel):
    """Global MotionFence application settings."""
    app_name: str = "MotionFence"
    version: str = "0.1.0"
    environment: str = Field(
        default_factory=lambda: os.getenv("MOTIONFENCE_ENV", os.getenv("ENVIRONMENT", "simulation")),
        description="Runtime environment: 'simulation', 'development', 'testing', or 'production'."
    )
    policy: PolicySettings = Field(default_factory=PolicySettings)
    nebius: NebiusSettings = Field(default_factory=NebiusSettings)
    tavily: TavilySettings = Field(default_factory=TavilySettings)
    security: SecuritySettings = Field(default_factory=SecuritySettings)
    log_level: str = "INFO"

    def validate_production_security(self) -> None:
        """Validate all security invariants for production deployment."""
        self.security.validate_for_production(self.environment)


# Default singleton instance
settings = Settings()

