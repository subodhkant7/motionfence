"""Deterministic canonical serialization and cryptographic hashing for MotionFence Decision Records."""

import hashlib
import json
from typing import Any, Dict, Optional


def canonical_json_dump(obj: Any) -> str:
    """Serialize data structures into a deterministic canonical JSON string.
    
    Guarantees:
    1. Lexicographically sorted dictionary keys.
    2. Compact separators without trailing whitespace (',', ':').
    3. Deterministic float precision handling (6 decimal places for floats).
    4. UTF-8 compatible ASCII escaping.
    """
    def _normalize(val: Any) -> Any:
        if isinstance(val, dict):
            return {str(k): _normalize(v) for k, v in sorted(val.items())}
        elif isinstance(val, (list, tuple)):
            return [_normalize(x) for x in val]
        elif isinstance(val, float):
            # Format float to 6 decimal places to prevent platform precision divergence
            return round(val, 6)
        elif hasattr(val, "model_dump"):
            return _normalize(val.model_dump(mode="json"))
        return val

    normalized = _normalize(obj)
    return json.dumps(normalized, sort_keys=True, separators=(",", ":"), ensure_ascii=True)


def canonical_serialize(obj: Any) -> bytes:
    """Serialize data structures into canonical deterministic UTF-8 bytes."""
    return canonical_json_dump(obj).encode("utf-8")


def compute_record_hash(record_dict: Dict[str, Any], previous_record_hash: Optional[str]) -> str:
    """Compute cryptographic SHA-256 hash of a DecisionRecord and previous chain link.
    
    Excludes volatile fields ('record_hash', 'finalized_at') so the hash is
    deterministic across re-evaluations.
    """
    payload = dict(record_dict)
    # Volatile fields stripped from pre-image
    payload.pop("record_hash", None)
    payload.pop("finalized_at", None)
    payload["is_finalized"] = True
    payload["previous_record_hash"] = previous_record_hash or "GENESIS"

    canonical_bytes = canonical_serialize(payload)
    return hashlib.sha256(canonical_bytes).hexdigest()
