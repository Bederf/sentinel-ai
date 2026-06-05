from __future__ import annotations

import logging
from datetime import UTC, datetime, timedelta
from typing import Any

from app.config.settings import settings
from app.database.supabase_client import get_supabase_client
from app.services.residential.residential_telegram_sender import ResidentialTelegramSender

logger = logging.getLogger(__name__)


class MorningSummaryService:
    """Sends daily 07:00 SAST morning summary messages per residential site.

    For new sites without history, sends current status only and notes that a full
    summary will be available tomorrow.
    """

    def __init__(self) -> None:
        self._sender = ResidentialTelegramSender()

    def _read_current_status(self, site_id: str) -> dict[str, Any]:
        """Read retained MQTT values for current status.

        Returns dict including 'last_updated' if available.
        """
        try:
            import paho.mqtt.client as mqtt
        except Exception:
            mqtt = None  # type: ignore[assignment]

        result: dict[str, Any] = {
            "battery_soc_pct": None,
            "pv_power_w": None,
            "grid_power_w": None,
            "load_power_w": None,
            "last_updated": None,
        }

        if mqtt is None:
            return result

        values: dict[str, Any] = {"_last": None}

        def _on_message(client, userdata, msg):
            try:
                topic = msg.topic
                payload = msg.payload.decode("utf-8", errors="replace")
                prefix = f"sentinel/{site_id}/energy/"
                if topic.startswith(prefix):
                    field = topic[len(prefix) :]
                    if field == "last_updated":
                        try:
                            values["_last"] = datetime.fromisoformat(payload.replace("Z", "+00:00"))
                        except Exception:
                            pass
                    else:
                        try:
                            values[field] = float(payload)
                        except Exception:
                            values[field] = payload
            except Exception:
                pass

        client = mqtt.Client(client_id=f"sentinel-morning-{site_id}")
        try:
            if settings.residential_mqtt_username:
                client.username_pw_set(settings.residential_mqtt_username, settings.residential_mqtt_password)
            client.connect(
                settings.residential_mqtt_broker or "127.0.0.1", settings.residential_mqtt_port, keepalive=10
            )
            client.on_message = _on_message
            topics = [
                f"sentinel/{site_id}/energy/battery_soc_pct",
                f"sentinel/{site_id}/energy/pv_power_w",
                f"sentinel/{site_id}/energy/grid_power_w",
                f"sentinel/{site_id}/energy/load_power_w",
                f"sentinel/{site_id}/energy/last_updated",
            ]
            client.loop_start()
            for t in topics:
                client.subscribe(t, qos=0)
            # Short dwell to receive retained messages
            import time as _t

            _t.sleep(0.5)
        except Exception as exc:
            logger.warning("Morning summary MQTT read failed for %s: %s", site_id, exc)
        finally:
            try:
                client.loop_stop()
                client.disconnect()
            except Exception:
                pass

        result.update({k: values.get(k) for k in ("battery_soc_pct", "pv_power_w", "grid_power_w", "load_power_w")})
        result["last_updated"] = values.get("_last")
        return result

    def _format_summary(self, site_id: str, status: dict[str, Any], loadshedding: dict[str, Any] | None) -> str:
        now = datetime.now(UTC)
        lines: list[str] = []

        # Yesterday section — until we add history, emit the short message
        lines.append("Monitoring started — full summary available tomorrow.")

        # Current status
        soc = status.get("battery_soc_pct")
        pv = status.get("pv_power_w")
        grid = status.get("grid_power_w")
        last = status.get("last_updated")

        grid_status = "Grid available" if (isinstance(grid, (int, float)) and grid and grid > 0) else "Off-grid"
        lines.append("")
        lines.append(f"Right now:")
        if soc is not None:
            try:
                lines.append(f"🔋 Battery: {float(soc):.0f}%")
            except Exception:
                pass
        if pv is not None:
            try:
                lines.append(f"☀️ Solar: {float(pv):.0f}W")
            except Exception:
                pass
        if grid is not None:
            try:
                lines.append(f"🔌 Grid: {grid_status}")
            except Exception:
                pass
        if isinstance(last, datetime):
            age_min = int((now - last.replace(tzinfo=UTC)).total_seconds() / 60)
            if age_min > 15:
                lines.append(f"(last updated {age_min} min ago)")

        # Loadshedding
        if loadshedding and loadshedding.get("area"):
            stage = loadshedding.get("stage", 0)
            slots = loadshedding.get("slots", [])
            lines.append("")
            if stage and stage > 0:
                lines.append(f"Today's loadshedding (Stage {stage}):")
                for s in slots:
                    lines.append(f"• {s}")
            else:
                lines.append("No shedding scheduled ✅")
        else:
            lines.append("")
            lines.append("Set your area code via /setarea for loadshedding alerts.")

        return "\n".join(lines)

    def _get_loadshedding(self, area_code: str | None) -> dict[str, Any] | None:
        if not area_code:
            return None
        try:
            from app.services.residential.eskomsepush_client import get_area_schedule

            sched = get_area_schedule(area_code)
            if not sched:
                return {"area": area_code, "stage": 0, "slots": []}
            slots: list[str] = []
            # Best-effort: format next_slot_start only
            if sched.next_slot_start and sched.next_slot_end:
                start = sched.next_slot_start.astimezone(UTC).strftime("%H:%M UTC")
                end = sched.next_slot_end.astimezone(UTC).strftime("%H:%M UTC")
                slots.append(f"{start} – {end}")
            return {"area": area_code, "stage": sched.stage or 0, "slots": slots}
        except Exception as exc:
            logger.warning("Loadshedding lookup failed for %s: %s", area_code, exc)
            return {"area": area_code, "stage": 0, "slots": []}

    async def send_summary(self, site_id: str) -> None:
        """Async entry point for APScheduler to send the morning summary."""
        try:
            sb = get_supabase_client()
            row = (
                sb.table("residential_sites").select("chat_id, eskom_area_code").eq("site_id", site_id).maybe_execute()
            )
            if not row.data:
                return
            chat_id = row.data[0].get("chat_id")
            area_code = row.data[0].get("eskom_area_code")
            if not chat_id:
                return

            status = self._read_current_status(site_id)
            ls = self._get_loadshedding(area_code)
            msg = self._format_summary(site_id, status, ls)
            await self._sender.send_text(int(chat_id), msg)
        except Exception as exc:
            logger.error("Failed to send morning summary for %s: %s", site_id, exc)
