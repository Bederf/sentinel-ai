from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime


@dataclass
class EnergySnapshot:
    site_id: str
    device_id: str
    timestamp: datetime
    pv_power_w: float | None
    battery_soc_pct: float | None
    battery_power_w: float | None
    grid_power_w: float | None
    load_power_w: float | None
    grid_voltage_v: float | None
    battery_soh_pct: float | None = None  # Victron only; None for other platforms
    source_system: str = ""  # "solarman"|"victron"|"growatt"|"fronius"|"home_assistant"
    # Home Assistant extended fields (None for non-HA platforms)
    geyser_power_w: float | None = None
    geyser_state: str | None = None  # "on" | "off" | None
    ev_charger_power_w: float | None = None


@dataclass
class DeviceManifest:
    device_id: str
    device_name: str
    device_type: str  # "inverter"|"battery"|"logger"|"meter"
    source_system: str
    capabilities: list[str] = field(default_factory=list)  # ["pv","battery","grid","load"]


@dataclass
class AlarmEvent:
    device_id: str
    alarm_code: str
    alarm_message: str
    severity: str  # "warning"|"error"|"critical"
    timestamp: datetime
    is_active: bool = True
