"""Constraint extractor protocol and error definitions."""

from typing import List, Protocol, runtime_checkable
from motionfence.knowledge.models import KnowledgeEvidence
from motionfence.constraints.models import CandidateConstraint


class ConstraintExtractionError(Exception):
    """Base exception for constraint extraction failures."""
    pass


class ConstraintValidationError(Exception):
    """Raised when a candidate constraint violates structural or provenance integrity."""
    pass


@runtime_checkable
class ConstraintExtractor(Protocol):
    """Protocol for converting raw KnowledgeEvidence text into structured CandidateConstraint objects."""

    def extract(self, evidence_list: List[KnowledgeEvidence]) -> List[CandidateConstraint]:
        """Extract structured operational constraints from a list of knowledge evidence items."""
        ...
