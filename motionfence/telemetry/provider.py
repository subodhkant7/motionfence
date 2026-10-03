"""Generic interface for external public physical telemetry providers (Phase 2O).

SECURITY INVARIANTS:
1. Public telemetry providers are read-only observation sources.
2. Providers must fail closed on transport, schema, or semantic errors.
3. Providers possess ZERO physical actuator authority or ticket-minting authority.
"""

from abc import ABC, abstractmethod
from typing import Any, Dict, List, Optional
from motionfence.telemetry.models import ObservationSnapshot, TelemetryStatus


class PublicTelemetryProvider(ABC):
    """Abstract base class for public physical observation providers."""

    @abstractmethod
    def fetch_latest_observations(
        self,
        monitoring_location_id: Optional[str] = None,
        parameter_codes: Optional[List[str]] = None,
    ) -> List[ObservationSnapshot]:
        """Fetch latest physical observations from external public endpoint.
        
        Must fail closed on network or data failures.
        """
        pass

    @abstractmethod
    def get_last_status(self) -> TelemetryStatus:
        """Return status classification of the most recent acquisition attempt."""
        pass

    @abstractmethod
    def get_status_details(self) -> Dict[str, Any]:
        """Return diagnostic and audit details from the most recent acquisition."""
        pass
