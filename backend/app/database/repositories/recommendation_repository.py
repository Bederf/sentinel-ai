"""Repository for recommendation tracking operations."""

import logging
from datetime import UTC, datetime, timedelta
from typing import Any
from uuid import UUID

from app.database.repositories.base import SupabaseRepository
from app.models.recommendation import Recommendation, RecommendationStatus
from app.services.cache_service import cache

logger = logging.getLogger(__name__)


class RecommendationRepository(SupabaseRepository):
    """Repository for recommendation database operations."""

    _COLUMNS = (
        "id, site_id, timestamp, action_type, risk_level, target_equipment, "
        "action, reason, expected_impact, confidence, confidence_score, profile, "
        "multi_objective_score, status, requires_approval, approval_status, "
        "approved_by, approved_at, approval_reason, executed_at, execution_result, "
        "rejection_reason, source, source_type, metadata, outcome_validated, "
        "outcome_notes, actual_value_set, power_at_creation_kw, tariff_rate_at_creation, "
        "baseline_energy_kwh, actual_energy_kwh, actual_saving_kwh, actual_saving_zar"
    )
    _WRITE_COLUMNS = {
        "id",
        "site_id",
        "timestamp",
        "action_type",
        "risk_level",
        "target_equipment",
        "action",
        "reason",
        "expected_impact",
        "confidence",
        "confidence_score",
        "profile",
        "multi_objective_score",
        "status",
        "requires_approval",
        "approval_status",
        "approved_by",
        "approved_at",
        "approval_reason",
        "executed_at",
        "execution_result",
        "rejection_reason",
        "shadow_mode",
        "source",
        "source_type",
        "metadata",
        "outcome_validated",
        "outcome_notes",
        "actual_value_set",
        "power_at_creation_kw",
        "tariff_rate_at_creation",
        "baseline_energy_kwh",
        "actual_energy_kwh",
        "actual_saving_kwh",
        "actual_saving_zar",
    }

    def _filter_supabase_payload(self, rec_dict: dict[str, Any]) -> dict[str, Any]:
        """Drop model-only keys that do not exist in the live recommendations table."""
        return {key: value for key, value in rec_dict.items() if key in self._WRITE_COLUMNS}

    def _normalise_source_fields(self, rec_dict: dict[str, Any]) -> dict[str, Any]:
        """Ensure AI optimization recommendations remain visible to phase gates."""
        normalised = dict(rec_dict)
        metadata = normalised.get("metadata") or {}
        if not isinstance(metadata, dict):
            metadata = {}

        action_type = str(normalised.get("action_type") or "")
        family = (
            "maintenance"
            if action_type
            in {
                "health_maintenance",
                "maintenance",
                "maintenance_gap",
                "maintenance_schedule",
                "inspect",
                "repair",
                "replace",
                "schedule_maintenance",
            }
            or str(normalised.get("source") or "") in {"maintenance_recommender", "reflex_reconciliation"}
            else "ai"
        )
        metadata.setdefault("recommendation_family", family)
        normalised["metadata"] = metadata
        if action_type not in {"ai_optimization", "coordinated_optimization"}:
            normalised.setdefault("recommendation_family", family)
            return normalised

        if not normalised.get("source"):
            normalised["source"] = "ai_optimizer"

        if not normalised.get("source_type"):
            metadata = normalised.get("metadata") or {}
            source_metadata = metadata.get("source_metadata") if isinstance(metadata, dict) else {}
            rule = ""
            if isinstance(metadata, dict):
                rule = str(metadata.get("rule") or "")
            if not rule and isinstance(source_metadata, dict):
                rule = str(source_metadata.get("rule") or "")

            if rule == "closed_empty_building_hvac_running":
                normalised["source_type"] = "operating_state_gate"
            else:
                normalised["source_type"] = "ml_model"

        normalised.setdefault("recommendation_family", family)
        return normalised

    async def create(self, rec: Recommendation) -> Recommendation:
        """Create new recommendation in the canonical DB store."""
        rec_dict = self._normalise_source_fields(rec.to_dict())
        action_type = str(rec_dict.get("action_type") or "")
        if action_type in {
            "health_maintenance",
            "maintenance",
            "maintenance_gap",
            "maintenance_schedule",
            "inspect",
            "repair",
            "replace",
            "schedule_maintenance",
        }:
            try:
                client = await self.get_client()
                existing = (
                    client.table("recommendations")
                    .select("*")
                    .eq("site_id", rec_dict.get("site_id"))
                    .eq("status", "pending")
                    .eq("target_equipment", rec_dict.get("target_equipment"))
                    .eq("action_type", action_type)
                    .order("timestamp", desc=True)
                    .limit(1)
                    .execute()
                )
                if existing.data:
                    logger.info(
                        "Deduped pending maintenance recommendation for %s/%s",
                        rec_dict.get("site_id"),
                        rec_dict.get("target_equipment"),
                    )
                    return Recommendation.from_dict(existing.data[0])
            except Exception as exc:
                logger.warning("Maintenance recommendation dedupe check failed: %s", exc)
        try:
            duplicate = await self._find_recent_duplicate_control_recommendation(rec_dict)
            if duplicate:
                logger.info(
                    "Deduped recent control recommendation for %s/%s action=%s",
                    rec_dict.get("site_id"),
                    rec_dict.get("target_equipment"),
                    rec_dict.get("action"),
                )
                return Recommendation.from_dict(duplicate)
        except Exception as exc:
            logger.warning("Control recommendation dedupe check failed: %s", exc)
        result = await self._supabase_insert(rec_dict)
        if result:
            await self._record_audit_event(
                recommendation_id=str(result.get("id") or rec.id),
                site_id=str(result.get("site_id") or rec.site_id),
                event_type="created",
                previous_state={},
                new_state=result,
                source="recommendation_repository.create",
                metadata={"action_type": result.get("action_type")},
            )
            return Recommendation.from_dict(result)
        logger.error("Error creating recommendation %s: canonical DB write failed", rec.id)
        raise RuntimeError("Failed to persist recommendation to canonical DB store")

    async def _find_recent_duplicate_control_recommendation(self, rec_dict: dict[str, Any]) -> dict[str, Any] | None:
        """Find an open duplicate control recommendation.

        Executed recommendations are intentionally excluded. A newly generated
        Telegram advisory must not reuse the ID of an already-actioned record,
        otherwise a fresh inline button can point at a closed recommendation and
        fail with a misleading stale/current message.
        """
        action = rec_dict.get("action") or {}
        if not isinstance(action, dict):
            return None
        site_id = rec_dict.get("site_id")
        equipment = rec_dict.get("target_equipment")
        point = action.get("point")
        value = action.get("value")
        action_type = str(rec_dict.get("action_type") or "")
        if action_type not in {"ai_optimization", "coordinated_optimization"}:
            return None
        if not site_id or not equipment or not point or value is None:
            return None

        client = await self.get_client()
        if not client:
            return None
        since = (datetime.now(UTC) - timedelta(hours=2)).isoformat()
        result = await (
            client.table("recommendations")
            .select(self._COLUMNS)
            .eq("site_id", site_id)
            .eq("target_equipment", equipment)
            .in_("status", ["pending", "approved"])
            .gte("timestamp", since)
            .order("timestamp", desc=True)
            .limit(50)
            .execute()
        )
        for row in result.data or []:
            row_action = row.get("action") or {}
            if not isinstance(row_action, dict):
                continue
            if row_action.get("point") == point and str(row_action.get("value")) == str(value):
                return row
        return None

    async def get(self, rec_id: str) -> Recommendation | None:
        """Get recommendation by ID."""
        rec_dict = await self._supabase_get(rec_id)
        return Recommendation.from_dict(rec_dict) if rec_dict else None

    async def get_by_id(self, rec_id: str) -> Recommendation | None:
        """Alias for get() for consistency with other repositories."""
        return await self.get(rec_id)

    async def get_by_status(
        self,
        site_id: str,
        status: RecommendationStatus | str,
        limit: int = 10,
    ) -> list[Recommendation]:
        """Get recommendations with status, newest first."""
        recs = await self._supabase_get_by_status(site_id, status, limit)
        return [Recommendation.from_dict(rec) for rec in recs]

    async def get_history(
        self,
        site_id: str,
        status_filter: str | None = None,
        risk_level_filter: str | None = None,
        limit: int = 50,
    ) -> list[Recommendation]:
        """Get historical recommendations for a site with optional filters."""
        recs = await self._supabase_get_history(site_id, status_filter, risk_level_filter, limit)
        return [Recommendation.from_dict(rec) for rec in recs]

    async def update(self, rec_id: str, rec: Recommendation) -> Recommendation:
        """Update recommendation."""
        rec_dict = rec.to_dict()
        result = await self._supabase_update(rec_id, rec_dict)
        if result:
            return Recommendation.from_dict(result)
        logger.error("Error updating recommendation %s: canonical DB write failed", rec_id)
        raise RuntimeError("Failed to update recommendation in canonical DB store")

    async def upsert(self, rec: Recommendation) -> Recommendation:
        """Insert or update recommendation (upsert)."""
        existing = await self.get(rec.id)
        if existing:
            return await self.update(rec.id, rec)
        return await self.create(rec)

    async def resolve_id_prefix(self, token: str) -> str:
        """Resolve a full recommendation ID from either a full ID or short prefix."""
        if not token:
            return ""

        try:
            UUID(token)
            exact = await self.get(token)
            if exact:
                return token
        except ValueError:
            pass

        client = await self.get_client()
        if not client:
            return ""

        try:
            result = await (
                client.table("recommendations")
                .select("id,timestamp")
                .order("timestamp", desc=True)
                .limit(1000)
                .execute()
            )
            matches = [row["id"] for row in (result.data or []) if str(row.get("id", "")).startswith(token)]
            if len(matches) == 1:
                return matches[0]
        except Exception as e:
            logger.error("Recommendation prefix resolution failed: %s", e)

        return ""

    async def _supabase_insert(self, rec_dict: dict[str, Any]) -> dict[str, Any] | None:
        """Insert recommendation to Supabase."""
        client = await self.get_client()
        if not client:
            return None
        try:
            payload = self._filter_supabase_payload(rec_dict)
            result = await client.table("recommendations").insert(payload).execute()
            if result.data and len(result.data) > 0:
                cache.delete_pattern("recommendations:*")
                return result.data[0]
            return None
        except Exception as e:
            logger.error("Supabase insert failed: %s", e)
            return None

    async def _supabase_get(self, rec_id: str) -> dict[str, Any] | None:
        """Get recommendation from Supabase."""
        client = await self.get_client()
        if not client:
            return None
        try:
            result = await client.table("recommendations").select(self._COLUMNS).eq("id", rec_id).execute()
            if result.data and len(result.data) > 0:
                return result.data[0]
            return None
        except Exception as e:
            logger.error("Supabase get failed: %s", e)
            return None

    async def _supabase_get_by_status(
        self,
        site_id: str,
        status: RecommendationStatus | str,
        limit: int,
    ) -> list[dict[str, Any]]:
        """Query recommendations from Supabase by status."""
        client = await self.get_client()
        if not client:
            return []
        try:
            status_value = status.value if isinstance(status, RecommendationStatus) else str(status)
            query = (
                client.table("recommendations")
                .select("*")
                .eq("site_id", site_id)
                .eq("action_type", "ai_optimization")
                .eq("shadow_mode", False)
                .order("risk_level", desc=True)
                .order("timestamp", desc=True)
                .limit(limit)
            )
            if status_value == RecommendationStatus.PENDING.value:
                query = query.in_(
                    "status",
                    [
                        RecommendationStatus.PENDING.value,
                        RecommendationStatus.ADVISORY_INFO.value,
                    ],
                )
            else:
                query = query.eq("status", status_value)
            result = await query.execute()
            return result.data or []
        except Exception as e:
            logger.error("Supabase query failed: %s", e)
            return []

    async def expire_superseded_setpoints(self, site_id: str, target_equipment: str, point_name: str) -> int:
        """Expire all pending setpoint recs for equipment+point, superseded by a new one.

        Called before creating a new ai_optimization rec so stale Telegram advisories
        can't be approved after the value has already been updated.
        """
        client = await self.get_client()
        if not client:
            return 0
        try:
            result = await (
                client.table("recommendations")
                .update({"status": "expired"})
                .eq("site_id", site_id)
                .eq("target_equipment", target_equipment)
                .eq("status", "pending")
                .filter("action->>point", "eq", point_name)
                .execute()
            )
            count = len(result.data or [])
            if count:
                cache.delete_pattern("recommendations:*")
                for row in result.data or []:
                    previous_state = {
                        "status": "pending",
                        "risk_level": row.get("risk_level"),
                        "target_equipment": row.get("target_equipment"),
                        "action_type": row.get("action_type"),
                    }
                    await self._record_audit_event(
                        recommendation_id=str(row.get("id") or ""),
                        site_id=str(row.get("site_id") or site_id),
                        event_type="expired",
                        previous_state=previous_state,
                        new_state=row,
                        source="recommendation_repository.expire_superseded_setpoints",
                        metadata={"point_name": point_name},
                    )
                logger.info(
                    "[REC-SUPERSEDE] Expired %d stale pending recs for %s/%s",
                    count,
                    target_equipment,
                    point_name,
                )
            return count
        except Exception as e:
            logger.warning("expire_superseded_setpoints failed for %s/%s: %s", target_equipment, point_name, e)
            return 0

    @staticmethod
    def _metadata_rule(metadata: dict[str, Any] | None) -> str:
        if not isinstance(metadata, dict):
            return ""
        source_metadata = metadata.get("source_metadata")
        if isinstance(source_metadata, dict) and source_metadata.get("rule"):
            return str(source_metadata.get("rule") or "")
        return str(metadata.get("rule") or "")

    async def expire_pending_by_source_rules(
        self,
        site_id: str,
        source_rules: list[str] | tuple[str, ...] | set[str],
        *,
        superseded_by_rule: str,
        superseded_reason: str,
        target_prefixes: list[str] | tuple[str, ...] | set[str] | None = None,
        limit: int = 500,
    ) -> int:
        """Expire active recommendations by logical rule, not target/point key.

        This covers safety gates where the corrective recommendation intentionally
        uses a different target than the stale recommendation it invalidates.
        """
        rules = {str(rule) for rule in source_rules if rule}
        if not rules:
            return 0
        prefixes = tuple(str(prefix).upper() for prefix in (target_prefixes or ()) if prefix)
        expired = 0
        now_iso = datetime.now(UTC).isoformat()
        try:
            active = await self.get_by_status(site_id, RecommendationStatus.PENDING, limit=limit)
            for rec in active:
                status_value = rec.status.value if isinstance(rec.status, RecommendationStatus) else str(rec.status)
                if status_value not in {
                    RecommendationStatus.PENDING.value,
                    RecommendationStatus.ADVISORY_INFO.value,
                }:
                    continue
                if rec.action_type != "ai_optimization":
                    continue
                target = str(rec.target_equipment or "").upper()
                if prefixes and not any(target.startswith(prefix) for prefix in prefixes):
                    continue
                rule = self._metadata_rule(rec.metadata)
                if rule not in rules:
                    continue

                previous_state = rec.to_dict()
                metadata = dict(rec.metadata or {})
                metadata.update(
                    {
                        "superseded_by_rule": superseded_by_rule,
                        "superseded_reason": superseded_reason,
                        "superseded_at": now_iso,
                    }
                )
                rec.metadata = metadata
                rec.status = RecommendationStatus.EXPIRED
                rec.approval_status = "superseded"
                if superseded_reason and "[SUPERSEDED" not in str(rec.reason or ""):
                    rec.reason = f"{rec.reason}\n\n[SUPERSEDED {now_iso}: {superseded_reason}]".strip()
                updated = await self.update(rec.id, rec)
                if updated:
                    expired += 1
                    await self._record_audit_event(
                        recommendation_id=str(rec.id or ""),
                        site_id=site_id,
                        event_type="expired",
                        previous_state=previous_state,
                        new_state=updated.to_dict() if hasattr(updated, "to_dict") else metadata,
                        source="recommendation_repository.expire_pending_by_source_rules",
                        metadata={
                            "source_rules": sorted(rules),
                            "superseded_by_rule": superseded_by_rule,
                        },
                    )
            if expired:
                cache.delete_pattern("recommendations:*")
                logger.warning(
                    "[REC-SUPERSEDE] Expired %d pending recs for %s by source rules %s",
                    expired,
                    site_id,
                    sorted(rules),
                )
            return expired
        except Exception as e:
            logger.warning(
                "expire_pending_by_source_rules failed for %s/%s: %s",
                site_id,
                sorted(rules),
                e,
            )
            return 0

    async def expire_all_pending_for_equipment(self, site_id: str, target_equipment: str) -> int:
        """Expire all pending ai_optimization recs for equipment — called when fault gate blocks it."""
        client = await self.get_client()
        if not client:
            return 0
        try:
            result = await (
                client.table("recommendations")
                .update({"status": "expired"})
                .eq("site_id", site_id)
                .eq("target_equipment", target_equipment)
                .eq("status", "pending")
                .eq("action_type", "ai_optimization")
                .execute()
            )
            count = len(result.data or [])
            if count:
                cache.delete_pattern("recommendations:*")
                for row in result.data or []:
                    previous_state = {
                        "status": "pending",
                        "risk_level": row.get("risk_level"),
                        "target_equipment": row.get("target_equipment"),
                        "action_type": row.get("action_type"),
                    }
                    await self._record_audit_event(
                        recommendation_id=str(row.get("id") or ""),
                        site_id=str(row.get("site_id") or site_id),
                        event_type="expired",
                        previous_state=previous_state,
                        new_state=row,
                        source="recommendation_repository.expire_all_pending_for_equipment",
                        metadata={"target_equipment": target_equipment},
                    )
                logger.info(
                    "[REC-FAULT-GATE] Expired %d stale pending recs for fault-gated equipment %s",
                    count,
                    target_equipment,
                )
            return count
        except Exception as e:
            logger.warning("expire_all_pending_for_equipment failed for %s: %s", target_equipment, e)
            return 0

    async def _supabase_update(self, rec_id: str, rec_dict: dict[str, Any]) -> dict[str, Any] | None:
        """Update recommendation in Supabase."""
        client = await self.get_client()
        if not client:
            return None
        try:
            previous_query = client.table("recommendations").select(self._COLUMNS).eq("id", rec_id).limit(1)
            previous_result = await previous_query.execute()
            previous = previous_result.data[0] if previous_result.data else {}
            payload = self._filter_supabase_payload(rec_dict)
            result = await client.table("recommendations").update(payload).eq("id", rec_id).execute()
            if result.data and len(result.data) > 0:
                cache.delete_pattern("recommendations:*")
                updated = result.data[0]
                await self._record_status_update_event(previous, updated)
                return result.data[0]
            return None
        except Exception as e:
            logger.error("Supabase update failed: %s", e)
            return None

    async def _supabase_get_history(
        self,
        site_id: str,
        status_filter: str | None,
        risk_level_filter: str | None,
        limit: int,
    ) -> list[dict[str, Any]]:
        """Query historical recommendations from Supabase with filters."""
        client = await self.get_client()
        if not client:
            return []
        try:
            query = (
                client.table("recommendations")
                .select("*")
                .eq("site_id", site_id)
                .eq("action_type", "ai_optimization")
                .neq("status", "pending")
                .eq("shadow_mode", False)
                .order("timestamp", desc=True)
                .limit(limit)
            )
            if status_filter:
                query = query.eq("status", status_filter)
            if risk_level_filter:
                query = query.eq("risk_level", risk_level_filter)
            result = await query.execute()
            return result.data or []
        except Exception as e:
            logger.error("Supabase history query failed: %s", e)
            return []

    async def get_history_aggregates(
        self,
        site_id: str,
    ) -> dict[str, Any]:
        """Get aggregate counts and savings across all non-pending recommendations.

        Returns counts without limit — accurate for the summary card.
        """
        client = await self.get_client()
        if not client:
            return {"total": 0, "actioned": 0, "verified": 0, "saving_kwh": 0.0, "saving_zar": 0.0}
        try:
            base = (
                client.table("recommendations")
                .eq("site_id", site_id)
                .eq("action_type", "ai_optimization")
                .neq("status", "pending")
                .eq("shadow_mode", False)
            )
            result = await base.select(
                "status, outcome_validated, actual_saving_kwh, actual_saving_zar", count="exact"
            ).execute()
            rows = result.data or []
            total = len(rows)
            actioned = sum(1 for r in rows if r.get("status") in ("executed", "auto_executed"))
            verified = sum(
                1 for r in rows if r.get("outcome_validated") is True or r.get("actual_saving_kwh") is not None
            )
            saving_kwh = sum(float(r.get("actual_saving_kwh") or 0) for r in rows)
            saving_zar = sum(float(r.get("actual_saving_zar") or 0) for r in rows)
            return {
                "total": total,
                "actioned": actioned,
                "verified": verified,
                "saving_kwh": round(saving_kwh, 2),
                "saving_zar": round(saving_zar, 2),
            }
        except Exception as e:
            logger.error("Supabase history aggregates query failed: %s", e)
            return {"total": 0, "actioned": 0, "verified": 0, "saving_kwh": 0.0, "saving_zar": 0.0}

    async def _record_audit_event(
        self,
        *,
        recommendation_id: str,
        site_id: str,
        event_type: str,
        previous_state: dict[str, Any],
        new_state: dict[str, Any],
        source: str,
        metadata: dict[str, Any] | None = None,
    ) -> None:
        """Best-effort append-only audit write. Recommendation writes must not fail on audit outage."""
        if not recommendation_id or not site_id:
            return
        try:
            from app.database.repositories.recommendation_audit_repository import (
                get_recommendation_audit_repository,
                recommendation_state,
            )

            audit_repo = get_recommendation_audit_repository()
            await audit_repo.record_event(
                recommendation_id=recommendation_id,
                site_id=site_id,
                event_type=event_type,
                previous_state=previous_state,
                new_state=recommendation_state(new_state),
                actor_type="system",
                source=source,
                metadata=metadata or {},
            )
        except Exception as exc:
            logger.warning("Recommendation audit event skipped: %s", exc)

    async def _record_status_update_event(self, previous: dict[str, Any], updated: dict[str, Any]) -> None:
        """Append an audit event for materialized recommendation updates."""
        try:
            from app.database.repositories.recommendation_audit_repository import (
                infer_lifecycle_event_type,
                recommendation_state,
            )

            previous_state = recommendation_state(previous)
            new_state = recommendation_state(updated)
            if previous_state == new_state:
                return
            event_type = infer_lifecycle_event_type(previous_state, new_state)
            await self._record_audit_event(
                recommendation_id=str(updated.get("id") or ""),
                site_id=str(updated.get("site_id") or previous.get("site_id") or ""),
                event_type=event_type,
                previous_state=previous_state,
                new_state=new_state,
                source="recommendation_repository.update",
                metadata={"action_type": updated.get("action_type")},
            )
        except Exception as exc:
            logger.warning("Recommendation status audit event skipped: %s", exc)


_repository: RecommendationRepository | None = None


def get_recommendation_repository() -> RecommendationRepository:
    """Get or create RecommendationRepository singleton."""
    global _repository
    if _repository is None:
        _repository = RecommendationRepository()
    return _repository
