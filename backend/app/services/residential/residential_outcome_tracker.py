"""Residential outcome tracker — measures recommendation quality from telemetry.

Checks telemetry 30min after recommendation delivery.
Compares before/after to assess whether the recommendation worked.
Feeds back to recommendation confidence scoring.
"""

from __future__ import annotations

import logging
from datetime import UTC, datetime, timedelta

logger = logging.getLogger(__name__)


async def track_outcome_for_rec(
    recommendation_id: str,
    site_id: str,
) -> bool | None:
    """Check telemetry 30min after recommendation delivery.

    Returns True if improved, False if not, None if cannot measure.
    Stores result in residential_recommendations.outcome_improved.
    """
    from app.database.supabase_client import get_supabase_client

    # Get the delivered recommendation
    try:
        supabase = get_supabase_client()
        rec_row = supabase.table("residential_recommendations").select("*").eq("id", recommendation_id).maybe_execute()
        if not rec_row.data:
            logger.warning("Rec %s not found for outcome tracking", recommendation_id)
            return None
        rec = rec_row.data[0]
    except Exception as exc:
        logger.error("Could not fetch rec %s: %s", recommendation_id, exc)
        return None

    trigger = rec.get("trigger", "").lower()
    context_soc = rec.get("context_soc_pct")  # stored at delivery time
    context_load = rec.get("context_load_w")

    # Get current telemetry (approximate via MQTT last_updated)
    # For simplicity: check residential_readings for the 30-min mark
    rec_time = rec.get("delivered_at")
    if not rec_time:
        return None

    try:
        rec_dt = datetime.fromisoformat(rec_time.replace("Z", "+00:00"))
    except (ValueError, AttributeError):
        return None

    check_window_start = rec_dt + timedelta(minutes=25)
    check_window_end = rec_dt + timedelta(minutes=35)

    try:
        readings = (
            supabase.table("residential_readings")
            .select("battery_soc_pct,load_w,timestamp")
            .eq("site_id", site_id)
            .gte("timestamp", check_window_start.isoformat())
            .lte("timestamp", check_window_end.isoformat())
            .order("timestamp", desc=False)
            .limit(1)
            .maybe_execute()
        )
    except Exception:
        readings = None

    current_soc = readings.data[0]["battery_soc_pct"] if readings and readings.data else None
    current_load = readings.data[0]["load_w"] if readings and readings.data else None

    improved: bool | None = None

    if "geyser" in trigger and context_load is not None and current_load is not None:
        # Did load drop (geyser switched off)?
        improved = current_load < context_load - 500

    elif "battery" in trigger or "soc" in trigger:
        # Did SOC stabilise or improve?
        if context_soc is not None and current_soc is not None:
            improved = current_soc >= context_soc - 5

    elif current_soc is not None and context_soc is not None:
        # Generic: no significant SOC regression
        improved = current_soc >= context_soc - 10

    # Store outcome
    try:
        supabase.table("residential_recommendations").update(
            {
                "outcome_improved": improved,
                "outcome_measured_at": datetime.now(UTC).isoformat(),
            }
        ).eq("id", recommendation_id).execute()
    except Exception as exc:
        logger.warning("Could not store outcome for %s: %s", recommendation_id, exc)

    return improved
