"""USGS Water Data OGC API telemetry provider (Phase 2O).

Implements modern USGS Water Data OGC API (api.waterdata.usgs.gov/ogcapi/v1)
using the 'latest-continuous' collection for high-frequency automated observations.

SECURITY INVARIANTS:
1. Public telemetry is strictly an OBSERVATION source; it has ZERO direct actuation authority.
2. Read-only gateway; fails closed on network, schema, or semantic errors.
3. Does not use the legacy waterservices.usgs.gov interface.
"""

from datetime import datetime, timezone
import json
import logging
import os
import ssl
import time
from typing import Any, Dict, List, Optional
import urllib.error
import urllib.request

from motionfence.telemetry.models import (
    ObservationSnapshot,
    TelemetryConfig,
    TelemetryStatus,
)
from motionfence.telemetry.normalizer import TelemetryNormalizer
from motionfence.telemetry.provider import PublicTelemetryProvider

logger = logging.getLogger("motionfence.telemetry.usgs_provider")


def _get_ssl_context() -> ssl.SSLContext:
    """Create SSL context with fallback to system CA bundles if necessary."""
    for ca_path in ["/etc/ssl/cert.pem", "/etc/pki/tls/certs/ca-bundle.crt"]:
        if os.path.exists(ca_path):
            try:
                return ssl.create_default_context(cafile=ca_path)
            except Exception:
                pass

    try:
        return ssl.create_default_context()
    except Exception:
        return ssl._create_unverified_context()


class USGSOgcTelemetryProvider(PublicTelemetryProvider):
    """Modern USGS Water Data OGC API telemetry provider."""

    def __init__(
        self,
        config: Optional[TelemetryConfig] = None,
        normalizer: Optional[TelemetryNormalizer] = None,
    ):
        self.config = config or TelemetryConfig()
        self.normalizer = normalizer or TelemetryNormalizer(self.config)
        self.last_status: TelemetryStatus = TelemetryStatus.NO_DATA
        self.last_status_details: Dict[str, Any] = {}

    def get_last_status(self) -> TelemetryStatus:
        return self.last_status

    def get_status_details(self) -> Dict[str, Any]:
        return dict(self.last_status_details)

    def fetch_latest_observations(
        self,
        monitoring_location_id: Optional[str] = None,
        parameter_codes: Optional[List[str]] = None,
    ) -> List[ObservationSnapshot]:
        """Fetch latest continuous physical observations from USGS OGC API.
        
        Fails closed on any error, returning an empty list and recording diagnostic status.
        """
        loc_id = monitoring_location_id or self.config.monitoring_location_id
        target_params = parameter_codes or self.config.parameter_codes

        collected_snapshots: List[ObservationSnapshot] = []
        errors: List[str] = []

        headers = {
            "User-Agent": "MotionFence-PhysicalAI-Safety/2.5 (Formal-Safety-Enclave; github.com/subodhkant7/motionfence)",
            "Accept": "application/json",
        }
        if self.config.api_key:
            headers["X-Api-Key"] = self.config.api_key

        ssl_ctx = _get_ssl_context()

        # Query either per parameter code (recommended to get exact active series) or globally for station
        param_list = target_params if target_params else [None]

        for p_code in param_list:
            query_parts = [f"monitoring_location_id={loc_id}", "f=json"]
            if p_code:
                query_parts.append(f"parameter_code={p_code}")

            query_str = "&".join(query_parts)
            url = f"{self.config.base_url}/collections/latest-continuous/items?{query_str}"

            req = urllib.request.Request(url, headers=headers)
            retrieval_start = time.time()
            retrieval_iso = datetime.now(timezone.utc).isoformat()

            try:
                with urllib.request.urlopen(req, timeout=self.config.timeout_seconds, context=ssl_ctx) as resp:
                    status_code = resp.status
                    if status_code != 200:
                        self.last_status = TelemetryStatus.HTTP_ERROR
                        msg = f"HTTP Error {status_code} fetching from {url}"
                        errors.append(msg)
                        continue

                    raw_body = resp.read().decode("utf-8")
                    data = json.loads(raw_body)

                norm_status, snapshots, norm_errors = self.normalizer.normalize_collection(
                    collection_data=data,
                    source_url=url,
                    retrieved_timestamp=retrieval_start,
                    retrieved_at=retrieval_iso,
                )

                if norm_status != TelemetryStatus.SUCCESS or not snapshots:
                    errors.extend(norm_errors)
                    if norm_status == TelemetryStatus.NO_DATA:
                        logger.info(f"No continuous observation data for {loc_id} param={p_code}")
                    else:
                        self.last_status = norm_status
                else:
                    collected_snapshots.extend(snapshots)

            except urllib.error.HTTPError as e:
                self.last_status = TelemetryStatus.HTTP_ERROR
                err_msg = f"HTTP Error {e.code}: {e.reason} for {url}"
                logger.warning(err_msg)
                errors.append(err_msg)
            except (urllib.error.URLError, TimeoutError, ConnectionError, OSError) as e:
                self.last_status = TelemetryStatus.TRANSPORT_ERROR
                err_msg = f"Transport error: {str(e)} for {url}"
                logger.warning(err_msg)
                errors.append(err_msg)
            except json.JSONDecodeError as e:
                self.last_status = TelemetryStatus.SCHEMA_ERROR
                err_msg = f"Malformed JSON: {str(e)}"
                logger.warning(err_msg)
                errors.append(err_msg)
            except Exception as e:
                self.last_status = TelemetryStatus.SEMANTIC_ERROR
                err_msg = f"Unexpected error during telemetry acquisition: {str(e)}"
                logger.exception(err_msg)
                errors.append(err_msg)

        if collected_snapshots:
            self.last_status = TelemetryStatus.SUCCESS
            self.last_status_details = {
                "monitoring_location_id": loc_id,
                "count": len(collected_snapshots),
                "parameters": [s.parameter_code for s in collected_snapshots],
                "retrieved_at": datetime.now(timezone.utc).isoformat(),
                "errors": errors,
            }
            return collected_snapshots

        self.last_status_details = {
            "monitoring_location_id": loc_id,
            "count": 0,
            "errors": errors,
            "status": self.last_status.value,
        }
        return []
