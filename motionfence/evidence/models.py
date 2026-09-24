"""Evidence representation and contradiction reporting models."""

from enum import Enum
from typing import Any, Dict, List, Optional
import time
import uuid
from pydantic import BaseModel, Field


class EvidenceSource(str, Enum):
    """Categorization of evidence gathering sources."""
    VISION = "vision"
    PRESSURE_SENSOR = "pressure_sensor"
    THERMAL_SENSOR = "thermal_sensor"
    ACOUSTIC_SENSOR = "acoustic_sensor"
    HUMAN_OPERATOR = "human_operator"
    SYSTEM_TELEMETRY = "system_telemetry"


class ContradictionSeverity(str, Enum):
    """Severity levels for contradictory physical observations."""
    NONE = "NONE"
    LOW = "LOW"
    MEDIUM = "MEDIUM"
    HIGH = "HIGH"


class Evidence(BaseModel):
    """Structured evidence item capturing an observation with provenance and confidence."""
    id: str = Field(default_factory=lambda: f"ev_{uuid.uuid4().hex[:8]}")
    source: EvidenceSource = Field(..., description="Sensor or human source of this observation.")
    target: str = Field(..., description="Entity or component observed (e.g., 'valve_b', 'cooling').")
    observation: Dict[str, Any] = Field(..., description="Observed values, flags, or structured readings.")
    confidence: float = Field(..., ge=0.0, le=1.0, description="Evaluated confidence in the observation.")
    timestamp: float = Field(default_factory=time.time)
    provenance: str = Field(..., description="Lineage or instrument identifier that produced the observation.")
    metadata: Dict[str, Any] = Field(default_factory=dict)


class ContradictionReport(BaseModel):
    """Machine-readable assessment of conflicting physical observations."""
    contradiction: bool = Field(default=False, description="Whether a factual contradiction exists.")
    sources: List[str] = Field(default_factory=list, description="Sensor sources involved in the contradiction.")
    severity: ContradictionSeverity = Field(
        default=ContradictionSeverity.NONE,
        description="Severity level of the contradiction."
    )
    target: Optional[str] = Field(default=None, description="Entity under conflicting observation.")
    conflicting_evidence_ids: List[str] = Field(
        default_factory=list,
        description="IDs of the conflicting evidence objects."
    )
    details: str = Field(default="", description="Human-readable explanation of the conflict.")
