"""Schneider Electric connector — Conext CL series inverters + PM metering.

Supports:
  - Modbus TCP register reads (holding registers)
  - Simulated data for demo (legacy inverter fleet with realistic patterns)

Register maps sourced from Schneider Conext CL25000E Modbus Register Map.
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


# === Schneider Conext CL Modbus Register Map (Holding Registers) ===
SCHNEIDER_CONEXT_REGISTERS: Dict[str, tuple] = {
    # (address, count, type, scale_factor, unit)
    "model":           (40005, 8, "str",    1,     ""),
    "serial":          (40013, 8, "str",    1,     ""),
    "firmware":        (40021, 8, "str",    1,     ""),
    "rated_power":     (40071, 2, "u32",    1,     "W"),
    "dc_power":        (40101, 2, "i32",    1,     "W"),
    "ac_power":        (40103, 2, "i32",    1,     "W"),
    "dc_voltage":      (40105, 1, "u16",    10,    "V"),
    "dc_current":      (40106, 1, "u16",    100,   "A"),
    "ac_voltage_l1":   (40107, 1, "u16",    10,    "V"),
    "ac_voltage_l2":   (40108, 1, "u16",    10,    "V"),
    "ac_voltage_l3":   (40109, 1, "u16",    10,    "V"),
    "ac_current":      (40110, 1, "u16",    100,   "A"),
    "frequency":       (40111, 1, "u16",    100,   "Hz"),
    "power_factor":    (40112, 1, "i16",    1000,  ""),
    "inverter_temp":   (40113, 1, "i16",    10,    "C"),
    "status":          (40115, 1, "u16",    1,     ""),
    "error_code":      (40116, 2, "u32",    1,     ""),
    "daily_yield":     (40120, 2, "u32",    1,     "Wh"),
    "total_yield":     (40122, 2, "u32",    1,     "Wh"),
    # MPPT inputs (Conext CL has 2-5 MPPT depending on model)
    "pv1_voltage":     (40131, 1, "u16",    10,    "V"),
    "pv1_current":     (40132, 1, "u16",    100,   "A"),
    "pv2_voltage":     (40133, 1, "u16",    10,    "V"),
    "pv2_current":     (40134, 1, "u16",    100,   "A"),
}

# Schneider PM8000 / PM5110 meter registers
SCHNEIDER_PM_REGISTERS: Dict[str, tuple] = {
    "voltage_l1":      (3000, 2, "float32", 1,    "V"),
    "voltage_l2":      (3002, 2, "float32", 1,    "V"),
    "voltage_l3":      (3004, 2, "float32", 1,    "V"),
    "current_l1":      (3006, 2, "float32", 1,    "A"),
    "current_l2":      (3008, 2, "float32", 1,    "A"),
    "current_l3":      (3010, 2, "float32", 1,    "A"),
    "active_power":    (3054, 2, "float32", 1,    "kW"),
    "reactive_power":  (3058, 2, "float32", 1,    "kVAR"),
    "apparent_power":  (3062, 2, "float32", 1,    "kVA"),
    "power_factor":    (3066, 2, "float32", 1,    ""),
    "frequency":       (3110, 2, "float32", 1,    "Hz"),
    "thd_v":           (3114, 2, "float32", 1,    "%"),
    "thd_i":           (3118, 2, "float32", 1,    "%"),
    "energy_import":   (3204, 2, "float32", 1,    "kWh"),
    "energy_export":   (3208, 2, "float32", 1,    "kWh"),
}

# Schneider status code mapping
SCHNEIDER_STATUS_MAP = {
    0: "standby",
    1: "online",
    2: "warning",
    3: "fault",
    4: "offline",
}

# Johannesburg latitude
JHB_LATITUDE = -26.2


def _solar_power_factor(hour: float) -> float:
    """Solar power factor (0-1) for JHB."""
    if hour < 5.5 or hour > 18.5:
        return 0.0
    solar_noon = 12.2
    sigma = 3.0
    return max(0.0, min(1.0, math.exp(-0.5 * ((hour - solar_noon) / sigma) ** 2)))


class SimulatedSchneiderConnector(SolarConnector):
    """Generates realistic Schneider Conext CL data for demo.

    Models the legacy Eastern Carports fleet — 23 smaller (25 kVA) inverters.
    Slightly lower efficiency than Huawei fleet to model aging equipment.
    """

    def __init__(
        self,
        inverters: List[Dict],
        meters: Optional[List[Dict]] = None,
    ):
        super().__init__(manufacturer="schneider", protocol="modbus_tcp")
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
            f"Schneider simulated connector online — "
            f"{len(self._inverter_configs)} inverters"
        )
        return True

    async def disconnect(self) -> None:
        self._status.connected = False
        logger.info("Schneider simulated connector disconnected")

    async def read_inverter(self, inverter_id: str) -> Optional[SolarInverter]:
        cfg = self._inverter_configs.get(inverter_id)
        if not cfg:
            return None

        now = datetime.now(timezone.utc)
        sast_hour = (now.hour + 2) % 24 + now.minute / 60.0
        solar_factor = _solar_power_factor(sast_hour)

        rated_kva = cfg.get("rated_kva", 25)
        # Schneider fleet is older, slightly lower efficiency (~94%)
        inv_variance = 1.0 + random.uniform(-0.04, 0.03)
        efficiency = 0.94 + random.uniform(-0.01, 0.02)
        ac_power = rated_kva * solar_factor * inv_variance * efficiency
        dc_power = ac_power / efficiency if ac_power > 0 else 0

        # Temperature: ambient + load contribution (smaller units run cooler)
        ambient = 22 + 8 * solar_factor
        temp = ambient + (ac_power / rated_kva) * 10

        inv = SolarInverter(
            inverter_id=inverter_id,
            plant_id=cfg.get("plant_id", ""),
            site_id=cfg.get("site_id", ""),
            name=cfg.get("name", inverter_id),
            manufacturer="Schneider Electric",
            model=cfg.get("model", "Conext CL25000E"),
            serial=cfg.get("serial", f"SE{inverter_id[-3:]}SIM"),
            rated_power_kva=rated_kva,
            mppt_count=cfg.get("mppt_count", 5),
            firmware_version="V3.12.1",
            protocol="modbus_tcp",
            ip_address=cfg.get("ip", "10.1.2.101"),
            port=cfg.get("port", 502),
            unit_id=cfg.get("unit_id", 1),
            dc_power_kw=round(dc_power, 2),
            ac_power_kw=round(ac_power, 2),
            efficiency_pct=round(efficiency * 100, 1),
            temp_c=round(temp, 1),
            status="online" if solar_factor > 0.01 else "standby",
            frequency_hz=round(50.0 + random.uniform(-0.05, 0.05), 2),
            power_factor=round(0.98 + random.uniform(-0.02, 0.01), 3),
            daily_yield_kwh=round(rated_kva * 4.8 * solar_factor * random.uniform(0.88, 1.0), 1),
            total_yield_mwh=round(rated_kva * 1200 * random.uniform(0.80, 0.92) / 1000, 1),
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

        mppt_count = cfg.get("mppt_count", 5)
        strings_per_mppt = cfg.get("strings_per_mppt", 2)
        panel_rating_w = cfg.get("panel_rating_w", 260)  # older panels

        strings = []
        for mppt in range(1, mppt_count + 1):
            for s_idx in range(1, strings_per_mppt + 1):
                string_id = f"{inverter_id}-MPPT{mppt:02d}-S{s_idx}"
                variance = 1.0 + random.uniform(-0.05, 0.02)
                panels_on_string = cfg.get("panels_per_string", 10)

                # --- Simulated fault: S15 MPPT3 string 1 has bypass diode
                #     issue — voltage drops ~15% while current stays normal ---
                bypass_diode_fault = (
                    inverter_id == "FNB-INV-S15"
                    and mppt == 3
                    and s_idx == 1
                )
                voltage_factor = 0.85 if bypass_diode_fault else 1.0

                vmp = 37.0 * panels_on_string * solar_factor * variance * voltage_factor
                imp = (panel_rating_w / 37.0) * solar_factor * variance
                dc_power = (vmp * imp / 1000) if solar_factor > 0 else 0

                strings.append(SolarString(
                    string_id=string_id,
                    inverter_id=inverter_id,
                    mppt_tracker=mppt,
                    panel_count=panels_on_string,
                    panel_model=cfg.get("panel_model", "Trina TSM-260PA05"),
                    panel_rating_w=panel_rating_w,
                    dc_voltage_v=round(vmp, 1),
                    dc_current_a=round(imp, 2),
                    dc_power_kw=round(dc_power, 3),
                    irradiance_w_m2=round(1000 * solar_factor * variance, 0),
                ))
        return strings

    async def read_bess(self, container_id: str) -> None:
        """Schneider connector does not manage BESS (handled by Huawei connector)."""
        return None

    async def read_meter(self, meter_id: str) -> Optional[GridMeter]:
        cfg = self._meter_configs.get(meter_id)
        if not cfg:
            return None

        now = datetime.now(timezone.utc)
        sast_hour = (now.hour + 2) % 24 + now.minute / 60.0
        solar_factor = _solar_power_factor(sast_hour)

        # PV generation meter for Eastern Carports
        total_pv_kw = 600.88 * solar_factor * 0.94  # fleet efficiency
        pv_kw = total_pv_kw + random.uniform(-5, 5)

        return GridMeter(
            meter_id=meter_id,
            site_id=cfg.get("site_id", ""),
            name=cfg.get("name", meter_id),
            manufacturer="Schneider Electric",
            model=cfg.get("model", "PM5110"),
            protocol="modbus_tcp",
            import_kw=0.0,  # PV meter only exports
            export_kw=round(max(0, pv_kw), 1),
            voltage_v=round(400 + random.uniform(-3, 3), 1),
            current_a=round(pv_kw / 0.4 / 1.732, 1) if pv_kw > 0 else 0.0,
            frequency_hz=round(50.0 + random.uniform(-0.04, 0.04), 2),
            power_factor=round(0.99 + random.uniform(-0.005, 0.005), 3),
            thd_pct=round(random.uniform(1.5, 3.0), 1),
            daily_import_kwh=0.0,
            daily_export_kwh=round(600.88 * 4.8 * solar_factor * 0.94, 0),
        )

    async def get_normalised_readings(self) -> List[NormalisedReading]:
        readings: List[NormalisedReading] = []
        now = datetime.now(timezone.utc).isoformat()

        for inv_id in self._inverter_configs:
            inv = await self.read_inverter(inv_id)
            if inv:
                readings.extend([
                    NormalisedReading(
                        timestamp=now, equipment_id=inv_id,
                        equipment_type="inverter", reading_type="power",
                        value=inv.ac_power_kw, unit="kW",
                        quality_flag=QualityFlag.GOOD.value,
                        source=DataSource.SIMULATED.value,
                    ),
                    NormalisedReading(
                        timestamp=now, equipment_id=inv_id,
                        equipment_type="inverter", reading_type="temperature",
                        value=inv.temp_c, unit="C",
                        quality_flag=QualityFlag.GOOD.value,
                        source=DataSource.SIMULATED.value,
                    ),
                    NormalisedReading(
                        timestamp=now, equipment_id=inv_id,
                        equipment_type="inverter", reading_type="energy",
                        value=inv.daily_yield_kwh, unit="kWh",
                        quality_flag=QualityFlag.GOOD.value,
                        source=DataSource.SIMULATED.value,
                    ),
                ])

        for mtr_id in self._meter_configs:
            mtr = await self.read_meter(mtr_id)
            if mtr:
                readings.append(NormalisedReading(
                    timestamp=now, equipment_id=mtr_id,
                    equipment_type="meter", reading_type="power",
                    value=-mtr.export_kw,  # negative = generation
                    unit="kW",
                    quality_flag=QualityFlag.GOOD.value,
                    source=DataSource.SIMULATED.value,
                ))

        self._status.last_poll = now
        return readings
