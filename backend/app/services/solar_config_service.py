"""
Solar & BESS Configuration Service — Single source of truth for site solar/BESS/tariff parameters.

Loads configuration in priority order:
1. site-002_config.json — BESS 200 kWh / 100 kW, PV 297 kWp, grid specs
2. city_power_2025_26.json — primary tariff (verified invoice rates)
3. city_power_2026.json — deprecated fallback only
4. energy_centre.json — max_demand_kw as NMD fallback

All solar/BESS/demand services should import from here instead of hardcoding constants.
"""

import json
import logging
from dataclasses import dataclass, field
from pathlib import Path
from typing import Dict, Optional

from app.core.site_resolver import get_primary_site

logger = logging.getLogger(__name__)

# Base data directory
_DATA_DIR = Path(__file__).parent.parent / "data"
_SOLAR_DIR = _DATA_DIR / "solar"
_TARIFF_DIR = _SOLAR_DIR / "tariffs"
_SITES_DIR = _DATA_DIR / "sites"


@dataclass(frozen=True)
class BESSConfig:
    """Battery Energy Storage System parameters."""

    capacity_kwh: float = 200.0
    rated_power_kw: float = 100.0
    cell_chemistry: str = "LFP"
    rack_count: int = 2
    manufacturer: str = "huawei"
    model: str = "LUNA2000-200KWH-2H1"
    grid_export_enabled: bool = True
    operating_modes: tuple = ("peak_shaving", "load_shifting", "grid_export", "backup")


@dataclass(frozen=True)
class PVConfig:
    """Photovoltaic system parameters."""

    total_capacity_kwp: float = 297.0  # 4 × 100 kVA inverters (roof)
    roof_capacity_kwp: float = 297.0
    carport_capacity_kwp: float = 0.0
    panel_count: int = 540


@dataclass(frozen=True)
class GridConfig:
    """Grid connection parameters."""

    nmd_limit_kva: float = 1820.0
    max_export_kw: float = 297.0
    voltage_kv: float = 11.0
    transformer_mva: float = 1.5
    sseg_category: str = "B"
    nrs_097_compliant: bool = True
    export_enabled: bool = True


@dataclass(frozen=True)
class TariffRates:
    """Time-of-use tariff rates (all ex-VAT)."""

    # Energy charges (c/kWh)
    summer_peak_c_kwh: float = 295.39
    summer_standard_c_kwh: float = 222.39
    summer_off_peak_c_kwh: float = 170.95
    winter_peak_c_kwh: float = 827.09
    winter_standard_c_kwh: float = 289.11
    winter_off_peak_c_kwh: float = 188.05

    # Network charge (c/kWh) — flat across all TOU periods
    network_charge_c_kwh: float = 6.0

    # Demand charge (R/kVA/month)
    demand_charge_r_kva_summer: float = 395.48
    demand_charge_r_kva_winter: float = 395.48

    # SSEG feed-in
    feed_in_rate_c_kwh: float = 78.5

    # Service charge
    service_charge_r_month: float = 11658.08

    # Reactive surcharge
    reactive_surcharge_c_kvarh: float = 42.43

    # VAT
    vat_rate_pct: float = 15.0

    @property
    def summer_peak_r_kwh(self) -> float:
        """Summer peak in R/kWh (energy + network)."""
        return (self.summer_peak_c_kwh + self.network_charge_c_kwh) / 100.0

    @property
    def summer_standard_r_kwh(self) -> float:
        """Summer standard in R/kWh (energy + network)."""
        return (self.summer_standard_c_kwh + self.network_charge_c_kwh) / 100.0

    @property
    def summer_off_peak_r_kwh(self) -> float:
        """Summer off-peak in R/kWh (energy + network)."""
        return (self.summer_off_peak_c_kwh + self.network_charge_c_kwh) / 100.0

    @property
    def winter_peak_r_kwh(self) -> float:
        return (self.winter_peak_c_kwh + self.network_charge_c_kwh) / 100.0

    @property
    def winter_standard_r_kwh(self) -> float:
        return (self.winter_standard_c_kwh + self.network_charge_c_kwh) / 100.0

    @property
    def winter_off_peak_r_kwh(self) -> float:
        return (self.winter_off_peak_c_kwh + self.network_charge_c_kwh) / 100.0

    def rate_r_kwh(self, period: str, season: str = "summer") -> float:
        """Get total rate in R/kWh for given TOU period and season."""
        key = f"{season}_{period}_r_kwh"
        return getattr(self, key, self.summer_standard_r_kwh)

    def demand_charge_r_kva(self, season: str = "summer") -> float:
        """Get demand charge for given season."""
        if season == "winter":
            return self.demand_charge_r_kva_winter
        return self.demand_charge_r_kva_summer


@dataclass(frozen=True)
class TimeBand:
    """TOU time band definition."""

    start: str
    end: str


@dataclass
class TariffTimeBands:
    """Time-of-use period definitions."""

    summer_months: tuple = (9, 10, 11, 12, 1, 2, 3, 4, 5)
    winter_months: tuple = (6, 7, 8)
    summer_peak: tuple = field(default_factory=lambda: (TimeBand("07:00", "10:00"), TimeBand("18:00", "20:00")))
    summer_standard: tuple = field(
        default_factory=lambda: (TimeBand("06:00", "07:00"), TimeBand("10:00", "18:00"), TimeBand("20:00", "22:00"))
    )
    summer_off_peak: tuple = field(default_factory=lambda: (TimeBand("22:00", "06:00"),))
    winter_peak: tuple = field(default_factory=lambda: (TimeBand("06:00", "09:00"), TimeBand("17:00", "19:00")))
    winter_standard: tuple = field(default_factory=lambda: (TimeBand("09:00", "17:00"), TimeBand("19:00", "22:00")))
    winter_off_peak: tuple = field(default_factory=lambda: (TimeBand("22:00", "06:00"),))

    def get_season(self, month: int) -> str:
        """Return 'winter' or 'summer' for a given month."""
        return "winter" if month in self.winter_months else "summer"

    def get_period(self, hour: int, month: int) -> str:
        """Return 'peak', 'standard', or 'off_peak' for given hour and month."""
        season = self.get_season(month)
        bands = {
            "peak": self.summer_peak if season == "summer" else self.winter_peak,
            "standard": self.summer_standard if season == "summer" else self.winter_standard,
            "off_peak": self.summer_off_peak if season == "summer" else self.winter_off_peak,
        }
        for period_name, band_list in bands.items():
            for band in band_list:
                start_h = int(band.start.split(":")[0])
                end_h = int(band.end.split(":")[0])
                if start_h < end_h:
                    if start_h <= hour < end_h:
                        return period_name
                else:  # wraps midnight
                    if hour >= start_h or hour < end_h:
                        return period_name
        return "standard"  # fallback


@dataclass
class SiteConfig:
    """Complete solar/BESS/tariff configuration for a site."""

    site_id: str
    bess: BESSConfig
    pv: PVConfig
    grid: GridConfig
    tariff: TariffRates
    time_bands: TariffTimeBands


def _load_json(path: Path) -> Optional[Dict]:
    """Load JSON file, return None on failure."""
    try:
        if path.exists():
            with open(path, "r") as f:
                return json.load(f)
    except Exception as e:
        logger.warning(f"Failed to load {path}: {e}")
    return None


def _load_site_config(site_id: str) -> SiteConfig:
    """Load site configuration from JSON files with fallback chain."""
    # 1. Site solar config
    solar_cfg = _load_json(_SOLAR_DIR / f"{site_id}_config.json") or {}

    # 2. Primary tariff
    tariff_data = _load_json(_TARIFF_DIR / "city_power_2025_26.json")
    if not tariff_data:
        # 3. Deprecated fallback
        tariff_data = _load_json(_TARIFF_DIR / "city_power_2026.json") or {}
        if tariff_data:
            logger.warning("Using deprecated city_power_2026.json — migrate to city_power_2025_26.json")

    # 4. Energy centre fallback for NMD
    energy_centre = _load_json(_SITES_DIR / site_id / "energy_centre.json") or {}

    # Build BESS config
    bess_data = solar_cfg.get("bess", {})
    bess = BESSConfig(
        capacity_kwh=bess_data.get("capacity_kwh", 200.0),
        rated_power_kw=bess_data.get("rated_power_kw", 100.0),
        cell_chemistry=bess_data.get("cell_chemistry", "LFP"),
        rack_count=bess_data.get("rack_count", 2),
        manufacturer=bess_data.get("manufacturer", "huawei"),
        model=bess_data.get("model", "LUNA2000-200KWH-2H1"),
        grid_export_enabled=bess_data.get("grid_export_enabled", True),
        operating_modes=tuple(
            bess_data.get("operating_modes", ["peak_shaving", "load_shifting", "grid_export", "backup"])
        ),
    )

    # Build PV config from plants
    plants = solar_cfg.get("plants", [])
    total_kwp = sum(p.get("capacity_kwp", 0) for p in plants)
    total_panels = sum(p.get("panel_count", 0) for p in plants)
    roof_kwp = next((p.get("capacity_kwp", 0) for p in plants if "roof" in p.get("plant_id", "")), 0)
    carport_kwp = next((p.get("capacity_kwp", 0) for p in plants if "carport" in p.get("plant_id", "")), 0)

    pv = PVConfig(
        total_capacity_kwp=total_kwp if total_kwp > 0 else 297.0,
        roof_capacity_kwp=roof_kwp if roof_kwp > 0 else 297.0,
        carport_capacity_kwp=carport_kwp,  # 0 if no carport plant present
        panel_count=total_panels if total_panels > 0 else 540,
    )

    # Build grid config
    grid_data = solar_cfg.get("grid", {})
    # NMD from energy centre power meters (max_demand_kw on main meter)
    nmd_fallback = 1820.0
    for meter in energy_centre.get("power_meters", []):
        if meter.get("meter_type") == "main":
            nmd_fallback = meter.get("max_demand_kw", 1820.0)
            break

    grid = GridConfig(
        nmd_limit_kva=nmd_fallback,
        max_export_kw=grid_data.get("max_export_kw", 297.0),
        voltage_kv=grid_data.get("voltage_kv", 11.0),
        transformer_mva=grid_data.get("transformer_mva", 1.5),
        sseg_category=grid_data.get("sseg_category", "B"),
        nrs_097_compliant=grid_data.get("nrs_097_compliant", True),
        export_enabled=grid_data.get("export_enabled", True),
    )

    # Build tariff config
    energy_charges = tariff_data.get("energy_charge_c_kwh", {})
    summer_energy = energy_charges.get("summer", {})
    winter_energy = energy_charges.get("winter", {})
    network = tariff_data.get("network_charge_c_kwh", {}).get("summer", {})
    demand = tariff_data.get("demand_charge_r_kva", {})
    sseg = tariff_data.get("sseg_feed_in", {})

    tariff = TariffRates(
        summer_peak_c_kwh=summer_energy.get("peak", 295.39),
        summer_standard_c_kwh=summer_energy.get("standard", 222.39),
        summer_off_peak_c_kwh=summer_energy.get("off_peak", 170.95),
        winter_peak_c_kwh=winter_energy.get("peak", 827.09),
        winter_standard_c_kwh=winter_energy.get("standard", 289.11),
        winter_off_peak_c_kwh=winter_energy.get("off_peak", 188.05),
        network_charge_c_kwh=network.get("peak", 6.0),
        demand_charge_r_kva_summer=demand.get("summer", 395.48),
        demand_charge_r_kva_winter=demand.get("winter", 395.48),
        feed_in_rate_c_kwh=sseg.get("rate_c_kwh", 78.5),
        service_charge_r_month=tariff_data.get("service_charge_r_month", 11658.08),
        reactive_surcharge_c_kvarh=tariff_data.get("reactive_energy_surcharge_c_kvarh", 42.43),
        vat_rate_pct=tariff_data.get("vat_rate_pct", 15.0),
    )

    # Build time bands
    tb_data = tariff_data.get("time_bands", {})
    time_bands = TariffTimeBands()
    if tb_data:
        summer_tb = tb_data.get("summer", {})
        winter_tb = tb_data.get("winter", {})
        time_bands = TariffTimeBands(
            summer_months=tuple(summer_tb.get("months", [9, 10, 11, 12, 1, 2, 3, 4, 5])),
            winter_months=tuple(winter_tb.get("months", [6, 7, 8])),
            summer_peak=tuple(TimeBand(b["start"], b["end"]) for b in summer_tb.get("peak", [])),
            summer_standard=tuple(TimeBand(b["start"], b["end"]) for b in summer_tb.get("standard", [])),
            summer_off_peak=tuple(TimeBand(b["start"], b["end"]) for b in summer_tb.get("off_peak", [])),
            winter_peak=tuple(TimeBand(b["start"], b["end"]) for b in winter_tb.get("peak", [])),
            winter_standard=tuple(TimeBand(b["start"], b["end"]) for b in winter_tb.get("standard", [])),
            winter_off_peak=tuple(TimeBand(b["start"], b["end"]) for b in winter_tb.get("off_peak", [])),
        )

    return SiteConfig(
        site_id=site_id,
        bess=bess,
        pv=pv,
        grid=grid,
        tariff=tariff,
        time_bands=time_bands,
    )


# Module-level cache
_site_configs: Dict[str, SiteConfig] = {}


def get_site_solar_config(site_id: str | None = None) -> SiteConfig:
    """Get solar/BESS/tariff config for a site. Cached after first load."""
    site_id = site_id or get_primary_site() or "unknown"
    if site_id not in _site_configs:
        _site_configs[site_id] = _load_site_config(site_id)
        logger.info(
            f"Loaded solar config for {site_id}: "
            f"PV={_site_configs[site_id].pv.total_capacity_kwp}kWp, "
            f"BESS={_site_configs[site_id].bess.capacity_kwh}kWh/{_site_configs[site_id].bess.rated_power_kw}kW, "
            f"NMD={_site_configs[site_id].grid.nmd_limit_kva}kVA"
        )
    return _site_configs[site_id]


def clear_config_cache():
    """Clear cached configs (for testing or config reload)."""
    _site_configs.clear()
