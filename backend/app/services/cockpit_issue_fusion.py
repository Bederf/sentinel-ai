from __future__ import annotations

import json
import logging
from datetime import UTC, datetime, timedelta
from typing import Any

import httpx

from app.config.settings import settings
from app.database.repositories.alert_repository import AlertRepository, get_alert_repository
from app.database.repositories.audit_repository import AuditRepository
from app.database.repositories.email_intake_repository import EmailIntakeRepository, get_email_intake_repository
from app.database.repositories.recommendation_repository import get_recommendation_repository
from app.database.repositories.work_order_repository import WorkOrderRepository, get_work_order_repository
from app.processing.cockpit_table import CockpitTableProcessor
from app.schemas.cockpit import (
    CockpitActionAudit,
    CockpitIssue,
    CockpitSourceStatus,
)

logger = logging.getLogger(__name__)


class CockpitIssueFusionService:
    """Fetch raw issue rows from three sources and fuse them into a ranked feed.

    Tabular shaping (normalisation, deduplication, ranking, source-status
    computation, audit-trail assembly) is delegated entirely to
    ``CockpitTableProcessor`` in ``app/processing/cockpit_table.py``.
    """

    def __init__(
        self,
        alert_repo: AlertRepository | None = None,
        email_repo: EmailIntakeRepository | None = None,
        work_order_repo: WorkOrderRepository | None = None,
        audit_repo: AuditRepository | None = None,
    ):
        self.alert_repo = alert_repo or get_alert_repository()
        self.email_repo = email_repo or get_email_intake_repository()
        self.work_order_repo = work_order_repo or get_work_order_repository()
        self.audit_repo = audit_repo or AuditRepository()

    def aggregate(
        self,
        site_id: str,
        selected_issue_id: str | None = None,
        *,
        alert_entries: list[dict[str, Any]] | None = None,
        intake_entries: list[dict[str, Any]] | None = None,
        work_order_entries: list[dict[str, Any]] | None = None,
        recommendation_entries: list[dict[str, Any]] | None = None,
        audit_entries: list[dict[str, Any]] | None = None,
        local_audit_entries: list[dict[str, Any]] | None = None,
    ) -> tuple[list[CockpitIssue], list[CockpitIssue], list[CockpitSourceStatus], list[CockpitActionAudit], str | None]:
        """Fetch + fuse issue rows into a ranked, deduplicated feed.

        Includes AI recommendations as a source for cockpit intelligence.
        Callers may pass pre-fetched entries via the keyword arguments to
        bypass the repository calls (useful for testing or server-side caching).
        """
        alerts = alert_entries if alert_entries is not None else self._fetch_alerts(site_id)
        intakes = intake_entries if intake_entries is not None else self._fetch_intakes(site_id)
        work_orders = work_order_entries if work_order_entries is not None else self._fetch_work_orders(site_id)
        recommendations = (
            recommendation_entries if recommendation_entries is not None else self._fetch_recommendations(site_id)
        )
        audit_logs = audit_entries if audit_entries is not None else self._fetch_audit_logs(site_id)
        if local_audit_entries:
            audit_logs = local_audit_entries + audit_logs

        onboarding_phase = self._fetch_onboarding_phase(site_id)
        zone_count = self._fetch_zone_count(site_id)
        co2_condition = self._fetch_co2_condition(site_id)
        bridge_last_updated = self._fetch_bridge_last_updated(site_id)
        return CockpitTableProcessor.fuse(
            alerts,
            intakes,
            work_orders,
            audit_logs,
            selected_issue_id,
            bridge_last_updated=bridge_last_updated,
            recommendations=recommendations,
            onboarding_phase=onboarding_phase,
            zone_count=zone_count,
            co2_condition=co2_condition,
        )

    # ------------------------------------------------------------------
    # Fetch helpers (repository / JSON fallback only — no shaping here)
    # ------------------------------------------------------------------

    def _fetch_alerts(self, site_id: str) -> list[dict[str, Any]]:
        try:
            return self.alert_repo.get_active_by_site(site_id)
        except Exception:
            return []

    def _fetch_intakes(self, site_id: str) -> list[dict[str, Any]]:
        try:
            client = self.email_repo.client
            if client:
                response = (
                    client.table("email_intakes")
                    .select("*")
                    .eq("site_id", site_id)
                    .in_("pipeline_status", ["received", "enriched"])
                    .order("created_at", desc=True)
                    .limit(10)
                    .execute()
                )
                return response.data or []
        except Exception:
            pass
        return self._filter_json_intakes(site_id)

    def _fetch_work_orders(self, site_id: str) -> list[dict[str, Any]]:
        try:
            client = self.work_order_repo.client
            if client:
                response = (
                    client.table("work_orders")
                    .select("*")
                    .eq("site_id", site_id)
                    .in_("status", ["new", "in_progress"])
                    .order("updated_at", desc=True)
                    .limit(10)
                    .execute()
                )
                return response.data or []
        except Exception:
            pass
        return []

    def _fetch_recommendations(self, site_id: str) -> list[dict[str, Any]]:
        """Fetch active AI recommendations for the site."""
        try:
            repo = get_recommendation_repository()
            one_day_ago = (datetime.now(UTC) - timedelta(hours=24)).isoformat()
            rows = (
                repo.client.table("recommendations")
                .select("*")
                .eq("site_id", site_id)
                .neq("status", "expired")
                .gte("timestamp", one_day_ago)
                .order("timestamp", desc=True)
                .limit(20)
                .execute()
            )
            return rows.data or []
        except Exception as e:
            logger.warning("[COCKPIT] Failed to fetch AI recommendations: %s", e)
            return []

    def _fetch_audit_logs(self, site_id: str) -> list[dict[str, Any]]:
        try:
            entries = self.audit_repo.get_all(limit=10, offset=0)
            return [entry for entry in entries if entry.get("metadata", {}).get("site_id") == site_id]
        except Exception:
            return []

    def _filter_json_intakes(self, site_id: str) -> list[dict[str, Any]]:
        try:
            with open(self.email_repo._json_path()) as f:
                records = json.load(f)
        except Exception:
            return []
        cutoff = datetime.now(UTC) - timedelta(hours=24)
        return [
            record
            for record in records
            if record.get("site_id") == site_id
            and datetime.fromisoformat(record.get("received_at")).replace(tzinfo=UTC) >= cutoff
        ]

    def _fetch_zone_count(self, site_id: str) -> int:
        """Return the number of zones for the site; 0 on any error."""
        try:
            client = self.alert_repo.client
            if not client:
                return 0
            site_uuid = self.alert_repo._resolve_site_uuid(site_id)
            rows = client.table("zones").select("id", count="exact").eq("site_id", site_uuid).execute()
            return rows.count or 0
        except Exception:
            return 0

    def _fetch_co2_condition(self, site_id: str) -> dict[str, Any] | None:
        """Return current fresh CO2 condition by zone for cockpit snapshot wording."""
        try:
            client = self.alert_repo.client
            if not client:
                return None

            threshold_ppm = 800.0
            fresh_after = (datetime.now(UTC) - timedelta(minutes=30)).isoformat()
            site_prefix = site_id.upper().replace("SITE-", "S")
            rows = (
                client.table("equipment_sensor_readings")
                .select("equipment_id, value, recorded_at")
                .eq("site_id", site_id)
                .eq("sensor_type", "co2_ppm")
                .like("equipment_id", f"{site_prefix}-ZONE-%")
                .gte("recorded_at", fresh_after)
                .order("recorded_at", desc=True)
                .limit(500)
                .execute()
            )

            latest_by_zone: dict[str, dict[str, Any]] = {}
            for row in rows.data or []:
                equipment_id = row.get("equipment_id")
                if not equipment_id or equipment_id in latest_by_zone:
                    continue
                latest_by_zone[equipment_id] = row

            elevated_zone_ids: list[str] = []
            for equipment_id, row in latest_by_zone.items():
                try:
                    value = float(row.get("value"))  # type: ignore[arg-type]  # None/non-numeric caught below
                except (TypeError, ValueError):
                    continue
                if value >= threshold_ppm:
                    elevated_zone_ids.append(equipment_id.replace(f"{site_prefix}-", ""))

            return {
                "fresh_zone_count": len(latest_by_zone),
                "elevated_zone_ids": sorted(elevated_zone_ids),
                "threshold_ppm": threshold_ppm,
            }
        except Exception:
            return None

    def _fetch_onboarding_phase(self, site_id: str) -> str:
        """Return the site's onboarding_phase; defaults to 'supervised' on any error."""
        try:
            client = self.alert_repo.client
            if not client:
                return "supervised"
            row = client.table("sites").select("onboarding_phase").eq("code", site_id).maybe_single().execute()
            return (row.data or {}).get("onboarding_phase") or "supervised"
        except Exception:
            return "supervised"

    def _fetch_bridge_last_updated(self, site_id: str) -> datetime | None:
        if not settings.simbiot_api_url:
            return None
        if not settings.simbiot_api_key and not (settings.simbiot_username and settings.simbiot_password):
            return None

        base = settings.simbiot_api_url.rstrip("/")
        url = f"{base}/api/sites/{site_id}/health"
        headers: dict[str, str] = {}
        if settings.simbiot_api_key:
            headers["Authorization"] = f"Bearer {settings.simbiot_api_key}"
            headers["X-API-Key"] = settings.simbiot_api_key

        auth = None
        if settings.simbiot_username and settings.simbiot_password:
            auth = (settings.simbiot_username, settings.simbiot_password)

        try:
            with httpx.Client(timeout=2.5) as client:
                response = client.get(url, headers=headers, auth=auth)
                response.raise_for_status()
                payload = response.json()
        except Exception:
            return None

        last_ts = payload.get("last_telemetry_at") or payload.get("checked_at")
        if not last_ts:
            return None
        try:
            parsed = datetime.fromisoformat(last_ts.replace("Z", "+00:00"))
            return parsed if parsed.tzinfo else parsed.replace(tzinfo=UTC)
        except Exception:
            return None
