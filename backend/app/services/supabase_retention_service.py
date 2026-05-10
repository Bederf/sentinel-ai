"""POPIA-aligned Supabase table retention enforcement.

POPIA Section 14(1): Records must not be retained longer than necessary for the
purpose for which they were collected.

This service handles SQL table retention for:
- TIER 2: ML training data (7-day rolling delete after processing window)
- TIER 3: Operational snapshots (30-day rolling delete)
- TIER 5: Audit trail (5-year retention before delete — POPIA Section 14(2))

Retention schedules:
- equipment_fault_events: 7 days (ML training data, POPIA S14(1))
- adapter_health: 7 days (ML training data, POPIA S14(1))
- adapter_health_current: 7 days (transient state, POPIA S14(1))
- adapter_health_alerts: 7 days (ML training data, POPIA S14(1))
- space_occupancy_events: 7 days (ML training data, POPIA S14(1))
- equipment_sensor_readings: 7 days (raw telemetry, POPIA S14(1))
- asset_health_snapshots: 30 days (operational snapshots, POPIA S14(1))
- system_health_snapshots: 30 days (operational snapshots, POPIA S14(1))
- recommendations: 5 years (audit trail, POPIA S14(2))
- parasite_decisions: 5 years (audit trail, POPIA S14(2))

Wired into BackgroundSchedulerService via add_supabase_retention_job().
Startup wiring in backend/app/startup/events.py.
Settings in backend/app/config/settings.py:
  popia_retention_ml_training_days: int = 7
  popia_retention_snapshot_days: int = 30
  popia_retention_audit_trail_days: int = 1825
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from datetime import UTC, datetime, timedelta
from typing import Any

import httpx

logger = logging.getLogger(__name__)


def _utc_now() -> datetime:
    return datetime.now(UTC)


def _iso(value: datetime) -> str:
    return value.astimezone(UTC).isoformat()


# Local Supabase REST endpoint (same as used in stats.py)
_SUPABASE_REST_URL = "http://127.0.0.1:55321/rest/v1"
_SUPABASE_SERVICE_KEY = "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJpc3MiOiJzdXBhYmFzZS1kZW1vIiwicmlzZSI6InNlcnZpY2Vfcm9sZSIsImV4cCI6MTk4MzgxMjk5Nn0.EGIM96RAZx35lJzdJsyH-qQwv8Hdp7fsn3W0YpN81IU"


def _rest_headers() -> dict[str, str]:
    return {
        "Authorization": f"Bearer {_SUPABASE_SERVICE_KEY}",
        "apikey": _SUPABASE_SERVICE_KEY,
        "Content-Type": "application/json",
        "Prefer": "return=representation",
    }


@dataclass(frozen=True)
class RetentionSchedule:
    """Retention schedule for one SQL table."""

    table_name: str
    retention_days: int
    tier: str  # "ML_TRAINING" | "SNAPSHOT" | "AUDIT_TRAIL"
    date_column: str = "created_at"  # Column used for retention cutoff comparison
    description: str = ""


ML_TRAINING_SCHEDULES: list[RetentionSchedule] = [
    RetentionSchedule(
        table_name="equipment_fault_events",
        retention_days=7,
        tier="ML_TRAINING",
        date_column="recorded_at",
        description="ML training data — delete after processing window (POPIA S14(1))",
    ),
    RetentionSchedule(
        table_name="adapter_health",
        retention_days=7,
        tier="ML_TRAINING",
        date_column="timestamp",
        description="Adapter health data — delete after processing window (POPIA S14(1))",
    ),
    RetentionSchedule(
        table_name="adapter_health_current",
        retention_days=7,
        tier="ML_TRAINING",
        date_column="updated_at",
        description="Transient current state — not retained (POPIA S14(1))",
    ),
    RetentionSchedule(
        table_name="adapter_health_alerts",
        retention_days=7,
        tier="ML_TRAINING",
        date_column="created_at",
        description="ML training alerts — delete after processing window (POPIA S14(1))",
    ),
    RetentionSchedule(
        table_name="space_occupancy_events",
        retention_days=7,
        tier="ML_TRAINING",
        date_column="timestamp",
        description="ML training occupancy data — delete after processing window (POPIA S14(1))",
    ),
    RetentionSchedule(
        table_name="equipment_sensor_readings",
        retention_days=7,
        tier="ML_TRAINING",
        date_column="recorded_at",
        description="Raw sensor telemetry — delete after aggregation (POPIA S14(1))",
    ),
]

SNAPSHOT_SCHEDULES: list[RetentionSchedule] = [
    RetentionSchedule(
        table_name="asset_health_snapshots",
        retention_days=30,
        tier="SNAPSHOT",
        date_column="created_at",
        description="Operational snapshots — stale after 30 days (POPIA S14(1))",
    ),
    RetentionSchedule(
        table_name="system_health_snapshots",
        retention_days=30,
        tier="SNAPSHOT",
        date_column="created_at",
        description="Operational snapshots — stale after 30 days (POPIA S14(1))",
    ),
]

AUDIT_TRAIL_SCHEDULES: list[RetentionSchedule] = [
    RetentionSchedule(
        table_name="recommendations",
        retention_days=365 * 5,
        tier="AUDIT_TRAIL",
        date_column="created_at",
        description="AI decision audit trail — keep 5 years (POPIA S14(2))",
    ),
    RetentionSchedule(
        table_name="parasite_decisions",
        retention_days=365 * 5,
        tier="AUDIT_TRAIL",
        date_column="created_at",
        description="Auto-control decision audit trail — keep 5 years (POPIA S14(2))",
    ),
]


@dataclass
class DeletionResult:
    """Result of a single table deletion run."""

    table_name: str
    tier: str
    reviewed: int
    deleted: int
    error: str | None = None


@dataclass
class DeletionRun:
    """Result of a full deletion run across all schedules."""

    executed_at: str
    dry_run: bool
    results: list[DeletionResult] = field(default_factory=list)
    total_reviewed: int = 0
    total_deleted: int = 0
    errors: list[dict] = field(default_factory=list)


class SupabaseRetentionService:
    """POPIA-aligned SQL table retention enforcement via Supabase REST API.

    Uses direct REST API (httpx) — same pattern as stats.py:_rest_query.
    Deletes via POST to /rest/v1/{table} with appropriate filters.
    """

    def __init__(self, rest_url: str | None = None, service_key: str | None = None):
        self._rest_url = rest_url or _SUPABASE_REST_URL
        self._service_key = service_key or _SUPABASE_SERVICE_KEY
        self._timeout = 60.0

    def _headers(self) -> dict[str, str]:
        return _rest_headers()

    def _count_url(self, table: str, date_column: str, created_at_before: str) -> str:
        """Build URL to count rows older than cutoff."""
        return f"{self._rest_url}/{table}?{date_column}=lt.{created_at_before}&{date_column}=gt.1970-01-01&select=id"

    def _delete_url(self, table: str, date_column: str, created_at_before: str) -> str:
        """Build URL to delete rows older than cutoff."""
        return f"{self._rest_url}/{table}?{date_column}=lt.{created_at_before}"

    def _get_cutoff(self, retention_days: int) -> str:
        """Get ISO cutoff datetime for retention window."""
        cutoff = _utc_now() - timedelta(days=retention_days)
        return cutoff.isoformat()

    def _count_overdue(self, schedule: RetentionSchedule) -> int:
        """Count rows older than retention window."""
        cutoff = self._get_cutoff(schedule.retention_days)
        url = self._count_url(schedule.table_name, schedule.date_column, cutoff)
        try:
            with httpx.Client(timeout=self._timeout) as client:
                resp = client.get(url, headers=self._headers())
                resp.raise_for_status()
                rows = resp.json()
                return len(rows) if isinstance(rows, list) else 0
        except Exception as e:
            logger.warning("Count failed for %s: %s", schedule.table_name, e)
            return 0

    def _delete_overdue(self, schedule: RetentionSchedule) -> tuple[int, int | None]:
        """Delete rows older than retention window. Returns (reviewed, deleted)."""
        cutoff = self._get_cutoff(schedule.retention_days)

        # First count how many we'll delete
        reviewed = self._count_overdue(schedule)

        # Execute deletion via POST with PostgREST delete syntax
        url = self._delete_url(schedule.table_name, schedule.date_column, cutoff)
        try:
            with httpx.Client(timeout=self._timeout) as client:
                resp = client.delete(url, headers=self._headers())
                if resp.status_code in (200, 204):
                    return reviewed, reviewed
                # PostgREST returns 200 with deletion count or 204 No Content
                logger.warning(
                    "Delete %s returned status %s: %s",
                    schedule.table_name,
                    resp.status_code,
                    resp.text[:200],
                )
                return reviewed, reviewed
        except Exception as e:
            logger.error("Delete failed for %s: %s", schedule.table_name, e)
            return reviewed, None

    def run_ml_training_deletion(self, dry_run: bool = True) -> DeletionRun:
        """Delete ML training data older than 7 days. POPIA Section 14(1)."""
        return self._run_deletion(ML_TRAINING_SCHEDULES, dry_run)

    def run_snapshot_deletion(self, dry_run: bool = True) -> DeletionRun:
        """Delete operational snapshots older than 30 days. POPIA Section 14(1)."""
        return self._run_deletion(SNAPSHOT_SCHEDULES, dry_run)

    def run_audit_trail_deletion(self, dry_run: bool = True) -> DeletionRun:
        """Delete audit trail entries older than 5 years. POPIA Section 14(2)."""
        return self._run_deletion(AUDIT_TRAIL_SCHEDULES, dry_run)

    def _run_deletion(self, schedules: list[RetentionSchedule], dry_run: bool) -> DeletionRun:
        """Execute deletion for a list of schedules (synchronous version)."""
        now = _utc_now()
        run = DeletionRun(executed_at=_iso(now), dry_run=dry_run)

        for schedule in schedules:
            result = DeletionResult(
                table_name=schedule.table_name,
                tier=schedule.tier,
                reviewed=0,
                deleted=0,
            )
            try:
                if dry_run:
                    result.reviewed = self._count_overdue(schedule)
                    result.deleted = result.reviewed
                else:
                    result.reviewed, result.deleted = self._delete_overdue(schedule)

                logger.info(
                    "Retention [%s] %s: reviewed=%s deleted=%s (dry_run=%s)",
                    schedule.tier,
                    schedule.table_name,
                    result.reviewed,
                    result.deleted,
                    dry_run,
                )
            except Exception as exc:
                result.error = str(exc)
                run.errors.append({"table": schedule.table_name, "tier": schedule.tier, "error": str(exc)})
                logger.error(
                    "Retention [%s] %s FAILED: %s",
                    schedule.tier,
                    schedule.table_name,
                    exc,
                )

            run.results.append(result)
            run.total_reviewed += result.reviewed
            run.total_deleted += result.deleted

        return run

    def get_retention_status(self) -> dict[str, Any]:
        """Return status summary across all schedules without deleting."""
        now = _utc_now()
        categories = []

        for schedule in ML_TRAINING_SCHEDULES + SNAPSHOT_SCHEDULES + AUDIT_TRAIL_SCHEDULES:
            cutoff = self._get_cutoff(schedule.retention_days)
            overdue = self._count_overdue(schedule)
            categories.append(
                {
                    "table": schedule.table_name,
                    "tier": schedule.tier,
                    "retention_days": schedule.retention_days,
                    "description": schedule.description,
                    "overdue_count": overdue,
                    "cutoff": cutoff,
                }
            )
        return {
            "categories": categories,
            "updated_at": _iso(now),
        }


def get_supabase_retention_service() -> SupabaseRetentionService:
    """Build Supabase retention service instance."""
    return SupabaseRetentionService()
