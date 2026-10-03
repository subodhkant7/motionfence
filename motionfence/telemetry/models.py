"""Data models for real-world public telemetry in MotionFence (Phase 2O).

SECURITY INVARIANTS:
1. Public telemetry is strictly an OBSERVATION source; it has ZERO direct actuation authority.
2. Observations are immutable once normalized and cryptographically bound to source provenance.
3. Freshness is explicitly classified and never silently promoted from STALE to FRESH.
4. Telemetry is cleanly distinguished from internal modeled plant control state.
"""

from enum import Enum
import hashlib
import json
import time
from typing import Any, Dict, List, Optional
from pydantic import BaseModel, Field


class ObservationFreshness(str, Enum):
    """Categorical freshness status of an external observation."""
    FRESH = "FRESH"
    STALE = "STALE"
    UNKNOWN = "UNKNOWN"


class TelemetryStatus(str, Enum):
    """Status outcomes for public telemetry acquisition and parsing."""
    SUCCESS = "SUCCESS"
    TRANSPORT_ERROR = "TRANSPORT_ERROR"
    HTTP_ERROR = "HTTP_ERROR"
    SCHEMA_ERROR = "SCHEMA_ERROR"
    SEMANTIC_ERROR = "SEMANTIC_ERROR"
    STALE_DATA = "STALE_DATA"
    NO_DATA = "NO_DATA"


class TelemetryMode(str, Enum):
    """Explicit operational mode for observation acquisition."""
    LIVE_OBSERVATION = "LIVE_OBSERVATION"
    REPLAYED_OBSERVATION = "REPLAYED_OBSERVATION"


class TelemetryConfig(BaseModel):
    """Configuration for public telemetry acquisition."""
    provider_name: str = Field(default="USGS", description="Canonical provider name.")
    monitoring_location_id: str = Field(
        default="USGS-01646500",
        description="Canonical USGS monitoring location identifier."
    )
    monitoring_location_name: str = Field(
        default="POTOMAC RIVER NEAR WASH, DC LITTLE FALLS PUMP STA",
        description="Human-readable station designation verified against official metadata."
    )
    parameter_codes: List[str] = Field(
        default_factory=lambda: ["00060", "00065"],
        description="USGS parameter codes: '00060' (Discharge / Streamflow, ft³/s), '00065' (Gage height, ft)."
    )
    freshness_threshold_seconds: float = Field(
        default=7200.0,
        description="Maximum age in seconds (2 hours) before observation is classified as STALE."
    )
    base_url: str = Field(
        default="https://api.waterdata.usgs.gov/ogcapi/v1",
        description="Modern USGS Water Data OGC API base endpoint."
    )
    timeout_seconds: float = Field(
        default=10.0,
        description="Network HTTP timeout in seconds."
    )
    api_key: Optional[str] = Field(
        default=None,
        description="Optional API key for higher rate limits (never hardcoded, kept empty by default)."
    )


class ObservationSnapshot(BaseModel):
    """Immutable normalized external physical observation with source provenance.
    
    SECURITY INVARIANT:
    Retains full origin lineage and deterministic hashes. Never silently discards provenance.
    """
    observation_id: str = Field(..., description="Unique deterministic or generated identifier.")
    provider: str = Field(default="USGS", description="Name of external telemetry provider.")
    source_system: str = Field(
        default="USGS Water Data OGC API (latest-continuous)",
        description="System or API family providing the observation."
    )
    source_url: str = Field(..., description="Exact public endpoint URL used to retrieve this observation.")
    monitoring_location_id: str = Field(..., description="Monitoring location identifier (e.g. USGS-01646500).")
    monitoring_location_name: Optional[str] = Field(
        default=None,
        description="Official monitoring station name if available from metadata."
    )
    parameter_code: str = Field(..., description="Provider constituent parameter code (e.g. 00060).")
    parameter_name: Optional[str] = Field(
        default=None,
        description="Standardized constituent name (e.g. Streamflow/Discharge or Gage height)."
    )
    raw_value: str = Field(..., description="Verbatim value string from the API to preserve original precision.")
    normalized_value: Optional[float] = Field(
        default=None,
        description="Parsed floating point measurement value, or None if unparseable."
    )
    unit: str = Field(..., description="Measurement unit (e.g. ft^3/s, ft, deg C).")
    observed_at: str = Field(..., description="Observation timestamp string from sensor/provider in ISO 8601.")
    observed_timestamp: float = Field(..., description="Observation epoch seconds.")
    retrieved_at: str = Field(..., description="Retrieval timestamp in ISO 8601 UTC.")
    retrieved_timestamp: float = Field(..., description="Retrieval epoch seconds.")
    freshness: ObservationFreshness = Field(..., description="FRESH, STALE, or UNKNOWN.")
    freshness_age_seconds: float = Field(..., description="Age in seconds (retrieved_timestamp - observed_timestamp).")
    approval_status: Optional[str] = Field(
        default=None,
        description="USGS data approval status (e.g. 'Approved', 'Provisional')."
    )
    qualifier: Optional[List[str]] = Field(
        default=None,
        description="Provider data qualifiers or flags (e.g. ['DISCONTINUED'], ['ESTIMATED'])."
    )
    source_metadata: Dict[str, Any] = Field(
        default_factory=dict,
        description="Preserved raw metadata from provider response (time_series_id, statistic_id, etc.)."
    )
    provenance_hash: str = Field(..., description="SHA-256 hash of core origin and lineage metadata.")
    raw_record_hash: str = Field(..., description="SHA-256 hash of the normalized observation payload.")

    def compute_canonical_hash(self) -> str:
        """Compute deterministic SHA-256 hash over canonical observation fields."""
        canonical_dict = {
            "provider": self.provider,
            "source_url": self.source_url,
            "monitoring_location_id": self.monitoring_location_id,
            "parameter_code": self.parameter_code,
            "raw_value": self.raw_value,
            "unit": self.unit,
            "observed_at": self.observed_at,
            "approval_status": self.approval_status or "NONE",
            "qualifier": sorted(self.qualifier) if self.qualifier else [],
        }
        dump = json.dumps(canonical_dict, sort_keys=True)
        return hashlib.sha256(dump.encode("utf-8")).hexdigest()

    def verify_integrity(self) -> bool:
        """Verify that record content matches its canonical record hash."""
        return self.compute_canonical_hash() == self.raw_record_hash


class DerivedEnvironmentalContext(BaseModel):
    """Deterministic derived context from external observation.
    
    SECURITY INVARIANT:
    Safety thresholds and derivations must be 100% deterministic and rule-bound.
    No LLM may invent or modify safety thresholds.
    """
    context_id: str
    context_name: str = Field(..., description="Domain name (e.g. 'POTOMAC_RIVER_FLOW_REGIME').")
    classification: str = Field(..., description="Discrete classification (e.g. 'HIGH_FLOW', 'NORMAL_FLOW').")
    source_observation_ids: List[str] = Field(..., description="IDs of observations supporting this derivation.")
    threshold_value: float = Field(..., description="Configured deterministic threshold.")
    observed_metric_value: float = Field(..., description="Value evaluated against threshold.")
    unit: str = Field(..., description="Unit of measurement.")
    rule_id: str = Field(..., description="Identifier of deterministic policy derivation rule.")
    derivation_timestamp: float = Field(default_factory=time.time)
    deterministic_hash: str = Field(..., description="Cryptographic binding of rule + input -> derivation.")

    @classmethod
    def create(
        cls,
        context_name: str,
        classification: str,
        source_obs: ObservationSnapshot,
        threshold_value: float,
        rule_id: str,
    ) -> "DerivedEnvironmentalContext":
        observed_val = source_obs.normalized_value if source_obs.normalized_value is not None else 0.0
        derivation_time = time.time()
        canonical_content = {
            "context_name": context_name,
            "classification": classification,
            "source_observation_id": source_obs.observation_id,
            "threshold_value": threshold_value,
            "observed_val": observed_val,
            "unit": source_obs.unit,
            "rule_id": rule_id,
        }
        h = hashlib.sha256(json.dumps(canonical_content, sort_keys=True).encode("utf-8")).hexdigest()
        return cls(
            context_id=f"ctx_env_{h[:12]}",
            context_name=context_name,
            classification=classification,
            source_observation_ids=[source_obs.observation_id],
            threshold_value=threshold_value,
            observed_metric_value=observed_val,
            unit=source_obs.unit,
            rule_id=rule_id,
            derivation_timestamp=derivation_time,
            deterministic_hash=h,
        )
