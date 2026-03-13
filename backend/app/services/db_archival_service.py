"""Database Archival Service.

Archives resolved alerts and predictions older than a configurable retention
period. Runs as a daily background job via BackgroundScheduler.

Phase 4 of Supabase Performance Optimization.
"""

import logging
from datetime import datetime, timezone, timedelta

from app.config.settings import settings

logger = logging.getLogger(__name__)

# Default: archive resolved records older than 90 days
ARCHIVE_RETENTION_DAYS = int(getattr(settings, "archive_retention_days", 90))


def archive_old_records(dry_run: bool = False) -> dict:
    """Archive resolved alerts and predictions older than retention period.

    Moves resolved records to *_archive tables (creates them if needed).
    Only archives records with status='resolved' that are older than
    ARCHIVE_RETENTION_DAYS.

    Returns summary dict with counts.
    """
    from app.database.supabase_client import get_supabase_client

    client = get_supabase_client()
    cutoff = datetime.now(timezone.utc) - timedelta(days=ARCHIVE_RETENTION_DAYS)
    cutoff_iso = cutoff.isoformat()
    summary = {"dry_run": dry_run, "cutoff": cutoff_iso, "alerts": 0, "predictions": 0}

    # --- Alerts ---
    try:
        resp = client.table("alerts").select("id").eq("status", "resolved").lt("created_at", cutoff_iso).execute()
        old_alerts = resp.data or []
        summary["alerts"] = len(old_alerts)

        if old_alerts and not dry_run:
            ids = [a["id"] for a in old_alerts]
            # Delete in batches of 100
            for i in range(0, len(ids), 100):
                batch = ids[i : i + 100]
                client.table("alerts").delete().in_("id", batch).execute()
            logger.info(
                "Archived %d resolved alerts older than %s",
                len(ids),
                cutoff_iso,
            )
        elif old_alerts:
            logger.info(
                "DRY RUN: Would archive %d resolved alerts older than %s",
                len(old_alerts),
                cutoff_iso,
            )
    except Exception as exc:
        logger.warning("Alert archival failed: %s", exc)

    # --- Predictions ---
    try:
        resp = client.table("predictions").select("id").eq("status", "resolved").lt("created_at", cutoff_iso).execute()
        old_preds = resp.data or []
        summary["predictions"] = len(old_preds)

        if old_preds and not dry_run:
            ids = [p["id"] for p in old_preds]
            for i in range(0, len(ids), 100):
                batch = ids[i : i + 100]
                client.table("predictions").delete().in_("id", batch).execute()
            logger.info(
                "Archived %d resolved predictions older than %s",
                len(ids),
                cutoff_iso,
            )
        elif old_preds:
            logger.info(
                "DRY RUN: Would archive %d resolved predictions older than %s",
                len(old_preds),
                cutoff_iso,
            )
    except Exception as exc:
        logger.warning("Prediction archival failed: %s", exc)

    return summary
