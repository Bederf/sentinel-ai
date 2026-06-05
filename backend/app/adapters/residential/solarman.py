from __future__ import annotations

import hashlib
import logging
import threading
from datetime import datetime

import httpx

from app.adapters.residential.base import ResidentialEnergyAdapter
from app.adapters.residential.schemas import AlarmEvent, DeviceManifest, EnergySnapshot

logger = logging.getLogger(__name__)


class SolarmanAdapter(ResidentialEnergyAdapter):
    BASE_URL = "https://globalapi.solarmanpv.com"

    def __init__(self, site_config: dict, app_id: str, app_secret: str) -> None:
        self._site_config = site_config
        self._app_id = app_id
        self._app_secret = app_secret
        self._access_token: str | None = None
        self._user_id: int | None = None
        self._token_needs_refresh = True
        self._token_lock = threading.Lock()

    # ── Token management ─────────────────────────────────────────────────────

    def _refresh_token(self) -> None:
        """Sync token refresh using httpx.Client — safe for BackgroundScheduler threads."""
        email = self._site_config["email"]
        password_hash = hashlib.sha256(self._site_config["password"].encode()).hexdigest()
        with httpx.Client(timeout=15) as client:
            resp = client.post(
                f"{self.BASE_URL}/account/v1.0/token",
                params={"appId": self._app_id, "language": "en"},
                json={
                    "email": email,
                    "appSecret": self._app_secret,
                    "password": password_hash,
                },
            )
            resp.raise_for_status()
            body = resp.json()
            self._access_token = body["access_token"]
            self._user_id = body.get("uid")
            self._token_needs_refresh = False

    def _get_token(self) -> str:
        """Double-checked locking for thread-safe token acquisition."""
        if not self._token_needs_refresh and self._access_token:
            return self._access_token
        with self._token_lock:
            if not self._token_needs_refresh and self._access_token:
                return self._access_token
            self._refresh_token()
        return self._access_token  # type: ignore[return-value]

    async def _request(self, method: str, path: str, **kwargs) -> dict:
        """Async request with one automatic token refresh on 401."""
        token = self._get_token()
        async with httpx.AsyncClient(timeout=30) as client:
            resp = await client.request(
                method,
                f"{self.BASE_URL}{path}",
                headers={"Authorization": f"Bearer {token}"},
                **kwargs,
            )
            if resp.status_code == 401:
                with self._token_lock:
                    self._token_needs_refresh = True
                token = self._get_token()
                resp = await client.request(
                    method,
                    f"{self.BASE_URL}{path}",
                    headers={"Authorization": f"Bearer {token}"},
                    **kwargs,
                )
            resp.raise_for_status()
            return resp.json()

    # ── ResidentialEnergyAdapter interface ───────────────────────────────────

    async def authenticate(self) -> bool:
        try:
            with self._token_lock:
                self._token_needs_refresh = True
                self._refresh_token()
            return True
        except Exception:
            return False

    async def discover_devices(self) -> list[DeviceManifest]:
        data = await self._request(
            "POST",
            "/station/v1.0/list",
            json={"page": 1, "size": 100, "userId": self._user_id},
        )
        return [
            DeviceManifest(
                device_id=str(plant["id"]),
                device_name=plant.get("name", ""),
                device_type="inverter",
                source_system="solarman",
                capabilities=["pv", "grid", "load"],
            )
            for plant in data.get("stationList", [])
        ]

    async def get_realtime(self, device_id: str) -> EnergySnapshot:
        data = await self._request(
            "POST",
            "/v1.0/device/currentData",
            json={"deviceSn": device_id},
        )
        attrs = {item["key"]: item.get("value") for item in data.get("dataList", [])}

        def _float(key: str) -> float | None:
            val = attrs.get(key)
            try:
                return float(val) if val is not None else None
            except (TypeError, ValueError):
                return None

        return EnergySnapshot(
            site_id=self._site_config.get("site_id", ""),
            device_id=device_id,
            timestamp=datetime.utcnow(),
            pv_power_w=_float("generationPower"),
            battery_soc_pct=_float("batterySoc"),
            battery_power_w=_float("batteryPower"),
            grid_power_w=_float("purchasePower"),
            load_power_w=_float("usePower"),
            grid_voltage_v=_float("gridVoltage"),
            source_system="solarman",
        )

    async def get_historical(self, device_id: str, start: datetime, end: datetime) -> list[EnergySnapshot]:
        data = await self._request(
            "POST",
            "/v1.0/device/historical",
            json={
                "deviceSn": device_id,
                "startTime": int(start.timestamp()),
                "endTime": int(end.timestamp()),
                "timeType": 1,
            },
        )
        snapshots = []
        for record in data.get("dataList", []):
            attrs = {item["key"]: item.get("value") for item in record.get("dataList", [])}

            def _float(key: str, _attrs: dict = attrs) -> float | None:
                val = _attrs.get(key)
                try:
                    return float(val) if val is not None else None
                except (TypeError, ValueError):
                    return None

            snapshots.append(
                EnergySnapshot(
                    site_id=self._site_config.get("site_id", ""),
                    device_id=device_id,
                    timestamp=datetime.utcfromtimestamp(record.get("collectTime", 0)),
                    pv_power_w=_float("generationPower"),
                    battery_soc_pct=_float("batterySoc"),
                    battery_power_w=_float("batteryPower"),
                    grid_power_w=_float("purchasePower"),
                    load_power_w=_float("usePower"),
                    grid_voltage_v=_float("gridVoltage"),
                    source_system="solarman",
                )
            )
        return snapshots

    async def get_alarms(self, device_id: str) -> list[AlarmEvent]:
        data = await self._request(
            "POST",
            "/v1.0/device/alarm",
            json={"deviceSn": device_id, "page": 1, "size": 50},
        )
        return [
            AlarmEvent(
                device_id=device_id,
                alarm_code=str(alarm.get("alarmCode", "")),
                alarm_message=alarm.get("alarmMessage", ""),
                severity="error" if alarm.get("alarmLevel", 1) >= 2 else "warning",
                timestamp=datetime.utcfromtimestamp(alarm.get("alarmTime", 0)),
                is_active=alarm.get("alarmStatus", 0) == 1,
            )
            for alarm in data.get("alarmList", [])
        ]
