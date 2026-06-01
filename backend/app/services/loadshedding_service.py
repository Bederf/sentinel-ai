"""Loadshedding data service using eskom-calendar.

Source: github.com/beyarkay/eskom-calendar (CC BY-NC-SA 4.0)
License Note: Non-commercial license — upgrade to EskomSePush paid tier for production commercial use.

Fetches loadshedding schedules and current stage for Johannesburg/Sandton area.
"""

from __future__ import annotations

import csv
import io
import logging
from datetime import UTC, datetime, timedelta
from typing import Any

import httpx

logger = logging.getLogger(__name__)


class LoadsheddingService:
    """
    Fetches loadshedding data from eskom-calendar.

    Source: github.com/beyarkay/eskom-calendar (CC BY-NC-SA 4.0)
    Note: Non-commercial license — upgrade to EskomSePush for production.

    City Power (Johannesburg) uses block-based scheduling:
    - Sandton/Rivonia Road area is typically in city-power-7 or city-power-8
    """

    # Configuration for Site-002 (Sandton area)
    AREA_CODES = ["city-power-7", "city-power-8"]  # Sandton covers multiple blocks
    CSV_URL = "https://github.com/beyarkay/eskom-calendar/releases/download/latest/machine_friendly.csv"

    # Cache settings
    CACHE_TTL_SCHEDULE = timedelta(hours=6)  # Schedule changes infrequently
    CACHE_TTL_STAGE = timedelta(hours=1)  # Stage can change more often

    def __init__(self):
        self.http_client = httpx.AsyncClient(timeout=30.0)
        self._cache: dict[str, Any] = {
            "schedule": None,
            "schedule_fetched_at": None,
            "current_stage": None,
            "stage_fetched_at": None,
        }

    async def close(self):
        """Close HTTP client."""
        await self.http_client.aclose()

    async def get_current_stage(self, use_cache: bool = True) -> int:
        """Returns current national loadshedding stage (0 = no loadshedding).

        Since eskom-calendar doesn't provide a direct "current stage" API,
        we infer it from the schedule data (highest stage in next 24h).

        Args:
            use_cache: Whether to use cached data if available

        Returns:
            Current loadshedding stage (0-8), or -1 if error
        """
        if use_cache and self._cache["current_stage"] is not None:
            cache_age = datetime.now(UTC) - self._cache["stage_fetched_at"]
            if cache_age < self.CACHE_TTL_STAGE:
                logger.debug(f"[LOADSHEDDING] Using cached stage: {self._cache['current_stage']}")
                return self._cache["current_stage"]

        try:
            # Get upcoming outages and infer stage from highest scheduled stage
            outages = await self.get_upcoming_outages(hours_ahead=24, use_cache=False)

            if not outages:
                # No outages scheduled = Stage 0
                current_stage = 0
            else:
                # Get the highest stage in the next 24h
                current_stage = max(o.get("stage", 0) for o in outages)

            self._cache["current_stage"] = current_stage
            self._cache["stage_fetched_at"] = datetime.now(UTC)

            logger.info(f"[LOADSHEDDING] Current stage determined: {current_stage}")
            return current_stage

        except Exception as e:
            logger.error(f"[LOADSHEDDING] Failed to get current stage: {e}")
            # Return cached value if available, else -1
            return self._cache.get("current_stage", -1)

    async def get_upcoming_outages(self, hours_ahead: int = 72, use_cache: bool = True) -> list[dict[str, Any]]:
        """Returns list of upcoming outages for Sandton area.

        Args:
            hours_ahead: How many hours ahead to look
            use_cache: Whether to use cached data if available

        Returns:
            List of outage dicts: {area_name, start, end, stage, duration_minutes, source}
        """
        if use_cache and self._cache["schedule"] is not None:
            cache_age = datetime.now(UTC) - self._cache["schedule_fetched_at"]
            if cache_age < self.CACHE_TTL_SCHEDULE:
                logger.debug("[LOADSHEDDING] Using cached schedule")
                return self._filter_outages(self._cache["schedule"], hours_ahead)

        try:
            schedule = await self._fetch_schedule()

            if not schedule:
                logger.warning("[LOADSHEDDING] No schedule data fetched")
                return []

            self._cache["schedule"] = schedule
            self._cache["schedule_fetched_at"] = datetime.now(UTC)

            return self._filter_outages(schedule, hours_ahead)

        except Exception as e:
            logger.error(f"[LOADSHEDDING] Failed to get outages: {e}")
            # Return cached data if available
            if self._cache["schedule"]:
                return self._filter_outages(self._cache["schedule"], hours_ahead)
            return []

    async def get_next_outage(self, use_cache: bool = True) -> dict[str, Any] | None:
        """Returns the next scheduled outage or None if no loadshedding.

        Used for BESS pre-charge recommendations.

        Args:
            use_cache: Whether to use cached data

        Returns:
            Outage dict or None
        """
        outages = await self.get_upcoming_outages(hours_ahead=168, use_cache=use_cache)  # 1 week ahead

        if not outages:
            return None

        now = datetime.now(UTC)

        # Find the first future outage
        for outage in sorted(outages, key=lambda x: x["start"]):
            if outage["start"] > now:
                return outage

        return None

    async def get_outage_status(self, use_cache: bool = True) -> dict[str, Any]:
        """Get comprehensive loadshedding status for Site-002.

        Returns:
            Status dict with current stage, next outage, and upcoming outages
        """
        stage = await self.get_current_stage(use_cache=use_cache)
        next_outage = await self.get_next_outage(use_cache=use_cache)
        upcoming = await self.get_upcoming_outages(hours_ahead=48, use_cache=use_cache)

        # Calculate time to next outage
        time_to_next = None
        if next_outage:
            now = datetime.now(UTC)
            time_to_next = next_outage["start"] - now

        return {
            "current_stage": stage,
            "is_loadshedding_now": stage > 0,
            "next_outage": next_outage,
            "time_to_next_minutes": int(time_to_next.total_seconds() / 60) if time_to_next else None,
            "upcoming_outages_48h": upcoming,
            "area_codes": self.AREA_CODES,
            "source": "eskom-calendar (CC BY-NC-SA 4.0)",
            "license_note": "Non-commercial use only - upgrade to EskomSePush for production",
            "cached": use_cache,
        }

    async def _fetch_schedule(self) -> list[dict[str, Any]]:
        """Fetch loadshedding schedule CSV from eskom-calendar.

        Returns:
            List of parsed schedule entries
        """
        try:
            response = await self.http_client.get(self.CSV_URL, follow_redirects=True)
            response.raise_for_status()

            csv_content = response.text
            schedule = []

            # Parse CSV
            reader = csv.DictReader(io.StringIO(csv_content))
            for row in reader:
                area_name = row.get("area_name", "").strip()

                # Filter for our area codes
                if area_name not in self.AREA_CODES:
                    continue

                # Parse dates
                start_str = row.get("start", "")
                finish_str = row.get("finsh", "")  # Note: 'finsh' not 'finish'

                try:
                    start = datetime.fromisoformat(start_str)
                    end = datetime.fromisoformat(finish_str)

                    # Ensure timezone aware
                    if start.tzinfo is None:
                        start = start.replace(tzinfo=UTC)
                    if end.tzinfo is None:
                        end = end.replace(tzinfo=UTC)

                    duration = end - start

                    schedule.append(
                        {
                            "area_name": area_name,
                            "start": start,
                            "end": end,
                            "stage": int(row.get("stage", 0)),
                            "duration_minutes": int(duration.total_seconds() / 60),
                            "source": row.get("source", ""),
                        }
                    )

                except (ValueError, TypeError) as e:
                    logger.debug(f"[LOADSHEDDING] Failed to parse date: {e}")
                    continue

            logger.info(f"[LOADSHEDDING] Fetched {len(schedule)} outages for areas {self.AREA_CODES}")
            return schedule

        except Exception as e:
            logger.error(f"[LOADSHEDDING] Failed to fetch schedule: {e}")
            raise

    def _filter_outages(self, schedule: list[dict[str, Any]], hours_ahead: int) -> list[dict[str, Any]]:
        """Filter schedule to only future outages within hours_ahead.

        Args:
            schedule: Full schedule list
            hours_ahead: How many hours ahead to include

        Returns:
            Filtered list of future outages
        """
        now = datetime.now(UTC)
        cutoff = now + timedelta(hours=hours_ahead)

        filtered = []
        for outage in schedule:
            # Include if outage ends in the future AND starts before cutoff
            if outage["end"] > now and outage["start"] <= cutoff:
                # Convert datetime to ISO strings for JSON serialization
                filtered.append(
                    {
                        "area_name": outage["area_name"],
                        "start": outage["start"].isoformat(),
                        "end": outage["end"].isoformat(),
                        "stage": outage["stage"],
                        "duration_minutes": outage["duration_minutes"],
                        "source": outage["source"],
                    }
                )

        # Sort by start time
        filtered.sort(key=lambda x: x["start"])

        return filtered

    def format_for_prompt(self, status: dict[str, Any]) -> str:
        """Format loadshedding status for AI optimizer prompt.

        Args:
            status: Status dict from get_outage_status()

        Returns:
            Formatted string for prompt
        """
        lines = ["LOADSHEDDING (Sandton — eskom-calendar):"]

        stage = status.get("current_stage", 0)
        next_outage = status.get("next_outage")

        if stage > 0:
            lines.append(f"⚡ ACTIVE Stage {stage} loadshedding in progress")
        elif next_outage:
            start = next_outage.get("start", "unknown")
            duration = next_outage.get("duration_minutes", 0)
            stage = next_outage.get("stage", 0)

            # Parse time for display
            try:
                start_dt = datetime.fromisoformat(start.replace("Z", "+00:00"))
                now = datetime.now(UTC)
                time_until = start_dt - now
                hours_until = int(time_until.total_seconds() / 3600)
                mins_until = int((time_until.total_seconds() % 3600) / 60)

                time_str = f"{hours_until}h {mins_until}min" if hours_until > 0 else f"{mins_until}min"
                lines.append(f"⏰ Next outage: {time_str} away (Stage {stage}, {duration} min)")
            except:
                lines.append(f"⏰ Next outage: {start} (Stage {stage}, {duration} min)")
        else:
            lines.append("✅ No loadshedding scheduled for next 48 hours")

        # Add upcoming outages summary
        upcoming = status.get("upcoming_outages_48h", [])
        if len(upcoming) > 1:
            lines.append(f"📅 {len(upcoming)} outages scheduled in next 48h")

        lines.append(f"Source: eskomcalendar.co.za (Area codes: {', '.join(self.AREA_CODES)})")

        return "\n".join(lines)


# Singleton instance
_loadshedding_service: LoadsheddingService | None = None


def get_loadshedding_service() -> LoadsheddingService:
    """Get or create loadshedding service singleton."""
    global _loadshedding_service
    if _loadshedding_service is None:
        _loadshedding_service = LoadsheddingService()
    return _loadshedding_service
