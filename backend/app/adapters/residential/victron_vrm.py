from __future__ import annotations

import logging
import threading
from datetime import datetime

import httpx

from app.adapters.residential.base import ResidentialEnergyAdapter
from app.adapters.residential.schemas import AlarmEvent, DeviceManifest, EnergySnapshot

logger = logging.getLogger(__name__)


def _safe_float(value) -> float | None:
    if value is None:
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _derive_load(
    pv: float | None, grid: float | None, battery: float | None
) -> float | None:
    """Derive load from generation triangle. Returns None only if all inputs are None."""
    if pv is None and grid is None and battery is None:
        return None
    return (pv or 0.0) + (grid or 0.0) - (battery or 0.0)


class VictronVRMAdapter(ResidentialEnergyAdapter):
    BASE_URL = "https://vrmapi.victronenergy.com/v2"

    def __init__(self, site_config: dict) -> None:
        self._site_config = site_config
        self._token: str | None = None
        self._id_user: int | None = site_config.get("id_user")  # cached from prior auth
        self._token_needs_refresh = True
        self._token_lock = threading.Lock()

    # ── Token management ──────────────────────────────────────────────────────

    def _refresh_token(self) -> None:
        """Sync token refresh — safe for BackgroundScheduler threads."""
        username = self._site_config["username"]
        password = self._site_config["password"]
        with httpx.Client(timeout=15) as client:
            resp = client.post(
                f"{self.BASE_URL}/auth/login",
                json={"username": username, "password": password},
            )
            resp.raise_for_status()
            data = resp.json()
            self._token = data["token"]
            self._id_user = data["idUser"]
            self._token_needs_refresh = False

    def _get_token(self) -> str:
        """Double-checked locking for thread-safe token acquisition."""
        if not self._token_needs_refresh and self._token:
            return self._token
        with self._token_lock:
            if not self._token_needs_refresh and self._token:
                return self._token
            self._refresh_token()
        return self._token  # type: ignore[return-value]

    async def _request(self, method: str, path: str, **kwargs) -> dict:
        """Async request with one automatic token refresh on 401."""
        token = self._get_token()
        async with httpx.AsyncClient(timeout=30) as client:
            resp = await client.request(
                method,
                f"{self.BASE_URL}{path}",
                headers={"X-Authorization": f"Token {token}"},
                **kwargs,
            )
            if resp.status_code == 401:
                with self._token_lock:
                    self._token_needs_refresh = True
                token = self._get_token()
                resp = await client.request(
                    method,
                    f"{self.BASE_URL}{path}",
                    headers={"X-Authorization": f"Token {token}"},
                    **kwargs,
                )
            resp.raise_for_status()
            return resp.json()

    def _get_id_user(self) -> int:
        """Return cached idUser — guaranteed after _get_token() succeeds."""
        if self._id_user is None:
            self._get_token()
        return self._id_user  # type: ignore[return-value]

    # ── Widget helpers ────────────────────────────────────────────────────────

    def _extract_widget_value(self, widget_data: dict, key: str) -> float | None:
        records = widget_data.get("records", {})
        entry = records.get(key)
        if entry is None:
            return None
        if isinstance(entry, dict):
            return _safe_float(entry.get("value"))
        return _safe_float(entry)

    # ── ResidentialEnergyAdapter interface ────────────────────────────────────

    async def authenticate(self) -> bool:
        try:
            with self._token_lock:
                self._token_needs_refresh = True
                self._refresh_token()
            return True
        except Exception as exc:
            logger.warning("Victron VRM auth failed: %s", exc)
            return False

    async def discover_devices(self) -> list[DeviceManifest]:
        id_user = self._get_id_user()
        data = await self._request("GET", f"/users/{id_user}/installations")
        manifests = []
        for installation in data.get("records", []):
            id_site = installation.get("idSite")
            if id_site is None:
                continue
            name = installation.get("name", f"Installation {id_site}")
            has_battery = installation.get("hasBattery", False)
            has_generator = installation.get("hasGenerator", False)
            caps = ["pv", "grid", "load"]
            if has_battery:
                caps.append("battery")
            if has_generator:
                caps.append("generator")
            device_type = "inverter"
            if has_battery and not has_generator:
                device_type = "inverter"  # Multiplus/Quattro with battery
            manifests.append(
                DeviceManifest(
                    device_id=str(id_site),
                    device_name=name,
                    device_type=device_type,
                    source_system="victron",
                    capabilities=caps,
                )
            )
        return manifests

    async def get_realtime(self, device_id: str) -> EnergySnapshot:
        id_site = device_id
        battery_data, solar_data, grid_data = {}, {}, {}
        try:
            battery_data = await self._request(
                "GET", f"/installations/{id_site}/widgets/BatteryMonitor"
            )
        except Exception as exc:
            logger.debug("BatteryMonitor widget unavailable for %s: %s", id_site, exc)

        try:
            solar_data = await self._request(
                "GET", f"/installations/{id_site}/widgets/SolarChargerSummary"
            )
        except Exception as exc:
            logger.debug("SolarChargerSummary widget unavailable for %s: %s", id_site, exc)

        try:
            grid_data = await self._request(
                "GET", f"/installations/{id_site}/widgets/GridMeter"
            )
        except Exception as exc:
            logger.debug("GridMeter widget unavailable for %s: %s", id_site, exc)

        pv_power_w = self._extract_widget_value(solar_data, "Ppv")
        battery_soc_pct = self._extract_widget_value(battery_data, "Soc")
        battery_power_w = self._extract_widget_value(battery_data, "P")
        grid_power_w = self._extract_widget_value(grid_data, "Power")
        grid_voltage_v = self._extract_widget_value(grid_data, "VoltageL1")
        battery_soh_pct = self._extract_widget_value(battery_data, "Soh")

        load_power_w = _derive_load(pv_power_w, grid_power_w, battery_power_w)

        return EnergySnapshot(
            site_id=self._site_config.get("site_id", ""),
            device_id=device_id,
            timestamp=datetime.utcnow(),
            pv_power_w=pv_power_w,
            battery_soc_pct=battery_soc_pct,
            battery_power_w=battery_power_w,
            grid_power_w=grid_power_w,
            load_power_w=load_power_w,
            grid_voltage_v=grid_voltage_v,
            battery_soh_pct=battery_soh_pct,
            source_system="victron",
        )

    async def get_historical(
        self, device_id: str, start: datetime, end: datetime
    ) -> list[EnergySnapshot]:
        data = await self._request(
            "GET",
            f"/installations/{device_id}/stats",
            params={
                "type": "custom",
                "start": int(start.timestamp()),
                "end": int(end.timestamp()),
                "interval": "hours",
            },
        )
        snapshots = []
        records = data.get("records", {})
        pv_series = records.get("Ppv", [])
        soc_series = records.get("batteryMonitorState", [])
        grid_series = records.get("gridPower", [])

        # Align by index — series are same length and time-aligned
        for i, pv_entry in enumerate(pv_series):
            ts_raw = pv_entry.get("timestamp")
            if ts_raw is None:
                continue
            ts = datetime.utcfromtimestamp(ts_raw)
            pv = _safe_float(pv_entry.get("value"))
            soc_entry = soc_series[i] if i < len(soc_series) else {}
            soc = _safe_float(soc_entry.get("value")) if isinstance(soc_entry, dict) else None
            grid_entry = grid_series[i] if i < len(grid_series) else {}
            grid = _safe_float(grid_entry.get("value")) if isinstance(grid_entry, dict) else None
            snapshots.append(
                EnergySnapshot(
                    site_id=self._site_config.get("site_id", ""),
                    device_id=device_id,
                    timestamp=ts,
                    pv_power_w=pv,
                    battery_soc_pct=soc,
                    battery_power_w=None,  # stats endpoint lacks per-sample battery power
                    grid_power_w=grid,
                    load_power_w=_derive_load(pv, grid, None),
                    grid_voltage_v=None,
                    battery_soh_pct=None,
                    source_system="victron",
                )
            )
        return snapshots

    async def get_alarms(self, device_id: str) -> list[AlarmEvent]:
        data = await self._request("GET", f"/installations/{device_id}/alarms")
        alarms = []
        for alarm in data.get("alarms", []):
            code = str(alarm.get("idAlarm", ""))
            message = alarm.get("description") or alarm.get("name", "")
            raw_severity = alarm.get("severity", "warning").lower()
            severity: str
            if raw_severity in ("critical", "fault"):
                severity = "critical"
            elif raw_severity == "error":
                severity = "error"
            else:
                severity = "warning"
            ts_raw = alarm.get("started")
            ts = datetime.utcfromtimestamp(ts_raw) if ts_raw else datetime.utcnow()
            alarms.append(
                AlarmEvent(
                    device_id=device_id,
                    alarm_code=code,
                    alarm_message=message,
                    severity=severity,
                    timestamp=ts,
                    is_active=alarm.get("ended") is None,
                )
            )
        return alarms
