"""Background trust score updater — daily cron job for trust maintenance.

Phase 162: Semantic Control Foundation — Plan 04.
Runs at 02:00 daily to recalculate trust scores for all active points,
keeping the three-layer trust model current as operational data accumulates.
"""

from __future__ import annotations

import asyncio
import logging

from apscheduler.schedulers.background import BackgroundScheduler
from apscheduler.triggers.cron import CronTrigger

logger = logging.getLogger(__name__)


class BackgroundTrustUpdater:
    """Updates trust scores for all active points on a daily schedule."""

    def __init__(self) -> None:
        self.scheduler = BackgroundScheduler()
        self._main_loop: asyncio.AbstractEventLoop | None = None
        # Lazy import to avoid circular dependency at module load time
        self._trust_service = None

    @property
    def trust_service(self):
        if self._trust_service is None:
            from app.services.simbiot.trust_scoring_service import TrustScoringService

            self._trust_service = TrustScoringService()
        return self._trust_service

    def set_main_loop(self, loop: asyncio.AbstractEventLoop) -> None:
        """Store reference to the main event loop for async job dispatch."""
        self._main_loop = loop

    def start(self) -> None:
        """Start the daily trust update job (runs at 02:00)."""
        if not self.scheduler.running:
            self.scheduler.add_job(
                self._dispatch_update,
                trigger=CronTrigger(hour=2, minute=0),
                id="daily_trust_update",
                replace_existing=True,
                misfire_grace_time=3600,  # tolerate up to 1-hour late start
            )
            self.scheduler.start()
            logger.info("BackgroundTrustUpdater started — daily job at 02:00")

    def stop(self) -> None:
        """Stop the scheduler cleanly."""
        if self.scheduler.running:
            self.scheduler.shutdown(wait=False)
            logger.info("BackgroundTrustUpdater stopped")

    # ------------------------------------------------------------------
    # Internal dispatch — bridges sync APScheduler to async coroutine
    # ------------------------------------------------------------------

    def _dispatch_update(self) -> None:
        """Called by APScheduler (sync thread); dispatches async job."""
        if self._main_loop is not None and self._main_loop.is_running():
            asyncio.run_coroutine_threadsafe(self.update_all_trust_scores(), self._main_loop)
        else:
            # Fallback: create a new event loop for standalone execution
            try:
                asyncio.run(self.update_all_trust_scores())
            except Exception as exc:
                logger.error("Trust updater dispatch failed: %s", exc)

    # ------------------------------------------------------------------
    # Async job body
    # ------------------------------------------------------------------

    async def update_all_trust_scores(self) -> dict:
        """Update trust scores for all active classified points.

        Workflow:
        1. Load all trust history records from the repository.
        2. For each record, recalculate the trust score (stability + actions).
        3. Persist the updated score.
        4. Return a summary report of changed records.

        Returns a dict with keys: processed, updated, errors.
        """
        from app.database.repositories.trust_history_repository import (
            TrustHistoryRepository,
        )
        from app.models.trust_history import TrustHistory

        repo = TrustHistoryRepository()
        summary = {"processed": 0, "updated": 0, "errors": 0}

        try:
            # Load all persisted trust records
            records = await self._load_all_trust_records(repo)
            logger.info("Trust updater: processing %d records", len(records))

            for history in records:
                try:
                    old_score = history.trust_score
                    new_score = TrustHistory.calculate_trust_score(
                        history.stability_days,
                        history.validation_runs,
                        history.successful_actions,
                        history.failed_actions,
                    )
                    history.trust_score = new_score
                    await repo.upsert_trust_history(history)
                    summary["processed"] += 1
                    if abs(new_score - old_score) > 0.001:
                        summary["updated"] += 1
                        logger.debug(
                            "Trust score updated for %s: %.3f → %.3f",
                            history.point_id,
                            old_score,
                            new_score,
                        )
                except Exception as exc:
                    logger.warning("Failed to update trust for %s: %s", history.point_id, exc)
                    summary["errors"] += 1

        except Exception as exc:
            logger.error("Trust updater batch failed: %s", exc)
            summary["errors"] += 1

        logger.info(
            "Trust updater complete: processed=%d updated=%d errors=%d",
            summary["processed"],
            summary["updated"],
            summary["errors"],
        )
        return summary

    async def _load_all_trust_records(self, repo) -> list:
        """Load all trust history records from storage.

        Falls back to scanning the JSON fallback directory if Supabase
        is unavailable.
        """
        import json

        from app.database.repositories.trust_history_repository import DATA_DIR
        from app.models.trust_history import TrustHistory

        records: list[TrustHistory] = []

        # Try Supabase first
        if not repo._use_json and repo.client is not None:
            try:
                result = repo.client.table("trust_history").select("*").execute()
                if result.data:
                    return [TrustHistory(**row) for row in result.data]
            except Exception as exc:
                logger.warning("Supabase batch read failed: %s", exc)

        # JSON fallback: scan directory
        if DATA_DIR.exists():
            for path in DATA_DIR.glob("*.json"):
                try:
                    with path.open() as fh:
                        data = json.load(fh)
                    records.append(TrustHistory(**data))
                except Exception as exc:
                    logger.warning("Could not load %s: %s", path, exc)

        return records
