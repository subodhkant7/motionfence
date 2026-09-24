"""Evidence trust assessment, source classification, and corroboration models."""

from enum import Enum
import re
from typing import Any, Dict, List, Optional, Set, Tuple
from urllib.parse import urlparse
from pydantic import BaseModel, Field

from motionfence.knowledge.models import KnowledgeEvidence, TrustStatus, FreshnessStatus


class SourceCategory(str, Enum):
    """Categorical classification of knowledge source origin and institutional authority."""
    FIRST_PARTY_OFFICIAL = "FIRST_PARTY_OFFICIAL"          # Internal plant engineering manuals, SOPs, direct facility specs
    MANUFACTURER_DOCUMENTATION = "MANUFACTURER_DOCUMENTATION"  # OEM equipment manuals, technical datasheets, certified vendor guides
    REGULATORY_OR_STANDARDS = "REGULATORY_OR_STANDARDS"    # ISO, ASME, OSHA, EIGA, NIST standards
    CURATED_TECHNICAL_SOURCE = "CURATED_TECHNICAL_SOURCE"  # Peer-reviewed papers, engineering handbooks, verified publishers
    GENERAL_TECHNICAL_SOURCE = "GENERAL_TECHNICAL_SOURCE"  # Third-party technical blogs, generic equipment supplier guides
    COMMUNITY_OR_USER_CONTENT = "COMMUNITY_OR_USER_CONTENT"# Forums, social media, Reddit, Facebook, Scribd, user blogs
    UNKNOWN = "UNKNOWN"                                    # Unattributed, unverifiable, or missing source


class AuthorityLevel(str, Enum):
    """Graded assessment of authoritative weight in safety-relevant decisions."""
    HIGH = "HIGH"          # Sufficient for primary physical prohibitions and requirements
    MEDIUM = "MEDIUM"      # Sufficient as supporting evidence; requires corroboration for prohibitions
    LOW = "LOW"            # Sufficient for DISCOVERY only; cannot independently command/prohibit actions
    UNTRUSTED = "UNTRUSTED"# Rejected or suspicious provenance; inadmissible for policy


class EvidenceRole(str, Enum):
    """Functional role of retrieved evidence in the MotionFence control loop."""
    DISCOVERY = "DISCOVERY"                            # Alerts operators/agents to issues; never activates safety prohibitions
    SUPPORTING = "SUPPORTING"                          # Corroborates primary sources or provides guidance
    AUTHORIZATION_RELEVANT = "AUTHORIZATION_RELEVANT"  # Qualified to directly influence deterministic authorization
    REJECTED = "REJECTED"                              # Malformed, missing provenance, or untrusted


class CorroborationStatus(str, Enum):
    """Multi-source corroboration status for extracted operational claims."""
    CORROBORATED = "CORROBORATED"        # Independently confirmed by multiple distinct, qualified sources
    SINGLE_SOURCE = "SINGLE_SOURCE"      # Derived from a single authoritative source
    DUPLICATE_SOURCE = "DUPLICATE_SOURCE"# Multiple citations with identical text/scraped mirror content
    UNSUPPORTED = "UNSUPPORTED"          # Sourced solely from low-authority/community content without corroboration


class SourceTrustAssessment(BaseModel):
    """Formal deterministic assessment of knowledge evidence provenance and authority.
    
    SECURITY INVARIANT:
    trust_score is an internal prioritization metric, NOT an objective proof of truth.
    Categorical reasons and evidence_role are the auditable determinants for admissibility.
    """
    evidence_id: str = Field(..., description="ID of the assessed KnowledgeEvidence.")
    source_type: Optional[str] = Field(default=None, description="Categorical source type name.")
    source_category: SourceCategory = Field(..., description="Institutional classification of the source.")
    authority_level: AuthorityLevel = Field(..., description="Graded authoritative weight.")
    evidence_role: EvidenceRole = Field(..., description="Assigned role (DISCOVERY, SUPPORTING, AUTHORIZATION_RELEVANT, REJECTED).")
    relevance: float = Field(default=1.0, ge=0.0, le=1.0, description="Relevance to industrial operations.")
    provenance_quality: str = Field(default="VERIFIED", description="Evaluation of source URL/URI validity.")
    freshness: FreshnessStatus = Field(default=FreshnessStatus.FRESH, description="Temporal validity state.")
    trust_score: float = Field(default=0.5, ge=0.0, le=1.0, description="Internal composite trust score.")
    reasons: List[str] = Field(default_factory=list, description="Auditable deterministic rationale.")

    def model_post_init(self, __context: Any) -> None:
        if self.source_type is None and self.source_category is not None:
            self.source_type = self.source_category.value

    @property
    def is_authorization_sufficient(self) -> bool:
        """Helper indicating whether evidence role is qualified to influence authorization."""
        return self.evidence_role == EvidenceRole.AUTHORIZATION_RELEVANT


class SourceTrustClassifier:
    """Deterministically classifies knowledge sources based on URL patterns, provenance, and metadata."""

    # Community and social media domains: discovery only, never authorization
    COMMUNITY_DOMAINS: Set[str] = {
        "facebook.com", "m.facebook.com", "reddit.com", "quora.com", "medium.com",
        "scribd.com", "blogspot.com", "wordpress.com", "twitter.com", "x.com",
        "linkedin.com", "instagram.com", "youtube.com", "pinterest.com"
    }

    # Regulatory and engineering standards organizations
    STANDARDS_DOMAINS: Set[str] = {
        "eiga.eu", "iso.org", "asme.org", "osha.gov", "nist.gov", "ansi.org",
        "astm.org", "nfpa.org", "api.org", "iec.ch"
    }

    # Established pump & valve OEMs / curated publishers
    OEM_MANUFACTURER_DOMAINS: Set[str] = {
        "ksb.com", "flowserve.com", "sulzer.com", "grundfos.com", "itt.com",
        "sciencedirect.com", "ieee.org", "springer.com"
    }

    @classmethod
    def assess(cls, evidence: KnowledgeEvidence, query: str = "") -> SourceTrustAssessment:
        """Independently assess provenance, authority, and assign an evidence role."""
        reasons: List[str] = []
        freshness = evidence.check_freshness()

        # 1. Missing provenance or explicitly rejected status
        if not evidence.provenance or evidence.trust_status == TrustStatus.REJECTED:
            return SourceTrustAssessment(
                evidence_id=evidence.id,
                source_category=SourceCategory.UNKNOWN,
                authority_level=AuthorityLevel.UNTRUSTED,
                evidence_role=EvidenceRole.REJECTED,
                relevance=0.0,
                provenance_quality="MISSING_OR_REJECTED",
                freshness=freshness,
                trust_score=0.0,
                reasons=["Missing provenance attribution or explicitly rejected trust status."],
            )

        # 2. Local synthetic plant fixtures (local:// URIs)
        if evidence.source_url.startswith("local://") or (evidence.trust_status == TrustStatus.LOCAL_FIXTURE and not evidence.source_url.startswith("http")):
            provenance_lower = evidence.provenance.lower()
            url_lower = evidence.source_url.lower()

            if "safety_manual" in provenance_lower or "plant_manual" in url_lower:
                category = SourceCategory.FIRST_PARTY_OFFICIAL
                auth = AuthorityLevel.HIGH
                role = EvidenceRole.AUTHORIZATION_RELEVANT
                score = 0.98
                reasons.append("First-party official plant safety manual fixture.")
            elif "emergency" in provenance_lower or "sop" in provenance_lower:
                category = SourceCategory.FIRST_PARTY_OFFICIAL
                auth = AuthorityLevel.HIGH
                role = EvidenceRole.AUTHORIZATION_RELEVANT
                score = 0.92
                reasons.append("First-party plant operational handbook/SOP.")
            elif "legacy" in provenance_lower or "archived" in url_lower or freshness == FreshnessStatus.STALE:
                category = SourceCategory.FIRST_PARTY_OFFICIAL
                auth = AuthorityLevel.MEDIUM
                role = EvidenceRole.SUPPORTING
                score = 0.60
                reasons.append("Archived legacy documentation; requires recertification.")
            else:
                category = SourceCategory.FIRST_PARTY_OFFICIAL
                auth = AuthorityLevel.HIGH
                role = EvidenceRole.AUTHORIZATION_RELEVANT
                score = 0.90
                reasons.append("Local plant operational documentation fixture.")

            return SourceTrustAssessment(
                evidence_id=evidence.id,
                source_category=category,
                authority_level=auth,
                evidence_role=role,
                relevance=evidence.confidence,
                provenance_quality="VERIFIED_LOCAL_FIXTURE",
                freshness=freshness,
                trust_score=score,
                reasons=reasons,
            )

        # 3. Web URLs (e.g. from Tavily)
        parsed = urlparse(evidence.source_url)
        domain = parsed.netloc.lower()
        if domain.startswith("www."):
            domain = domain[4:]

        path_lower = parsed.path.lower()
        is_community_path = any(p in path_lower for p in ["/posts/", "/forum/", "/thread/", "/community/"])

        # Check community domains
        if domain in cls.COMMUNITY_DOMAINS or is_community_path:
            reasons.append(
                f"Source domain '{domain}' is categorized as community/user-generated content. "
                "Admissible for DISCOVERY only; cannot independently activate safety constraints."
            )
            return SourceTrustAssessment(
                evidence_id=evidence.id,
                source_category=SourceCategory.COMMUNITY_OR_USER_CONTENT,
                authority_level=AuthorityLevel.LOW,
                evidence_role=EvidenceRole.DISCOVERY,
                relevance=evidence.confidence,
                provenance_quality="EXTERNAL_COMMUNITY_WEB",
                freshness=freshness,
                trust_score=0.35,
                reasons=reasons,
            )

        # Check standards domains
        if any(std in domain for std in cls.STANDARDS_DOMAINS):
            reasons.append(f"Domain '{domain}' verified as recognized industrial standards organization.")
            return SourceTrustAssessment(
                evidence_id=evidence.id,
                source_category=SourceCategory.REGULATORY_OR_STANDARDS,
                authority_level=AuthorityLevel.HIGH,
                evidence_role=EvidenceRole.AUTHORIZATION_RELEVANT,
                relevance=evidence.confidence,
                provenance_quality="VERIFIED_STANDARDS_ORGANIZATION",
                freshness=freshness,
                trust_score=0.96,
                reasons=reasons,
            )

        # Check OEM / curated manufacturer domains
        if any(oem in domain for oem in cls.OEM_MANUFACTURER_DOMAINS):
            reasons.append(f"Domain '{domain}' verified as industrial equipment manufacturer / publisher.")
            return SourceTrustAssessment(
                evidence_id=evidence.id,
                source_category=SourceCategory.MANUFACTURER_DOCUMENTATION,
                authority_level=AuthorityLevel.HIGH,
                evidence_role=EvidenceRole.AUTHORIZATION_RELEVANT,
                relevance=evidence.confidence,
                provenance_quality="VERIFIED_OEM_MANUFACTURER",
                freshness=freshness,
                trust_score=0.92,
                reasons=reasons,
            )

        # Check generic technical / vendor sites
        if domain:
            reasons.append(
                f"Domain '{domain}' classified as general technical/commercial publication. "
                "Role assigned as SUPPORTING; requires multi-source corroboration for safety-critical prohibitions."
            )
            return SourceTrustAssessment(
                evidence_id=evidence.id,
                source_category=SourceCategory.GENERAL_TECHNICAL_SOURCE,
                authority_level=AuthorityLevel.MEDIUM,
                evidence_role=EvidenceRole.SUPPORTING,
                relevance=evidence.confidence,
                provenance_quality="GENERAL_TECHNICAL_WEB",
                freshness=freshness,
                trust_score=0.65,
                reasons=reasons,
            )

        # Fallback unknown
        reasons.append("Unidentified source domain; treated as discovery evidence.")
        return SourceTrustAssessment(
            evidence_id=evidence.id,
            source_category=SourceCategory.UNKNOWN,
            authority_level=AuthorityLevel.LOW,
            evidence_role=EvidenceRole.DISCOVERY,
            relevance=0.3,
            provenance_quality="UNVERIFIABLE",
            freshness=freshness,
            trust_score=0.30,
            reasons=reasons,
        )


class CorroborationEngine:
    """Evaluates multi-source corroboration and identifies duplicate/scraped web content."""

    @classmethod
    def normalize_text(cls, text: str) -> str:
        """Strip punctuation and whitespace for near-duplicate text detection."""
        cleaned = re.sub(r"[^\w\s]", "", text.lower())
        return " ".join(cleaned.split())

    @classmethod
    def is_duplicate_content(cls, text_a: str, text_b: str, similarity_threshold: float = 0.85) -> bool:
        """Check if two texts are verbatim copies or near-duplicates (scraped mirrors)."""
        words_a = set(cls.normalize_text(text_a).split())
        words_b = set(cls.normalize_text(text_b).split())
        if not words_a or not words_b:
            return False
        jaccard = len(words_a.intersection(words_b)) / len(words_a.union(words_b))
        return jaccard >= similarity_threshold

    @classmethod
    def evaluate_corroboration(
        cls,
        evidence_list: List[KnowledgeEvidence],
        assessments: Dict[str, SourceTrustAssessment],
    ) -> Tuple[CorroborationStatus, List[str]]:
        """Determine if an operational claim is corroborated by distinct qualified sources."""
        if not evidence_list:
            return CorroborationStatus.UNSUPPORTED, ["No evidence provided."]

        if len(evidence_list) == 1:
            ev = evidence_list[0]
            ass = assessments.get(ev.id)
            if ass and ass.authority_level in (AuthorityLevel.HIGH, AuthorityLevel.MEDIUM):
                return CorroborationStatus.SINGLE_SOURCE, [f"Single authoritative source: {ev.provenance}"]
            return CorroborationStatus.UNSUPPORTED, ["Single source with insufficient authority."]

        # Check for duplicate/mirror sources
        distinct_sources: List[KnowledgeEvidence] = []
        for ev in evidence_list:
            is_dup = False
            for prev in distinct_sources:
                # Same domain or identical text snippet
                same_domain = urlparse(ev.source_url).netloc == urlparse(prev.source_url).netloc and ev.source_url != ""
                duplicate_text = cls.is_duplicate_content(ev.content, prev.content)
                if same_domain or duplicate_text:
                    is_dup = True
                    break
            if not is_dup:
                distinct_sources.append(ev)

        if len(distinct_sources) < 2 and len(evidence_list) >= 2:
            return (
                CorroborationStatus.DUPLICATE_SOURCE,
                ["Multiple citations identified as duplicate mirrors/scraped text, not independent corroboration."]
            )

        # Check authority of distinct sources
        qualified_count = sum(
            1 for ev in distinct_sources
            if assessments.get(ev.id) and assessments[ev.id].authority_level in (AuthorityLevel.HIGH, AuthorityLevel.MEDIUM)
        )

        if qualified_count >= 2:
            notes = [f"Corroborated by {qualified_count} independent, qualified sources: {[e.provenance for e in distinct_sources]}"]
            return CorroborationStatus.CORROBORATED, notes

        return (
            CorroborationStatus.UNSUPPORTED,
            [f"Only {qualified_count} qualified source(s) among distinct citations; insufficient for corroboration."]
        )
