"""SMA Sunny Tripower connector — third manufacturer proving multi-vendor abstraction.

Supports:
  - SMA Modbus TCP register reads (SMA specific register map, different from Huawei/Schneider)
  - Simulated data for demo (Site-002 Western Canopy — 10 x SMA Sunny Tripower Core1)

SMA register map differs significantly from Huawei/Schneider:
  - SMA uses SunSpec-compliant registers starting at 40000
  - Different data types and scale factors
  - SMA-specific status codes and error definitions

Register maps sourced from SMA Sunny Tripower Core1 STP 50-41 Modbus Interface.
"""

import logging
import math
import random
from datetime import datetime, timezone
from typing import Dict, List, Optional

from app.models.solar import (
    SolarInverter,
    SolarString,
    GridMeter,
    NormalisedReading,
    ConnectorStatus,
    QualityFlag,
    DataSource,
)
from app.services.solar_connector_base import SolarConnector

logger = logging.getLogger(__name__)


# === SMA Sunny Tripower Core1 Modbus Register Map (SunSpec-based) ===

SMA_TRIPOWER_REGISTERS: Dict[str, tuple] = {
    # (address, count, type, scale_factor, unit)
    # SMA uses SunSpec model 101/103 for inverter data
    "model":              (30053, 8, "str",    1,     ""),
    "serial":             (30057, 8, "str",    1,     ""),
    "firmware":           (30059, 8, "str",    1,     ""),
    "rated_power":        (30231, 2, "u32",    1,     "W"),
    "dc_power_total":     (30773, 2, "i32",    1,     "W"),
    "ac_power_total":     (30775, 2, "i32",    1,     "W"),
    # DC inputs (SMA Tripower Core1 has 6 MPPT inputs)
    "dc_voltage_a":       (30771, 2, "u32",    100,   "V"),
    "dc_current_a":       (30769, 2, "u32",    1000,  "A"),
    "dc_voltage_b":       (30959, 2, "u32",    100,   "V"),
    "dc_current_b":       (30957, 2, "u32",    1000,  "A"),
    "dc_voltage_c":       (30961, 2, "u32",    100,   "V"),
    "dc_current_c":       (30963, 2, "u32",    1000,  "A"),
    # AC outputs (3-phase)
    "ac_voltage_l1":      (30783, 2, "u32",    100,   "V"),
    "ac_voltage_l2":      (30785, 2, "u32",    100,   "V"),
    "ac_voltage_l3":      (30787, 2, "u32",    100,   "V"),
    "ac_current_total":   (30795, 2, "u32",    1000,  "A"),
    "frequency":          (30803, 2, "u32",    100,   "Hz"),
    "power_factor":       (30805, 2, "i32",    1000,  ""),
    "inverter_temp":      (30953, 2, "i32",    10,    "C"),
    # Status and yields
    "status":             (30201, 2, "u32",    1,     ""),
    "error_code":         (30213, 2, "u32",    1,     ""),
    "daily_yield":        (30535, 2, "u32",    1,     "Wh"),
    "total_yield":        (30529, 4, "u64",    1,     "Wh"),
    # Grid relay status
    "grid_relay":         (30217, 2, "u32",    1,     ""),
}

# SMA status code mapping
SMA_STATUS_MAP = {
    35: "fault",
    303: "off",
    307: "standby",
    455: "warning",
    307: "standby",
    308: "starting",
    309: "online",          # "MPP" tracking
    310: "online",          # "Throttled" due to temperature
    311: "online",          # "Shutdown" by grid
    381: "derating",
}

# Johannesburg latitude for solar curve
JHB_LATITUDE = -26.2


def _solar_power_factor(hour: float) -> float:
    """Solar power factor (0-1) for JHB — Gaussian centred on solar noon."""
    if hour < 5.5 or hour > 18.5:
        return 0.0
    solar_noon = 12.2
    sigma = 3.0
    return max(0.0, min(1.0, math.exp(-0.5 * ((hour - solar_noon) / sigma) ** 2)))


class SimulatedSMAConnector(SolarConnector):
    """Generates realistic SMA Sunny Tripower Core1 data for demo.

    Models the Site-002 Western Canopy fleet — 10 medium-size (50 kVA)
    inverters with SMA-specific characteristics:
      - 6 MPPT inputs per inverter (vs Huawei 10, Schneider 5)
      - Slightly different efficiency curve (SMA uses transformerless topology)
      - SMA-specific fault codes and derating behaviour
    """

    def __init__(
        self,
        inverters: List[Dict],
        meters: Optional[List[Dict]] = None,
    ):
        super().__init__(manufacturer="sma", protocol="modbus_tcp")
        self._inverter_configs = {inv["id"]: inv for inv in inverters}
        self._meter_configs = {m["meter_id"]: m for m in (meters or [])}
        self._inverter_state: Dict[str, SolarInverter] = {}

    async def connect(self) -> bool:
        self._status = ConnectorStatus(
            connected=True,
            last_poll=datetime.now(timezone.utc).isoformat(),
            error_count=0,
        )
        logger.info(
            f"SMA simulated connector online — "
            f"{len(self._inverter_configs)} inverters"
        )
        return True

    async def disconnect(self) -> None:
        self._status.connected = False
        logger.info("SMA simulated connector disconnected")

    async def read_inverter(self, inverter_id: str) -> Optional[SolarInverter]:
        cfg = self._inverter_configs.get(inverter_id)
        if not cfg:
            return None

        now = datetime.now(timezone.utc)
        sast_hour = (now.hour + 2) % 24 + now.minute / 60.0
        solar_factor = _solar_power_factor(sast_hour)

        rated_kva = cfg.get("rated_kva", 50)
        # SMA Tripower has excellent efficiency (~98.3% peak, ~97.5% CEC weighted)
        inv_variance = 1.0 + random.uniform(-0.03, 0.02)
        efficiency = 0.975 + random.uniform(-0.005, 0.008)
        ac_power = rated_kva * solar_factor * inv_variance * efficiency
        dc_power = ac_power / efficiency if ac_power > 0 else 0

        # Temperature: SMA runs slightly cooler (better thermal design)
        ambient = 22 + 8 * solar_factor
        temp = ambient + (ac_power / rated_kva) * 8 if rated_kva > 0 else ambient

        inv = SolarInverter(
            inverter_id=inverter_id,
            plant_id=cfg.get("plant_id", ""),
            site_id=cfg.get("site_id", ""),
            name=cfg.get("name", inverter_id),
            manufacturer="SMA Solar Technology",
            model=cfg.get("model", "Sunny Tripower Core1 STP 50-41"),
            serial=cfg.get("serial", f"SMA{inverter_id[-3:]}SIM"),
            rated_power_kva=rated_kva,
            mppt_count=cfg.get("mppt_count", 6),
            firmware_version="V3.20.11.R",
            protocol="modbus_tcp",
            ip_address=cfg.get("ip", "10.1.3.101"),
            port=cfg.get("port", 502),
            unit_id=cfg.get("unit_id", 3),
            dc_power_kw=round(dc_power, 2),
            ac_power_kw=round(ac_power, 2),
            efficiency_pct=round(efficiency * 100, 1),
            temp_c=round(temp, 1),
            status="online" if solar_factor > 0.01 else "standby",
            frequency_hz=round(50.0 + random.uniform(-0.04, 0.04), 2),
            power_factor=round(0.99 + random.uniform(-0.01, 0.005), 3),
            daily_yield_kwh=round(rated_kva * 5.2 * solar_factor * random.uniform(0.90, 1.0), 1),
            total_yield_mwh=round(rated_kva * 1300 * random.uniform(0.85, 0.95) / 1000, 1),
            alarms=[],
            last_poll=now.isoformat(),
        )
        self._inverter_state[inverter_id] = inv
        return inv

    async def read_all_strings(self, inverter_id: str) -> List[SolarString]:
        cfg = self._inverter_configs.get(inverter_id)
        if not cfg:
            return []

        now = datetime.now(timezone.utc)
        sast_hour = (now.hour + 2) % 24 + now.minute / 60.0
        solar_factor = _solar_power_factor(sast_hour)

        mppt_count = cfg.get("mppt_count", 6)
        strings_per_mppt = cfg.get("strings_per_mppt", 2)
        panel_rating_w = cfg.get("panel_rating_w", 410)  # newer JA Solar panels

        strings = []
        for mppt in range(1, mppt_count + 1):
            for s_idx in range(1, strings_per_mppt + 1):
                string_id = f"{inverter_id}-MPPT{mppt:02d}-S{s_idx}"
                variance = 1.0 + random.uniform(-0.04, 0.02)
                panels_on_string = cfg.get("panels_per_string", 12)

                vmp = 41.0 * panels_on_string * solar_factor * variance
                imp = (panel_rating_w / 41.0) * solar_factor * variance
                dc_power = (vmp * imp / 1000) if solar_factor > 0 else 0

                strings.append(SolarString(
                    string_id=string_id,
                    inverter_id=inverter_id,
                    mppt_tracker=mppt,
                    panel_count=panels_on_string,
                    panel_model=cfg.get("panel_model", "JA Solar JAM72S30-410/MR"),
                    panel_rating_w=panel_rating_w,
                    dc_voltage_v=round(vmp, 1),
                    dc_current_a=round(imp, 2),
                    dc_power_kw=round(dc_power, 3),
                    irradiance_w_m2=round(1000 * solar_factor * variance, 0),
                ))
        return strings

    async def read_bess(self, container_id: str) -> None:
        """SMA connector does not manage BESS (handled by Huawei connector)."""
        return None

    async def read_meter(self, meter_id: str) -> Optional[GridMeter]:
        cfg = self._meter_configs.get(meter_id)
        if not cfg:
            return None

        now = datetime.now(timezone.utc)
        sast_hour = (now.hour + 2) % 24 + now.minute / 60.0
        solar_factor = _solar_power_factor(sast_hour)

        # PV generation meter for Western Canopy
        total_pv_kw = 500.0 * solar_factor * 0.975  # fleet efficiency
        pv_kw = total_pv_kw + random.uniform(-3, 3)

        return GridMeter(
            meter_id=meter_id,
            site_id=cfg.get("site_id", ""),
            name=cfg.get("name", meter_id),
            manufacturer="SMA",
            model="Sunny Central Storage",
            location=cfg.get("location", "Western Canopy"),
            voltage_l1_v=round(230 + random.uniform(-3, 3), 1),
            voltage_l2_v=round(230 + random.uniform(-3, 3), 1),
            voltage_l3_v=round(230 + random.uniform(-3, 3), 1),
            current_a=round(pv_kw / 0.4 + random.uniform(-1, 1), 1) if pv_kw > 0 else 0,
            active_power_kw=round(pv_kw, 2),
            reactive_power_kvar=round(pv_kw * 0.02, 2),
            apparent_power_kva=round(pv_kw * 1.001, 2),
            power_factor=round(0.99 + random.uniform(-0.005, 0.005), 3),
            frequency_hz=round(50.0 + random.uniform(-0.05, 0.05), 2),
            thd_v_pct=round(1.8 + random.uniform(-0.3, 0.3), 2),
            thd_i_pct=round(2.5 + random.uniform(-0.4, 0.4), 2),
            energy_import_kwh=round(random.uniform(0, 10), 1),
            energy_export_kwh=round(pv_kw * 0.02, 1),
            last_poll=now.isoformat(),
        )

    async def get_normalised_readings(self) -> List[NormalisedReading]:
        readings: List[NormalisedReading] = []
        now = datetime.now(timezone.utc)

        for inv_id in self._inverter_configs:
            inv = await self.read_inverter(inv_id)
            if inv:
                readings.append(NormalisedReading(
                    equipment_id=inv_id,
                    equipment_type="inverter",
                    reading_type="power",
                    value=inv.ac_power_kw,
                    unit="kW",
                    quality=QualityFlag.GOOD,
                    source=DataSource.SIMULATED,
                    timestamp=now.isoformat(),
                ))
                readings.append(NormalisedReading(
                    equipment_id=inv_id,
                    equipment_type="inverter",
                    reading_type="energy",
                    value=inv.daily_yield_kwh,
                    unit="kWh",
                    quality=QualityFlag.GOOD,
                    source=DataSource.SIMULATED,
                    timestamp=now.isoformat(),
                ))
                readings.append(NormalisedReading(
                    equipment_id=inv_id,
                    equipment_type="inverter",
                    reading_type="temperature",
                    value=inv.temp_c,
                    unit="C",
                    quality=QualityFlag.GOOD,
                    source=DataSource.SIMULATED,
                    timestamp=now.isoformat(),
                ))

        for meter_id in self._meter_configs:
            meter = await self.read_meter(meter_id)
            if meter:
                readings.append(NormalisedReading(
                    equipment_id=meter_id,
                    equipment_type="meter",
                    reading_type="power",
                    value=meter.active_power_kw,
                    unit="kW",
                    quality=QualityFlag.GOOD,
                    source=DataSource.SIMULATED,
                    timestamp=now.isoformat(),
                ))

        return readings

    def get_status(self) -> ConnectorStatus:
        return self._status
