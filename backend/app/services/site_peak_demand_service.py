"""Site peak demand service.

Computes and persists a site-specific peak demand value from historical
telemetry so after-hours HVAC gating can scale by the building itself instead
of falling back to a global constant.
"""

from __future__ import annotations

import logging
from datetime import UTC, datetime, timedelta
from typing import Any, cast

from app.core.site_resolver import get_registered_site_ids
from app.database.repositories.site_repository import SiteRepository
from app.database.supabase_client import get_supabase_client

logger = logging.getLogger(__name__)

DEFAULT_LOOKBACK_DAYS = 90
SITE_PEAK_SETTING_KEYS = (
    "site_peak_kw",
    "site_peak_kw_source",
    "site_peak_kw_basis",
    "site_peak_kw_equipment_id",
    "site_peak_kw_sensor_type",
    "site_peak_kw_lookback_days",
    "site_peak_kw_updated_at",
)


def _as_float(value: Any, default: float = 0.0) -> float:
    try:
        return float(value)
    except (TypeError, ValueError):
        return default


class SitePeakDemandService:
    """Compute, cache, and persist site peak demand metadata."""

    def __init__(self, site_repo: SiteRepository | None = None, client: Any | None = None):
        self.site_repo = site_repo or SiteRepository()
        self.client = client or get_supabase_client()

    def _cached_peak_from_site_row(self, site_row: dict[str, Any] | None) -> dict[str, Any] | None:
        if not site_row:
            return None
        settings = site_row.get("optimization_settings") or {}
        peak_kw = _as_float(settings.get("site_peak_kw"))
        if peak_kw <= 0:
            return None
        return {
            "site_peak_kw": round(peak_kw, 2),
            "site_peak_kw_source": settings.get("site_peak_kw_source") or "optimization_settings",
            "site_peak_kw_basis": settings.get("site_peak_kw_basis") or "cached",
            "site_peak_kw_equipment_id": settings.get("site_peak_kw_equipment_id"),
            "site_peak_kw_sensor_type": settings.get("site_peak_kw_sensor_type"),
            "site_peak_kw_lookback_days": settings.get("site_peak_kw_lookback_days"),
            "site_peak_kw_updated_at": settings.get("site_peak_kw_updated_at"),
        }

    def get_cached_site_peak_kw(self, site_code: str) -> dict[str, Any] | None:
        site_row = self.site_repo.get_by_id(site_code)
        return self._cached_peak_from_site_row(site_row)

    def compute_site_peak_kw(self, site_code: str, lookback_days: int = DEFAULT_LOOKBACK_DAYS) -> dict[str, Any] | None:
        """Compute a peak demand value from recent telemetry.

        Prefers the highest observed HVAC load from the site aggregate, but will
        fall back to total site load if that is the only signal available.
        """

        site_prefix = site_code.replace("site-", "S").upper()
        candidate_equipment_ids = [f"{site_prefix}-SITE-AGG", f"{site_prefix}-CHILLER-AGG"]
        since = (datetime.now(UTC) - timedelta(days=lookback_days)).isoformat()
        try:
            reading_resp = (
                self.client.table("equipment_sensor_readings")
                .select("equipment_id,sensor_type,value,recorded_at")
                .eq("site_id", site_code)
                .in_("equipment_id", candidate_equipment_ids)
                .in_("sensor_type", ["hvac_kw", "total_kw"])
                .gte("recorded_at", since)
                .order("recorded_at", desc=True)
                .limit(5000)
                .execute()
            )
        except Exception as exc:
            logger.warning("[PeakDemand] Failed to load telemetry for %s: %s", site_code, exc)
            return None

        peak_by_sensor: dict[str, dict[str, Any]] = {}
        for row in reading_resp.data or []:
            sensor_type = str(row.get("sensor_type") or "").strip().lower()
            if sensor_type not in {"hvac_kw", "total_kw"}:
                continue
            value = _as_float(row.get("value"))
            if value <= 0:
                continue

            current = peak_by_sensor.get(sensor_type)
            if current and _as_float(current.get("value")) >= value:
                continue
            peak_by_sensor[sensor_type] = {
                "equipment_id": row.get("equipment_id"),
                "sensor_type": sensor_type,
                "value": value,
                "recorded_at": row.get("recorded_at"),
            }

        hvac_peak = peak_by_sensor.get("hvac_kw")
        total_peak = peak_by_sensor.get("total_kw")
        if not hvac_peak and not total_peak:
            return None

        chosen: dict[str, Any] = cast(dict[str, Any], hvac_peak if hvac_peak is not None else total_peak)
        if hvac_peak is not None and total_peak is not None:
            if _as_float(total_peak.get("value")) > _as_float(hvac_peak.get("value")):
                chosen = total_peak

        peak_kw = _as_float(chosen.get("value"))
        if peak_kw <= 0:
            return None

        now = datetime.now(UTC).isoformat()
        return {
            "site_peak_kw": round(peak_kw, 2),
            "site_peak_kw_source": "equipment_sensor_readings",
            "site_peak_kw_basis": "max_hvac_kw" if chosen is hvac_peak else "max_total_kw",
            "site_peak_kw_equipment_id": chosen.get("equipment_id"),
            "site_peak_kw_sensor_type": chosen.get("sensor_type"),
            "site_peak_kw_lookback_days": lookback_days,
            "site_peak_kw_updated_at": now,
        }

    def refresh_site_peak_kw(self, site_code: str, lookback_days: int = DEFAULT_LOOKBACK_DAYS) -> dict[str, Any] | None:
        """Compute and persist the current site peak demand snapshot."""
        site_row = self.site_repo.get_by_id(site_code)
        if not site_row:
            logger.warning("[PeakDemand] Site not found: %s", site_code)
            return None

        snapshot = self.compute_site_peak_kw(site_code, lookback_days=lookback_days)
        if not snapshot:
            logger.warning("[PeakDemand] No demand telemetry available for %s", site_code)
            return None

        settings = dict(site_row.get("optimization_settings") or {})
        settings.update(snapshot)
        try:
            updated = self.site_repo.update(site_code, {"optimization_settings": settings})
            if updated:
                logger.info(
                    "[PeakDemand] Updated %s peak demand to %.2f kW (%s/%s)",
                    site_code,
                    snapshot["site_peak_kw"],
                    snapshot.get("site_peak_kw_basis"),
                    snapshot.get("site_peak_kw_sensor_type"),
                )
            return snapshot
        except Exception as exc:
            logger.warning("[PeakDemand] Failed to persist peak demand for %s: %s", site_code, exc)
            return snapshot

    def refresh_registered_sites(self, lookback_days: int = DEFAULT_LOOKBACK_DAYS) -> dict[str, Any]:
        """Refresh peak demand snapshots for all registered sites."""
        refreshed: list[str] = []
        missing: list[str] = []
        for site_code in get_registered_site_ids():
            snapshot = self.refresh_site_peak_kw(site_code, lookback_days=lookback_days)
            if snapshot and snapshot.get("site_peak_kw", 0) > 0:
                refreshed.append(site_code)
            else:
                missing.append(site_code)
        return {
            "refreshed_sites": refreshed,
            "missing_sites": missing,
            "refreshed_count": len(refreshed),
            "missing_count": len(missing),
        }


_SITE_PEAK_DEMAND_SERVICE: SitePeakDemandService | None = None


def get_site_peak_demand_service() -> SitePeakDemandService:
    global _SITE_PEAK_DEMAND_SERVICE
    if _SITE_PEAK_DEMAND_SERVICE is None:
        _SITE_PEAK_DEMAND_SERVICE = SitePeakDemandService()
    return _SITE_PEAK_DEMAND_SERVICE
