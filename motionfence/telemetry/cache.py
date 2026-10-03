"""Bounded local cache for normalized public telemetry observations (Phase 2O).

SECURITY INVARIANTS:
1. Every cached observation is explicitly tagged with TelemetryMode.
2. A cached or replayed observation can NEVER be mislabeled as LIVE_OBSERVATION.
3. Integrity is verified using canonical SHA-256 hashes upon retrieval.
4. Bounded capacity prevents unbounded memory growth.
"""

from collections import OrderedDict
import logging
import time
from typing import Any, Dict, List, Optional, Tuple

from motionfence.telemetry.models import (
    ObservationSnapshot,
    TelemetryMode,
)
from motionfence.telemetry.provenance import verify_observation_integrity

logger = logging.getLogger("motionfence.telemetry.cache")


class CachedObservationEntry:
    """Internal cache entry wrapper with explicit mode and timestamps."""

    def __init__(
        self,
        snapshot: ObservationSnapshot,
        mode: TelemetryMode,
        cached_at: float,
    ):
        self.snapshot = snapshot
        self.mode = mode
        self.cached_at = cached_at
        self.canonical_hash = snapshot.raw_record_hash
        self.provenance_hash = snapshot.provenance_hash

    def to_dict(self) -> Dict[str, Any]:
        return {
            "snapshot": self.snapshot.model_dump(),
            "mode": self.mode.value,
            "cached_at": self.cached_at,
            "canonical_hash": self.canonical_hash,
            "provenance_hash": self.provenance_hash,
        }


class BoundedTelemetryCache:
    """Thread-safe bounded in-memory LRU cache for external observations."""

    def __init__(self, max_entries: int = 100):
        self.max_entries = max_entries
        self._cache: OrderedDict[str, CachedObservationEntry] = OrderedDict()

    def put(
        self,
        snapshot: ObservationSnapshot,
        mode: TelemetryMode = TelemetryMode.LIVE_OBSERVATION,
    ) -> bool:
        """Store an ObservationSnapshot in the cache with explicit mode.
        
        Verifies integrity before storing.
        """
        if not snapshot.verify_integrity():
            logger.error(f"Cannot cache observation {snapshot.observation_id}: integrity verification failed.")
            return False

        key = f"{snapshot.monitoring_location_id}:{snapshot.parameter_code}"

        # Evict oldest if capacity exceeded
        if len(self._cache) >= self.max_entries and key not in self._cache:
            self._cache.popitem(last=False)

        entry = CachedObservationEntry(
            snapshot=snapshot,
            mode=mode,
            cached_at=time.time(),
        )
        self._cache[key] = entry
        self._cache.move_to_end(key)
        return True

    def get(
        self,
        monitoring_location_id: str,
        parameter_code: str,
    ) -> Tuple[Optional[ObservationSnapshot], Optional[TelemetryMode]]:
        """Retrieve cached observation.
        
        CRITICAL INVARIANT:
        Returns the snapshot along with its explicit TelemetryMode.
        If cache hit is replayed or older than acquisition, its mode reflects its true provenance.
        """
        key = f"{monitoring_location_id}:{parameter_code}"
        entry = self._cache.get(key)
        if not entry:
            return None, None

        # Verify integrity on read
        if not verify_observation_integrity(entry.snapshot):
            logger.error(f"Cached observation {key} corrupted! Purging from cache.")
            del self._cache[key]
            return None, None

        self._cache.move_to_end(key)
        return entry.snapshot, entry.mode

    def get_all(self) -> List[Tuple[ObservationSnapshot, TelemetryMode]]:
        """Retrieve all currently cached observations with their modes."""
        results = []
        for entry in self._cache.values():
            if verify_observation_integrity(entry.snapshot):
                results.append((entry.snapshot, entry.mode))
        return results

    def clear(self) -> None:
        """Clear cache contents."""
        self._cache.clear()

    def __len__(self) -> int:
        return len(self._cache)
