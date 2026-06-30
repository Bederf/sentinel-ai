"""Append-only recommendation audit event repository."""

import logging
from datetime import UTC, datetime, timedelta
from typing import Any

from app.database.repositories.base import SupabaseRepository
from app.services.cache_service import cache

logger = logging.getLogger(__name__)


LIFECYCLE_EVENT_TYPES = {
    "created",
    "surfaced",
    "viewed",
    "acknowledged",
    "approved",
    "rejected",
    "deferred",
    "wo_linked",
    "resolved",
    "expired",
    "escalated",
    "executed",
    "failed",
    "updated",
}

QUALITY_EXCEPTION_TYPES = {
    "severity_reclassified",
    "missed_escalation",
    "confidence_gate_failed",
    "false_positive_marked",
    "false_negative_identified",
    "recommendation_withdrawn",
    "model_logic_corrected",
    "other",
}

OPEN_RECOMMENDATION_STATUSES = {"pending", "advisory_info", "approved"}


def recommendation_state(row: dict[str, Any] | None) -> dict[str, Any]:
    """Extract the compact state snapshot stored on every audit event."""
    if not row:
        return {}
    return {
        "status": row.get("status"),
        "risk_level": row.get("risk_level"),
        "approval_status": row.get("approval_status"),
        "approved_by": row.get("approved_by"),
        "approved_at": row.get("approved_at"),
        "rejection_reason": row.get("rejection_reason"),
        "executed_at": row.get("executed_at"),
        "execution_result": row.get("execution_result"),
        "target_equipment": row.get("target_equipment"),
        "action_type": row.get("action_type"),
    }


def infer_lifecycle_event_type(previous_state: dict[str, Any], new_state: dict[str, Any]) -> str:
    """Map materialized recommendation status transitions into lifecycle events."""
    old_status = str(previous_state.get("status") or "")
    new_status = str(new_state.get("status") or "")
    if old_status == new_status:
        return "updated"
    if new_status == "approved":
        return "approved"
    if new_status == "rejected":
        return "rejected"
    if new_status == "expired":
        return "expired"
    if new_status == "failed":
        return "failed"
    if new_status == "executed":
        return "executed"
    if new_status == "auto_executed":
        return "resolved"
    return "updated"


class RecommendationAuditRepository(SupabaseRepository):
    """Writes and reads immutable recommendation lifecycle/quality events."""

    _TABLE = "recommendation_audit_events"
    _WRITE_COLUMNS = {
        "id",
        "recommendation_id",
        "linked_recommendation_id",
        "site_id",
        "event_track",
        "event_type",
        "quality_exception_type",
        "actor_type",
        "actor_id",
        "detected_by",
        "source",
        "previous_state",
        "new_state",
        "metadata",
        "occurred_at",
    }

    def _filter_payload(self, payload: dict[str, Any]) -> dict[str, Any]:
        return {key: value for key, value in payload.items() if key in self._WRITE_COLUMNS}

    async def record_event(
        self,
        *,
        recommendation_id: str | None,
        site_id: str,
        event_type: str,
        previous_state: dict[str, Any] | None = None,
        new_state: dict[str, Any] | None = None,
        actor_type: str = "system",
        actor_id: str | None = None,
        source: str = "sentinel",
        metadata: dict[str, Any] | None = None,
        linked_recommendation_id: str | None = None,
        detected_by: str | None = None,
        quality_exception_type: str | None = None,
        occurred_at: datetime | str | None = None,
    ) -> dict[str, Any] | None:
        """Append one immutable audit event."""
        if event_type == "system_quality_exception":
            event_track = "system_quality"
            if not linked_recommendation_id:
                linked_recommendation_id = recommendation_id
            if not linked_recommendation_id:
                raise ValueError("system quality events require linked_recommendation_id")
            if not detected_by:
                raise ValueError("system quality events require detected_by")
            if quality_exception_type not in QUALITY_EXCEPTION_TYPES:
                raise ValueError(f"invalid quality_exception_type: {quality_exception_type}")
        else:
            event_track = "lifecycle"
            if event_type not in LIFECYCLE_EVENT_TYPES:
                raise ValueError(f"invalid lifecycle event_type: {event_type}")
            if not recommendation_id:
                raise ValueError("lifecycle events require recommendation_id")

        if isinstance(occurred_at, datetime):
            occurred_value = occurred_at.isoformat()
        else:
            occurred_value = occurred_at or datetime.now(UTC).isoformat()

        payload = {
            "recommendation_id": recommendation_id,
            "linked_recommendation_id": linked_recommendation_id,
            "site_id": site_id,
            "event_track": event_track,
            "event_type": event_type,
            "quality_exception_type": quality_exception_type,
            "actor_type": actor_type,
            "actor_id": actor_id,
            "detected_by": detected_by,
            "source": source,
            "previous_state": previous_state or {},
            "new_state": new_state or {},
            "metadata": metadata or {},
            "occurred_at": occurred_value,
        }

        client = await self.get_client()
        if not client:
            return None
        try:
            result = await client.table(self._TABLE).insert(self._filter_payload(payload)).execute()
            cache.delete_pattern("recommendation_audit:*")
            return result.data[0] if result.data else None
        except Exception as exc:
            logger.warning("Recommendation audit event insert failed: %s", exc)
            return None

    async def get_events_for_recommendation(self, recommendation_id: str, limit: int = 100) -> list[dict[str, Any]]:
        """Return lifecycle and quality events for a recommendation chain."""
        client = await self.get_client()
        if not client:
            return []
        try:
            query = (
                client.table(self._TABLE)
                .select("*")
                .or_(f"recommendation_id.eq.{recommendation_id},linked_recommendation_id.eq.{recommendation_id}")
                .order("occurred_at", desc=False)
                .limit(limit)
            )
            result = await query.execute()
            return result.data or []
        except Exception as exc:
            logger.warning("Recommendation audit event query failed: %s", exc)
            return []

    async def get_manager_exceptions(
        self,
        *,
        site_id: str,
        stale_hours: int = 24,
        limit: int = 50,
    ) -> dict[str, Any]:
        """Build the manager exception feed from recommendations and audit events."""
        client = await self.get_client()
        cutoff = datetime.now(UTC) - timedelta(hours=stale_hours)
        cutoff_iso = cutoff.isoformat()
        if not client:
            return {
                "site_id": site_id,
                "stale_hours": stale_hours,
                "stale_unactioned": [],
                "approved_without_wo": [],
                "system_quality_exceptions": [],
                "counts": {"stale_unactioned": 0, "approved_without_wo": 0, "system_quality_exceptions": 0},
            }

        stale_unactioned: list[dict[str, Any]] = []
        approved_without_wo: list[dict[str, Any]] = []
        quality_exceptions: list[dict[str, Any]] = []
        try:
            stale_query = (
                client.table("recommendations")
                .select("id,site_id,timestamp,action_type,risk_level,target_equipment,reason,status,metadata")
                .eq("site_id", site_id)
                .in_("status", sorted(OPEN_RECOMMENDATION_STATUSES))
                .eq("shadow_mode", False)
                .lte("timestamp", cutoff_iso)
                .order("timestamp", desc=False)
                .limit(limit)
            )
            stale_resp = await stale_query.execute()
            stale_unactioned = stale_resp.data or []
        except Exception as exc:
            logger.warning("Manager stale recommendation query failed: %s", exc)

        try:
            approved_query = (
                client.table("recommendations")
                .select(
                    "id,site_id,timestamp,action_type,risk_level,target_equipment,reason,status,execution_result,metadata"
                )
                .eq("site_id", site_id)
                .eq("status", "approved")
                .eq("shadow_mode", False)
                .order("timestamp", desc=True)
                .limit(limit)
            )
            approved_resp = await approved_query.execute()
            for row in approved_resp.data or []:
                execution_result = row.get("execution_result") or {}
                metadata = row.get("metadata") or {}
                if not isinstance(execution_result, dict):
                    execution_result = {}
                if not isinstance(metadata, dict):
                    metadata = {}
                if (
                    not execution_result.get("work_order_id")
                    and not execution_result.get("work_order_code")
                    and not metadata.get("work_order_id")
                    and not metadata.get("work_order_code")
                ):
                    approved_without_wo.append(row)
        except Exception as exc:
            logger.warning("Manager approved-without-WO query failed: %s", exc)

        try:
            quality_query = (
                client.table(self._TABLE)
                .select("*")
                .eq("site_id", site_id)
                .eq("event_track", "system_quality")
                .order("occurred_at", desc=True)
                .limit(limit)
            )
            quality_resp = await quality_query.execute()
            quality_exceptions = quality_resp.data or []
        except Exception as exc:
            logger.warning("Manager quality exception query failed: %s", exc)

        return {
            "site_id": site_id,
            "stale_hours": stale_hours,
            "stale_unactioned": stale_unactioned,
            "approved_without_wo": approved_without_wo[:limit],
            "system_quality_exceptions": quality_exceptions,
            "counts": {
                "stale_unactioned": len(stale_unactioned),
                "approved_without_wo": len(approved_without_wo[:limit]),
                "system_quality_exceptions": len(quality_exceptions),
            },
        }


_repository: RecommendationAuditRepository | None = None


def get_recommendation_audit_repository() -> RecommendationAuditRepository:
    """Get or create the recommendation audit repository singleton."""
    global _repository
    if _repository is None:
        _repository = RecommendationAuditRepository()
    return _repository
