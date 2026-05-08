"""Repository for integration/log source operations."""

import logging
from datetime import datetime, timedelta
from typing import Any

from app.database.supabase_client import get_supabase_client

logger = logging.getLogger(__name__)


class IntegrationRepository:
    """Repository for integration database operations."""

    def __init__(self):
        self.client = get_supabase_client()

    # ==================== Log Sources ====================

    def get_log_sources(
        self,
        site_id: str | None = None,
        source_type: str | None = None,
        is_active: bool | None = None,
    ) -> list[dict[str, Any]]:
        """Get log sources with optional filtering."""
        query = self.client.table("log_sources").select("*")

        if site_id:
            query = query.eq("site_id", site_id)
        if source_type:
            query = query.eq("source_type", source_type)
        if is_active is not None:
            query = query.eq("is_active", is_active)

        response = query.order("created_at", desc=True).execute()
        return response.data

    def get_log_source(self, source_id: str) -> dict[str, Any] | None:
        """Get log source by ID."""
        response = self.client.table("log_sources").select("*").eq("id", source_id).execute()
        return response.data[0] if response.data else None

    def get_log_source_by_name(self, name: str) -> dict[str, Any] | None:
        """Get a log source by name."""
        response = self.client.table("log_sources").select("*").eq("name", name).execute()
        return response.data[0] if response.data else None

    def get_log_sources_by_ids(self, source_ids: list[str]) -> list[dict[str, Any]]:
        """Get multiple log sources by their IDs."""
        if not source_ids:
            return []
        response = self.client.table("log_sources").select("id,name").in_("id", source_ids).execute()
        return response.data or []

    def create_log_source(self, data: dict[str, Any]) -> dict[str, Any]:
        """Create a new log source."""
        response = self.client.table("log_sources").insert(data).execute()
        return response.data[0]

    def update_log_source(self, source_id: str, data: dict[str, Any]) -> dict[str, Any] | None:
        """Update a log source."""
        response = self.client.table("log_sources").update(data).eq("id", source_id).execute()
        return response.data[0] if response.data else None

    def delete_log_source(self, source_id: str) -> bool:
        """Delete a log source."""
        response = self.client.table("log_sources").delete().eq("id", source_id).execute()
        return len(response.data) > 0

    def update_sync_status(
        self,
        source_id: str,
        status: str,
        records: int = 0,
        error: str | None = None,
    ) -> None:
        """Update last sync status for a log source."""
        self.client.table("log_sources").update(
            {
                "last_sync_at": datetime.utcnow().isoformat(),
                "last_sync_status": status,
                "last_sync_records": records,
                "last_sync_error": error,
            }
        ).eq("id", source_id).execute()

    # ==================== Column Mappings ====================

    def get_column_mappings(self, source_id: str) -> list[dict[str, Any]]:
        """Get column mappings for a log source."""
        response = self.client.table("column_mappings").select("*").eq("log_source_id", source_id).execute()
        return response.data

    def save_column_mappings(
        self,
        source_id: str,
        mappings: list[dict[str, Any]],
    ) -> list[dict[str, Any]]:
        """Save column mappings (replace all for source)."""
        # Delete existing
        self.client.table("column_mappings").delete().eq("log_source_id", source_id).execute()

        # Insert new
        if mappings:
            for m in mappings:
                m["log_source_id"] = source_id
            response = self.client.table("column_mappings").insert(mappings).execute()
            return response.data
        return []

    # ==================== Point-Asset Mappings ====================

    def get_point_mappings(
        self,
        site_id: str,
        confidence: str | None = None,
        verified_only: bool = False,
    ) -> list[dict[str, Any]]:
        """Get point-to-asset mappings for a building."""
        query = self.client.table("point_asset_mappings").select("*").eq("site_id", site_id)

        if confidence:
            query = query.eq("match_confidence", confidence)
        if verified_only:
            query = query.eq("is_verified", True)

        response = query.execute()
        return response.data

    def get_all_point_mappings(
        self,
        site_id: str | None = None,
        confidence: str | None = None,
        verified_only: bool = False,
        limit: int = 100,
        offset: int = 0,
    ) -> dict[str, Any]:
        """Get point-to-asset mappings across all buildings with pagination.

        Returns dict with 'points' list and 'total' count.
        """
        query = self.client.table("point_asset_mappings").select("*", count="exact")

        if site_id:
            query = query.eq("site_id", site_id)
        if confidence:
            query = query.eq("match_confidence", confidence)
        if verified_only:
            query = query.eq("is_verified", True)

        query = query.range(offset, offset + limit - 1)
        response = query.execute()

        return {
            "points": response.data,
            "total": response.count or len(response.data),
        }

    def get_point_mapping(self, site_id: str, point_id: str) -> dict[str, Any] | None:
        """Get mapping for a specific point."""
        response = (
            self.client.table("point_asset_mappings")
            .select("*")
            .eq("site_id", site_id)
            .eq("bms_point_id", point_id)
            .execute()
        )
        return response.data[0] if response.data else None

    def upsert_point_mapping(self, site_id: str, data: dict[str, Any]) -> dict[str, Any]:
        """Create or update point mapping."""
        data["site_id"] = site_id
        response = self.client.table("point_asset_mappings").upsert(data, on_conflict="site_id,bms_point_id").execute()
        return response.data[0]

    def bulk_upsert_point_mappings(
        self,
        site_id: str,
        mappings: list[dict[str, Any]],
    ) -> int:
        """Bulk upsert point mappings."""
        for m in mappings:
            m["site_id"] = site_id

        response = (
            self.client.table("point_asset_mappings").upsert(mappings, on_conflict="site_id,bms_point_id").execute()
        )
        return len(response.data)

    def verify_point_mapping(self, mapping_id: str, cafm_asset_id: str) -> dict[str, Any]:
        """Manually verify/correct a point mapping."""
        response = (
            self.client.table("point_asset_mappings")
            .update(
                {
                    "cafm_asset_id": cafm_asset_id,
                    "match_confidence": "manual",
                    "is_verified": True,
                }
            )
            .eq("id", mapping_id)
            .execute()
        )
        return response.data[0]

    def get_unmatched_points(
        self,
        site_id: str | None = None,
        limit: int = 10,
        offset: int = 0,
    ) -> dict[str, Any]:
        """
        Get unmatched points for the monitoring dashboard.

        Returns points with match_confidence = 'unmatched'.
        """
        try:
            query = (
                self.client.table("point_asset_mappings")
                .select("id,bms_point_id,created_at", count="exact")
                .eq("match_confidence", "unmatched")
            )

            if site_id:
                query = query.eq("site_id", site_id)

            query = query.range(offset, offset + limit - 1).order("created_at", desc=True)
            response = query.execute()

            # Transform to expected format
            points = []
            for p in response.data or []:
                points.append(
                    {
                        "point_id": p.get("id"),
                        "point_name": p.get("bms_point_id"),
                        "last_seen": p.get("created_at"),
                        "occurrence_count": 1,  # Default since we don't track this yet
                    }
                )

            return {
                "points": points,
                "total": response.count or len(points),
            }
        except Exception as e:
            logger.warning(f"get_unmatched_points failed: {e}", exc_info=True)
            return {"points": [], "total": 0}

    # ==================== Ingested Data ====================

    def insert_alarms(self, alarms: list[dict[str, Any]]) -> int:
        """Insert parsed alarms (with deduplication)."""
        if not alarms:
            return 0

        # Upsert to handle duplicates
        response = (
            self.client.table("ingested_alarms").upsert(alarms, on_conflict="log_source_id,source_hash").execute()
        )
        return len(response.data)

    def insert_trends(self, trends: list[dict[str, Any]]) -> int:
        """Insert parsed trends (with deduplication)."""
        if not trends:
            return 0

        response = (
            self.client.table("ingested_trends")
            .upsert(trends, on_conflict="log_source_id,point_id,recorded_at")
            .execute()
        )
        return len(response.data)

    def get_recent_alarms(
        self,
        site_id: str,
        limit: int = 100,
        severity: str | None = None,
    ) -> list[dict[str, Any]]:
        """Get recent alarms for a building."""
        query = self.client.table("ingested_alarms").select("*").eq("site_id", site_id)

        if severity:
            query = query.eq("severity", severity)

        response = query.order("occurred_at", desc=True).limit(limit).execute()
        return response.data

    # ==================== Sync Jobs ====================

    def create_sync_job(self, source_id: str, file_name: str | None = None) -> dict[str, Any]:
        """Create a new sync job record."""
        response = (
            self.client.table("sync_jobs")
            .insert(
                {
                    "log_source_id": source_id,
                    "status": "running",
                    "file_name": file_name,
                }
            )
            .execute()
        )
        return response.data[0]

    def complete_sync_job(
        self,
        job_id: str,
        status: str,
        processed: int,
        inserted: int,
        skipped: int,
        failed: int,
        error_message: str | None = None,
        processing_time_ms: int | None = None,
    ) -> None:
        """Complete a sync job with results."""
        self.client.table("sync_jobs").update(
            {
                "completed_at": datetime.utcnow().isoformat(),
                "status": status,
                "records_processed": processed,
                "records_inserted": inserted,
                "records_skipped": skipped,
                "records_failed": failed,
                "error_message": error_message,
                "processing_time_ms": processing_time_ms,
            }
        ).eq("id", job_id).execute()

    def get_sync_jobs(
        self,
        source_id: str,
        limit: int = 20,
    ) -> list[dict[str, Any]]:
        """Get recent sync jobs for a source."""
        response = (
            self.client.table("sync_jobs")
            .select("*")
            .eq("log_source_id", source_id)
            .order("started_at", desc=True)
            .limit(limit)
            .execute()
        )
        return response.data

    # ==================== CAFM Data ====================

    def upsert_cafm_assets(
        self,
        site_id: str,
        source_id: str,
        assets: list[dict[str, Any]],
    ) -> int:
        """Upsert synced CAFM assets."""
        for a in assets:
            a["site_id"] = site_id
            a["log_source_id"] = source_id
            a["last_synced_at"] = datetime.utcnow().isoformat()

        response = self.client.table("cafm_assets").upsert(assets, on_conflict="site_id,cafm_id").execute()
        return len(response.data)

    def get_cafm_assets(self, site_id: str) -> list[dict[str, Any]]:
        """Get CAFM assets for a building."""
        response = self.client.table("cafm_assets").select("*").eq("site_id", site_id).order("asset_tag").execute()
        return response.data

    # ==================== Reference Data ====================

    def get_alarm_taxonomy(self) -> list[dict[str, Any]]:
        """Get alarm code taxonomy."""
        response = self.client.table("alarm_taxonomy").select("*").execute()
        return response.data

    def get_severity_mappings(self, source_id: str | None = None) -> list[dict[str, Any]]:
        """Get severity mappings (global or per-source)."""
        query = self.client.table("severity_mappings").select("*")
        if source_id:
            import re

            safe_source_id = re.sub(r"[,.()\s]", "", source_id)
            query = query.or_(f"log_source_id.eq.{safe_source_id},log_source_id.is.null")
        else:
            query = query.is_("log_source_id", "null")
        response = query.execute()
        return response.data

    # ==================== Monitoring Aggregations ====================

    def _resolve_site_id(self, site_id: str) -> str:
        """Resolve site code string to UUID for FK column queries.

        The sites table stores codes (e.g. 'site-002') in sites.code,
        but FK columns in log_sources and point_asset_mappings store UUIDs.
        """
        if not site_id:
            return site_id
        # If it looks like a UUID already, skip lookup
        if len(site_id) == 36 and "-" in site_id:
            return site_id
        try:
            response = self.client.table("sites").select("id").eq("code", site_id).execute()
            if response.data:
                return response.data[0]["id"]
        except Exception as e:
            logger.warning(f"_resolve_site_id failed: {e}", exc_info=True)
        return site_id  # Fallback: return as-is and let the query fail gracefully

    def get_integration_health(self, site_id: str | None = None) -> dict[str, Any]:
        """
        Get integration health summary.

        Returns aggregate metrics for monitoring dashboard:
        - sources_count: Total log sources
        - active_sources: Count of active sources
        - last_sync: Most recent sync timestamp
        - total_records_ingested: Sum of all ingested records
        - total_points_mapped: Count of point mappings
        - unmatched_points: Count of unmatched point mappings
        - recent_errors_count: Failed sync jobs in last 24 hours
        """
        resolved_site_id = self._resolve_site_id(site_id) if site_id else None

        try:
            # Get log sources
            sources_query = self.client.table("log_sources").select("*")
            if resolved_site_id:
                sources_query = sources_query.eq("site_id", resolved_site_id)
            sources_response = sources_query.execute()
            sources = sources_response.data or []
        except Exception as e:
            logger.warning(f"get_integration_health failed: {e}", exc_info=True)
            return {
                "sources_count": 0,
                "active_sources": 0,
                "last_sync": None,
                "total_records_ingested": 0,
                "total_points_mapped": 0,
                "unmatched_points": 0,
                "recent_errors_count": 0,
            }

        sources_count = len(sources)
        active_sources = len([s for s in sources if s.get("is_active")])

        # Find most recent sync and sum records
        last_sync = None
        total_records_ingested = 0
        for source in sources:
            sync_at = source.get("last_sync_at")
            if sync_at and (last_sync is None or sync_at > last_sync):
                last_sync = sync_at
            records = source.get("last_sync_records") or 0
            total_records_ingested += records

        # Get point mappings count
        try:
            mappings_query = self.client.table("point_asset_mappings").select("id,match_confidence")
            if resolved_site_id:
                mappings_query = mappings_query.eq("site_id", resolved_site_id)
            mappings_response = mappings_query.execute()
            mappings = mappings_response.data or []
        except Exception as e:
            logger.warning(f"get_integration_health point mappings query failed: {e}", exc_info=True)
            mappings = []

        total_points_mapped = len(mappings)
        unmatched_points = len([m for m in mappings if m.get("match_confidence") == "unmatched"])

        # Get failed sync jobs in last 24 hours
        recent_errors_count = 0
        try:
            cutoff = (datetime.utcnow() - timedelta(hours=24)).isoformat()
            failed_jobs_query = (
                self.client.table("sync_jobs").select("id").eq("status", "failed").gte("started_at", cutoff)
            )
            if site_id:
                # Need to filter by log_source site_id via join or subquery
                # For simplicity, filter sources first then get job IDs
                source_ids = [s["id"] for s in sources]
                failed_jobs_query = failed_jobs_query.in_("log_source_id", source_ids) if source_ids else None

            if failed_jobs_query:
                failed_response = failed_jobs_query.execute()
                recent_errors_count = len(failed_response.data or [])
        except Exception as e:
            logger.warning(f"get_integration_health failed_jobs query failed: {e}", exc_info=True)

        return {
            "sources_count": sources_count,
            "active_sources": active_sources,
            "last_sync": last_sync,
            "total_records_ingested": total_records_ingested,
            "total_points_mapped": total_points_mapped,
            "unmatched_points": unmatched_points,
            "recent_errors_count": recent_errors_count,
        }

    def get_quality_metrics(self, site_id: str) -> dict[str, Any]:
        """
        Get data quality metrics for a building.

        Returns:
        - match_coverage: Percentage of points matched (0-100)
        - data_freshness_hours: Hours since last sync
        - error_rate: Percentage of failed sync jobs in last 7 days (0-100)
        - duplicate_rate: Percentage of skipped records (0-100)
        - overall_score: Weighted quality score (0-100)
        - trend: Quality trend ('improving', 'stable', 'degrading')
        """
        # Default values if tables don't exist
        default_response = {
            "match_coverage": 0,
            "data_freshness_hours": 9999,
            "error_rate": 0,
            "duplicate_rate": 0,
            "overall_score": 30,  # Base score for no data
            "trend": "stable",
        }

        resolved_site_id = self._resolve_site_id(site_id)

        try:
            # Get point mappings for match coverage
            mappings_response = (
                self.client.table("point_asset_mappings")
                .select("id,match_confidence")
                .eq("site_id", resolved_site_id)
                .execute()
            )
            mappings = mappings_response.data or []
        except Exception as e:
            logger.warning(f"get_quality_metrics point mappings query failed: {e}", exc_info=True)
            return default_response

        total_points = len(mappings)
        matched_points = len([m for m in mappings if m.get("match_confidence") != "unmatched"])
        match_coverage = (matched_points / total_points * 100) if total_points > 0 else 0

        # Get data freshness from data_freshness table (populated by data_freshness_monitor
        # every 5 min from log_sources.last_sync_at — the actual bridge sync time).
        try:
            freshness_response = (
                self.client.table("data_freshness")
                .select("age_seconds")
                .eq("site_id", site_id)  # site-002 format — matches data_freshness.site_id
                .execute()
            )
            freshness_rows = freshness_response.data or []
        except Exception as e:
            logger.warning(f"get_quality_metrics data_freshness query failed: {e}", exc_info=True)
            freshness_rows = []

        data_freshness_hours = float("inf")
        for row in freshness_rows:
            age = row.get("age_seconds")
            if age is not None:
                hours = age / 3600.0
                if hours < data_freshness_hours:
                    data_freshness_hours = hours

        if data_freshness_hours == float("inf"):
            data_freshness_hours = 9999  # Never synced

        # Get error rate from sync jobs in last 7 days
        total_jobs = 0
        failed_jobs = 0
        total_processed = 0
        total_skipped = 0

        try:
            cutoff = (datetime.utcnow() - timedelta(days=7)).isoformat()

            # Get source IDs for this building
            source_ids_response = (
                self.client.table("log_sources").select("id").eq("site_id", resolved_site_id).execute()
            )
            source_ids = [s["id"] for s in (source_ids_response.data or [])]

            if source_ids:
                jobs_response = (
                    self.client.table("sync_jobs")
                    .select("status,records_processed,records_skipped")
                    .in_("log_source_id", source_ids)
                    .gte("started_at", cutoff)
                    .execute()
                )
                jobs = jobs_response.data or []

                total_jobs = len(jobs)
                failed_jobs = len([j for j in jobs if j.get("status") == "failed"])
                for job in jobs:
                    total_processed += job.get("records_processed") or 0
                    total_skipped += job.get("records_skipped") or 0
        except Exception as e:
            logger.warning(f"get_quality_metrics sync_jobs query failed: {e}", exc_info=True)

        error_rate = (failed_jobs / total_jobs * 100) if total_jobs > 0 else 0
        duplicate_rate = (total_skipped / total_processed * 100) if total_processed > 0 else 0

        # Calculate freshness score (100 = fresh, 0 = stale)
        # Consider 1 hour as perfect, 24+ hours as 0
        if data_freshness_hours <= 1:
            freshness_score = 100
        elif data_freshness_hours >= 24:
            freshness_score = 0
        else:
            freshness_score = max(0, 100 - (data_freshness_hours - 1) * (100 / 23))

        # Calculate overall score: weighted average
        overall_score = (
            match_coverage * 0.4 + freshness_score * 0.3 + (100 - error_rate) * 0.2 + (100 - duplicate_rate) * 0.1
        )

        # Trend is static for now (would need historical data to calculate)
        trend = "stable"

        return {
            "match_coverage": round(match_coverage, 1),
            "data_freshness_hours": round(data_freshness_hours, 1),
            "error_rate": round(error_rate, 1),
            "duplicate_rate": round(duplicate_rate, 1),
            "overall_score": round(overall_score, 1),
            "trend": trend,
        }

    def get_sync_jobs_summary(
        self,
        site_id: str | None = None,
        days: int = 7,
    ) -> list[dict[str, Any]]:
        """
        Get sync job summary for the last N days.

        Returns list of sync jobs with:
        - log_source_id, status, records_processed, records_inserted,
          records_failed, processing_time_ms, started_at, completed_at
        """
        try:
            cutoff = (datetime.utcnow() - timedelta(days=days)).isoformat()

            # If site_id specified, get source IDs first
            source_ids = None
            if site_id:
                sources_response = self.client.table("log_sources").select("id").eq("site_id", site_id).execute()
                source_ids = [s["id"] for s in (sources_response.data or [])]
                if not source_ids:
                    return []

            query = (
                self.client.table("sync_jobs")
                .select(
                    "id,log_source_id,status,records_processed,records_inserted,"
                    "records_failed,records_skipped,processing_time_ms,started_at,completed_at,file_name"
                )
                .gte("started_at", cutoff)
            )

            if source_ids:
                query = query.in_("log_source_id", source_ids)

            response = query.order("started_at", desc=True).limit(100).execute()
            return response.data or []
        except Exception as e:
            logger.warning(f"get_sync_jobs_summary failed: {e}", exc_info=True)
            return []

    # ==================== Building Status / Go-Live Workflow ====================

    # In-memory storage for building status (MVP - no new migration needed)
    _site_status_store: dict[str, dict[str, Any]] = {}  # noqa: RUF012

    def get_site_status(self, site_id: str) -> dict[str, Any] | None:
        """Get building status record."""
        return self._site_status_store.get(site_id)

    def update_site_status(
        self,
        site_id: str,
        status: str,
        notes: str | None = None,
    ) -> dict[str, Any]:
        """Update building status (upsert)."""
        record = {
            "site_id": site_id,
            "status": status,
            "last_validated_at": datetime.utcnow().isoformat(),
            "notes": notes,
            "updated_at": datetime.utcnow().isoformat(),
        }
        self._site_status_store[site_id] = record
        return record

    def get_validation_checklist(self, site_id: str) -> dict[str, Any]:
        """
        Run all validation checks and return a checklist.

        Returns:
        - items: List of ChecklistItem dicts
        - summary: {passed: int, failed: int, warnings: int}
        - can_activate: bool (True if no 'fail' status)
        - blocking_issues: List of failed check names
        """
        items = []
        blocking_issues = []

        # ==================== Data Source Checks ====================

        # Check 1: data_source_configured
        try:
            sources = self.get_log_sources(site_id=site_id)
        except Exception as e:
            logger.warning(f"get_validation_checklist data_source_configured failed: {e}", exc_info=True)
            sources = []

        has_source = len(sources) > 0
        items.append(
            {
                "id": "data_source_configured",
                "category": "data_source",
                "name": "Data Source Configured",
                "description": "At least one log source exists for the building",
                "status": "pass" if has_source else "fail",
                "value": len(sources),
                "threshold": 1,
                "details": f"{len(sources)} log source(s) configured" if has_source else "No log sources configured",
            }
        )
        if not has_source:
            blocking_issues.append("data_source_configured")

        # Check 2: data_source_active
        active_sources = [s for s in sources if s.get("is_active")]
        has_active = len(active_sources) > 0
        items.append(
            {
                "id": "data_source_active",
                "category": "data_source",
                "name": "Active Data Source",
                "description": "At least one log source is active",
                "status": "pass" if has_active else "fail",
                "value": len(active_sources),
                "threshold": 1,
                "details": f"{len(active_sources)} active source(s)" if has_active else "No active sources",
            }
        )
        if not has_active:
            blocking_issues.append("data_source_active")

        # Check 3: recent_sync
        last_sync = None
        for source in sources:
            sync_at = source.get("last_sync_at")
            if sync_at and (last_sync is None or sync_at > last_sync):
                last_sync = sync_at

        hours_since_sync = float("inf")
        if last_sync:
            try:
                if isinstance(last_sync, str):
                    sync_time = datetime.fromisoformat(last_sync.replace("Z", "+00:00").replace("+00:00", ""))
                else:
                    sync_time = last_sync
                hours_since_sync = (datetime.utcnow() - sync_time).total_seconds() / 3600
            except (ValueError, TypeError):
                pass

        recent_sync = hours_since_sync < 24
        items.append(
            {
                "id": "recent_sync",
                "category": "data_source",
                "name": "Recent Sync",
                "description": "Successful sync within last 24 hours",
                "status": "pass" if recent_sync else ("warning" if hours_since_sync < 48 else "fail"),
                "value": round(hours_since_sync, 1) if hours_since_sync != float("inf") else None,
                "threshold": 24,
                "details": f"Last sync {round(hours_since_sync, 1)} hours ago"
                if hours_since_sync != float("inf")
                else "Never synced",
            }
        )
        if hours_since_sync >= 48:
            blocking_issues.append("recent_sync")

        # ==================== Point Mapping Checks ====================

        try:
            mappings = self.get_point_mappings(site_id)
        except Exception as e:
            logger.warning(f"get_validation_checklist point_mappings check failed: {e}", exc_info=True)
            mappings = []

        total_points = len(mappings)
        matched_points = len([m for m in mappings if m.get("match_confidence") != "unmatched"])
        high_confidence = len([m for m in mappings if m.get("match_confidence") in ["exact", "manual"]])

        # Check 4: points_discovered
        has_points = total_points > 0
        items.append(
            {
                "id": "points_discovered",
                "category": "point_mapping",
                "name": "Points Discovered",
                "description": "Points have been discovered from log files",
                "status": "pass" if has_points else "fail",
                "value": total_points,
                "threshold": 1,
                "details": f"{total_points} points discovered" if has_points else "No points discovered",
            }
        )
        if not has_points:
            blocking_issues.append("points_discovered")

        # Check 5: match_coverage
        match_coverage = (matched_points / total_points * 100) if total_points > 0 else 0
        match_status = "pass" if match_coverage >= 75 else ("warning" if match_coverage >= 50 else "fail")
        items.append(
            {
                "id": "match_coverage",
                "category": "point_mapping",
                "name": "Match Coverage",
                "description": "Match coverage >= 50% (warning if <75%)",
                "status": match_status,
                "value": round(match_coverage, 1),
                "threshold": 50,
                "details": f"{round(match_coverage, 1)}% of points matched to assets",
            }
        )
        if match_coverage < 50:
            blocking_issues.append("match_coverage")

        # Check 6: high_confidence_matches
        high_confidence_pct = (high_confidence / total_points * 100) if total_points > 0 else 0
        items.append(
            {
                "id": "high_confidence_matches",
                "category": "point_mapping",
                "name": "High Confidence Matches",
                "description": "At least 25% of matches are high confidence",
                "status": "pass" if high_confidence_pct >= 25 else "warning",
                "value": round(high_confidence_pct, 1),
                "threshold": 25,
                "details": (
                    f"{round(high_confidence_pct, 1)}% high confidence matches ({high_confidence} of {total_points})"
                ),
            }
        )

        # ==================== Data Quality Checks ====================

        quality_metrics = self.get_quality_metrics(site_id)

        # Check 7: error_rate
        error_rate = quality_metrics.get("error_rate", 0)
        items.append(
            {
                "id": "error_rate",
                "category": "data_quality",
                "name": "Error Rate",
                "description": "Error rate < 10%",
                "status": "pass" if error_rate < 10 else ("warning" if error_rate < 25 else "fail"),
                "value": error_rate,
                "threshold": 10,
                "details": f"{error_rate}% of sync jobs failed",
            }
        )
        if error_rate >= 25:
            blocking_issues.append("error_rate")

        # Check 8: duplicate_rate
        duplicate_rate = quality_metrics.get("duplicate_rate", 0)
        items.append(
            {
                "id": "duplicate_rate",
                "category": "data_quality",
                "name": "Duplicate Rate",
                "description": "Duplicate rate < 20%",
                "status": "pass" if duplicate_rate < 20 else "warning",
                "value": duplicate_rate,
                "threshold": 20,
                "details": f"{duplicate_rate}% of records were duplicates",
            }
        )

        # Check 9: quality_score
        quality_score = quality_metrics.get("overall_score", 0)
        items.append(
            {
                "id": "quality_score",
                "category": "data_quality",
                "name": "Quality Score",
                "description": "Overall quality score >= 60 (warning if <75)",
                "status": "pass" if quality_score >= 75 else ("warning" if quality_score >= 60 else "fail"),
                "value": quality_score,
                "threshold": 60,
                "details": f"Quality score: {quality_score}/100",
            }
        )
        if quality_score < 60:
            blocking_issues.append("quality_score")

        # ==================== Configuration Checks ====================

        # Check 10: column_mappings
        has_mappings = False
        for source in active_sources:
            try:
                col_mappings = self.get_column_mappings(source["id"])
                if col_mappings:
                    has_mappings = True
                    break
            except Exception as e:
                logger.warning(f"get_validation_checklist column_mappings check failed: {e}", exc_info=True)

        items.append(
            {
                "id": "column_mappings",
                "category": "configuration",
                "name": "Column Mappings",
                "description": "Column mappings configured for active sources",
                "status": "pass" if has_mappings else ("fail" if active_sources else "not_checked"),
                "value": 1 if has_mappings else 0,
                "threshold": 1,
                "details": "Column mappings configured" if has_mappings else "No column mappings found",
            }
        )
        if active_sources and not has_mappings:
            blocking_issues.append("column_mappings")

        # Check 11: sync_settings (always pass for MVP since we use defaults)
        items.append(
            {
                "id": "sync_settings",
                "category": "configuration",
                "name": "Sync Settings",
                "description": "Sync frequency and retention configured",
                "status": "pass",
                "value": True,
                "threshold": None,
                "details": "Default sync settings applied",
            }
        )

        # Calculate summary
        passed = len([i for i in items if i["status"] == "pass"])
        failed = len([i for i in items if i["status"] == "fail"])
        warnings = len([i for i in items if i["status"] == "warning"])

        return {
            "items": items,
            "summary": {
                "passed": passed,
                "failed": failed,
                "warnings": warnings,
            },
            "can_activate": failed == 0,
            "blocking_issues": blocking_issues,
        }
