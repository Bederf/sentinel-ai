"""
Asset Health Service — Phase 109A

Aggregates equipment health scores and baseline status into a single snapshot
per equipment item. Used by the asset health endpoints to avoid N+1 queries.

Health status is delegated to HealthThresholdService (single source of truth).
Deviation classification is baseline-specific: <=15% normal, <30% warning, >=30% critical.
"""

import logging
from typing import List, Optional

from app.config.settings import settings
from app.database.repositories.baseline_repository import BaselineRepository
from app.database.repositories.equipment_repository import get_equipment_repository
from app.models.asset_health import AssetHealthBaseline
from app.services.health_threshold_service import get_health_threshold_service

logger = logging.getLogger(__name__)


class AssetHealthService:
    """Combines equipment health + baseline data into AssetHealthBaseline snapshots."""

    def __init__(self):
        self._equipment_repo = get_equipment_repository()
        self._baseline_repo = BaselineRepository()
        self._threshold_svc = get_health_threshold_service()

    async def get_site_assets(self, site_code: str) -> List[AssetHealthBaseline]:
        """Get baseline + health snapshot for ALL equipment at a site."""
        # 1. Fetch equipment list
        equipment_list = self._equipment_repo.get_by_building_code(site_code)
        if not equipment_list:
            logger.debug("No equipment found for site %s", site_code)
            return []

        # Extract equipment codes for bulk queries
        equipment_ids = [eq.get("code", eq.get("id", "")) for eq in equipment_list]

        # 2. Bulk-fetch baseline summaries and deviations (2 queries, not N)
        baseline_status = await self._baseline_repo.get_bulk_baseline_status(equipment_ids)
        deviation_status = await self._baseline_repo.get_bulk_max_deviation_24h(equipment_ids)

        # 3. Build results
        assets: List[AssetHealthBaseline] = []
        for eq in equipment_list:
            code = eq.get("code", eq.get("id", ""))
            asset = self._build_asset(eq, code, baseline_status, deviation_status)
            assets.append(asset)

        return assets

    async def get_equipment_detail(self, equipment_id: str) -> Optional[AssetHealthBaseline]:
        """Get baseline + health snapshot for a single equipment item."""
        # equipment_id here is an equipment code (e.g. S002-CHILLER-B1-001)
        eq = self._equipment_repo.get_by_id(equipment_id)
        if not eq:
            return None

        code = eq.get("code", eq.get("id", ""))

        # Fetch baseline + deviation for this single item
        baseline_status = await self._baseline_repo.get_bulk_baseline_status([code])
        deviation_status = await self._baseline_repo.get_bulk_max_deviation_24h([code])

        return self._build_asset(eq, code, baseline_status, deviation_status)

    def _build_asset(
        self,
        eq: dict,
        code: str,
        baseline_status: dict,
        deviation_status: dict,
    ) -> AssetHealthBaseline:
        """Construct an AssetHealthBaseline from equipment dict + bulk query results."""
        health_score = eq.get("health_score") or eq.get("health", 80)
        if isinstance(health_score, str):
            try:
                health_score = int(float(health_score))
            except (ValueError, TypeError):
                health_score = 80
        health_score = int(health_score)

        health_status = self._threshold_svc.get_health_status(health_score)

        # Determine health source
        if settings.demo_mode:
            health_source = "simulation"
        else:
            health_source = "equipment_table"

        # Baseline data
        bl = baseline_status.get(code, {})
        has_active = bl.get("has_active_baseline", False)
        last_baseline_at = bl.get("last_baseline_at")
        total_baselines = bl.get("total_baselines", 0)
        baseline_source = bl.get("baseline_source")

        # Deviation data
        dev = deviation_status.get(code, {})
        max_dev = dev.get("max_deviation_percent")
        dev_status = dev.get("deviation_status")

        return AssetHealthBaseline(
            equipment_id=code,
            equipment_name=eq.get("name", code),
            equipment_type=eq.get("type", eq.get("equipment_type", "unknown")),
            category=eq.get("category", "Other"),
            health_score=health_score,
            health_status=health_status,
            health_source=health_source,
            health_updated_at=eq.get("updated_at"),
            has_active_baseline=has_active,
            last_baseline_at=last_baseline_at,
            total_baselines=total_baselines,
            baseline_source=baseline_source,
            max_deviation_percent_24h=max_dev,
            deviation_status=dev_status,
        )


# Singleton
_asset_health_service_instance: Optional[AssetHealthService] = None


def get_asset_health_service() -> AssetHealthService:
    """Get or create the AssetHealthService singleton."""
    global _asset_health_service_instance
    if _asset_health_service_instance is None:
        _asset_health_service_instance = AssetHealthService()
    return _asset_health_service_instance
