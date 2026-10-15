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
        (is_valid, reported_hash, computed_hash)
    """
    reported_hash = bundle_dict.get("sha256_hash", "")
    if not reported_hash:
        return False, "", "MISSING_HASH"

    computed_hash = compute_evidence_hash(bundle_dict)
    is_valid = (reported_hash.lower() == computed_hash.lower())
    return is_valid, reported_hash, computed_hash


def validate_evidence_schema(bundle_dict: Dict[str, Any]) -> Tuple[bool, Optional[str]]:
    """Validate structure and essential fields of an exported evidence bundle or benchmark report.
    
    Rejects malformed, incomplete, or corrupted schema structures.
    """
    if not isinstance(bundle_dict, dict):
        return False, "Evidence artifact must be a JSON object dictionary."

    # Identify artifact type
    if "bundle_id" in bundle_dict:
        # Single Scenario Evidence Bundle
        required_fields = {
            "bundle_id", "run_id", "scenario_id", "scenario_version",
            "benchmark_version", "created_at_utc", "sanitized_initial_state",
            "sanitized_final_state", "policy_verdict", "authorization",
            "execution", "verification", "assertions", "timing", "sha256_hash",
        }
    elif "benchmark_version" in bundle_dict and "scenario_results" in bundle_dict:
        # Full Benchmark Report
        required_fields = {
            "benchmark_version", "registry_version", "run_id", "timestamp_utc",
            "build_id", "execution_mode", "total_scenarios_evaluated",
            "scenarios_passed", "scenarios_failed", "metrics", "scenario_results",
            "sha256_hash",
        }
    else:
        return False, "Unrecognized artifact schema: missing recognized root identifiers (bundle_id or benchmark_version)."

    missing = [f for f in required_fields if f not in bundle_dict]
    if missing:
        return False, f"Malformed evidence artifact: missing required fields {missing}."

    return True, None


def get_hash_scope_disclosure() -> Dict[str, Any]:
    """Return explicit cryptographic disclosure defining the exact scope and limitations of SHA-256 integrity hashing."""
    return {
        "hash_algorithm": "SHA-256",
        "serialization_standard": "RFC 8785 Canonical JSON (sorted keys, minimal separators, UTF-8)",
        "covered_fields": "All fields in artifact excluding 'sha256_hash' and 'is_integrity_verified'",
        "excluded_fields": ["sha256_hash", "is_integrity_verified"],
        "scope_description": (
            "The SHA-256 hash covers the exact canonical JSON serialization of the evidence bundle or benchmark report, "
            "including inputs (sanitized_initial_state, fault_injection_applied, proposal), pipeline evaluations (policy_verdict, "
            "authorization, execution, verification), metric records, and ground truth assertion outcomes."
        ),
        "disclaimer": (
            "A matching SHA-256 hash establishes byte-level consistency and tamper detection with the hashed JSON representation. "
            "It does NOT constitute a PKI digital signature, non-repudiation identity proof, or cryptographic attestation of physical actuation."
        ),
    }
