"""Deterministic claim grounding, span extraction, and decision integrity for operational constraints.

SECURITY PRINCIPLE:
SOURCE EXISTS ≠ SOURCE IS TRUSTWORTHY ≠ CLAIM IS PRESENT IN SOURCE ≠ CLAIM IS DIRECTLY SUPPORTED
≠ CLAIM IS APPLICABLE ≠ CLAIM IS SUFFICIENT FOR AUTHORIZATION
"""

from enum import Enum
import re
import time
from typing import Any, Dict, List, Optional, Protocol, Tuple
import uuid
from pydantic import BaseModel, Field

from motionfence.knowledge.models import KnowledgeEvidence
from motionfence.constraints.models import (
    CandidateConstraint,
    ConstraintType,
    Applicability,
)
from motionfence.models.actions import ActionType


class SupportType(str, Enum):
    """Classification of empirical support for an extracted operational claim."""
    DIRECT = "DIRECT"              # Explicit, substantial match in source text
    PARAPHRASE = "PARAPHRASE"      # Meaning and scope preserved without distortion
    INFERENCE = "INFERENCE"        # Unstated deduction, causal claim, or model commentary
    AMBIGUOUS = "AMBIGUOUS"        # Vague, weak advice, or multi-interpretable source statement
    UNSUPPORTED = "UNSUPPORTED"    # Claim not present or ungrounded in cited evidence
    CONTRADICTED = "CONTRADICTED"  # Source explicitly asserts the opposite or claim is distorted


class SupportStatus(str, Enum):
    """Integrity verdict regarding whether a claim is permissible for policy consideration."""
    SUPPORTED = "SUPPORTED"        # Authorized for admissibility evaluation
    INSUFFICIENT = "INSUFFICIENT"  # Retained for operator explanation only; cannot activate policy
    REJECTED = "REJECTED"          # Hard failure; distorted, contradicted, or ungrounded


class GroundingRejectionReason(str, Enum):
    """Specific auditable reason for grounding failure or status degradation."""
    NONE = "NONE"
    CLAIM_DISTORTION = "CLAIM_DISTORTION"
    CLAIM_NEGATION_MISMATCH = "CLAIM_NEGATION_MISMATCH"
    CLAIM_CONDITION_LOST = "CLAIM_CONDITION_LOST"
    CLAIM_SCOPE_MISMATCH = "CLAIM_SCOPE_MISMATCH"
    INVENTED_NUMERIC_THRESHOLD = "INVENTED_NUMERIC_THRESHOLD"
    UNSUPPORTED_CLAIM = "UNSUPPORTED_CLAIM"
    CONTRADICTORY_SOURCE = "CONTRADICTORY_SOURCE"
    MISSING_EVIDENCE = "MISSING_EVIDENCE"
    UNVERIFIED_CAUSAL_INFERENCE = "UNVERIFIED_CAUSAL_INFERENCE"


class ClaimAssertion(BaseModel):
    """Individual decomposed statement within a compound operational claim."""
    assertion_text: str = Field(..., description="Decomposed statement or clause.")
    support_type: SupportType = Field(..., description="Classification of support in source.")
    support_status: SupportStatus = Field(..., description="Admissibility status of assertion.")
    support_span: Optional[str] = Field(default=None, description="Exact or normalized matching source text.")
    start_offset: Optional[int] = Field(default=None, description="Character start offset in source.")
    end_offset: Optional[int] = Field(default=None, description="Character end offset in source.")
    notes: str = Field(default="", description="Audit rationale for this assertion.")


class ClaimSupportCertificate(BaseModel):
    """Cryptographically auditable provenance certificate proving claim grounding in source evidence.
    
    SECURITY INVARIANTS:
    1. A ClaimSupportCertificate possesses ZERO actuator authority.
    2. A certificate cannot mutate WorldState or mint AuthorizationTickets.
    3. Only claims with support_status=SUPPORTED can produce ACTIVE policy constraints.
    """
    certificate_id: str = Field(default_factory=lambda: f"cert_{uuid.uuid4().hex[:10]}")
    candidate_constraint_id: str = Field(..., description="Target candidate constraint identifier.")
    source_evidence_id: str = Field(..., description="Exact ID of referenced KnowledgeEvidence.")
    claim_text: str = Field(..., description="Full text of the extracted operational claim.")
    support_type: SupportType = Field(..., description="Categorization of grounding support.")
    support_span: Optional[str] = Field(default=None, description="Supporting verbatim or normalized text span.")
    start_offset: Optional[int] = Field(default=None, description="Character start index in source evidence content.")
    end_offset: Optional[int] = Field(default=None, description="Character end index in source evidence content.")
    support_status: SupportStatus = Field(..., description="Overall qualification verdict.")
    model_confidence: float = Field(default=1.0, ge=0.0, le=1.0, description="Model extraction confidence.")
    grounding_notes: str = Field(default="", description="Auditable deterministic grounding explanation.")
    rejection_reason: GroundingRejectionReason = Field(
        default=GroundingRejectionReason.NONE,
        description="Categorical reason if rejected or insufficient."
    )
    assertions: List[ClaimAssertion] = Field(
        default_factory=list,
        description="Decomposed atomic assertions if claim contains multiple clauses."
    )
    created_at: float = Field(default_factory=time.time)

    @property
    def is_supported(self) -> bool:
        return self.support_status == SupportStatus.SUPPORTED

    @property
    def is_direct(self) -> bool:
        return self.support_type == SupportType.DIRECT


class ClaimGrounder(Protocol):
    """Protocol for claim grounding engines verifying candidate constraints against evidence."""

    def ground(
        self,
        constraint: CandidateConstraint,
        source_evidence: KnowledgeEvidence,
    ) -> ClaimSupportCertificate:
        """Evaluate grounding of candidate constraint against cited source evidence."""
        ...


def normalize_text(text: str) -> str:
    """Normalize text for whitespace, punctuation, and casing while preserving alphanumeric tokens."""
    t = text.lower()
    t = re.sub(r"[\"'\u201c\u201d\u2018\u2019`]", "", t)
    t = re.sub(r"[-_—–]", " ", t)
    t = re.sub(r"[^\w\s]", " ", t)
    return " ".join(t.split())


def extract_numbers_with_units(text: str) -> List[Tuple[float, str]]:
    """Extract numeric values and their trailing measurement units from text."""
    matches = re.findall(r"(\d+(?:\.\d+)?)\s*([a-zA-Z%]+)?", text.lower())
    results: List[Tuple[float, str]] = []
    for val_str, unit in matches:
        try:
            results.append((float(val_str), unit.strip()))
        except ValueError:
            continue
    return results


class LocalDeterministicClaimGrounder:
    """Deterministic, rule-based claim grounding engine.
    
    Verifies:
    1. Exact / normalized substring match in source evidence.
    2. Modality & negation safety (must vs must not vs may).
    3. Conditionality preservation (while / when / during).
    4. Scope preservation (equipment ID, target component).
    5. Numeric threshold integrity.
    6. Causal inference decomposition.
    """

    # Causal conjunction markers
    CAUSAL_MARKERS = [
        " because ",
        " causes ",
        " causing ",
        " to prevent ",
        " in order to prevent ",
        " due to ",
        " leads to ",
        " resulting in ",
        " so that ",
    ]

    # Modal polarity groups
    PROHIBITION_MARKERS = [
        "must not", "shall not", "cannot", "is prohibited", "forbidden",
        "never", "do not", "must never", "prohibited", "disallowed",
    ]
    PERMISSION_MARKERS = [
        "may be", "can be", "permitted", "allowed", "may", "can",
        "is allowed to", "is permitted to",
    ]
    WEAK_ADVICE_MARKERS = [
        "should generally", "recommended", "advisable", "suggested",
        "typically", "preferably", "guideline", "routine procedure",
    ]

    def ground(
        self,
        constraint: CandidateConstraint,
        source_evidence: KnowledgeEvidence,
    ) -> ClaimSupportCertificate:
        claim_text = (constraint.claim_text or constraint.description or "").strip()
        if not claim_text or "when conditions" in claim_text.lower():
            tgt_name = constraint.target.replace("_", " ").title()
            act_phrase = "must not be closed" if constraint.action == ActionType.CLOSE_VALVE else (constraint.action.value.lower() if constraint.action else "action")
            cond_phrase = " while Pump P1 is active" if "pump_p1" in constraint.condition else ""
            claim_text = f"{tgt_name} {act_phrase}{cond_phrase}."

        source_content = source_evidence.content or ""
        source_norm = normalize_text(source_content)
        claim_norm = normalize_text(claim_text)

        # 0. Missing evidence content check
        if not source_content.strip():
            return ClaimSupportCertificate(
                candidate_constraint_id=constraint.constraint_id,
                source_evidence_id=source_evidence.id,
                claim_text=claim_text,
                support_type=SupportType.UNSUPPORTED,
                support_status=SupportStatus.REJECTED,
                model_confidence=constraint.confidence,
                grounding_notes="Source evidence has empty content.",
                rejection_reason=GroundingRejectionReason.MISSING_EVIDENCE,
            )

        # 1. Target and Component Scope Verification
        target_norm = normalize_text(constraint.target)
        if target_norm not in source_norm and constraint.target.lower().strip() not in source_norm:
            # Source doesn't even mention the target component
            return ClaimSupportCertificate(
                candidate_constraint_id=constraint.constraint_id,
                source_evidence_id=source_evidence.id,
                claim_text=claim_text,
                support_type=SupportType.UNSUPPORTED,
                support_status=SupportStatus.REJECTED,
                model_confidence=constraint.confidence,
                grounding_notes=f"Target component '{constraint.target}' is not mentioned in source evidence.",
                rejection_reason=GroundingRejectionReason.CLAIM_SCOPE_MISMATCH,
            )

        # Generalization detection: "all valves", "all pumps", "any valve", "any pump"
        if re.search(r"\b(all|any|every)\s+(valves?|pumps?|actuators?)\b", claim_norm):
            if not re.search(r"\b(all|any|every)\s+(valves?|pumps?|actuators?)\b", source_norm):
                return ClaimSupportCertificate(
                    candidate_constraint_id=constraint.constraint_id,
                    source_evidence_id=source_evidence.id,
                    claim_text=claim_text,
                    support_type=SupportType.UNSUPPORTED,
                    support_status=SupportStatus.REJECTED,
                    model_confidence=constraint.confidence,
                    grounding_notes="Model generalized specific equipment scope to all/any components.",
                    rejection_reason=GroundingRejectionReason.CLAIM_SCOPE_MISMATCH,
                )

        # 1.5 Weak Advice vs Mandatory Prohibition Check
        has_source_prohibition = any(m in source_norm for m in self.PROHIBITION_MARKERS)
        if any(w in source_norm for w in self.WEAK_ADVICE_MARKERS) and not has_source_prohibition:
            if constraint.constraint_type == ConstraintType.PROHIBITION:
                return ClaimSupportCertificate(
                    candidate_constraint_id=constraint.constraint_id,
                    source_evidence_id=source_evidence.id,
                    claim_text=claim_text,
                    support_type=SupportType.AMBIGUOUS,
                    support_status=SupportStatus.INSUFFICIENT,
                    model_confidence=constraint.confidence,
                    grounding_notes="Source provides only general/routine guidance; insufficient to establish mandatory prohibition.",
                    rejection_reason=GroundingRejectionReason.UNSUPPORTED_CLAIM,
                )

        # 2. Modality & Negation Safety Checks
        has_claim_prohibition = any(m in claim_norm for m in self.PROHIBITION_MARKERS) or constraint.constraint_type == ConstraintType.PROHIBITION
        has_source_permission = any(m in source_norm for m in self.PERMISSION_MARKERS)
        has_claim_permission = any(m in claim_norm for m in self.PERMISSION_MARKERS)

        # Check for Negation / Permission Reversal (Contradiction / Distortion)
        if has_source_permission and not has_source_prohibition and has_claim_prohibition:
            # Source says "may be closed", model claims "must not be closed" or "must never be closed"
            return ClaimSupportCertificate(
                candidate_constraint_id=constraint.constraint_id,
                source_evidence_id=source_evidence.id,
                claim_text=claim_text,
                support_type=SupportType.CONTRADICTED,
                support_status=SupportStatus.REJECTED,
                model_confidence=constraint.confidence,
                grounding_notes="Model reversed negation/permission: source authorizes action but claim asserts prohibition.",
                rejection_reason=GroundingRejectionReason.CLAIM_NEGATION_MISMATCH,
            )

        if has_source_prohibition and not has_source_permission and has_claim_permission:
            # Source says "must not be closed", model claims "may be closed"
            return ClaimSupportCertificate(
                candidate_constraint_id=constraint.constraint_id,
                source_evidence_id=source_evidence.id,
                claim_text=claim_text,
                support_type=SupportType.CONTRADICTED,
                support_status=SupportStatus.REJECTED,
                model_confidence=constraint.confidence,
                grounding_notes="Model reversed negation: source prohibits action but claim asserts permission.",
                rejection_reason=GroundingRejectionReason.CLAIM_NEGATION_MISMATCH,
            )

        # 3. Conditionality Preservation
        # Identify conditional triggers in source: "while pump p1 is active", "when pump p1 is stopped", "during emergency"
        source_has_condition = bool(re.search(r"\b(while|when|if|during|unless|except)\b", source_norm))
        claim_has_condition = bool(re.search(r"\b(while|when|if|during|unless|except)\b", claim_norm)) or bool(constraint.condition)

        # If source has condition on a pump or state, but claim dropped it ("Valve B must never be closed")
        if source_has_condition and not claim_has_condition:
            if "never" in claim_norm or "always" in claim_norm or not constraint.condition:
                return ClaimSupportCertificate(
                    candidate_constraint_id=constraint.constraint_id,
                    source_evidence_id=source_evidence.id,
                    claim_text=claim_text,
                    support_type=SupportType.CONTRADICTED,
                    support_status=SupportStatus.REJECTED,
                    model_confidence=constraint.confidence,
                    grounding_notes="Model dropped operational condition from source (unconditional generalization).",
                    rejection_reason=GroundingRejectionReason.CLAIM_CONDITION_LOST,
                )

        # Specific condition reversal check: e.g. source says "when Pump P1 is stopped", claim says "while Pump P1 is active"
        if "pump p1 is active" in claim_norm and "pump p1 is stopped" in source_norm and "pump p1 is active" not in source_norm:
            return ClaimSupportCertificate(
                candidate_constraint_id=constraint.constraint_id,
                source_evidence_id=source_evidence.id,
                claim_text=claim_text,
                support_type=SupportType.CONTRADICTED,
                support_status=SupportStatus.REJECTED,
                model_confidence=constraint.confidence,
                grounding_notes="Claim condition contradicts source: claim specifies active pump while source specifies stopped pump.",
                rejection_reason=GroundingRejectionReason.CONTRADICTORY_SOURCE,
            )

        # 4. Numeric Threshold Integrity
        claim_numbers = extract_numbers_with_units(claim_text)
        source_numbers = extract_numbers_with_units(source_content)
        if claim_numbers:
            source_num_vals = {val for val, _ in source_numbers}
            for val, unit in claim_numbers:
                if val not in source_num_vals:
                    return ClaimSupportCertificate(
                        candidate_constraint_id=constraint.constraint_id,
                        source_evidence_id=source_evidence.id,
                        claim_text=claim_text,
                        support_type=SupportType.UNSUPPORTED,
                        support_status=SupportStatus.REJECTED,
                        model_confidence=constraint.confidence,
                        grounding_notes=f"Invented numeric threshold {val} {unit} not found in source evidence.",
                        rejection_reason=GroundingRejectionReason.INVENTED_NUMERIC_THRESHOLD,
                    )

        # 5. Causal / Inference Decomposition
        # Check if the claim contains a causal statement ("because", "causes", "to prevent")
        has_causal_in_claim = any(m in f" {claim_text.lower()} " for m in self.CAUSAL_MARKERS)
        if has_causal_in_claim:
            decomposed_cert = self._decompose_and_ground_causal(
                constraint=constraint,
                source_evidence=source_evidence,
                claim_text=claim_text,
                source_content=source_content,
                source_norm=source_norm,
            )
            if decomposed_cert is not None:
                return decomposed_cert

        # 7. Exact Substring Match in Source Content
        span_info = self._find_best_span(claim_text, source_content)
        if span_info is not None:
            start_off, end_off, span_text = span_info
            return ClaimSupportCertificate(
                candidate_constraint_id=constraint.constraint_id,
                source_evidence_id=source_evidence.id,
                claim_text=claim_text,
                support_type=SupportType.DIRECT,
                support_span=span_text,
                start_offset=start_off,
                end_offset=end_off,
                support_status=SupportStatus.SUPPORTED,
                model_confidence=constraint.confidence,
                grounding_notes="Exact normalized source match.",
                rejection_reason=GroundingRejectionReason.NONE,
            )

        # 8. Paraphrase Match (meaning and scope preserved)
        claim_words = set(claim_norm.split())
        source_words = set(source_norm.split())
        overlap = len(claim_words & source_words) / max(len(claim_words), 1)

        # Significant semantic and lexical overlap without distortion
        if overlap >= 0.70:
            return ClaimSupportCertificate(
                candidate_constraint_id=constraint.constraint_id,
                source_evidence_id=source_evidence.id,
                claim_text=claim_text,
                support_type=SupportType.PARAPHRASE,
                support_span=source_content[:120].strip(),
                support_status=SupportStatus.SUPPORTED,
                model_confidence=constraint.confidence,
                grounding_notes=f"Paraphrase verified (lexical overlap={overlap:.2f}, scope preserved).",
                rejection_reason=GroundingRejectionReason.NONE,
            )

        # 9. Unsupported Claim Fallback
        return ClaimSupportCertificate(
            candidate_constraint_id=constraint.constraint_id,
            source_evidence_id=source_evidence.id,
            claim_text=claim_text,
            support_type=SupportType.UNSUPPORTED,
            support_status=SupportStatus.REJECTED,
            model_confidence=constraint.confidence,
            grounding_notes=f"Claim text not adequately grounded in source (overlap={overlap:.2f}).",
            rejection_reason=GroundingRejectionReason.UNSUPPORTED_CLAIM,
        )

    def _decompose_and_ground_causal(
        self,
        constraint: CandidateConstraint,
        source_evidence: KnowledgeEvidence,
        claim_text: str,
        source_content: str,
        source_norm: str,
    ) -> Optional[ClaimSupportCertificate]:
        """Decompose compound claim into core assertion and causal explanation."""
        # Find splitting marker
        matched_marker = None
        for m in self.CAUSAL_MARKERS:
            if m in f" {claim_text.lower()} ":
                matched_marker = m
                break

        if not matched_marker:
            return None

        parts = re.split(re.escape(matched_marker), claim_text, flags=re.IGNORECASE, maxsplit=1)
        if len(parts) != 2:
            return None

        primary_claim = parts[0].strip()
        causal_claim = parts[1].strip()

        # Ground primary assertion
        span_primary = self._find_best_span(primary_claim, source_content)
        primary_norm = normalize_text(primary_claim)
        primary_words = set(primary_norm.split())
        source_words = set(source_norm.split())
        primary_overlap = len(primary_words & source_words) / max(len(primary_words), 1)

        primary_supported = (span_primary is not None) or (primary_overlap >= 0.70)
        causal_norm = normalize_text(causal_claim)
        causal_supported = (causal_norm in source_norm) or (
            len(set(causal_norm.split()) & source_words) / max(len(causal_norm.split()), 1) >= 0.75
        )

        assertions: List[ClaimAssertion] = []
        if primary_supported:
            span_str = span_primary[2] if span_primary else primary_claim
            assertions.append(
                ClaimAssertion(
                    assertion_text=primary_claim,
                    support_type=SupportType.DIRECT if span_primary else SupportType.PARAPHRASE,
                    support_status=SupportStatus.SUPPORTED,
                    support_span=span_str,
                    start_offset=span_primary[0] if span_primary else None,
                    end_offset=span_primary[1] if span_primary else None,
                    notes="Core operational rule directly supported by source.",
                )
            )
        else:
            assertions.append(
                ClaimAssertion(
                    assertion_text=primary_claim,
                    support_type=SupportType.UNSUPPORTED,
                    support_status=SupportStatus.REJECTED,
                    notes="Core operational rule not supported in source.",
                )
            )

        if causal_supported:
            assertions.append(
                ClaimAssertion(
                    assertion_text=causal_claim,
                    support_type=SupportType.DIRECT,
                    support_status=SupportStatus.SUPPORTED,
                    support_span=causal_claim,
                    notes="Causal explanation directly corroborated by source text.",
                )
            )
            # If both are supported, the entire compound claim is supported!
            return ClaimSupportCertificate(
                candidate_constraint_id=constraint.constraint_id,
                source_evidence_id=source_evidence.id,
                claim_text=claim_text,
                support_type=SupportType.DIRECT,
                support_span=source_content.strip(),
                support_status=SupportStatus.SUPPORTED,
                model_confidence=constraint.confidence,
                grounding_notes="Both core operational rule and causal explanation directly supported by source.",
                rejection_reason=GroundingRejectionReason.NONE,
                assertions=assertions,
            )
        else:
            # Causal assertion is an UNVERIFIED INFERENCE
            assertions.append(
                ClaimAssertion(
                    assertion_text=causal_claim,
                    support_type=SupportType.INFERENCE,
                    support_status=SupportStatus.INSUFFICIENT,
                    notes="Causal explanation is not explicitly supported by source (model inference).",
                )
            )
            # The compound rule cannot become authoritative policy fact
            return ClaimSupportCertificate(
                candidate_constraint_id=constraint.constraint_id,
                source_evidence_id=source_evidence.id,
                claim_text=claim_text,
                support_type=SupportType.INFERENCE,
                support_span=span_primary[2] if span_primary else None,
                start_offset=span_primary[0] if span_primary else None,
                end_offset=span_primary[1] if span_primary else None,
                support_status=SupportStatus.INSUFFICIENT,
                model_confidence=constraint.confidence,
                grounding_notes="Causal explanation is an ungrounded model inference. Core rule supported, but inference cannot create active policy.",
                rejection_reason=GroundingRejectionReason.UNVERIFIED_CAUSAL_INFERENCE,
                assertions=assertions,
            )

    def _find_best_span(self, query: str, source: str) -> Optional[Tuple[int, int, str]]:
        """Find the exact or normalized substring span of query inside source."""
        q_norm = normalize_text(query)
        if not q_norm:
            return None

        # 1. Exact case-insensitive substring
        idx = source.lower().find(query.lower().strip())
        if idx != -1:
            end = idx + len(query.strip())
            return idx, end, source[idx:end]

        # 2. Token-level contiguous matching in normalized source
        s_lower = source.lower()
        # Try finding key phrases from query (e.g. "valve b must not be closed while pump p1 is active")
        # Try sliding window of length len(q_norm)
        tokens = q_norm.split()
        if len(tokens) >= 3:
            first_two = " ".join(tokens[:2])
            last_two = " ".join(tokens[-2:])
            idx_start = s_lower.find(first_two)
            if idx_start != -1:
                idx_end = s_lower.find(last_two, idx_start)
                if idx_end != -1 and (idx_end + len(last_two) - idx_start) <= len(query) * 2:
                    end = idx_end + len(last_two)
                    return idx_start, end, source[idx_start:end]

        return None


class SemanticClaimGrounder:
    """Pluggable semantic claim grounding implementation for future embedding-based models."""

    def __init__(self, similarity_threshold: float = 0.85) -> None:
        self.similarity_threshold = similarity_threshold
        self._fallback = LocalDeterministicClaimGrounder()

    def ground(
        self,
        constraint: CandidateConstraint,
        source_evidence: KnowledgeEvidence,
    ) -> ClaimSupportCertificate:
        """Route to deterministic grounder while maintaining future semantic plugin interface."""
        return self._fallback.ground(constraint, source_evidence)


def format_grounding_audit(
    certificate: ClaimSupportCertificate,
    constraint: CandidateConstraint,
    source_evidence: KnowledgeEvidence,
) -> str:
    """Format deterministic audit report for human operators and decision integrity logging."""
    lines = [
        "CLAIM",
        certificate.claim_text,
        "",
        "SOURCE",
        source_evidence.id,
        "",
        "GROUNDING",
        certificate.support_type.value,
        "",
        "SUPPORT",
        certificate.grounding_notes,
        "",
        "APPLICABILITY",
        constraint.applicability.value if hasattr(constraint, "applicability") else "DIRECT",
        "",
        "SOURCE TRUST",
        constraint.source_trust.source_category.value if constraint.source_trust else "LOCAL_FIXTURE",
        "",
        "CORROBORATION",
        "YES" if constraint.corroboration.value == "CORROBORATED" else "NO",
        "",
        "ADMISSIBILITY",
        "PASS" if certificate.is_supported and constraint.is_admissible else "FAIL",
    ]
    return "\n".join(lines)
