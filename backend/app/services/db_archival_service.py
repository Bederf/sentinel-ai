"""Database Archival Service.

Purges resolved raw alerts after their short troubleshooting window and archives
resolved predictions older than a configurable retention period.
Runs as a daily background job via BackgroundScheduler.

Phase 4 of Supabase Performance Optimization.
"""

import logging
from datetime import UTC, datetime, timedelta

from app.config.settings import settings

logger = logging.getLogger(__name__)

# Raw alerts are source trace data, not long-term business records.
ALERT_RETENTION_DAYS = 7

# Default: archive resolved prediction records older than 90 days
ARCHIVE_RETENTION_DAYS = int(getattr(settings, "archive_retention_days", 90))

# Archive tables are created on first run via _ensure_archive_table()
_ARCHIVE_TABLES_VERIFIED: set = set()


def _ensure_archive_table(client, source_table: str) -> bool:
    """Create the archive table if it doesn't exist (same schema as source)."""
    archive_table = f"{source_table}_archive"
    if archive_table in _ARCHIVE_TABLES_VERIFIED:
        return True

    try:
        # Check if archive table exists by attempting a count query
        client.table(archive_table).select("id", count="exact").limit(0).execute()
        _ARCHIVE_TABLES_VERIFIED.add(archive_table)
        return True
    except Exception:
        # Table doesn't exist — create it via RPC or raw SQL
        try:
            client.rpc(
                "exec_sql",
                {"sql": f"CREATE TABLE IF NOT EXISTS {archive_table} (LIKE {source_table} INCLUDING ALL)"},
            ).execute()
            _ARCHIVE_TABLES_VERIFIED.add(archive_table)
            logger.info("Created archive table: %s", archive_table)
            return True
        except Exception as e:
            # RPC may not exist — fall back to direct delete (no archive)
            logger.warning(
                "Cannot create %s (exec_sql RPC unavailable: %s). Records will be deleted without archival.",
                archive_table,
                e,
            )
            return False


def _archive_and_delete(client, table: str, record_ids: list, batch_size: int = 100) -> tuple:
    """Copy records to archive table, then delete from live table.

    Returns (archived_count, deleted_count).
    """
    archive_table = f"{table}_archive"
    has_archive = _ensure_archive_table(client, table)

    archived = 0
    deleted = 0

    for i in range(0, len(record_ids), batch_size):
        batch = record_ids[i : i + batch_size]

        # Step 1: Copy to archive table (if available)
        if has_archive:
            try:
                # Fetch full records for this batch
                resp = client.table(table).select("*").in_("id", batch).execute()
                rows = resp.data or []
                if rows:
                    # Remove any auto-generated fields that might conflict
                    for row in rows:
                        row.pop("_metadata", None)
                    client.table(archive_table).insert(rows).execute()
                    archived += len(rows)
            except Exception as e:
                logger.warning("Archive copy failed for %s batch %d: %s", table, i, e)
                # Continue to delete even if archive copy fails — retention is more important

        # Step 2: Delete from live table
        try:
            client.table(table).delete().in_("id", batch).execute()
            deleted += len(batch)
        except Exception as e:
            logger.warning("Delete failed for %s batch %d: %s", table, i, e)

    return archived, deleted


def archive_old_records(dry_run: bool = False) -> dict:
    """Purge resolved raw alerts and archive resolved predictions.

    Alerts are not copied into alerts_archive because BACnet object IDs are
    short-lived technical trace data. Predictions keep the existing archive path.

    Returns summary dict with counts.
    """
    from app.database.supabase_client import get_supabase_client

    client = get_supabase_client()
    prediction_cutoff = datetime.now(UTC) - timedelta(days=ARCHIVE_RETENTION_DAYS)
    prediction_cutoff_iso = prediction_cutoff.isoformat()
    alert_cutoff = datetime.now(UTC) - timedelta(days=ALERT_RETENTION_DAYS)
    alert_cutoff_iso = alert_cutoff.isoformat()
    summary = {
        "dry_run": dry_run,
        "cutoff": prediction_cutoff_iso,
        "alert_cutoff": alert_cutoff_iso,
        "alerts_archived": 0,
        "alerts_deleted": 0,
        "predictions_archived": 0,
        "predictions_deleted": 0,
    }

    # --- Alerts ---
    try:
        resp = client.table("alerts").select("id").eq("status", "resolved").lt("updated_at", alert_cutoff_iso).execute()
        old_alerts = resp.data or []

        if old_alerts and not dry_run:
            ids = [a["id"] for a in old_alerts]
            client.table("alerts").delete().in_("id", ids).execute()
            summary["alerts_deleted"] = len(ids)
            logger.info(
                "DB retention: %d resolved raw alerts deleted without archive (older than %s)",
                len(ids),
                alert_cutoff_iso,
            )
        elif old_alerts:
            summary["alerts_deleted"] = len(old_alerts)
            logger.info(
                "DRY RUN: Would delete %d resolved raw alerts older than %s",
                len(old_alerts),
                alert_cutoff_iso,
            )
    except Exception as exc:
        logger.warning("Alert archival failed: %s", exc)

    # --- Predictions ---
    try:
        resp = (
            client.table("predictions")
            .select("id")
            .eq("status", "resolved")
            .lt("created_at", prediction_cutoff_iso)
            .execute()
        )
        old_preds = resp.data or []

        if old_preds and not dry_run:
            ids = [p["id"] for p in old_preds]
            archived, deleted = _archive_and_delete(client, "predictions", ids)
            summary["predictions_archived"] = archived
            summary["predictions_deleted"] = deleted
            logger.info(
                "DB archival: %d predictions archived, %d deleted (older than %s)",
                archived,
                deleted,
                prediction_cutoff_iso,
            )
        elif old_preds:
            summary["predictions_archived"] = len(old_preds)
            logger.info(
                "DRY RUN: Would archive %d resolved predictions older than %s",
                len(old_preds),
                prediction_cutoff_iso,
            )
    except Exception as exc:
        logger.warning("Prediction archival failed: %s", exc)

    return summary
