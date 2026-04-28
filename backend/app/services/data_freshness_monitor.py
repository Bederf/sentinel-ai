"""Data Freshness Monitor — SLI Tier 2: Data Freshness Pipeline.

Runs every 5 minutes (300s) via BackgroundSchedulerService.
Calculates age of normalized data per source, updates SLI pass/fail,
detects new breaches, auto-resolves resolved ones.

Wired into BackgroundSchedulerService via add_data_freshness_monitor_job().
"""

import logging
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Any, ClassVar

logger = logging.getLogger("data-freshness-monitor")


@dataclass
class FreshnessResult:
    site_id: str
    data_source: str
    age_seconds: int | None
    target_seconds: int
    sli_pass: bool
    breach_started: bool = False
    breach_resolved: bool = False
    breach_duration_seconds: int | None = None


class DataFreshnessMonitor:
    """5-minute interval freshness checks for all registered data sources per site."""

    # High-priority sources that trigger Telegram alerts on breach
    _CRITICAL_SOURCES: ClassVar[set[str]] = {"bms_telemetry", "anomalies"}

    async def run_freshness_cycle(self) -> dict[str, dict[str, FreshnessResult]]:
        """Run one complete freshness check cycle across all sites and sources.

        Returns:
            {site_id: {data_source: FreshnessResult}}
        """
        from app.database.supabase_client import get_supabase_client

        supabase = get_supabase_client()
        results: dict[str, dict[str, FreshnessResult]] = {}

        try:
            # Get all unique sites registered in data_freshness table
            sites_result = supabase.table("data_freshness").select("site_id").execute()
            sites = list({row["site_id"] for row in sites_result.data})

            logger.debug(f"Freshness cycle: {len(sites)} sites → {sites}")

            for site_id in sites:
                results[site_id] = {}
                try:
                    results[site_id] = await self._check_site_freshness(supabase, site_id)
                except Exception as e:
                    logger.exception(f"Freshness check failed for {site_id}: {e}")

            logger.info(f"✓ Freshness cycle complete: {len(sites)} sites checked")
            return results

        except Exception as e:
            logger.error(f"Freshness monitor cycle failed: {e}", exc_info=True)
            return {}

    async def _check_site_freshness(self, supabase, site_id: str) -> dict[str, FreshnessResult]:
        """Check all data sources at one site; update age and SLI in DB."""
        freshness_rows = supabase.table("data_freshness").select("*").eq("site_id", site_id).execute()

        results: dict[str, FreshnessResult] = {}
        now = datetime.now(UTC)

        for row in freshness_rows.data:
            data_source = row["data_source"]
            last_updated_str = row["last_updated"]
            sli_target = row["sli_target_seconds"]

            # Calculate age
            if last_updated_str:
                last_updated = datetime.fromisoformat(last_updated_str.replace("Z", "+00:00"))
                age_seconds = int((now - last_updated).total_seconds())
            else:
                age_seconds = None

            # Determine SLI pass/fail
            sli_pass = age_seconds is not None and age_seconds <= sli_target

            # Update age and SLI in data_freshness table
            supabase.table("data_freshness").update(
                {"age_seconds": age_seconds, "sli_pass": sli_pass, "updated_at": now.isoformat()}
            ).eq("site_id", site_id).eq("data_source", data_source).execute()

            result = FreshnessResult(
                site_id=site_id,
                data_source=data_source,
                age_seconds=age_seconds,
                target_seconds=sli_target,
                sli_pass=sli_pass,
            )

            # Handle breach transitions
            breach_result = await self._handle_breach_logic(
                supabase, site_id, data_source, age_seconds, sli_target, sli_pass
            )
            result.breach_started = breach_result["breach_started"]
            result.breach_resolved = breach_result["breach_resolved"]
            result.breach_duration_seconds = breach_result.get("breach_duration_seconds")

            results[data_source] = result

            # Log transitions
            if breach_result["breach_started"]:
                logger.warning(f"⚠️ Freshness BREACH: {data_source}@{site_id} ({age_seconds}s > {sli_target}s target)")
            elif breach_result["breach_resolved"]:
                logger.info(
                    f"✅ Freshness resolved: {data_source}@{site_id} "
                    f"(was stale for {breach_result['breach_duration_seconds']}s)"
                )

        return results

    async def _handle_breach_logic(
        self,
        supabase,
        site_id: str,
        data_source: str,
        age_seconds: int | None,
        target: int,
        sli_pass: bool,
    ) -> dict[str, Any]:
        """Detect new breaches and resolve active ones."""
        # Check for active (unresolved) breach
        active_breach_result = (
            supabase.table("data_freshness_breaches")
            .select("id, breach_time")
            .eq("site_id", site_id)
            .eq("data_source", data_source)
            .is_("resolved_at", None)
            .order("breach_time", desc=True)
            .limit(1)
            .execute()
        )

        active_breach = active_breach_result.data
        now = datetime.now(UTC)

        if sli_pass and active_breach:
            # Breach is resolved
            breach_id = active_breach[0]["id"]
            breach_time = datetime.fromisoformat(active_breach[0]["breach_time"].replace("Z", "+00:00"))
            duration = int((now - breach_time).total_seconds())

            supabase.table("data_freshness_breaches").update(
                {"resolved_at": now.isoformat(), "duration_seconds": duration}
            ).eq("id", breach_id).execute()

            return {"breach_started": False, "breach_resolved": True, "breach_duration_seconds": duration}

        elif not sli_pass and not active_breach:
            # New breach detected
            supabase.table("data_freshness_breaches").insert(
                {
                    "site_id": site_id,
                    "data_source": data_source,
                    "age_seconds": age_seconds,
                    "sli_target": target,
                    "breach_time": now.isoformat(),
                }
            ).execute()

            # Telegram alert for critical sources
            if data_source in self._CRITICAL_SOURCES:
                await self._send_freshness_alert(site_id, data_source, age_seconds, target)

            return {"breach_started": True, "breach_resolved": False}

        return {"breach_started": False, "breach_resolved": False}

    async def _send_freshness_alert(self, site_id: str, data_source: str, age_seconds: int | None, target: int) -> None:
        """Send Telegram alert for critical source breaches (bms_telemetry, anomalies)."""
        try:
            from app.services.notification_providers.telegram_provider import TelegramProvider

            provider = TelegramProvider()
            await provider.send(
                recipient=getattr(
                    __import__("settings", fromlist=["telegram_alert_chat_id"]), "telegram_alert_chat_id", ""
                ),
                title=f"Data Freshness Breach: {data_source}",
                body=f"{data_source} at {site_id} is stale.\nAge: {age_seconds}s | Target: {target}s",
                priority="high",
            )
        except Exception as e:
            logger.warning(f"Failed to send freshness Telegram alert: {e}")
