"""Knowledge evidence representations and trust models for operational documentation."""

from enum import Enum
from typing import Any, Dict, Optional
import time
import uuid
from pydantic import BaseModel, Field


class TrustStatus(str, Enum):
    """Categorical trust and validation state of retrieved operational knowledge."""
    UNVERIFIED_EXTERNAL = "UNVERIFIED_EXTERNAL"
    LOCAL_FIXTURE = "LOCAL_FIXTURE"
    VALIDATED = "VALIDATED"
    STALE = "STALE"
    REJECTED = "REJECTED"


class FreshnessStatus(str, Enum):
    """Temporal freshness state of knowledge evidence."""
    FRESH = "FRESH"
    AGING = "AGING"
    STALE = "STALE"


class KnowledgeEvidence(BaseModel):
    """Structured evidence object representing retrieved operational knowledge with full provenance."""
    id: str = Field(default_factory=lambda: f"kb_{uuid.uuid4().hex[:8]}")
    query: str = Field(..., description="The query string that retrieved this knowledge.")
    title: str = Field(..., description="Document or section title.")
    source_url: str = Field(..., description="URL or local URI identifier (e.g. 'local://plant_manual_v1').")
    content: str = Field(..., description="Extracted text snippet or operating guidance.")
    retrieved_at: float = Field(default_factory=time.time, description="Timestamp of retrieval.")
    source_metadata: Dict[str, Any] = Field(default_factory=dict, description="Metadata from knowledge source.")
    provenance: str = Field(..., description="Detailed source attribution (e.g., 'tavily:search', 'fixture:sop_402').")
    confidence: float = Field(default=1.0, ge=0.0, le=1.0, description="Confidence in the source / retrieval relevance.")
    trust_status: TrustStatus = Field(default=TrustStatus.UNVERIFIED_EXTERNAL, description="Current trust qualification.")

    @property
    def age_seconds(self) -> float:
        """Elapsed time in seconds since this knowledge item was retrieved."""
        return time.time() - self.retrieved_at

    def check_freshness(self, max_age_seconds: float = 86400.0 * 30.0) -> FreshnessStatus:
        """Evaluate whether this knowledge item is temporally fresh or stale."""
        age = time.time() - self.retrieved_at
        if age < (max_age_seconds * 0.5):
            return FreshnessStatus.FRESH
        elif age < max_age_seconds:
            return FreshnessStatus.AGING
        return FreshnessStatus.STALE

    def is_stale(self, max_age_seconds: float = 86400.0 * 30.0) -> bool:
        """Helper to determine if knowledge item is considered STALE."""
        return self.check_freshness(max_age_seconds) == FreshnessStatus.STALE
