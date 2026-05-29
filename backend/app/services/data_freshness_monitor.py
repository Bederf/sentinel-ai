"""Data Freshness Monitor — SLI Tier 2: Data Freshness Pipeline.

Runs every 5 minutes (300s) via BackgroundSchedulerService.
Calculates age of normalized data per source, updates SLI pass/fail,
detects new breaches, auto-resolves resolved ones.

Wired into BackgroundSchedulerService via add_data_freshness_monitor_job().
"""

import logging
import os
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

    # Standard data sources and their SLI targets (seconds)
    _STANDARD_SOURCES: ClassVar[dict[str, int]] = {
        "bms_telemetry": 30,
        "anomalies": 300,
        "documents": 7200,
        "recommendations": 900,
    }

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
            sites = set(row["site_id"] for row in sites_result.data)

            # Also discover sites from active bridge adapters — handles sites that
            # haven't been seeded into data_freshness yet (new site deployments).
            adapter_result = (
                supabase.table("site_adapter_config")
                .select("site_id")
                .eq("enabled", True)
                .execute()
            )
            for row in (adapter_result.data or []):
                if row.get("site_id"):
                    sites.add(row["site_id"])

            if not sites:
                logger.warning("Freshness cycle: no sites found in data_freshness or bridge adapters")
                return {}

            sites = sorted(sites)

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

        # Fetch the latest sync time from log_sources to derive current freshness.
        # Shadow bridge polling upserts log_sources on every poll cycle, so this
        # reflects actual bridge activity even though data_freshness.last_updated
        # is never written by the bridge itself.
        log_sources = (
            supabase.table("log_sources")
            .select("last_sync_at")
            .like("name", f"%{self._site_code(site_id)}%")
            .eq("is_active", True)
            .order("last_sync_at", desc=True)
            .limit(1)
            .execute()
        )
        latest_sync = log_sources.data[0]["last_sync_at"] if log_sources.data and log_sources.data[0] else None
        latest_sync_dt = datetime.fromisoformat(latest_sync.replace("Z", "+00:00")) if latest_sync else None

        # Seed standard sources if no rows exist for this site but bridge has polled.
        # This handles first-run: monitor discovers bridge has polled but data_freshness
        # has no rows yet, so we create them with the correct sync time as baseline.
        if not freshness_rows.data and latest_sync_dt is not None:
            for data_source, sli_target in self._STANDARD_SOURCES.items():
                supabase.table("data_freshness").insert(
                    {
                        "site_id": site_id,
                        "data_source": data_source,
                        "sli_target_seconds": sli_target,
                        "last_updated": latest_sync_dt.isoformat(),
                        "age_seconds": int((now - latest_sync_dt).total_seconds()),
                        "sli_pass": True,
                        "updated_at": now.isoformat(),
                    }
                ).execute()
            freshness_rows = supabase.table("data_freshness").select("*").eq("site_id", site_id).execute()
            logger.info(f"Seeded data_freshness for {site_id} with {len(self._STANDARD_SOURCES)} sources")

        for row in freshness_rows.data:
            data_source = row["data_source"]
            last_updated_str = row["last_updated"]
            sli_target = row["sli_target_seconds"]

            # Derive age from log_sources (actual bridge sync time) when available.
            # Fall back to data_freshness.last_updated when log_sources has no entry.
            if latest_sync_dt is not None:
                effective_last_updated = latest_sync_dt
            elif last_updated_str:
                effective_last_updated = datetime.fromisoformat(last_updated_str.replace("Z", "+00:00"))
            else:
                effective_last_updated = None

            if effective_last_updated is not None:
                age_seconds = int((now - effective_last_updated).total_seconds())
            else:
                age_seconds = None

            # Determine SLI pass/fail
            sli_pass = age_seconds is not None and age_seconds <= sli_target

            # Sync SLI target from code in case it changed since seeding
            code_target = self._STANDARD_SOURCES.get(data_source)
            if code_target is not None and code_target != sli_target:
                sli_target = code_target

            # Update age, SLI, and derived last_updated in data_freshness so the
            # column stays current even when the bridge bypasses it directly.
            update_payload = {
                "age_seconds": age_seconds,
                "sli_pass": sli_pass,
                "sli_target_seconds": sli_target,
                "updated_at": now.isoformat(),
            }
            if effective_last_updated is not None:
                update_payload["last_updated"] = effective_last_updated.isoformat()
            supabase.table("data_freshness").update(update_payload).eq("site_id", site_id).eq(
                "data_source", data_source
            ).execute()

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
        """Detect new breaches and resolve active ones.

        Alert policy:
        - Auto-recovery window: 10 minutes (600s)
        - Only alert if breach persists beyond auto-recovery window (unrecoverable)
        - Alert once per breach via Sentry Telegram bot to manager
        """
        # Check for active (unresolved) breach
        active_breach_result = (
            supabase.table("data_freshness_breaches")
            .select("id, breach_time, alert_sent")
            .eq("site_id", site_id)
            .eq("data_source", data_source)
            .is_("resolved_at", None)
            .order("breach_time", desc=True)
            .limit(1)
            .execute()
        )

        active_breach = active_breach_result.data
        now = datetime.now(UTC)
        AUTO_RECOVERY_WINDOW_SECONDS = 600  # 10 minutes

        if sli_pass and active_breach:
            # Breach is resolved
            breach_id = active_breach[0]["id"]
            breach_time = datetime.fromisoformat(active_breach[0]["breach_time"].replace("Z", "+00:00"))
            duration = int((now - breach_time).total_seconds())

            supabase.table("data_freshness_breaches").update(
                {"resolved_at": now.isoformat(), "duration_seconds": duration}
            ).eq("id", breach_id).execute()

            # Send recovery notification if alert was previously sent
            if active_breach[0].get("alert_sent"):
                await self._send_recovery_notification(site_id, data_source, duration)

            return {"breach_started": False, "breach_resolved": True, "breach_duration_seconds": duration}

        elif not sli_pass and not active_breach:
            # New breach detected
            supabase.table("data_freshness_breaches").insert(
                {
                    "site_id": site_id,
                    "metric_name": data_source,
                    "breach_type": "data_freshness",
                    "severity": "medium",
                    "detected_at": now.isoformat(),
                    "data_source": data_source,
                    "age_seconds": age_seconds,
                    "sli_target": target,
                    "alert_sent": False,
                }
            ).execute()

            # Don't alert immediately - wait for auto-recovery window
            logger.info(
                f"[FRESHNESS] Breach started for {data_source}@{site_id} - "
                f"waiting {AUTO_RECOVERY_WINDOW_SECONDS}s auto-recovery window before alerting"
            )

            return {"breach_started": True, "breach_resolved": False}

        elif not sli_pass and active_breach:
            # Ongoing breach — check if we've exceeded auto-recovery window
            breach_time = datetime.fromisoformat(active_breach[0]["breach_time"].replace("Z", "+00:00"))
            breach_duration = int((now - breach_time).total_seconds())
            alert_sent = active_breach[0].get("alert_sent", False)

            # Alert only if:
            # 1. Breach has persisted beyond auto-recovery window
            # 2. Alert hasn't been sent yet for this breach
            if (
                breach_duration > AUTO_RECOVERY_WINDOW_SECONDS
                and not alert_sent
                and data_source in self._CRITICAL_SOURCES
            ):
                await self._send_unrecoverable_alert(site_id, data_source, age_seconds, target, breach_duration)

                # Mark alert as sent
                supabase.table("data_freshness_breaches").update(
                    {"alert_sent": True}
                ).eq("id", active_breach[0]["id"]).execute()

            return {"breach_started": False, "breach_resolved": False}

        # No breach state change
        return {"breach_started": False, "breach_resolved": False}

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------

    @staticmethod
    def _site_code(site_id: str) -> str:
        """Convert S002 → 'site-002', leave 'site-002' unchanged."""
        if site_id.startswith("site-"):
            return site_id
        if site_id.startswith("S") and len(site_id) == 4:
            return f"site-{site_id[1:]}"  # S002[1:] = '002' → site-002
        return site_id

    async def _send_unrecoverable_alert(
        self, site_id: str, data_source: str, age_seconds: int | None, target: int, breach_duration: int
    ) -> None:
        """Send Telegram alert for UNRECOVERABLE breach (persisted > 10 min).

        Routes via Sentry gateway's manager bot to notify that auto-recovery failed
        and manual intervention is required.
        """
        try:
            import httpx

            bot_token = os.environ.get("TELEGRAM_BOT_TOKEN", os.environ.get("SENTRY_BOT_TOKEN", ""))
            chat_id = os.environ.get("TELEGRAM_CHAT_ID", "8359288792")  # Manager operator chat ID

            if not bot_token:
                logger.warning("[FRESHNESS] TELEGRAM_BOT_TOKEN not set - skipping Telegram alert")
                self._fallback_log(site_id, data_source, age_seconds, target, "No bot token configured")
                return

            minutes_down = breach_duration // 60

            message = (
                f"🚨 <b>SENTRY ALERT: Telemetry Unrecoverable</b>\n\n"
                f"<b>Site:</b> {site_id}\n"
                f"<b>Source:</b> {data_source}\n"
                f"<b>Duration:</b> {minutes_down} minutes\n"
                f"<b>Status:</b> Auto-recovery failed\n\n"
                f"⚠️ System has been down for over 10 minutes and has NOT auto-recovered.\n\n"
                f"🔧 <b>Action Required:</b> Check BMS backend and bridge connectivity immediately."
            )

            async with httpx.AsyncClient(timeout=15.0) as client:
                resp = await client.post(
                    f"https://api.telegram.org/bot{bot_token}/sendMessage",
                    json={"chat_id": chat_id, "text": message, "parse_mode": "HTML"},
                )
                result = resp.json()
                if not result.get("ok"):
                    logger.warning(f"[FRESHNESS] Unrecoverable alert failed: {result}")
                    self._fallback_log(site_id, data_source, age_seconds, target, result)
                else:
                    logger.info(f"[FRESHNESS] Unrecoverable alert sent to manager for {site_id}")

        except Exception as e:
            logger.warning(f"Failed to send unrecoverable alert: {e}")
            self._fallback_log(site_id, data_source, age_seconds, target, str(e))

    async def _send_recovery_notification(self, site_id: str, data_source: str, duration_seconds: int) -> None:
        """Send Telegram notification when breach is resolved (auto-recovered)."""
        try:
            import httpx

            bot_token = os.environ.get("TELEGRAM_BOT_TOKEN", os.environ.get("SENTRY_BOT_TOKEN", ""))
            chat_id = os.environ.get("TELEGRAM_CHAT_ID", "8359288792")  # Manager operator chat ID

            if not bot_token:
                logger.warning("[FRESHNESS] TELEGRAM_BOT_TOKEN not set - skipping Telegram alert")
                self._fallback_log(site_id, data_source, age_seconds, target, "No bot token configured")
                return

            minutes = duration_seconds // 60

            message = (
                f"✅ <b>SENTRY: Telemetry Restored</b>\n\n"
                f"<b>Site:</b> {site_id}\n"
                f"<b>Source:</b> {data_source}\n"
                f"<b>Duration:</b> {minutes} minutes\n\n"
                f"System has auto-recovered and telemetry is flowing normally."
            )

            async with httpx.AsyncClient(timeout=15.0) as client:
                resp = await client.post(
                    f"https://api.telegram.org/bot{bot_token}/sendMessage",
                    json={"chat_id": chat_id, "text": message, "parse_mode": "HTML"},
                )
                result = resp.json()
                if result.get("ok"):
                    logger.info(f"[FRESHNESS] Recovery notification sent for {site_id}")

        except Exception as e:
            logger.warning(f"Failed to send recovery notification: {e}")

    def _fallback_log(self, site_id: str, data_source: str, age_seconds: int | None, target: int, error: Any) -> None:
        """Write failed alert to fallback file for manual recovery."""
        import json
        from pathlib import Path

        fallback_path = Path("/tmp/sentinel_freshness_alert_fallback.json")
        entry = {
            "site_id": site_id,
            "data_source": data_source,
            "age_seconds": age_seconds,
            "target": target,
            "error": error,
            "timestamp": datetime.now(UTC).isoformat(),
        }
        try:
            existing = []
            if fallback_path.exists():
                existing = json.loads(fallback_path.read_text())
            existing.append(entry)
            fallback_path.write_text(json.dumps(existing, indent=2))
            logger.info(f"[FRESHNESS] Alert written to fallback file: {fallback_path}")
        except Exception as e:
            logger.error(f"[FRESHNESS] Failed to write fallback log: {e}")
