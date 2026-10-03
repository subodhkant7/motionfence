"""MotionFence Real-World Public Telemetry Package (Phase 2O).

Provides:
- PublicTelemetryProvider interface
- USGSOgcTelemetryProvider (modern USGS Water Data OGC API)
- TelemetryNormalizer for GeoJSON latest-continuous FeatureCollection
- ObservationSnapshot with provenance and cryptographic hashing
- BoundedTelemetryCache for LIVE vs REPLAY isolation
- TelemetryReplayEngine for 100% offline verified replay
- TelemetryEvidenceAdapter connecting observations to Evidence & WorldState
"""

from motionfence.telemetry.models import (
    DerivedEnvironmentalContext,
    ObservationFreshness,
    ObservationSnapshot,
    TelemetryConfig,
    TelemetryMode,
    TelemetryStatus,
)
from motionfence.telemetry.provenance import (
    compute_observation_payload_hash,
    compute_provenance_hash,
    compute_raw_record_hash,
    verify_observation_integrity,
)
from motionfence.telemetry.normalizer import TelemetryNormalizer
from motionfence.telemetry.provider import PublicTelemetryProvider
from motionfence.telemetry.usgs_provider import USGSOgcTelemetryProvider
from motionfence.telemetry.cache import BoundedTelemetryCache
from motionfence.telemetry.replay import TelemetryReplayEngine, TelemetryReplayRecord
from motionfence.telemetry.adapter import TelemetryEvidenceAdapter

__all__ = [
    "DerivedEnvironmentalContext",
    "ObservationFreshness",
    "ObservationSnapshot",
    "TelemetryConfig",
    "TelemetryMode",
    "TelemetryStatus",
    "compute_observation_payload_hash",
    "compute_provenance_hash",
    "compute_raw_record_hash",
    "verify_observation_integrity",
    "TelemetryNormalizer",
    "PublicTelemetryProvider",
    "USGSOgcTelemetryProvider",
    "BoundedTelemetryCache",
    "TelemetryReplayEngine",
    "TelemetryReplayRecord",
    "TelemetryEvidenceAdapter",
]
