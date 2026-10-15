"""Canonical JSON Evidence Serializer & SHA-256 Integrity Verifier.

Provides deterministic canonical serialization and cryptographic hash integrity
checking for MotionFence Safety Lab evidence bundles and benchmark reports.

SECURITY NOTICE:
A matching SHA-256 hash establishes byte-level consistency and tamper detection
with the hashed artifact. It does NOT constitute a PKI digital signature or
cryptographic proof of physical execution.
"""

from __future__ import annotations

import hashlib
import json
from typing import Any, Dict, Optional, Tuple
from motionfence.benchmark.models import EvidenceBundle


def sanitize_value(val: Any) -> Any:
    """Recursively scrub sensitive keys and normalize types for canonical serialization."""
    sensitive_keys = {
        "api_key", "secret", "secret_key", "token", "password",
        "authorization", "private_key", "nebius_api_key", "tavily_api_key",
    }
    if isinstance(val, dict):
        cleaned = {}
        for k, v in val.items():
            if str(k).lower() in sensitive_keys:
                cleaned[k] = "[REDACTED]"
            else:
                cleaned[k] = sanitize_value(v)
        return cleaned
    elif isinstance(val, (list, tuple)):
        return [sanitize_value(item) for item in val]
    elif isinstance(val, float):
        # Round floats to 4 decimal places for stable cross-platform serialization
        return round(val, 4)
    elif hasattr(val, "model_dump"):
        return sanitize_value(val.model_dump())
    elif hasattr(val, "value"):
        return val.value
    return val


def canonicalize_json(data: Dict[str, Any], exclude_hash: bool = True) -> str:
    """Serialize dictionary to deterministic, canonical JSON string (RFC 8785 subset).
    
    Keys are sorted lexicographically, whitespace is minimal (no extra spaces),
    and encoding is UTF-8 without trailing newlines.
    """
    clean_dict = sanitize_value(data)
    if exclude_hash:
        clean_dict = {k: v for k, v in clean_dict.items() if k not in ("sha256_hash", "is_integrity_verified")}
    return json.dumps(clean_dict, sort_keys=True, separators=(",", ":"), ensure_ascii=False)


def compute_evidence_hash(data: Dict[str, Any]) -> str:
    """Compute SHA-256 hash of canonicalized JSON excluding self-referential hash field."""
    canonical_str = canonicalize_json(data, exclude_hash=True)
    return hashlib.sha256(canonical_str.encode("utf-8")).hexdigest()


def verify_evidence_integrity(bundle_dict: Dict[str, Any]) -> Tuple[bool, str, str]:
    """Verify SHA-256 integrity of an evidence bundle.
    
    Returns:
        (is_valid, expected_hash, actual_computed_hash)
    """
    reported_hash = bundle_dict.get("sha256_hash", "")
    if not reported_hash:
        return False, "", "MISSING_HASH"

    computed_hash = compute_evidence_hash(bundle_dict)
    is_valid = (reported_hash.lower() == computed_hash.lower())
    return is_valid, reported_hash, computed_hash
