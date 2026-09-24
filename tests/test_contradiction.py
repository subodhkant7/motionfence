"""Tests for physical sensor contradiction detection."""

from motionfence.evidence.contradiction import ContradictionDetector
from motionfence.evidence.models import (
    Evidence,
    EvidenceSource,
    ContradictionSeverity,
)


def test_no_contradiction_when_evidence_consistent():
    """Consistent observations from multiple sensors must produce no contradiction."""
    evidence = [
        Evidence(
            source=EvidenceSource.VISION,
            target="valve_b",
            observation={"leak_detected": True, "visual_vapor": True},
            confidence=0.91,
            provenance="camera_overhead",
        ),
        Evidence(
            source=EvidenceSource.THERMAL_SENSOR,
            target="valve_b",
            observation={"leak_confirmed": True, "thermal_gradient_c": 12.0},
            confidence=0.94,
            provenance="thermal_cam",
        ),
    ]
    report = ContradictionDetector.detect(evidence, target="valve_b")
    assert not report.contradiction
    assert report.severity == ContradictionSeverity.NONE


def test_direct_leak_boolean_contradiction():
    """Conflicting boolean leak assertions must trigger contradiction."""
    evidence = [
        Evidence(
            source=EvidenceSource.VISION,
            target="valve_b",
            observation={"leak_detected": True},
            confidence=0.90,
            provenance="cam_01",
        ),
        Evidence(
            source=EvidenceSource.ACOUSTIC_SENSOR,
            target="valve_b",
            observation={"leak_detected": False},
            confidence=0.85,
            provenance="acoustic_01",
        ),
    ]
    report = ContradictionDetector.detect(evidence, target="valve_b")
    assert report.contradiction
    assert report.severity == ContradictionSeverity.HIGH
    assert "cam_01" in report.details or "acoustic_01" in report.details or "vision" in report.sources


def test_vision_vs_pressure_sensor_contradiction():
    """Vision reporting leak while pressure sensor reports nominal pressure must be detected."""
    evidence = [
        Evidence(
            source=EvidenceSource.VISION,
            target="valve_b",
            observation={"leak_detected": True},
            confidence=0.88,
            provenance="cam_overhead",
        ),
        Evidence(
            source=EvidenceSource.PRESSURE_SENSOR,
            target="valve_b",
            observation={"pressure_anomaly": False, "pressure_normal": True},
            confidence=0.89,
            provenance="press_sensor",
        ),
    ]
    report = ContradictionDetector.detect(evidence, target="valve_b")
    assert report.contradiction
    assert report.severity == ContradictionSeverity.HIGH
    assert "vision" in report.sources
    assert "pressure_sensor" in report.sources


def test_contradiction_severity_medium_when_moderate_confidence():
    """Contradiction between moderate confidence sources must be scored MEDIUM."""
    evidence = [
        Evidence(
            source=EvidenceSource.VISION,
            target="valve_b",
            observation={"leak_detected": True},
            confidence=0.85,
            provenance="cam_01",
        ),
        Evidence(
            source=EvidenceSource.ACOUSTIC_SENSOR,
            target="valve_b",
            observation={"leak_detected": False},
            confidence=0.65,  # Moderate confidence
            provenance="acoustic_01",
        ),
    ]
    report = ContradictionDetector.detect(evidence, target="valve_b")
    assert report.contradiction
    assert report.severity == ContradictionSeverity.MEDIUM
