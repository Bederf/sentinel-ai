"""Uptime Aggregator — Tier 4: Availability SLI.

Computes daily and monthly uptime SLI from synthetic check data.
Daily aggregation runs at 01:00 SAST; monthly on the 1st at 02:00 SAST.
Writes results to api_uptime_daily and api_uptime_monthly tables.
"""

import logging
from datetime import UTC, date, datetime, timedelta
from typing import Any

logger = logging.getLogger("uptime-aggregator")

SLO_TARGET = 99.5


class UptimeAggregator:
    """Compute daily + monthly uptime SLI from synthetic check data."""

    def aggregate_daily_uptime(self) -> dict[str, Any]:
        """
        Aggregate yesterday's raw checks into one row in api_uptime_daily.
        Sync wrapper — called by APScheduler via run_in_executor().
        """
        import asyncio

        try:
            return asyncio.run(self._aggregate_daily_uptime_async())
        except Exception as e:
            logger.error(f"aggregate_daily_uptime failed: {e}", exc_info=True)
            return {"error": str(e)}

    async def _aggregate_daily_uptime_async(self) -> dict[str, Any]:
        """Async internals of daily aggregation."""
        from app.database.supabase_client import get_supabase_client

        yesterday = date.today() - timedelta(days=1)
        start_dt = datetime.combine(yesterday, datetime.min.time()).replace(tzinfo=UTC)
        end_dt = datetime.combine(yesterday, datetime.max.time()).replace(tzinfo=UTC)

        supabase = get_supabase_client()

        try:
            checks_result = (
                await supabase.table("api_uptime_checks")
                .select("status_code, latency_ms")
                .gte("check_time", start_dt.isoformat())
                .lt("check_time", end_dt.isoformat())
                .execute()
            )

            if not checks_result.data:
                logger.warning(f"No uptime checks found for {yesterday}")
                return {"date": yesterday.isoformat(), "checks": 0}

            total = len(checks_result.data)
            successful = sum(1 for c in checks_result.data if c["status_code"] == 200)
            uptime_percent = round(100 * successful / total, 3) if total > 0 else 0.0
            avg_latency = round(sum(c["latency_ms"] for c in checks_result.data) / total, 2)
            max_latency = round(max(c["latency_ms"] for c in checks_result.data), 2)

            await (
                supabase.table("api_uptime_daily")
                .upsert(
                    {
                        "check_date": yesterday.isoformat(),
                        "total_checks": total,
                        "successful_checks": successful,
                        "uptime_percent": uptime_percent,
                        "avg_latency_ms": avg_latency,
                        "max_latency_ms": max_latency,
                    }
                )
                .execute()
            )

            logger.info(f"Daily uptime {yesterday}: {uptime_percent}% ({successful}/{total} checks)")
            return {
                "date": yesterday.isoformat(),
                "uptime_percent": uptime_percent,
                "total_checks": total,
                "successful_checks": successful,
            }

        except Exception as e:
            logger.error(f"aggregate_daily_uptime failed: {e}", exc_info=True)
            return {"error": str(e)}

    def aggregate_monthly_uptime(self, month: str | None = None) -> dict[str, Any]:
        """
        Aggregate all checks for a month into one row in api_uptime_monthly.
        Sync wrapper — called by APScheduler via run_in_executor().
        """
        import asyncio

        try:
            return asyncio.run(self._aggregate_monthly_uptime_async(month))
        except Exception as e:
            logger.error(f"aggregate_monthly_uptime failed: {e}", exc_info=True)
            return {"error": str(e)}

    async def _aggregate_monthly_uptime_async(self, month: str | None = None) -> dict[str, Any]:
        """Async internals of monthly aggregation."""
        from app.database.supabase_client import get_supabase_client

        if month is None:
            today = date.today()
            if today.day == 1:
                prior = today.replace(day=1) - timedelta(days=1)
                month = prior.strftime("%Y-%m")
            else:
                month = today.strftime("%Y-%m")

        month_start = datetime.fromisoformat(f"{month}-01").replace(tzinfo=UTC)
        if month == date.today().strftime("%Y-%m"):
            month_end = datetime.now(UTC)
        else:
            next_month = month_start + timedelta(days=32)
            month_end = next_month.replace(day=1) - timedelta(seconds=1)

        supabase = get_supabase_client()

        try:
            checks_result = (
                await supabase.table("api_uptime_checks")
                .select("status_code, latency_ms")
                .gte("check_time", month_start.isoformat())
                .lt("check_time", month_end.isoformat())
                .execute()
            )

            if not checks_result.data:
                logger.warning(f"No uptime checks found for {month}")
                return {"month": month, "checks": 0}

            total = len(checks_result.data)
            successful = sum(1 for c in checks_result.data if c["status_code"] == 200)
            uptime_percent = round(100 * successful / total, 3) if total > 0 else 0.0

            slo_pass = uptime_percent >= SLO_TARGET
            error_budget = round(100 - uptime_percent, 3)
            downtime_checks = total - successful
            downtime_minutes = round(downtime_checks * 1.0 / 60, 2)

            await (
                supabase.table("api_uptime_monthly")
                .upsert(
                    {
                        "month": month,
                        "total_checks": total,
                        "successful_checks": successful,
                        "uptime_percent": uptime_percent,
                        "error_budget_remaining": error_budget,
                        "downtime_minutes": downtime_minutes,
                        "slo_target": SLO_TARGET,
                        "slo_pass": slo_pass,
                        "incidents": "[]",
                    }
                )
                .execute()
            )

            status = "PASS" if slo_pass else "FAIL"
            logger.info(
                f"Monthly SLO {status}: {month} → {uptime_percent}% "
                f"(target: {SLO_TARGET}%, error budget: {error_budget}%, "
                f"downtime: {downtime_minutes}min)"
            )

            return {
                "month": month,
                "uptime_percent": uptime_percent,
                "slo_pass": slo_pass,
                "error_budget_remaining": error_budget,
                "downtime_minutes": downtime_minutes,
            }

        except Exception as e:
            logger.error(f"aggregate_monthly_uptime failed: {e}", exc_info=True)
            return {"error": str(e)}
