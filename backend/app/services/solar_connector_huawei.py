"""Huawei FusionSolar connector — SUN2000 inverter + LUNA2000 BESS.

Supports:
  - Modbus TCP register reads (holding registers)
  - Simulated data for demo (bell-curve solar, TOU BESS dispatch)

Register maps sourced from Huawei SUN2000-100KTL-M2 Modbus Interface Definition.
"""

import logging
import math
import random
from datetime import datetime, timezone
from typing import Dict, List, Optional

from app.models.solar import (
    SolarInverter,
    SolarString,
    BESSContainer,
    GridMeter,
    NormalisedReading,
    ConnectorStatus,
    QualityFlag,
    DataSource,
)
from app.services.solar_connector_base import SolarConnector

logger = logging.getLogger(__name__)


# === Huawei SUN2000 Modbus Register Map (Holding Registers) ===
HUAWEI_SUN2000_REGISTERS: Dict[str, tuple] = {
    # (address, count, type, scale_factor, unit)
    "model": (30000, 15, "str", 1, ""),
    "serial": (30015, 10, "str", 1, ""),
    "firmware": (30025, 15, "str", 1, ""),
    "rated_power": (30073, 2, "u32", 1000, "kW"),
    "dc_power": (32064, 2, "i32", 1000, "kW"),
    "ac_power": (32080, 2, "i32", 1000, "kW"),
    "efficiency": (32086, 1, "u16", 100, "%"),
    "inverter_temp": (32087, 1, "i16", 10, "C"),
    "status": (32089, 1, "u16", 1, ""),
    "fault_code": (32090, 1, "u16", 1, ""),
    "grid_frequency": (32085, 1, "u16", 100, "Hz"),
    "power_factor": (32084, 1, "i16", 1000, ""),
    "daily_yield": (32114, 2, "u32", 100, "kWh"),
    "total_yield": (32106, 2, "u32", 100, "kWh"),
    # MPPT string inputs (per-tracker)
    "pv1_voltage": (32016, 1, "i16", 10, "V"),
    "pv1_current": (32017, 1, "i16", 100, "A"),
    "pv2_voltage": (32018, 1, "i16", 10, "V"),
    "pv2_current": (32019, 1, "i16", 100, "A"),
}

# === Huawei LUNA2000 BESS Registers ===
HUAWEI_LUNA2000_REGISTERS: Dict[str, tuple] = {
    "soc": (37004, 1, "u16", 10, "%"),
    "soh": (37760, 1, "u16", 10, "%"),
    "charge_power": (37001, 2, "i32", 1000, "kW"),
    "discharge_power": (37003, 2, "i32", 1000, "kW"),
    "bus_voltage": (37006, 1, "u16", 10, "V"),
    "bus_current": (37007, 1, "i16", 10, "A"),
    "batt_temp": (37022, 1, "i16", 10, "C"),
    "status": (37000, 1, "u16", 1, ""),
    "fault_code": (37014, 1, "u16", 1, ""),
}

# Inverter status code mapping
HUAWEI_STATUS_MAP = {
    0x0000: "standby",
    0x0001: "online",
    0x0002: "online",  # grid-connected
    0x0003: "fault",
    0x0100: "offline",
    0x0200: "warning",
}

# Johannesburg latitude for solar curve
JHB_LATITUDE = -26.2


def _solar_power_factor(hour: float) -> float:
    """Calculate solar power factor (0-1) for Johannesburg.

    Models a bell curve centered on solar noon (~12:30 SAST in winter,
    ~12:00 in summer).  Returns 0 outside 06:00-18:00.
    """
    if hour < 5.5 or hour > 18.5:
        return 0.0
    # Peak at ~12.2h (solar noon JHB)
    solar_noon = 12.2
    # Gaussian with sigma ~3.0h gives realistic spread
    sigma = 3.0
    factor = math.exp(-0.5 * ((hour - solar_noon) / sigma) ** 2)
    return max(0.0, min(1.0, factor))


def _bess_mode_for_hour(hour: float) -> str:
    """Determine BESS operating mode based on City Power TOU periods.

    Peak:      06:00-09:00, 17:00-19:00  -> discharge
    Standard:  09:00-17:00, 19:00-22:00  -> idle / solar charge
    Off-peak:  22:00-06:00               -> grid charge
    """
    if (6 <= hour < 9) or (17 <= hour < 19):
        return "discharging"
    elif 9 <= hour < 17:
        return "idle"  # solar tops up if excess
    else:
        return "charging"


class SimulatedHuaweiConnector(SolarConnector):
    """Generates realistic Huawei SUN2000 + LUNA2000 data for demo.

    Solar power follows a bell curve for JHB latitude.  BESS follows
    TOU dispatch.  Temperature correlates with ambient + load.
    String-level data includes 2-5% random variance for realism.
    """

    def __init__(
        self,
        inverters: List[Dict],
        bess: Optional[Dict] = None,
        meters: Optional[List[Dict]] = None,
    ):
        super().__init__(manufacturer="huawei", protocol="modbus_tcp")
        self._inverter_configs = {inv["id"]: inv for inv in inverters}
        self._bess_config = bess
        self._meter_configs = {m["meter_id"]: m for m in (meters or [])}
        self._inverter_state: Dict[str, SolarInverter] = {}
        self._bess_state: Optional[BESSContainer] = None

    async def connect(self) -> bool:
        self._status = ConnectorStatus(
            connected=True,
            last_poll=datetime.now(timezone.utc).isoformat(),
            error_count=0,
        )
        logger.info(f"Huawei simulated connector online — {len(self._inverter_configs)} inverters")
        return True

    async def disconnect(self) -> None:
        self._status.connected = False
        logger.info("Huawei simulated connector disconnected")

    async def read_inverter(self, inverter_id: str) -> Optional[SolarInverter]:
        cfg = self._inverter_configs.get(inverter_id)
        if not cfg:
            return None

        now = datetime.now(timezone.utc)
        # SAST = UTC+2
        sast_hour = (now.hour + 2) % 24 + now.minute / 60.0
        solar_factor = _solar_power_factor(sast_hour)

        rated_kva = cfg.get("rated_kva", 100)
        # Add per-inverter variance (+-3%)
        inv_variance = 1.0 + random.uniform(-0.03, 0.03)

        # --- Simulated fault: S002-INV-H07 consistently underperforms by ~12%
        #     due to string fault on MPPT tracker 4 ---
        if inverter_id == "S002-INV-H07":
            inv_variance *= 0.88  # 12% reduction

        ac_power = rated_kva * solar_factor * inv_variance * 0.97  # 97% avg efficiency
        dc_power = ac_power / 0.97 if ac_power > 0 else 0
        efficiency = (ac_power / dc_power * 100) if dc_power > 0 else 0

        # Temperature: ambient ~22C + load contribution
        ambient = 22 + 8 * solar_factor  # hotter at noon
        temp = ambient + (ac_power / rated_kva) * 15  # up to 15C above ambient at full load

        inv = SolarInverter(
            inverter_id=inverter_id,
            plant_id=cfg.get("plant_id", ""),
            site_id=cfg.get("site_id", ""),
            name=cfg.get("name", inverter_id),
            manufacturer="Huawei",
            model=cfg.get("model", "SUN2000-100KTL-M2"),
            serial=cfg.get("serial", f"HW{inverter_id[-3:]}SIM"),
            rated_power_kva=rated_kva,
            mppt_count=cfg.get("mppt_count", 10),
            firmware_version="V200R001C00SPC136",
            protocol="modbus_tcp",
            ip_address=cfg.get("ip", "10.1.1.101"),
            port=cfg.get("port", 502),
            unit_id=cfg.get("unit_id", 1),
            dc_power_kw=round(dc_power, 2),
            ac_power_kw=round(ac_power, 2),
            efficiency_pct=round(efficiency, 1),
            temp_c=round(temp, 1),
            status="online" if solar_factor > 0.01 else "standby",
            frequency_hz=round(50.0 + random.uniform(-0.05, 0.05), 2),
            power_factor=round(0.99 + random.uniform(-0.01, 0.005), 3),
            daily_yield_kwh=round(
                rated_kva
                * 5.2
                * solar_factor
                * random.uniform(0.92, 1.0)
                * (0.88 if inverter_id == "S002-INV-H07" else 1.0),
                1,
            ),
            total_yield_mwh=round(rated_kva * 1460 * random.uniform(0.85, 0.95) / 1000, 1),
            alarms=(["String fault detected on MPPT tracker 4"] if inverter_id == "S002-INV-H07" else []),
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

        mppt_count = cfg.get("mppt_count", 10)
        strings_per_mppt = cfg.get("strings_per_mppt", 4)
        panel_rating_w = cfg.get("panel_rating_w", 615)

        strings = []
        for mppt in range(1, mppt_count + 1):
            for s_idx in range(1, strings_per_mppt + 1):
                string_id = f"{inverter_id}-MPPT{mppt:02d}-S{s_idx}"
                # Per-string variance 2-5%
                variance = 1.0 + random.uniform(-0.05, 0.02)
                panels_on_string = cfg.get("panels_per_string", 14)

                # --- Simulated fault: H07 MPPT tracker 4 strings degraded
                #     Reduces current by ~30% (soiling + partial disconnect) ---
                mppt4_fault = inverter_id == "S002-INV-H07" and mppt == 4
                fault_factor = 0.70 if mppt4_fault else 1.0

                _voc = 49.5 * panels_on_string  # ~693V at Voc
                vmp = 41.7 * panels_on_string * solar_factor * variance
                imp = (panel_rating_w / 41.7) * solar_factor * variance * fault_factor
                dc_power = (vmp * imp / 1000) if solar_factor > 0 else 0

                strings.append(
                    SolarString(
                        string_id=string_id,
                        inverter_id=inverter_id,
                        mppt_tracker=mppt,
                        panel_count=panels_on_string,
                        panel_model=cfg.get("panel_model", "CS6.2-66TB-615"),
                        panel_rating_w=panel_rating_w,
                        dc_voltage_v=round(vmp, 1),
                        dc_current_a=round(imp, 2),
                        dc_power_kw=round(dc_power, 3),
                        irradiance_w_m2=round(1000 * solar_factor * variance, 0),
                    )
                )
        return strings

    async def read_bess(self, container_id: str) -> Optional[BESSContainer]:
        if not self._bess_config:
            return None

        now = datetime.now(timezone.utc)
        sast_hour = (now.hour + 2) % 24 + now.minute / 60.0
        mode = _bess_mode_for_hour(sast_hour)

        cfg = self._bess_config
        rated_kw = cfg.get("rated_power_kw", 100)
        capacity_kwh = cfg.get("capacity_kwh", 200)

        # SOC follows TOU pattern
        if mode == "discharging":
            soc = max(20, 80 - (sast_hour - 6) * 10)  # drain during peak
        elif mode == "charging":
            soc = min(95, 30 + (sast_hour - 22 if sast_hour >= 22 else sast_hour + 2) * 8)
        else:
            soc = 55 + random.uniform(-5, 10)  # idle with slight drift

        charge_kw = 0.0
        discharge_kw = 0.0
        if mode == "discharging":
            discharge_kw = rated_kw * random.uniform(0.6, 0.85)
        elif mode == "charging":
            charge_kw = rated_kw * random.uniform(0.3, 0.5)

        container = BESSContainer(
            container_id=container_id,
            site_id=cfg.get("site_id", ""),
            name=cfg.get("name", "LUNA2000 BESS"),
            manufacturer="Huawei",
            model=cfg.get("model", "LUNA2000-200KWH-2H1"),
            capacity_kwh=capacity_kwh,
            rated_power_kw=rated_kw,
            rack_count=cfg.get("rack_count", 2),
            cell_chemistry="LFP",
            protocol="modbus_tcp",
            soc_pct=round(soc, 1),
            soh_pct=round(98.5 + random.uniform(-0.5, 0.5), 1),
            charge_power_kw=round(charge_kw, 1),
            discharge_power_kw=round(discharge_kw, 1),
            mode=mode,
            temp_c=round(25 + random.uniform(-2, 4), 1),
            cell_min_v=round(3.20 + random.uniform(0, 0.05), 3),
            cell_max_v=round(3.35 + random.uniform(0, 0.05), 3),
            cell_imbalance_mv=round(random.uniform(8, 25), 1),
            cycles_count=random.randint(450, 520),
            alarms=[],
            last_poll=now.isoformat(),
        )
        self._bess_state = container
        return container

    async def read_meter(self, meter_id: str) -> Optional[GridMeter]:
        cfg = self._meter_configs.get(meter_id)
        if not cfg:
            return None

        now = datetime.now(timezone.utc)
        sast_hour = (now.hour + 2) % 24 + now.minute / 60.0
        solar_factor = _solar_power_factor(sast_hour)

        # Building base load ~800 kW
        building_load = 800 + random.uniform(-50, 50)
        # Total solar generation estimate
        total_pv_kw = 297 * solar_factor * 0.95
        # BESS contribution
        bess_kw = 0
        mode = _bess_mode_for_hour(sast_hour)
        if mode == "discharging":
            bess_kw = 100 * random.uniform(0.6, 0.85)

        net_grid = building_load - total_pv_kw - bess_kw
        import_kw = max(0, net_grid)
        export_kw = max(0, -net_grid)

        return GridMeter(
            meter_id=meter_id,
            site_id=cfg.get("site_id", ""),
            name=cfg.get("name", meter_id),
            manufacturer=cfg.get("manufacturer", "Schneider"),
            model=cfg.get("model", "PM8000"),
            protocol="modbus_tcp",
            import_kw=round(import_kw, 1),
            export_kw=round(export_kw, 1),
            voltage_v=round(400 + random.uniform(-5, 5), 1),
            current_a=round((import_kw + export_kw) / 0.4 / 1.732, 1),
            frequency_hz=round(50.0 + random.uniform(-0.04, 0.04), 2),
            power_factor=round(0.95 + random.uniform(-0.02, 0.04), 3),
            thd_pct=round(random.uniform(2.0, 4.5), 1),
            daily_import_kwh=round(building_load * sast_hour * 0.6, 0),
            daily_export_kwh=round(export_kw * max(0, sast_hour - 9) * 0.3, 0),
        )

    async def get_normalised_readings(self) -> List[NormalisedReading]:
        readings: List[NormalisedReading] = []
        now = datetime.now(timezone.utc).isoformat()

        # Inverter readings
        for inv_id in self._inverter_configs:
            inv = await self.read_inverter(inv_id)
            if inv:
                readings.extend(
                    [
                        NormalisedReading(
                            timestamp=now,
                            equipment_id=inv_id,
                            equipment_type="inverter",
                            reading_type="power",
                            value=inv.ac_power_kw,
                            unit="kW",
                            quality_flag=QualityFlag.GOOD.value,
                            source=DataSource.SIMULATED.value,
                        ),
                        NormalisedReading(
                            timestamp=now,
                            equipment_id=inv_id,
                            equipment_type="inverter",
                            reading_type="temperature",
                            value=inv.temp_c,
                            unit="C",
                            quality_flag=QualityFlag.GOOD.value,
                            source=DataSource.SIMULATED.value,
                        ),
                        NormalisedReading(
                            timestamp=now,
                            equipment_id=inv_id,
                            equipment_type="inverter",
                            reading_type="energy",
                            value=inv.daily_yield_kwh,
                            unit="kWh",
                            quality_flag=QualityFlag.GOOD.value,
                            source=DataSource.SIMULATED.value,
                        ),
                    ]
                )

        # BESS readings
        if self._bess_config:
            bess = await self.read_bess(self._bess_config["container_id"])
            if bess:
                readings.extend(
                    [
                        NormalisedReading(
                            timestamp=now,
                            equipment_id=bess.container_id,
                            equipment_type="bess",
                            reading_type="soc",
                            value=bess.soc_pct,
                            unit="%",
                            quality_flag=QualityFlag.GOOD.value,
                            source=DataSource.SIMULATED.value,
                        ),
                        NormalisedReading(
                            timestamp=now,
                            equipment_id=bess.container_id,
                            equipment_type="bess",
                            reading_type="power",
                            value=bess.discharge_power_kw - bess.charge_power_kw,
                            unit="kW",
                            quality_flag=QualityFlag.GOOD.value,
                            source=DataSource.SIMULATED.value,
                        ),
                        NormalisedReading(
                            timestamp=now,
                            equipment_id=bess.container_id,
                            equipment_type="bess",
                            reading_type="temperature",
                            value=bess.temp_c,
                            unit="C",
                            quality_flag=QualityFlag.GOOD.value,
                            source=DataSource.SIMULATED.value,
                        ),
                    ]
                )

        # Meter readings
        for mtr_id in self._meter_configs:
            mtr = await self.read_meter(mtr_id)
            if mtr:
                readings.extend(
                    [
                        NormalisedReading(
                            timestamp=now,
                            equipment_id=mtr_id,
                            equipment_type="meter",
                            reading_type="power",
                            value=mtr.import_kw - mtr.export_kw,
                            unit="kW",
                            quality_flag=QualityFlag.GOOD.value,
                            source=DataSource.SIMULATED.value,
                        ),
                        NormalisedReading(
                            timestamp=now,
                            equipment_id=mtr_id,
                            equipment_type="meter",
                            reading_type="power_factor",
                            value=mtr.power_factor,
                            unit="",
                            quality_flag=QualityFlag.GOOD.value,
                            source=DataSource.SIMULATED.value,
                        ),
                    ]
                )

        self._status.last_poll = now
        return readings


class RealHuaweiConnector(SolarConnector):
    """Real Modbus TCP connector for Huawei SUN2000 + LUNA2000.

    Uses pymodbus AsyncModbusTcpClient to read holding registers
    from HUAWEI_SUN2000_REGISTERS and HUAWEI_LUNA2000_REGISTERS maps.
    Falls back gracefully on connection or read errors.
    """

    def __init__(
        self,
        inverters: List[Dict],
        bess: Optional[Dict] = None,
        meters: Optional[List[Dict]] = None,
    ):
        super().__init__(manufacturer="huawei", protocol="modbus_tcp")
        self._inverter_configs = {inv["id"]: inv for inv in inverters}
        self._bess_config = bess
        self._meter_configs = {m["meter_id"]: m for m in (meters or [])}
        self._client = None

    async def connect(self) -> bool:
        """Connect to Huawei inverter via Modbus TCP."""
        from app.config.settings import settings

        ip = settings.modbus_bess_ip
        port = settings.modbus_bess_port
        if not ip:
            logger.warning("RealHuaweiConnector: no modbus_bess_ip configured")
            self._status = ConnectorStatus(connected=False, error_count=1)
            return False

        try:
            from pymodbus.client import AsyncModbusTcpClient

            self._client = AsyncModbusTcpClient(
                ip,
                port=port,
                timeout=settings.modbus_bess_timeout_s,
            )
            connected = await self._client.connect()
            self._status = ConnectorStatus(
                connected=connected,
                last_poll=datetime.now(timezone.utc).isoformat(),
                error_count=0 if connected else 1,
            )
            if connected:
                logger.info("RealHuaweiConnector online: %s:%d", ip, port)
            else:
                logger.warning("RealHuaweiConnector failed to connect: %s:%d", ip, port)
            return connected
        except Exception as e:
            logger.error("RealHuaweiConnector connect error: %s", e)
            self._status = ConnectorStatus(connected=False, error_count=1)
            return False

    async def disconnect(self) -> None:
        """Disconnect Modbus TCP client."""
        if self._client:
            self._client.close()
            self._client = None
        self._status.connected = False
        logger.info("RealHuaweiConnector disconnected")

    async def _read_registers(self, address: int, count: int, unit_id: int = 1) -> Optional[List[int]]:
        """Read holding registers from Modbus device."""
        if not self._client or not self._status.connected:
            return None
        try:
            result = await self._client.read_holding_registers(
                address,
                count=count,
                slave=unit_id,
            )
            if result.isError():
                logger.warning("Modbus read error at %d: %s", address, result)
                self._status.error_count += 1
                return None
            return list(result.registers)
        except Exception as e:
            logger.warning("Modbus read exception at %d: %s", address, e)
            self._status.error_count += 1
            return None

    @staticmethod
    def _decode_register(raw: List[int], reg_type: str, scale: float) -> Optional[float]:
        """Decode raw register values based on type and scale.

        Handles: u16, i16, u32, i32, str (returns None for str type).
        """
        if not raw:
            return None

        if reg_type == "str":
            return None  # String decoding handled separately

        if reg_type == "u16":
            value = raw[0]
        elif reg_type == "i16":
            value = raw[0] if raw[0] < 0x8000 else raw[0] - 0x10000
        elif reg_type == "u32":
            if len(raw) < 2:
                return None
            value = (raw[0] << 16) | raw[1]
        elif reg_type == "i32":
            if len(raw) < 2:
                return None
            value = (raw[0] << 16) | raw[1]
            if value >= 0x80000000:
                value -= 0x100000000
        else:
            return None

        return value / scale if scale != 0 else float(value)

    @staticmethod
    def _decode_string(raw: List[int], count: int) -> str:
        """Decode Modbus registers as ASCII string."""
        if not raw:
            return ""
        chars = []
        for reg in raw[:count]:
            chars.append(chr((reg >> 8) & 0xFF))
            chars.append(chr(reg & 0xFF))
        return "".join(chars).rstrip("\x00").strip()

    async def read_inverter(self, inverter_id: str) -> Optional[SolarInverter]:
        """Read inverter state from real Modbus registers."""
        cfg = self._inverter_configs.get(inverter_id)
        if not cfg:
            return None

        unit_id = cfg.get("unit_id", 1)
        now = datetime.now(timezone.utc)

        # Read key registers
        reads = {}
        for key, (addr, count, rtype, scale, _unit) in HUAWEI_SUN2000_REGISTERS.items():
            raw = await self._read_registers(addr, count, unit_id)
            if raw is None:
                reads[key] = None
                continue
            if rtype == "str":
                reads[key] = self._decode_string(raw, count)
            else:
                reads[key] = self._decode_register(raw, rtype, scale)

        # Map status code
        status_code = int(reads.get("status") or 0)
        status_str = HUAWEI_STATUS_MAP.get(status_code, "unknown")

        return SolarInverter(
            inverter_id=inverter_id,
            plant_id=cfg.get("plant_id", ""),
            site_id=cfg.get("site_id", ""),
            name=cfg.get("name", inverter_id),
            manufacturer="Huawei",
            model=reads.get("model") or cfg.get("model", "SUN2000-100KTL-M2"),
            serial=reads.get("serial") or cfg.get("serial", ""),
            rated_power_kva=reads.get("rated_power") or cfg.get("rated_kva", 100),
            mppt_count=cfg.get("mppt_count", 10),
            firmware_version=reads.get("firmware") or "",
            protocol="modbus_tcp",
            ip_address=cfg.get("ip", ""),
            port=cfg.get("port", 502),
            unit_id=unit_id,
            dc_power_kw=round(reads.get("dc_power") or 0, 2),
            ac_power_kw=round(reads.get("ac_power") or 0, 2),
            efficiency_pct=round(reads.get("efficiency") or 0, 1),
            temp_c=round(reads.get("inverter_temp") or 0, 1),
            status=status_str,
            frequency_hz=round(reads.get("grid_frequency") or 50.0, 2),
            power_factor=round(reads.get("power_factor") or 1.0, 3),
            daily_yield_kwh=round(reads.get("daily_yield") or 0, 1),
            total_yield_mwh=round((reads.get("total_yield") or 0) / 1000, 1),
            alarms=[],
            last_poll=now.isoformat(),
        )

    async def read_all_strings(self, inverter_id: str) -> List[SolarString]:
        """Read PV string data from real Modbus registers.

        Only PV1/PV2 registers are defined in the map; returns available strings.
        """
        cfg = self._inverter_configs.get(inverter_id)
        if not cfg:
            return []

        unit_id = cfg.get("unit_id", 1)
        strings = []

        # Read PV1 and PV2 from the register map
        for pv_idx, (v_key, i_key) in enumerate(
            [("pv1_voltage", "pv1_current"), ("pv2_voltage", "pv2_current")], start=1
        ):
            v_reg = HUAWEI_SUN2000_REGISTERS.get(v_key)
            i_reg = HUAWEI_SUN2000_REGISTERS.get(i_key)
            if not v_reg or not i_reg:
                continue

            v_raw = await self._read_registers(v_reg[0], v_reg[1], unit_id)
            i_raw = await self._read_registers(i_reg[0], i_reg[1], unit_id)

            voltage = self._decode_register(v_raw or [], v_reg[2], v_reg[3]) or 0
            current = self._decode_register(i_raw or [], i_reg[2], i_reg[3]) or 0

            strings.append(
                SolarString(
                    string_id=f"{inverter_id}-MPPT{pv_idx:02d}-S1",
                    inverter_id=inverter_id,
                    mppt_tracker=pv_idx,
                    panel_count=cfg.get("panels_per_string", 14),
                    panel_model=cfg.get("panel_model", ""),
                    panel_rating_w=cfg.get("panel_rating_w", 615),
                    dc_voltage_v=round(voltage, 1),
                    dc_current_a=round(current, 2),
                    dc_power_kw=round(voltage * current / 1000, 3),
                )
            )

        return strings

    async def read_bess(self, container_id: str) -> Optional[BESSContainer]:
        """Read BESS state from real LUNA2000 Modbus registers."""
        if not self._bess_config:
            return None

        from app.config.settings import settings

        unit_id = settings.modbus_bess_unit_id
        now = datetime.now(timezone.utc)
        cfg = self._bess_config

        reads = {}
        for key, (addr, count, rtype, scale, _unit) in HUAWEI_LUNA2000_REGISTERS.items():
            raw = await self._read_registers(addr, count, unit_id)
            if raw is None:
                reads[key] = None
                continue
            reads[key] = self._decode_register(raw, rtype, scale)

        soc = reads.get("soc") or 0
        charge_kw = reads.get("charge_power") or 0
        discharge_kw = reads.get("discharge_power") or 0

        # Determine mode from charge/discharge power
        if charge_kw > 0.1:
            mode = "charging"
        elif discharge_kw > 0.1:
            mode = "discharging"
        else:
            mode = "idle"

        return BESSContainer(
            container_id=container_id,
            site_id=cfg.get("site_id", ""),
            name=cfg.get("name", "LUNA2000 BESS"),
            manufacturer="Huawei",
            model=cfg.get("model", "LUNA2000-200KWH-2H1"),
            capacity_kwh=cfg.get("capacity_kwh", 200),
            rated_power_kw=cfg.get("rated_power_kw", 100),
            rack_count=cfg.get("rack_count", 2),
            cell_chemistry="LFP",
            protocol="modbus_tcp",
            soc_pct=round(soc, 1),
            soh_pct=round(reads.get("soh") or 0, 1),
            charge_power_kw=round(max(0, charge_kw), 1),
            discharge_power_kw=round(max(0, discharge_kw), 1),
            mode=mode,
            temp_c=round(reads.get("batt_temp") or 25.0, 1),
            cell_min_v=0.0,  # Not in register map
            cell_max_v=0.0,
            cell_imbalance_mv=0.0,
            cycles_count=0,
            alarms=[],
            last_poll=now.isoformat(),
        )

    async def read_meter(self, meter_id: str) -> Optional[GridMeter]:
        """Read grid meter — not yet implemented for real Modbus.

        Returns None; grid meters typically use Schneider PM8000
        which has its own connector.
        """
        return None

    async def get_normalised_readings(self) -> List[NormalisedReading]:
        """Poll all registered equipment and return normalised readings."""
        readings: List[NormalisedReading] = []
        now = datetime.now(timezone.utc).isoformat()

        for inv_id in self._inverter_configs:
            inv = await self.read_inverter(inv_id)
            if inv:
                readings.extend(
                    [
                        NormalisedReading(
                            timestamp=now,
                            equipment_id=inv_id,
                            equipment_type="inverter",
                            reading_type="power",
                            value=inv.ac_power_kw,
                            unit="kW",
                            quality_flag=QualityFlag.GOOD.value,
                            source=DataSource.MODBUS.value,
                        ),
                        NormalisedReading(
                            timestamp=now,
                            equipment_id=inv_id,
                            equipment_type="inverter",
                            reading_type="temperature",
                            value=inv.temp_c,
                            unit="C",
                            quality_flag=QualityFlag.GOOD.value,
                            source=DataSource.MODBUS.value,
                        ),
                        NormalisedReading(
                            timestamp=now,
                            equipment_id=inv_id,
                            equipment_type="inverter",
                            reading_type="energy",
                            value=inv.daily_yield_kwh,
                            unit="kWh",
                            quality_flag=QualityFlag.GOOD.value,
                            source=DataSource.MODBUS.value,
                        ),
                    ]
                )

        if self._bess_config:
            bess = await self.read_bess(self._bess_config.get("container_id", ""))
            if bess:
                readings.extend(
                    [
                        NormalisedReading(
                            timestamp=now,
                            equipment_id=bess.container_id,
                            equipment_type="bess",
                            reading_type="soc",
                            value=bess.soc_pct,
                            unit="%",
                            quality_flag=QualityFlag.GOOD.value,
                            source=DataSource.MODBUS.value,
                        ),
                        NormalisedReading(
                            timestamp=now,
                            equipment_id=bess.container_id,
                            equipment_type="bess",
                            reading_type="power",
                            value=bess.discharge_power_kw - bess.charge_power_kw,
                            unit="kW",
                            quality_flag=QualityFlag.GOOD.value,
                            source=DataSource.MODBUS.value,
                        ),
                        NormalisedReading(
                            timestamp=now,
                            equipment_id=bess.container_id,
                            equipment_type="bess",
                            reading_type="temperature",
                            value=bess.temp_c,
                            unit="C",
                            quality_flag=QualityFlag.GOOD.value,
                            source=DataSource.MODBUS.value,
                        ),
                    ]
                )

        self._status.last_poll = now
        return readings
