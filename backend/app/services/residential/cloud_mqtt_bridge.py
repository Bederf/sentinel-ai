from __future__ import annotations

import json
import logging
import time
from dataclasses import dataclass, field
from datetime import UTC, datetime
from typing import TYPE_CHECKING

from app.adapters.residential.schemas import EnergySnapshot

try:
    import paho.mqtt.client as mqtt
except ImportError:
    mqtt = None  # type: ignore[assignment]

if TYPE_CHECKING:
    from app.adapters.residential.base import ResidentialEnergyAdapter

logger = logging.getLogger(__name__)

_ENERGY_FIELDS = (
    "pv_power_w",
    "battery_soc_pct",
    "battery_power_w",
    "grid_power_w",
    "load_power_w",
    "grid_voltage_v",
)

_MAX_AUTH_FAILURES = 3
_BACKOFF_BASE_SECONDS = 60

# SOC thresholds for dynamic polling interval (with hysteresis)
_SOC_LOW_THRESHOLD = 25.0  # reduce interval below this
_SOC_HIGH_THRESHOLD = 30.0  # restore interval above this
_SOC_ALERT_INTERVAL = 60  # seconds when battery is low


@dataclass
class _SiteState:
    adapter: ResidentialEnergyAdapter
    polling_interval: int = 300
    devices: list[str] = field(default_factory=list)
    auth_failures: int = 0
    backoff_until: float = 0.0
    in_low_soc_mode: bool = False
    eskom_area_code: str | None = None


class CloudToMQTTBridge:
    """Polls cloud energy adapters and publishes normalised data to Mosquitto."""

    def __init__(self) -> None:
        self._sites: dict[str, _SiteState] = {}

    def register_site(
        self,
        site_id: str,
        adapter: ResidentialEnergyAdapter,
        polling_interval: int = 300,
        eskom_area_code: str | None = None,
    ) -> None:
        self._sites[site_id] = _SiteState(
            adapter=adapter,
            polling_interval=polling_interval,
            eskom_area_code=eskom_area_code,
        )
        logger.info("Registered residential site %s", site_id)

    def unregister_site(self, site_id: str) -> None:
        self._sites.pop(site_id, None)
        logger.info("Unregistered residential site %s", site_id)

    async def poll_site(self, site_id: str) -> None:
        state = self._sites.get(site_id)
        if state is None:
            return

        if time.monotonic() < state.backoff_until:
            logger.debug("Site %s in backoff — skipping poll", site_id)
            return

        try:
            if not state.devices:
                ok = await state.adapter.authenticate()
                if not ok:
                    raise RuntimeError("authenticate() returned False")
                manifests = await state.adapter.discover_devices()
                state.devices = [m.device_id for m in manifests]

            for device_id in state.devices:
                snapshot = await state.adapter.get_realtime(device_id)
                self._publish_snapshot(site_id, snapshot)
                self._maybe_adjust_polling_interval(site_id, state, snapshot)

            self._publish_loadshedding(site_id, state)
            self._publish_freshness(site_id)

            state.auth_failures = 0
            state.backoff_until = 0.0

        except Exception as exc:
            state.auth_failures += 1
            logger.warning(
                "Poll failed for site %s (failure %d/%d): %s",
                site_id,
                state.auth_failures,
                _MAX_AUTH_FAILURES,
                exc,
            )
            if state.auth_failures >= _MAX_AUTH_FAILURES:
                backoff = _BACKOFF_BASE_SECONDS * (2 ** (state.auth_failures - _MAX_AUTH_FAILURES))
                state.backoff_until = time.monotonic() + backoff
                state.devices = []
                logger.error("Site %s exceeded max failures — backing off %ds", site_id, backoff)

    def _maybe_adjust_polling_interval(self, site_id: str, state: _SiteState, snapshot: EnergySnapshot) -> None:
        """Apply SOC hysteresis: reduce polling when battery is low, restore when recovered."""
        soc = snapshot.battery_soc_pct
        if soc is None:
            return

        if not state.in_low_soc_mode and soc < _SOC_LOW_THRESHOLD:
            state.in_low_soc_mode = True
            self._reschedule_polling(site_id, _SOC_ALERT_INTERVAL)
            logger.info("Site %s entering low-SOC polling mode (SOC=%.1f%%)", site_id, soc)

        elif state.in_low_soc_mode and soc >= _SOC_HIGH_THRESHOLD:
            state.in_low_soc_mode = False
            self._reschedule_polling(site_id, state.polling_interval)
            logger.info("Site %s restored normal polling (SOC=%.1f%%)", site_id, soc)

    def _reschedule_polling(self, site_id: str, interval_seconds: int) -> None:
        try:
            from apscheduler.triggers.interval import IntervalTrigger

            from app.services.background_scheduler import scheduler_service
            from app.services.residential.bridge_scheduler import _make_job_id

            job_id = _make_job_id(site_id)
            job = scheduler_service.scheduler.get_job(job_id)
            if job:
                job.reschedule(trigger=IntervalTrigger(seconds=interval_seconds))
        except Exception as exc:
            logger.warning("Could not reschedule polling for %s: %s", site_id, exc)

    def _publish_loadshedding(self, site_id: str, state: _SiteState) -> None:
        if not state.eskom_area_code:
            return
        try:
            from app.services.residential.eskomsepush_client import get_area_schedule

            schedule = get_area_schedule(state.eskom_area_code)
        except Exception:
            return

        if mqtt is None:
            return

        from app.config.settings import settings as _settings

        try:
            client = mqtt.Client(client_id=f"sentinel-residential-ls-{site_id}")
            if _settings.residential_mqtt_username:
                client.username_pw_set(_settings.residential_mqtt_username, _settings.residential_mqtt_password)
            client.connect(
                _settings.residential_mqtt_broker or "127.0.0.1", _settings.residential_mqtt_port, keepalive=10
            )

            if schedule is None:
                for suffix in ("stage", "next_slot", "source"):
                    info = client.publish(f"sentinel/{site_id}/loadshedding/{suffix}", "null", qos=1, retain=True)
                    info.wait_for_publish(timeout=2.0)
            else:
                source = "stale" if schedule.is_stale else "live"
                next_slot = schedule.next_slot_start.isoformat() if schedule.next_slot_start else None
                for topic, value in (
                    (f"sentinel/{site_id}/loadshedding/stage", json.dumps(schedule.stage)),
                    (f"sentinel/{site_id}/loadshedding/next_slot", json.dumps(next_slot)),
                    (f"sentinel/{site_id}/loadshedding/source", json.dumps(source)),
                ):
                    info = client.publish(topic, value, qos=1, retain=True)
                    info.wait_for_publish(timeout=2.0)
            client.disconnect()
        except Exception as exc:
            logger.warning("Loadshedding publish failed for site %s: %s", site_id, exc)

    def _publish_freshness(self, site_id: str) -> None:
        if mqtt is None:
            return
        from app.config.settings import settings as _settings

        try:
            client = mqtt.Client(client_id=f"sentinel-residential-hb-{site_id}")
            if _settings.residential_mqtt_username:
                client.username_pw_set(_settings.residential_mqtt_username, _settings.residential_mqtt_password)
            client.connect(
                _settings.residential_mqtt_broker or "127.0.0.1", _settings.residential_mqtt_port, keepalive=10
            )
            ts = datetime.now(UTC).isoformat()
            info = client.publish(f"sentinel/{site_id}/energy/last_updated", json.dumps(ts), qos=1, retain=True)
            info.wait_for_publish(timeout=2.0)
            client.disconnect()
        except Exception as exc:
            logger.warning("Freshness heartbeat publish failed for %s: %s", site_id, exc)

    def _publish_snapshot(self, site_id: str, snapshot: EnergySnapshot) -> None:
        try:
            if mqtt is None:
                logger.warning("paho-mqtt not installed — skipping publish for site %s", site_id)
                return

            from app.config.settings import settings as _settings

            client = mqtt.Client(client_id=f"sentinel-residential-bridge-{site_id}-{snapshot.device_id}")
            if _settings.residential_mqtt_username:
                client.username_pw_set(_settings.residential_mqtt_username, _settings.residential_mqtt_password)
            client.connect(
                _settings.residential_mqtt_broker or "127.0.0.1",
                _settings.residential_mqtt_port,
                keepalive=10,
            )
            for field_name in _ENERGY_FIELDS:
                value = getattr(snapshot, field_name)
                topic = f"sentinel/{site_id}/energy/{field_name}"
                payload = json.dumps(value)  # None → "null", float → "1234.5"
                info = client.publish(topic, payload, qos=1, retain=True)
                info.wait_for_publish(timeout=2.0)
            client.disconnect()
        except Exception as exc:
            logger.warning("MQTT publish failed for site %s: %s", site_id, exc)


_bridge = CloudToMQTTBridge()


def get_cloud_bridge() -> CloudToMQTTBridge:
    return _bridge
