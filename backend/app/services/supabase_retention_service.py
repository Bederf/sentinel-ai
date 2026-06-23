"""POPIA-aligned Supabase table retention enforcement via direct psycopg2.

POPIA Section 14(1): Records must not be retained longer than necessary for the
purpose for which they were collected.

Uses direct PostgreSQL connections (not Supabase REST API) — avoids dependency
on SUPABASE_SERVICE_ROLE_KEY being set for admin-write operations.

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
- equipment_sensor_readings: 10 days (raw telemetry operational window)
- drift_detection_log: 10 days (ML drift monitoring — aggregated, not per-reading needed)
- alerts: active until cleared, then 7 days (raw fault events — noise, not decisions, POPIA S14(1))
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
import os
from typing import Any

from app.config.settings import settings

logger = logging.getLogger(__name__)
RAW_ALERT_RETENTION_DAYS = 7


def _utc_now() -> datetime:
    return datetime.now(UTC)


def _iso(value: datetime) -> str:
    return value.astimezone(UTC).isoformat()


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
        retention_days=10,
        tier="ML_TRAINING",
        date_column="recorded_at",
        description="Raw sensor telemetry — delete after 10-day operational window (aggregated in telemetry_hourly)",
    ),
    RetentionSchedule(
        table_name="drift_detection_log",
        retention_days=10,
        tier="ML_TRAINING",
        date_column="recorded_at",
        description="ML drift monitoring — delete after 10-day window (aggregated signals preserved elsewhere)",
    ),
]

SNAPSHOT_SCHEDULES: list[RetentionSchedule] = [
    RetentionSchedule(
        table_name="asset_health_snapshots",
        retention_days=30,
        tier="SNAPSHOT",
        date_column="snapshot_at",
        description="Operational snapshots — stale after 30 days (POPIA S14(1))",
    ),
    RetentionSchedule(
        table_name="system_health_snapshots",
        retention_days=30,
        tier="SNAPSHOT",
        date_column="timestamp",
        description="Operational snapshots — stale after 30 days (POPIA S14(1))",
    ),
    RetentionSchedule(
        table_name="telemetry_hourly",
        retention_days=365 * 3,
        tier="SNAPSHOT",
        date_column="hour_bucket",
        description="Hourly telemetry aggregates — delete after 3 years (FSR/SANS 204)",
    ),
    RetentionSchedule(
        table_name="telemetry_daily",
        retention_days=365 * 10,
        tier="SNAPSHOT",
        date_column="day_bucket",
        description="Daily telemetry aggregates — delete after 10 years (capex/compliance)",
    ),
]

AUDIT_TRAIL_SCHEDULES: list[RetentionSchedule] = [
    RetentionSchedule(
        table_name="recommendations",
        retention_days=365 * 5,
        tier="AUDIT_TRAIL",
        date_column="timestamp",
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
    """POPIA-aligned SQL table retention enforcement via direct psycopg2.

    Uses direct PostgreSQL connections (psycopg2) — avoids dependency on
    Supabase REST API auth for admin-write operations.
    """

    def __init__(self, database_url: str | None = None):
        self._db_url = database_url or os.environ.get("DATABASE_URL_DIRECT") or settings.database_url

    def _db_connect(self):
        """Create a psycopg2 connection from settings database_url."""
        import psycopg2

        return psycopg2.connect(self._db_url)

    def _count_overdue(self, schedule: RetentionSchedule) -> int:
        """Count rows older than retention window via direct SQL."""
        cutoff = _utc_now() - timedelta(days=schedule.retention_days)
        try:
            conn = self._db_connect()
            try:
                with conn.cursor() as cursor:
                    cursor.execute(
                        f"SELECT count(*) FROM {schedule.table_name} WHERE {schedule.date_column} < %s",
                        (cutoff,),
                    )
                    row = cursor.fetchone()
                    return int(row[0]) if row else 0
            finally:
                conn.close()
        except Exception as e:
            logger.warning("Count failed for %s: %s", schedule.table_name, e)
            return 0

    def _delete_overdue(self, schedule: RetentionSchedule) -> tuple[int, int | None]:
        """Delete rows older than retention window via direct SQL. Returns (reviewed, deleted)."""
        cutoff = _utc_now() - timedelta(days=schedule.retention_days)
        try:
            conn = self._db_connect()
            try:
                with conn.cursor() as cursor:
                    cursor.execute(
                        f"SELECT count(*) FROM {schedule.table_name} WHERE {schedule.date_column} < %s",
                        (cutoff,),
                    )
                    reviewed = int(cursor.fetchone()[0] or 0)

                    cursor.execute(
                        f"DELETE FROM {schedule.table_name} WHERE {schedule.date_column} < %s",
                        (cutoff,),
                    )
                    deleted = cursor.rowcount
                    conn.commit()
                return reviewed, deleted
            finally:
                conn.close()
        except Exception as e:
            logger.error("Delete failed for %s: %s", schedule.table_name, e)
            return 0, None

    def _write_enforcement_log(self, run: DeletionRun) -> None:
        """Write per-table enforcement audit records to retention_enforcement_log."""
        for result in run.results:
            try:
                conn = self._db_connect()
                try:
                    with conn.cursor() as cursor:
                        cursor.execute(
                            """INSERT INTO retention_enforcement_log
                               (executed_at, dry_run, tier, table_name, date_column, reviewed, deleted, errors)
                               VALUES (%s, %s, %s, %s, %s, %s, %s, %s)""",
                            (
                                run.executed_at,
                                run.dry_run,
                                result.tier,
                                result.table_name,
                                "created_at",
                                result.reviewed,
                                result.deleted if not run.dry_run else 0,
                                [{"error": result.error}] if result.error else None,
                            ),
                        )
                        conn.commit()
                finally:
                    conn.close()
            except Exception as exc:
                logger.warning("Failed to write retention enforcement log for %s: %s", result.table_name, exc)

    def run_ml_training_deletion(self, dry_run: bool = True) -> DeletionRun:
        """Delete ML training data older than its processing window. POPIA Section 14(1)."""
        run = self._run_deletion(ML_TRAINING_SCHEDULES, dry_run)
        alert_run = self.run_raw_alert_deletion(dry_run=dry_run)
        run.results.extend(alert_run.results)
        run.total_reviewed += alert_run.total_reviewed
        run.total_deleted += alert_run.total_deleted
        run.errors.extend(alert_run.errors)
        if not dry_run:
            self._write_enforcement_log(run)
        return run

    def run_raw_alert_deletion(self, dry_run: bool = True) -> DeletionRun:
        """Delete resolved raw alert rows 7 days after clear; never age-delete active alerts."""
        now = _utc_now()
        cutoff = now - timedelta(days=RAW_ALERT_RETENTION_DAYS)
        run = DeletionRun(executed_at=_iso(now), dry_run=dry_run)
        result = DeletionResult(
            table_name="alerts",
            tier="ML_TRAINING",
            reviewed=0,
            deleted=0,
        )
        query = """
            FROM alerts
            WHERE status = 'resolved'
              AND COALESCE(resolved_at, updated_at, created_at) < %s
        """
        try:
            conn = self._db_connect()
            try:
                with conn.cursor() as cursor:
                    cursor.execute(f"SELECT count(*) {query}", (cutoff,))
                    result.reviewed = int(cursor.fetchone()[0] or 0)
                    if not dry_run:
                        cursor.execute(f"DELETE {query}", (cutoff,))
                        result.deleted = cursor.rowcount
                        conn.commit()
                    else:
                        result.deleted = result.reviewed
            finally:
                conn.close()
            logger.info(
                "Retention [ML_TRAINING] alerts: reviewed=%s deleted=%s dry_run=%s cutoff=%s",
                result.reviewed,
                result.deleted,
                dry_run,
                cutoff.isoformat(),
            )
        except Exception as exc:
            result.error = str(exc)
            run.errors.append({"table": "alerts", "tier": "ML_TRAINING", "error": str(exc)})
            logger.error("Retention [ML_TRAINING] alerts FAILED: %s", exc)

        run.results.append(result)
        run.total_reviewed += result.reviewed
        run.total_deleted += result.deleted
        return run

    def run_snapshot_deletion(self, dry_run: bool = True) -> DeletionRun:
        """Delete operational snapshots older than 30 days. POPIA Section 14(1)."""
        run = self._run_deletion(SNAPSHOT_SCHEDULES, dry_run)
        if not dry_run:
            self._write_enforcement_log(run)
        return run

    def run_audit_trail_deletion(self, dry_run: bool = True) -> DeletionRun:
        """Delete audit trail entries older than 5 years. POPIA Section 14(2)."""
        run = self._run_deletion(AUDIT_TRAIL_SCHEDULES, dry_run)
        if not dry_run:
            self._write_enforcement_log(run)
        return run

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

        raw_alert_cutoff = (now - timedelta(days=RAW_ALERT_RETENTION_DAYS)).isoformat()
        categories.append(
            {
                "table": "alerts",
                "tier": "ML_TRAINING",
                "retention_days": RAW_ALERT_RETENTION_DAYS,
                "description": "Raw fault events — keep active rows, delete resolved rows 7 days after clear",
                "overdue_count": self.run_raw_alert_deletion(dry_run=True).total_reviewed,
                "cutoff": raw_alert_cutoff,
            }
        )

        for schedule in ML_TRAINING_SCHEDULES + SNAPSHOT_SCHEDULES + AUDIT_TRAIL_SCHEDULES:
            cutoff = (now - timedelta(days=schedule.retention_days)).isoformat()
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
