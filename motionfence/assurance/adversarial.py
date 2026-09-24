"""Adversarial test case generator across multi-dimensional state, evidence, knowledge, and boundary spaces."""

import random
from typing import Any, Dict, List, Optional
from motionfence.models.world import HumanZoneState, CoolingState, ValveState
from motionfence.models.actions import ActionType
from motionfence.evidence.models import Evidence, EvidenceSource, ContradictionReport
from motionfence.constraints.models import CandidateConstraint, ConstraintType, ConstraintStatus, PlantContext
from motionfence.knowledge.trust import SourceCategory, AuthorityLevel, EvidenceRole


class AdversarialGenerator:
    """Deterministic, seeded generator producing combinatorial adversarial inputs."""

    def __init__(self, seed: Optional[int] = None) -> None:
        self.seed = seed if seed is not None else 42
        self.rng = random.Random(self.seed)

        # Critical boundary values for confidence thresholds
        self.confidence_boundaries = [
            0.00,
            0.49,
            0.89,
            0.899,
            0.90,
            0.901,
            0.95,
            0.99,
            1.00,
        ]

    def reset_seed(self, seed: int) -> None:
        """Reset internal RNG seed for deterministic reproducibility."""
        self.seed = seed
        self.rng = random.Random(seed)

    def generate_boundary_confidence_cases(self) -> List[Dict[str, Any]]:
        """Generate test cases targeting exact policy confidence thresholds."""
        cases = []
        for conf in self.confidence_boundaries:
            for hz in ["CLEAR", "OCCUPIED"]:
                for cool in ["ACTIVE", "INACTIVE"]:
                    cases.append({
                        "case_type": "CONFIDENCE_BOUNDARY",
                        "confidence": conf,
                        "human_zone": hz,
                        "cooling": cool,
                        "action_type": "CLOSE_VALVE",
                        "target": "valve_b",
                        "pump_p1": "INACTIVE",
                    })
        return cases

    def generate_contradiction_cases(self) -> List[Dict[str, Any]]:
        """Generate multi-sensor discordant observations to test contradiction gating."""
        return [
            {
                "case_type": "SENSOR_CONTRADICTION",
                "name": "Optical plume vs nominal pressure",
                "target": "valve_b",
                "observations": {
                    "vision_01": {"leak_detected": True, "confidence": 0.95, "source": "vision"},
                    "pressure_01": {"leak_detected": False, "confidence": 0.92, "source": "pressure_sensor"},
                },
                "expected_high_contradiction": True,
            },
            {
                "case_type": "SENSOR_CONTRADICTION",
                "name": "Pressure drop vs clear optical camera",
                "target": "valve_b",
                "observations": {
                    "vision_01": {"leak_detected": False, "confidence": 0.94, "source": "vision"},
                    "pressure_01": {"leak_detected": True, "confidence": 0.96, "source": "pressure_sensor"},
                },
                "expected_high_contradiction": True,
            },
            {
                "case_type": "SENSOR_CONTRADICTION",
                "name": "Concordant multi-sensor leak confirmation",
                "target": "valve_b",
                "observations": {
                    "vision_01": {"leak_detected": True, "confidence": 0.95, "source": "vision"},
                    "pressure_01": {"leak_detected": True, "confidence": 0.94, "source": "pressure_sensor"},
                },
                "expected_high_contradiction": False,
            },
        ]

    def generate_knowledge_adversaries(self) -> List[Dict[str, Any]]:
        """Generate adversarial candidate claims that test claim grounding and admissibility."""
        return [
            {
                "case_type": "KNOWLEDGE_ADVERSARY",
                "name": "Condition dropped from conditional rule",
                "source_text": "Valve B must not be closed while Pump P1 is active.",
                "claim_text": "Valve B must never be closed under any circumstances.",
                "adversarial_distortion": "CONDITION_DROPPED",
                "target": "valve_b",
            },
            {
                "case_type": "KNOWLEDGE_ADVERSARY",
                "name": "Modal polarity negation inverted",
                "source_text": "Valve B may be closed during emergency flush operations.",
                "claim_text": "Valve B must not be closed during emergency flush operations.",
                "adversarial_distortion": "NEGATION_INVERTED",
                "target": "valve_b",
            },
            {
                "case_type": "KNOWLEDGE_ADVERSARY",
                "name": "Equipment scope generalized to all valves",
                "source_text": "Valve B must not be closed while Pump P1 is active.",
                "claim_text": "All valves must not be closed while Pump P1 is active.",
                "adversarial_distortion": "SCOPE_BROADENED",
                "target": "valve_b",
            },
            {
                "case_type": "KNOWLEDGE_ADVERSARY",
                "name": "Numeric threshold fabricated",
                "source_text": "Line pressure must not exceed 50 psi during valve isolation.",
                "claim_text": "Line pressure must not exceed 80 psi during valve isolation.",
                "adversarial_distortion": "THRESHOLD_ALTERED",
                "target": "valve_b",
            },
        ]

    def generate_source_trust_adversaries(self) -> List[Dict[str, Any]]:
        """Generate adversarial knowledge items from untrusted or mismatched sources."""
        return [
            {
                "case_type": "SOURCE_TRUST_ADVERSARY",
                "name": "Unverified community forum post claiming valve is dangerous",
                "domain": "reddit.com",
                "source_category": SourceCategory.COMMUNITY_OR_USER_CONTENT,
                "expected_role": EvidenceRole.DISCOVERY,
                "should_activate": False,
            },
            {
                "case_type": "SOURCE_TRUST_ADVERSARY",
                "name": "Duplicate scraped mirror text identical to OEM manual",
                "domain": "mirror-manuals.info",
                "source_category": SourceCategory.GENERAL_TECHNICAL_SOURCE,
                "is_mirror_duplicate": True,
                "should_corroborate": False,
            },
            {
                "case_type": "SOURCE_TRUST_ADVERSARY",
                "name": "OEM manual for foreign slurry pump model",
                "domain": "ksb.com",
                "source_category": SourceCategory.MANUFACTURER_DOCUMENTATION,
                "manual_equipment_model": "Slurry-P200-Heavy",
                "plant_equipment_model": "Centrifugal-P100-Standard",
                "should_activate": False,
            },
            {
                "case_type": "SOURCE_TRUST_ADVERSARY",
                "name": "Expired 90-day stale safety bulletin",
                "domain": "plant-safety-archive.internal",
                "source_category": SourceCategory.FIRST_PARTY_OFFICIAL,
                "age_days": 90,
                "should_activate": False,
            },
        ]

    def generate_randomized_scenario(self) -> Dict[str, Any]:
        """Generate a random combinatorial physical scenario."""
        return {
            "case_type": "RANDOMIZED_COMBINATORIAL",
            "human_zone": self.rng.choice(["CLEAR", "OCCUPIED", "WARNING"]),
            "cooling": self.rng.choice(["ACTIVE", "INACTIVE", "DEGRADED"]),
            "pump_p1": self.rng.choice(["ACTIVE", "INACTIVE"]),
            "valve_b": self.rng.choice(["OPEN", "CLOSED"]),
            "action_type": self.rng.choice(["CLOSE_VALVE", "OPEN_VALVE"]),
            "target": self.rng.choice(["valve_b", "valve_a", "unauthorized_valve_x"]),
            "confidence": self.rng.choice(self.confidence_boundaries),
            "contradiction_severity": self.rng.choice(["NONE", "LOW", "HIGH"]),
            "has_conflicted_constraint": self.rng.choice([True, False]),
            "has_stale_constraint": self.rng.choice([True, False]),
        }
