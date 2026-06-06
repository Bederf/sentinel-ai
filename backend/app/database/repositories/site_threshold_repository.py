"""Repository for unified site threshold CRUD.

Stores health + risk thresholds in the site_thresholds table.
One row per site_id (PK). site_id='__global__' is the fallback default.
"""

from __future__ import annotations

import logging
from typing import Any

from app.database.supabase_client import get_supabase_client

logger = logging.getLogger(__name__)

GLOBAL_SITE_ID = "__global__"

DEFAULT_HEALTH = {"healthy": 85, "warning": 65, "critical": 40}
DEFAULT_RISK = {"medium": 31, "high": 61, "critical": 81}


def _validate_ordering(health: dict[str, int], risk: dict[str, int]) -> None:
    if not (health["healthy"] > health["warning"] > health["critical"] >= 0 and health["healthy"] <= 100):
        raise ValueError(
            f"Health thresholds must satisfy: 0 <= critical < warning < healthy <= 100. "
            f"Got healthy={health['healthy']}, warning={health['warning']}, critical={health['critical']}"
        )
    if not (0 <= risk["medium"] < risk["high"] < risk["critical"] <= 100):
        raise ValueError(
            f"Risk thresholds must satisfy: 0 <= medium < high < critical <= 100. "
            f"Got medium={risk['medium']}, high={risk['high']}, critical={risk['critical']}"
        )


class SiteThresholdRepository:
    """CRUD for the site_thresholds table."""

    def __init__(self) -> None:
        self.client = get_supabase_client()

    def get(self, site_id: str | None) -> dict[str, Any] | None:
        site_key = site_id if site_id else GLOBAL_SITE_ID
        result = (
            self.client.table("site_thresholds")
            .select("site_id, health, risk")
            .eq("site_id", site_key)
            .limit(1)
            .execute()
        )
        if result.data:
            row = result.data[0]
            return {
                "site_id": row["site_id"],
                "health": dict(row["health"]) if isinstance(row["health"], dict) else row["health"],
                "risk": dict(row["risk"]) if isinstance(row["risk"], dict) else row["risk"],
            }
        return None

    def upsert(self, site_id: str, health: dict[str, int], risk: dict[str, int]) -> dict[str, Any]:
        _validate_ordering(health, risk)
        payload = {
            "site_id": site_id,
            "health": health,
            "risk": risk,
        }
        result = self.client.table("site_thresholds").upsert(payload, on_conflict="site_id").execute()
        if result.data:
            row = result.data[0]
            return {
                "site_id": row["site_id"],
                "health": dict(row["health"]) if isinstance(row["health"], dict) else row["health"],
                "risk": dict(row["risk"]) if isinstance(row["risk"], dict) else row["risk"],
            }
        return payload

    def update_health(self, site_id: str, health: dict[str, int]) -> dict[str, Any]:
        existing = self.get(site_id) or self.get(None) or {"health": dict(DEFAULT_HEALTH), "risk": dict(DEFAULT_RISK)}
        return self.upsert(site_id, health, existing["risk"])

    def update_risk(self, site_id: str, risk: dict[str, int]) -> dict[str, Any]:
        existing = self.get(site_id) or self.get(None) or {"health": dict(DEFAULT_HEALTH), "risk": dict(DEFAULT_RISK)}
        return self.upsert(site_id, existing["health"], risk)
