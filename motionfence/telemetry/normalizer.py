"""Telemetry normalizer for USGS Water Data OGC API responses (Phase 2O).

Normalizes GeoJSON FeatureCollection into strongly typed ObservationSnapshots.
Validates schemas, parses timestamps, evaluates freshness, and computes cryptographic hashes.
"""

from datetime import datetime, timezone
import logging
import time
from typing import Any, Dict, List, Optional, Tuple

from motionfence.telemetry.models import (
    ObservationFreshness,
    ObservationSnapshot,
    TelemetryConfig,
    TelemetryStatus,
)
from motionfence.telemetry.provenance import (
    compute_observation_payload_hash,
    compute_provenance_hash,
)

logger = logging.getLogger("motionfence.telemetry.normalizer")

# Standard canonical USGS parameter code mapping
USGS_PARAMETER_NAMES: Dict[str, str] = {
    "00060": "Discharge / Streamflow",
    "00065": "Gage height",
    "00010": "Water temperature",
    "00095": "Specific conductance",
    "00300": "Dissolved oxygen",
    "00400": "pH",
}


def parse_iso_timestamp(ts_str: str) -> Optional[float]:
    """Parse ISO 8601 / RFC 3339 timestamp into epoch seconds."""
    if not ts_str or not isinstance(ts_str, str):
        return None
    try:
        # Replace trailing Z with UTC offset
        clean_ts = ts_str.replace("Z", "+00:00")
        dt = datetime.fromisoformat(clean_ts)
        return dt.timestamp()
    except Exception as e:
        logger.warning(f"Failed to parse timestamp '{ts_str}': {e}")
        return None


class TelemetryNormalizer:
    """Normalizes raw USGS OGC API responses into validated ObservationSnapshots."""

    def __init__(self, config: Optional[TelemetryConfig] = None):
        self.config = config or TelemetryConfig()

    def validate_feature_collection(
        self, data: Any
    ) -> Tuple[TelemetryStatus, Optional[List[Dict[str, Any]]], str]:
        """Validate that response adheres to GeoJSON FeatureCollection schema."""
        if not isinstance(data, dict):
            return TelemetryStatus.SCHEMA_ERROR, None, "Response is not a valid JSON object."

        if data.get("type") != "FeatureCollection":
            return TelemetryStatus.SCHEMA_ERROR, None, f"Expected 'FeatureCollection', got '{data.get('type')}'."

        features = data.get("features")
        if not isinstance(features, list):
            return TelemetryStatus.SCHEMA_ERROR, None, "FeatureCollection 'features' must be a list."

        if len(features) == 0:
            return TelemetryStatus.NO_DATA, [], "FeatureCollection contains zero features."

        return TelemetryStatus.SUCCESS, features, "Valid FeatureCollection schema."

    def normalize_feature(
        self,
        feature: Dict[str, Any],
        source_url: str,
        retrieved_timestamp: Optional[float] = None,
        retrieved_at: Optional[str] = None,
    ) -> Tuple[TelemetryStatus, Optional[ObservationSnapshot], str]:
        """Normalize a single GeoJSON Feature from latest-continuous into an ObservationSnapshot."""
        if not isinstance(feature, dict):
            return TelemetryStatus.SCHEMA_ERROR, None, "Feature is not a JSON object."

        props = feature.get("properties")
        if not isinstance(props, dict):
            return TelemetryStatus.SCHEMA_ERROR, None, "Feature missing 'properties' dictionary."

        # Required fields according to USGS OGC API latest-continuous queryables
        monitoring_loc_id = props.get("monitoring_location_id")
        param_code = props.get("parameter_code")
        raw_val = props.get("value")
        obs_time_str = props.get("time")

        if not monitoring_loc_id or not isinstance(monitoring_loc_id, str):
            return TelemetryStatus.SCHEMA_ERROR, None, "Missing or invalid 'monitoring_location_id'."

        if not param_code or not isinstance(param_code, str):
            return TelemetryStatus.SCHEMA_ERROR, None, "Missing or invalid 'parameter_code'."

        if raw_val is None:
            return TelemetryStatus.SCHEMA_ERROR, None, f"Missing 'value' for parameter {param_code}."

        raw_val_str = str(raw_val).strip()
        if not raw_val_str:
            return TelemetryStatus.NO_DATA, None, f"Empty 'value' for parameter {param_code}."

        if not obs_time_str or not isinstance(obs_time_str, str):
            return TelemetryStatus.SCHEMA_ERROR, None, f"Missing or invalid 'time' for parameter {param_code}."

        # Parse observed timestamp
        obs_timestamp = parse_iso_timestamp(obs_time_str)
        if obs_timestamp is None:
            return TelemetryStatus.SCHEMA_ERROR, None, f"Invalid ISO 8601 timestamp '{obs_time_str}'."

        now_ts = retrieved_timestamp or time.time()
        now_str = retrieved_at or datetime.now(timezone.utc).isoformat()

        # Compute freshness
        age_seconds = now_ts - obs_timestamp
        if age_seconds < -300.0:
            # Future timestamp by > 5 mins
            freshness = ObservationFreshness.UNKNOWN
        elif age_seconds > self.config.freshness_threshold_seconds:
            freshness = ObservationFreshness.STALE
        else:
            freshness = ObservationFreshness.FRESH

        # Parameter name mapping (semantic honesty: UNKNOWN if unrecognized)
        param_name = USGS_PARAMETER_NAMES.get(param_code, "UNKNOWN")

        # Parse normalized value
        normalized_val: Optional[float] = None
        try:
            normalized_val = float(raw_val_str)
        except (ValueError, TypeError):
            normalized_val = None

        unit = props.get("unit_of_measure") or "UNKNOWN"
        approval = props.get("approval_status")
        qualifier = props.get("qualifier")
        if qualifier is not None and not isinstance(qualifier, list):
            qualifier = [str(qualifier)]

        # Location name from config if matching
        loc_name = None
        if monitoring_loc_id == self.config.monitoring_location_id:
            loc_name = self.config.monitoring_location_name

        # Build provenance & record hashes
        prov_hash = compute_provenance_hash(
            provider="USGS",
            source_url=source_url,
            monitoring_location_id=monitoring_loc_id,
            parameter_code=param_code,
            observed_at=obs_time_str,
        )

        rec_hash = compute_observation_payload_hash(
            provider="USGS",
            source_url=source_url,
            monitoring_location_id=monitoring_loc_id,
            parameter_code=param_code,
            raw_value=raw_val_str,
            unit=unit,
            observed_at=obs_time_str,
            approval_status=approval,
            qualifier=qualifier,
        )

        snapshot_id = f"obs_usgs_{param_code}_{rec_hash[:10]}"

        snapshot = ObservationSnapshot(
            observation_id=snapshot_id,
            provider="USGS",
            source_system="USGS Water Data OGC API (latest-continuous)",
            source_url=source_url,
            monitoring_location_id=monitoring_loc_id,
            monitoring_location_name=loc_name,
            parameter_code=param_code,
            parameter_name=param_name,
            raw_value=raw_val_str,
            normalized_value=normalized_val,
            unit=unit,
            observed_at=obs_time_str,
            observed_timestamp=obs_timestamp,
            retrieved_at=now_str,
            retrieved_timestamp=now_ts,
            freshness=freshness,
            freshness_age_seconds=max(0.0, age_seconds),
            approval_status=approval,
            qualifier=qualifier,
            source_metadata={
                "time_series_id": props.get("time_series_id"),
                "statistic_id": props.get("statistic_id"),
                "last_modified": props.get("last_modified"),
                "geometry": feature.get("geometry"),
            },
            provenance_hash=prov_hash,
            raw_record_hash=rec_hash,
        )

        return TelemetryStatus.SUCCESS, snapshot, "Observation normalized successfully."

    def normalize_collection(
        self,
        collection_data: Any,
        source_url: str,
        retrieved_timestamp: Optional[float] = None,
        retrieved_at: Optional[str] = None,
    ) -> Tuple[TelemetryStatus, List[ObservationSnapshot], List[str]]:
        """Normalize an entire FeatureCollection response into a list of ObservationSnapshots."""
        status, features, msg = self.validate_feature_collection(collection_data)
        if status != TelemetryStatus.SUCCESS or features is None:
            return status, [], [msg]

        snapshots: List[ObservationSnapshot] = []
        errors: List[str] = []

        for idx, feat in enumerate(features):
            feat_status, snapshot, feat_msg = self.normalize_feature(
                feat,
                source_url=source_url,
                retrieved_timestamp=retrieved_timestamp,
                retrieved_at=retrieved_at,
            )
            if feat_status == TelemetryStatus.SUCCESS and snapshot is not None:
                snapshots.append(snapshot)
            else:
                errors.append(f"Feature[{idx}]: {feat_msg}")

        if not snapshots and errors:
            return TelemetryStatus.SCHEMA_ERROR, [], errors

        return TelemetryStatus.SUCCESS, snapshots, errors
