"""Critical Path Monitor — Tier 3: Critical Path Latency SLI.

Captures wall-clock latency of PARASITE decisions:
  - Approval latency: approved_at - timestamp  (human think time)
  - Execution latency: executed_at - approved_at  (device write + COV verify)
  - Total latency: executed_at - timestamp  (end-to-end)

Hourly APScheduler job aggregates percentiles into critical_path_hourly.
SLO target: p99 < 7000ms for supervised-phase operations.
"""

import logging
from datetime import UTC, datetime, timedelta
from typing import Any

logger = logging.getLogger("critical-path-monitor")

SLO_TARGET_MS = 7000


class CriticalPathMonitor:
    """Capture and aggregate PARASITE decision latencies."""

    def capture_action_latency(self, site_id: str, recommendation) -> dict[str, Any]:
        """
        Write one latency trace after execute_approval() completes.

        Called from approval_service.execute_approval() on success.
        Runs in the async approval flow — not as an APScheduler job.

        Args:
            site_id: Site identifier (e.g. 'S002')
            recommendation: Recommendation dataclass instance with
                           timestamp, approved_at, executed_at

        Returns:
            {"status": "captured", "approval_ms": float, "execution_ms": float, "total_ms": float}
        """
        import asyncio

        try:
            return asyncio.run(self._capture_async(site_id, recommendation))
        except Exception as e:
            logger.warning(f"capture_action_latency failed (sync wrapper): {e}")
            return {"error": str(e)}

    async def _capture_async(self, site_id: str, recommendation) -> dict[str, Any]:
        """Async internals of latency capture."""
        from app.database.supabase_client import get_supabase_client

        supabase = get_supabase_client()

        # Extract timestamps
        created_at = recommendation.timestamp
        approved_at = recommendation.approved_at
        executed_at = recommendation.executed_at

        # Guard against None timestamps (shouldn't happen post-fix)
        if not created_at or not approved_at or not executed_at:
            logger.warning(
                f"Skipping trace for {recommendation.id}: "
                f"timestamp={created_at}, approved_at={approved_at}, executed_at={executed_at}"
            )
            return {"error": "missing timestamps"}

        # Normalize to UTC-aware datetimes
        if created_at.tzinfo is None:
            created_at = created_at.replace(tzinfo=UTC)
        if approved_at.tzinfo is None:
            approved_at = approved_at.replace(tzinfo=UTC)
        if executed_at.tzinfo is None:
            executed_at = executed_at.replace(tzinfo=UTC)

        # Millisecond deltas
        approval_ms = (approved_at - created_at).total_seconds() * 1000
        execution_ms = (executed_at - approved_at).total_seconds() * 1000
        total_ms = (executed_at - created_at).total_seconds() * 1000

        try:
            supabase.table("supervised_action_traces").upsert(
                {
                    "site_id": site_id,
                    "recommendation_id": recommendation.id,
                    "approval_latency_ms": round(approval_ms, 2),
                    "execution_latency_ms": round(execution_ms, 2),
                    "total_latency_ms": round(total_ms, 2),
                    "timestamp": datetime.now(UTC).isoformat(),
                }
            ).execute()

            logger.info(
                f"✓ Critical path trace: {recommendation.id} | "
                f"approval={approval_ms:.0f}ms execution={execution_ms:.0f}ms total={total_ms:.0f}ms"
            )

            return {
                "status": "captured",
                "approval_ms": round(approval_ms, 2),
                "execution_ms": round(execution_ms, 2),
                "total_ms": round(total_ms, 2),
            }

        except Exception as e:
            logger.error(f"Failed to write trace for {recommendation.id}: {e}", exc_info=True)
            return {"error": str(e)}

    # ---------------------------------------------------------------------
    # Hourly aggregation (called by APScheduler at :00 every hour)
    # ---------------------------------------------------------------------

    def run_hourly_aggregation(self) -> dict[str, Any]:
        """Sync wrapper — called by APScheduler at :00 SAST each hour."""
        import asyncio

        try:
            return asyncio.run(self._run_hourly_aggregation_async())
        except Exception as e:
            logger.error(f"run_hourly_aggregation failed: {e}", exc_info=True)
            return {"error": str(e)}

    async def _run_hourly_aggregation_async(self) -> dict[str, Any]:
        """Async internals of hourly percentile aggregation."""
        from app.database.supabase_client import get_supabase_client

        supabase = get_supabase_client()

        # Determine hour window (last complete hour)
        now = datetime.now(UTC)
        hour_start = now.replace(minute=0, second=0, microsecond=0) - timedelta(hours=1)
        hour_end = hour_start + timedelta(hours=1)

        try:
            # Get all sites with traces in this window
            sites_result = (
                supabase.table("supervised_action_traces")
                .select("DISTINCT site_id")
                .gte("timestamp", hour_start.isoformat())
                .lt("timestamp", hour_end.isoformat())
                .execute()
            )

            sites = [row["site_id"] for row in sites_result.data]
            results = {}

            for site_id in sites:
                traces_result = (
                    supabase.table("supervised_action_traces")
                    .select("total_latency_ms, approval_latency_ms, execution_latency_ms")
                    .eq("site_id", site_id)
                    .gte("timestamp", hour_start.isoformat())
                    .lt("timestamp", hour_end.isoformat())
                    .execute()
                )

                if not traces_result.data:
                    continue

                total_lats = [t["total_latency_ms"] for t in traces_result.data if t["total_latency_ms"] is not None]
                if not total_lats:
                    continue

                total_actions = len(total_lats)

                def pct(data, p):
                    """Compute percentile — numpy alternative for stdlib."""
                    sorted_data = sorted(data)
                    idx = (len(sorted_data) - 1) * p / 100
                    lo = int(idx)
                    hi = lo + 1
                    weight = idx - lo
                    return round(sorted_data[lo] * (1 - weight) + sorted_data[hi] * weight, 2)

                p50 = pct(total_lats, 50)
                p99 = pct(total_lats, 99)
                p99_9 = pct(total_lats, 99.9)
                max_lat = round(max(total_lats), 2)
                avg_lat = round(sum(total_lats) / len(total_lats), 2)

                slo_pass = p99 <= SLO_TARGET_MS

                supabase.table("critical_path_hourly").upsert(
                    {
                        "site_id": site_id,
                        "hour_start": hour_start.isoformat(),
                        "total_actions": total_actions,
                        "p50_total_ms": p50,
                        "p99_total_ms": p99,
                        "p99_9_total_ms": p99_9,
                        "max_total_ms": max_lat,
                        "avg_total_ms": avg_lat,
                        "slo_pass": slo_pass,
                        "updated_at": datetime.now(UTC).isoformat(),
                    }
                ).execute()

                results[site_id] = {
                    "hour": hour_start.isoformat(),
                    "actions": total_actions,
                    "p50_ms": p50,
                    "p99_ms": p99,
                    "p99_9_ms": p99_9,
                    "slo_pass": slo_pass,
                }

                status = "✅" if slo_pass else "⚠️"
                logger.info(
                    f"{status} Critical path {site_id} {hour_start.isoformat()}: "
                    f"p99={p99}ms (target: {SLO_TARGET_MS}ms), actions={total_actions}"
                )

            return results

        except Exception as e:
            logger.error(f"run_hourly_aggregation_async failed: {e}", exc_info=True)
            return {"error": str(e)}
