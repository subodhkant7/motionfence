"""Adapter connecting public telemetry observations to MotionFence Evidence and WorldState (Phase 2O).

SECURITY INVARIANTS:
1. Public telemetry enters the evidence pipeline:
   PUBLIC OBSERVATION -> EVIDENCE -> TRUST -> APPLICABILITY -> GROUNDING -> POLICY INPUT.
   Never direct actuation.
2. Semantic honesty: USGS streamflow != internal pump state. External environmental
   observations are explicitly namespaced under 'external_observations.usgs.*'.
3. Controlled physical plant model retains complete authority over internal actuators and zones.
"""

from typing import Any, Dict, List, Optional
from motionfence.evidence.models import Evidence, EvidenceSource
from motionfence.models.world import WorldState
from motionfence.telemetry.models import (
    DerivedEnvironmentalContext,
    ObservationFreshness,
    ObservationSnapshot,
)


class TelemetryEvidenceAdapter:
    """Translates normalized public physical observations into MotionFence Evidence and WorldState context."""

    @classmethod
    def to_evidence(cls, obs: ObservationSnapshot) -> Evidence:
        """Convert ObservationSnapshot into a formal MotionFence Evidence object."""
        # Derive confidence reflecting temporal freshness
        if obs.freshness == ObservationFreshness.FRESH:
            confidence = 0.98
        elif obs.freshness == ObservationFreshness.STALE:
            confidence = 0.40
        else:
            confidence = 0.10

        target_name = f"environmental.usgs.{obs.parameter_code}"
        ev_id = f"ev_usgs_{obs.parameter_code}_{obs.provenance_hash[:8]}"

        observation_payload = {
            "parameter_code": obs.parameter_code,
            "parameter_name": obs.parameter_name or "UNKNOWN",
            "value": obs.normalized_value,
            "raw_value": obs.raw_value,
            "unit": obs.unit,
            "observed_at": obs.observed_at,
            "observed_timestamp": obs.observed_timestamp,
            "retrieved_at": obs.retrieved_at,
            "freshness": obs.freshness.value,
            "freshness_age_seconds": round(obs.freshness_age_seconds, 1),
            "monitoring_location_id": obs.monitoring_location_id,
            "monitoring_location_name": obs.monitoring_location_name,
            "approval_status": obs.approval_status,
            "qualifier": obs.qualifier,
        }

        provenance_str = (
            f"USGS OGC API latest-continuous: station={obs.monitoring_location_id} "
            f"param={obs.parameter_code} [hash:{obs.provenance_hash[:8]}]"
        )

        metadata = {
            "provider": obs.provider,
            "source_system": obs.source_system,
            "source_url": obs.source_url,
            "provenance_hash": obs.provenance_hash,
            "raw_record_hash": obs.raw_record_hash,
            "freshness_status": obs.freshness.value,
            "is_public_external": True,
        }

        return Evidence(
            id=ev_id,
            source=EvidenceSource.SYSTEM_TELEMETRY,
            target=target_name,
            observation=observation_payload,
            confidence=confidence,
            timestamp=obs.retrieved_timestamp,
            provenance=provenance_str,
            metadata=metadata,
        )

    @classmethod
    def to_evidence_list(cls, snapshots: List[ObservationSnapshot]) -> List[Evidence]:
        """Convert a list of ObservationSnapshots into Evidence items."""
        return [cls.to_evidence(s) for s in snapshots]

    @classmethod
    def attach_to_world_state(
        cls,
        world_state: WorldState,
        snapshots: List[ObservationSnapshot],
        derived_context: Optional[DerivedEnvironmentalContext] = None,
    ) -> WorldState:
        """Incorporate external physical telemetry into WorldState under external_observations namespace.
        
        CRITICAL INVARIANT:
        Does NOT alter internal modeled plant entities (valves, cooling, human_zone, pumps).
        Maintains strict semantic separation between external observation and internal plant state.
        """
        if not hasattr(world_state, "external_observations"):
            return world_state

        usgs_dict: Dict[str, Any] = {}
        for s in snapshots:
            param_key = "streamflow_cfs" if s.parameter_code == "00060" else (
                "gage_height_ft" if s.parameter_code == "00065" else f"param_{s.parameter_code}"
            )
            usgs_dict[param_key] = {
                "value": s.normalized_value,
                "raw_value": s.raw_value,
                "unit": s.unit,
                "observed_at": s.observed_at,
                "freshness": s.freshness.value,
                "monitoring_location_id": s.monitoring_location_id,
                "monitoring_location_name": s.monitoring_location_name,
                "provenance_hash": s.provenance_hash,
                "raw_record_hash": s.raw_record_hash,
            }

        world_state.external_observations["usgs"] = usgs_dict

        if derived_context:
            world_state.external_observations["environmental_context"] = {
                "context_name": derived_context.context_name,
                "classification": derived_context.classification,
                "threshold_value": derived_context.threshold_value,
                "rule_id": derived_context.rule_id,
                "deterministic_hash": derived_context.deterministic_hash,
            }

        return world_state

    @classmethod
    def derive_environmental_flow_context(
        cls,
        streamflow_obs: ObservationSnapshot,
        high_flow_threshold_cfs: float = 5000.0,
        rule_id: str = "RULE_USGS_POTOMAC_HIGH_FLOW_STAGE_01",
    ) -> DerivedEnvironmentalContext:
        """Deterministically derive discrete environmental flow classification.
        
        SECURITY INVARIANT:
        Rule and threshold are 100% deterministic and auditable; never LLM generated.
        """
        val = streamflow_obs.normalized_value or 0.0
        classification = "HIGH_FLOW" if val >= high_flow_threshold_cfs else "NORMAL_FLOW"

        return DerivedEnvironmentalContext.create(
            context_name="POTOMAC_RIVER_FLOW_REGIME",
            classification=classification,
            source_obs=streamflow_obs,
            threshold_value=high_flow_threshold_cfs,
            rule_id=rule_id,
        )
