"""Repository for unified site threshold CRUD.

Stores health + risk thresholds in the site_thresholds table.
One row per site_id (PK). site_id='__global__' is the fallback default.

All writes go through tuner_promote_thresholds (SECURITY DEFINER, atomic):
  - writes threshold_change_log (audit trail)
  - upserts site_thresholds (active values)
  - updates proposal status (if promote from proposal)
Single transaction — if any step fails, all roll back.
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

    def upsert(
        self,
        site_id: str,
        health: dict[str, int],
        risk: dict[str, int],
        approved_by: str | None = None,
    ) -> dict[str, Any]:
        """Upsert thresholds — routes through atomic promote function.

        All writes go through tuner_promote_thresholds so the change_log
        is always written. triggered_by='operator' for direct edits.
        """
        _validate_ordering(health, risk)
        return self._promote(
            site_id=site_id,
            health=health,
            risk=risk,
            triggered_by="operator",
            proposal_id=None,
            approved_by=approved_by,
        )

    def promote_proposal(
        self,
        proposal_id: int,
        approved_by: str,
    ) -> dict[str, Any]:
        """Promote a pending proposal to active thresholds."""
        proposal = self.get_proposal(proposal_id)
        if not proposal:
            raise ValueError(f"Proposal {proposal_id} not found")
        if proposal["status"] != "pending":
            raise ValueError(f"Proposal {proposal_id} is not pending (status={proposal['status']})")

        return self._promote(
            site_id=proposal["site_id"],
            health=proposal["health"],
            risk=proposal["risk"],
            triggered_by="tuner_proposal",
            proposal_id=proposal_id,
            approved_by=approved_by,
        )

    def rollback_to_log_entry(
        self,
        log_id: int,
        site_id: str,
        approved_by: str,
    ) -> dict[str, Any]:
        """Restore the threshold values that a prior change_log entry established.

        Reads new_health/new_risk from the target log entry — the values that
        became active when that change was promoted. Promotes them again through
        the same _promote function with triggered_by='rollback', creating a new
        change_log entry that records the restoration.

        Note: this restores what the target entry SET (its new_* values), not
        what existed before it (its old_* values). If you want to undo change N,
        rollback to entry N-1, not entry N.
        """
        entry = self.get_change_log_entry(log_id)
        if not entry:
            raise ValueError(f"Change log entry {log_id} not found")
        if entry["site_id"] != site_id:
            raise ValueError(f"Change log entry {log_id} is for site {entry['site_id']}, not {site_id}")

        target_health = entry["new_health"]
        target_risk = entry["new_risk"]
        if target_health is None or target_risk is None:
            raise ValueError(f"Change log entry {log_id} has no target values")

        return self._promote(
            site_id=site_id,
            health=target_health,
            risk=target_risk,
            triggered_by="rollback",
            proposal_id=None,
            approved_by=approved_by,
        )

    def get_proposal(self, proposal_id: int) -> dict[str, Any] | None:
        result = (
            self.client.table("site_threshold_proposals").select("*").eq("proposal_id", proposal_id).limit(1).execute()
        )
        return result.data[0] if result.data else None

    def get_change_log_entry(self, log_id: int) -> dict[str, Any] | None:
        result = self.client.table("threshold_change_log").select("*").eq("log_id", log_id).limit(1).execute()
        return result.data[0] if result.data else None

    def get_change_log(
        self,
        site_id: str | None = None,
        limit: int = 20,
    ) -> list[dict[str, Any]]:
        query = self.client.table("threshold_change_log").select("*").order("changed_at", desc=True).limit(limit)
        if site_id:
            query = query.eq("site_id", site_id)
        result = query.execute()
        return result.data if result.data else []

    def _promote(
        self,
        site_id: str,
        health: dict[str, int],
        risk: dict[str, int],
        triggered_by: str,
        proposal_id: int | None = None,
        approved_by: str | None = None,
    ) -> dict[str, Any]:
        """Call tuner_promote_thresholds RPC — atomic change_log + upsert."""
        result = self.client.rpc(
            "tuner_promote_thresholds",
            {
                "p_site_id": site_id,
                "p_new_health": health,
                "p_new_risk": risk,
                "p_triggered_by": triggered_by,
                "p_proposal_id": proposal_id,
                "p_approved_by": approved_by,
            },
        ).execute()
        log_id = result.data if result.data else None
        return {
            "log_id": log_id,
            "site_id": site_id,
            "health": health,
            "risk": risk,
            "triggered_by": triggered_by,
        }

    def update_health(self, site_id: str, health: dict[str, int]) -> dict[str, Any]:
        existing = self.get(site_id) or self.get(None) or {"health": dict(DEFAULT_HEALTH), "risk": dict(DEFAULT_RISK)}
        return self.upsert(site_id, health, existing["risk"])

    def update_risk(self, site_id: str, risk: dict[str, int]) -> dict[str, Any]:
        existing = self.get(site_id) or self.get(None) or {"health": dict(DEFAULT_HEALTH), "risk": dict(DEFAULT_RISK)}
        return self.upsert(site_id, existing["health"], risk)
