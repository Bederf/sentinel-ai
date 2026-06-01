"""Residential recommendation context builder.

Assembles the current state of a residential site for the AI recommendation
prompt. Reads from MQTT retained values, EskomSePush cache, and historical
telemetry.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta

logger = logging.getLogger(__name__)

# MQTT energy topic fields and their types
ENERGY_FIELDS = [
    "pv_power_w",
    "battery_soc_pct",
    "battery_power_w",
    "grid_power_w",
    "load_power_w",
    "grid_voltage_v",
    "geyser_power_w",
    "geyser_state",
    "ev_charger_power_w",
]


_PLATFORM_APP_NAMES = {
    "solarman": "SOLARMAN app",
    "victron": "Victron VRM portal",
    "home_assistant": "Home Assistant",
}


@dataclass
class ResidentialRecommendationContext:
    """Context for residential AI recommendations."""

    site_id: str
    platform: str
    platform_app_name: str

    # Current telemetry (from MQTT retained values)
    battery_soc_pct: float | None = None
    battery_power_w: float | None = None
    pv_power_w: float | None = None
    grid_power_w: float | None = None
    load_power_w: float | None = None
    grid_voltage_v: float | None = None
    geyser_state: str | None = None
    geyser_power_w: float | None = None
    ev_charger_power_w: float | None = None

    # Telemetry freshness
    last_updated: datetime | None = None

    # Loadshedding context (from shared EskomSePush cache)
    loadshedding_stage: int = 0
    minutes_to_next_slot: int | None = None
    next_slot_end: datetime | None = None
    eskom_area_code: str | None = None

    # Historical patterns (from residential_readings table if available)
    avg_daily_pv_kwh: float | None = None
    avg_daily_consumption_kwh: float | None = None
    avg_morning_soc: float | None = None
    typical_full_charge_time: str | None = None

    @classmethod
    async def build(
        cls,
        site_id: str,
        mqtt_client,
    ) -> ResidentialRecommendationContext:
        """Build context for a residential site.

        Args:
            site_id: Residential site ID (res-{chat_id})
            mqtt_client: paho-mqtt Client instance connected to Mosquitto
        """
        # Get platform from residential_sites table
        platform, eskom_area_code = await cls._get_site_metadata(site_id)

        # Read MQTT retained values
        energy = cls._read_mqtt_retained(site_id, mqtt_client)

        # Get loadshedding status from shared cache
        ls_stage, minutes_to_next, next_end = cls._get_loadshedding(eskom_area_code)

        # Get historical patterns (optional — table may not exist)
        history = await cls._get_historical_patterns(site_id)

        return cls(
            site_id=site_id,
            platform=platform,
            platform_app_name=_PLATFORM_APP_NAMES.get(platform, platform),
            battery_soc_pct=energy.get("battery_soc_pct"),
            battery_power_w=energy.get("battery_power_w"),
            pv_power_w=energy.get("pv_power_w"),
            grid_power_w=energy.get("grid_power_w"),
            load_power_w=energy.get("load_power_w"),
            grid_voltage_v=energy.get("grid_voltage_v"),
            geyser_state=energy.get("geyser_state"),
            geyser_power_w=energy.get("geyser_power_w"),
            ev_charger_power_w=energy.get("ev_charger_power_w"),
            last_updated=energy.get("last_updated"),
            loadshedding_stage=ls_stage,
            minutes_to_next_slot=minutes_to_next,
            next_slot_end=next_end,
            eskom_area_code=eskom_area_code,
            avg_daily_pv_kwh=history.get("avg_daily_pv_kwh"),
            avg_daily_consumption_kwh=history.get("avg_daily_consumption_kwh"),
            avg_morning_soc=history.get("avg_morning_soc"),
            typical_full_charge_time=history.get("typical_full_charge_time"),
        )

    @staticmethod
    async def _get_site_metadata(site_id: str) -> tuple[str, str | None]:
        """Query residential_sites table for platform and area code."""
        try:
            from app.database.supabase_client import get_supabase_client

            client = get_supabase_client()
            result = (
                client.table("residential_sites")
                .select("platform,eskom_area_code")
                .eq("site_id", site_id)
                .maybe_execute()
            )
            if result.data:
                row = result.data[0]
                return row.get("platform", "solarman"), row.get("eskom_area_code")
        except Exception as exc:
            logger.warning("Could not fetch site metadata for %s: %s", site_id, exc)
        return "solarman", None

    @staticmethod
    def _read_mqtt_retained(site_id: str, mqtt_client) -> dict:
        """Read latest retained MQTT values for a site from Mosquitto.

        Returns dict of field -> value, plus last_updated timestamp.
        """

        # Subscribe to get retained messages
        energy_values: dict[str, float | str | None] = {}

        def on_message(client, userdata, msg):
            try:
                topic = msg.topic
                payload = msg.payload.decode("utf-8", errors="replace")
                # Expected topic: sentinel/{site_id}/energy/{field}
                prefix = f"sentinel/{site_id}/energy/"
                if topic.startswith(prefix) and topic != f"{prefix}last_updated":
                    field = topic[len(prefix) :]
                    if field in ENERGY_FIELDS:
                        if payload in ("", "null", "unavailable", "unknown"):
                            energy_values[field] = None
                        elif field == "geyser_state":
                            energy_values[field] = payload
                        else:
                            try:
                                energy_values[field] = float(payload)
                            except (ValueError, TypeError):
                                energy_values[field] = None
                elif topic == f"{prefix}last_updated":
                    try:
                        energy_values["_last_updated"] = datetime.fromisoformat(payload.replace("Z", "+00:00"))
                    except (ValueError, TypeError):
                        pass
            except Exception:
                pass

        energy_values["_last_updated"] = None
        mqtt_client.on_message = on_message

        # Subscribe to all energy topics
        energy_topics = [f"sentinel/{site_id}/energy/{f}" for f in ENERGY_FIELDS]
        energy_topics.append(f"sentinel/{site_id}/energy/last_updated")
        for t in energy_topics:
            mqtt_client.subscribe(t, qos=1)

        # Give it a moment to receive retained messages
        import time

        time.sleep(0.5)
        mqtt_client.loop_stop()
        mqtt_client.disconnect()

        last_updated = energy_values.pop("_last_updated", None)
        return {**energy_values, "last_updated": last_updated}

    @staticmethod
    def _get_loadshedding(
        area_code: str | None,
    ) -> tuple[int, int | None, datetime | None]:
        """Read loadshedding status from shared EskomSePush cache.

        Uses synchronous _area_cache dict directly — no API calls.
        """
        if not area_code:
            return 0, None, None

        try:
            from app.services.residential.eskomsepush_client import get_area_schedule

            schedule = get_area_schedule(area_code)
            if schedule is None:
                return 0, None, None

            stage = schedule.stage or 0
            minutes_to_next: int | None = None
            next_end: datetime | None = None

            if schedule.next_slot_start:
                delta = (schedule.next_slot_start - datetime.now(UTC)).total_seconds()
                minutes_to_next = max(0, int(delta / 60))
                next_end = schedule.next_slot_end

            return stage, minutes_to_next, next_end
        except Exception as exc:
            logger.warning("Could not get loadshedding for %s: %s", area_code, exc)
            return 0, None, None

    @staticmethod
    async def _get_historical_patterns(site_id: str) -> dict:
        """Read 7-day historical patterns from residential_readings table.

        If table does not exist, returns empty dict (graceful degradation).
        All historical fields will be None.
        """
        try:
            from app.database.supabase_client import get_supabase_client

            client = get_supabase_client()

            seven_days_ago = (datetime.now(UTC) - timedelta(days=7)).isoformat()

            result = (
                client.table("residential_readings")
                .select("pv_kwh,consumption_kwh,battery_soc_pct,timestamp")
                .eq("site_id", site_id)
                .gte("timestamp", seven_days_ago)
                .execute()
            )

            if not result.data:
                return {}

            import statistics

            pv_vals = [r["pv_kwh"] for r in result.data if r.get("pv_kwh") is not None]
            cons_vals = [r["consumption_kwh"] for r in result.data if r.get("consumption_kwh") is not None]

            avg_pv = statistics.mean(pv_vals) if pv_vals else None
            avg_cons = statistics.mean(cons_vals) if cons_vals else None

            return {
                "avg_daily_pv_kwh": round(avg_pv, 1) if avg_pv else None,
                "avg_daily_consumption_kwh": round(avg_cons, 1) if avg_cons else None,
            }
        except Exception:
            # Table doesn't exist or query fails — graceful degradation
            return {}
