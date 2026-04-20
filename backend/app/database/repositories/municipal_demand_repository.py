"""Repository for municipal demand history (local fallback/BMS aggregates)."""

import logging
from datetime import date
from typing import Any

from app.database.supabase_client import get_supabase_client

logger = logging.getLogger(__name__)


class MunicipalDemandRepository:
    """Read demand history data from Supabase."""

    def __init__(self):
        self.client = get_supabase_client()

    def get_by_site(
        self,
        site_id: str,
        start_date: date,
        end_date: date,
        meter_id: str | None = None,
    ) -> list[dict[str, Any]]:
        query = (
            self.client.table("municipal_demand_history")
            .select("*")
            .eq("site_id", site_id)
            .gte("date", start_date.isoformat())
            .lte("date", end_date.isoformat())
            .order("date", desc=False)
        )
        if meter_id:
            query = query.eq("meter_id", meter_id)
        try:
            result = query.execute()
            return result.data or []
        except Exception as exc:
            logger.error("Error fetching municipal demand history: %s", exc)
            return []

    def get_peak_window(
        self,
        site_id: str,
        start_date: date,
        end_date: date,
        meter_id: str | None = None,
    ) -> dict[str, Any] | None:
        query = (
            self.client.table("municipal_demand_history")
            .select("*")
            .eq("site_id", site_id)
            .gte("date", start_date.isoformat())
            .lte("date", end_date.isoformat())
            .order("peak_demand_kw", desc=True)
            .limit(1)
        )
        if meter_id:
            query = query.eq("meter_id", meter_id)
        try:
            result = query.execute()
            if result.data:
                return result.data[0]
            return None
        except Exception as exc:
            logger.error("Error fetching peak window: %s", exc)
            return None
