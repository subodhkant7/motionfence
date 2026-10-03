"""Deterministic offline replay engine for public telemetry (Phase 2O).

SECURITY INVARIANTS:
1. 100% OFFLINE: Zero network calls, zero public API credentials.
2. ZERO ACTUATOR AUTHORITY: Replay cannot actuate hardware or mint live tickets.
3. CRYPTOGRAPHIC VERIFICATION: Replay verifies the SHA-256 canonical hash of every snapshot.
4. PROVENANCE INTEGRITY: Replayed observations are explicitly tagged as REPLAYED_OBSERVATION.
"""

import json
import logging
import os
from typing import Any, Dict, List, Optional, Tuple

from motionfence.telemetry.models import (
    ObservationFreshness,
    ObservationSnapshot,
    TelemetryMode,
)
from motionfence.telemetry.provenance import verify_observation_integrity

logger = logging.getLogger("motionfence.telemetry.replay")


class TelemetryReplayRecord:
    """Serializable record containing recorded public observations and execution context."""

    def __init__(
        self,
        record_id: str,
        mode: TelemetryMode,
        snapshots: List[ObservationSnapshot],
        recorded_at: str,
        context_metadata: Optional[Dict[str, Any]] = None,
    ):
        self.record_id = record_id
        self.mode = mode
        self.snapshots = snapshots
        self.recorded_at = recorded_at
        self.context_metadata = context_metadata or {}

    def to_dict(self) -> Dict[str, Any]:
        return {
            "record_id": self.record_id,
            "mode": self.mode.value,
            "recorded_at": self.recorded_at,
            "context_metadata": self.context_metadata,
            "snapshots": [s.model_dump() for s in self.snapshots],
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "TelemetryReplayRecord":
        mode_str = data.get("mode", TelemetryMode.REPLAYED_OBSERVATION.value)
        mode = TelemetryMode(mode_str)
        raw_snapshots = data.get("snapshots", [])
        snapshots = [ObservationSnapshot.model_validate(s) for s in raw_snapshots]
        return cls(
            record_id=data.get("record_id", "rec_replay_001"),
            mode=mode,
            snapshots=snapshots,
            recorded_at=data.get("recorded_at", ""),
            context_metadata=data.get("context_metadata", {}),
        )


class TelemetryReplayEngine:
    """Offline deterministic replay engine for public physical telemetry."""

    @classmethod
    def load_from_fixture(cls, fixture_path: str) -> Tuple[bool, List[ObservationSnapshot], str]:
        """Load and cryptographically verify recorded observations from a fixture file.
        
        Fails closed if the fixture is missing, unparseable, or tampered with.
        """
        if not os.path.isfile(fixture_path):
            return False, [], f"Fixture file not found: {fixture_path}"

        try:
            with open(fixture_path, "r", encoding="utf-8") as f:
                data = json.load(f)
        except Exception as e:
            return False, [], f"Failed to load fixture JSON: {e}"

        raw_snapshots = []
        if isinstance(data, dict):
            if "snapshots" in data:
                raw_snapshots = data["snapshots"]
            elif "telemetry_observation" in data:
                raw_snapshots = [data["telemetry_observation"]]
            else:
                raw_snapshots = [data]
        elif isinstance(data, list):
            raw_snapshots = data

        validated_snapshots: List[ObservationSnapshot] = []

        for idx, item in enumerate(raw_snapshots):
            try:
                obs = ObservationSnapshot.model_validate(item)
            except Exception as e:
                return False, [], f"Schema validation error on item {idx}: {e}"

            # Strict cryptographic verification
            if not verify_observation_integrity(obs):
                return False, [], f"Cryptographic integrity verification failed on observation {obs.observation_id}!"

            validated_snapshots.append(obs)

        return True, validated_snapshots, f"Successfully loaded and verified {len(validated_snapshots)} observations."
