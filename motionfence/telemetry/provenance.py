"""Deterministic provenance tracking and cryptographic hashing for public telemetry.

SECURITY INVARIANTS:
1. Two identical normalized observations produce the exact same canonical hash.
2. Any modification to value, unit, location, or timestamp produces a distinct hash.
3. Provenance retains full origin lineage (source, endpoint, station, parameter, timestamps).
"""

import hashlib
import json
from typing import Any, Dict, List, Optional
from motionfence.telemetry.models import ObservationSnapshot


def compute_provenance_hash(
    provider: str,
    source_url: str,
    monitoring_location_id: str,
    parameter_code: str,
    observed_at: str,
) -> str:
    """Compute deterministic SHA-256 hash representing observation origin and parameter."""
    payload = {
        "provider": provider,
        "source_url": source_url,
        "monitoring_location_id": monitoring_location_id,
        "parameter_code": parameter_code,
        "observed_at": observed_at,
    }
    dump = json.dumps(payload, sort_keys=True)
    return hashlib.sha256(dump.encode("utf-8")).hexdigest()


def compute_observation_payload_hash(
    provider: str,
    source_url: str,
    monitoring_location_id: str,
    parameter_code: str,
    raw_value: str,
    unit: str,
    observed_at: str,
    approval_status: Optional[str] = None,
    qualifier: Optional[List[str]] = None,
) -> str:
    """Compute deterministic SHA-256 hash across canonical observation fields."""
    payload = {
        "provider": provider,
        "source_url": source_url,
        "monitoring_location_id": monitoring_location_id,
        "parameter_code": parameter_code,
        "raw_value": raw_value,
        "unit": unit,
        "observed_at": observed_at,
        "approval_status": approval_status or "NONE",
        "qualifier": sorted(qualifier) if qualifier else [],
    }
    dump = json.dumps(payload, sort_keys=True)
    return hashlib.sha256(dump.encode("utf-8")).hexdigest()


def compute_raw_record_hash(raw_data: Dict[str, Any]) -> str:
    """Compute SHA-256 hash of verbatim raw provider response record."""
    try:
        dump = json.dumps(raw_data, sort_keys=True)
    except Exception:
        dump = str(raw_data)
    return hashlib.sha256(dump.encode("utf-8")).hexdigest()


def verify_observation_integrity(obs: ObservationSnapshot) -> bool:
    """Verify that an ObservationSnapshot's payload matches its recorded raw_record_hash."""
    expected_hash = compute_observation_payload_hash(
        provider=obs.provider,
        source_url=obs.source_url,
        monitoring_location_id=obs.monitoring_location_id,
        parameter_code=obs.parameter_code,
        raw_value=obs.raw_value,
        unit=obs.unit,
        observed_at=obs.observed_at,
        approval_status=obs.approval_status,
        qualifier=obs.qualifier,
    )
    return obs.raw_record_hash == expected_hash
