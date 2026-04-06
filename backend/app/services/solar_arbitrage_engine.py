"""Solar Arbitrage Engine -- TOU tariff optimisation and BESS dispatch scheduling.

Core value proposition of SENTINEL Solar: autonomous BESS dispatch that charges
during off-peak and discharges during peak, saving R200-500K/year at 1 MWp scale.
The operator shouldn't need to think about it -- SENTINEL handles dispatch silently.

Tariff source: City Power Johannesburg Commercial TOU rates from
  backend/app/data/solar/tariffs/city_power_2026.json

BESS constraints (Site-002 LUNA2000-200KWH-2H1):
  - Capacity: 200 kWh usable
  - Max charge/discharge: 100 kW (0.5C)
  - Min SOC: 10%  (protect cell longevity)
  - Max SOC: 95%  (prevent overcharge)

Load shedding reserve:
  - When LS announced: raise SOC floor to 80% before LS window
  - During LS: discharge to sustain critical loads, generator takes priority
  - After LS: resume normal dispatch
"""

import json
import logging
from dataclasses import dataclass, field
from datetime import UTC, date, datetime, time, timedelta
from enum import Enum
from pathlib import Path
from typing import Any

from app.services.solar_config_service import get_site_solar_config

logger = logging.getLogger(__name__)


# === Enums ===


class TariffBandName(str, Enum):
    """TOU tariff band names."""

    PEAK = "peak"
    STANDARD = "standard"
    OFF_PEAK = "off_peak"


class DispatchActionType(str, Enum):
    """BESS dispatch action types."""

    CHARGE = "charge"
    DISCHARGE = "discharge"
    IDLE = "idle"
    SOLAR_PRIORITY = "solar_priority"


class Season(str, Enum):
    """Tariff season (SA winter = high demand = Jun/Jul/Aug)."""

    SUMMER = "summer"
    WINTER = "winter"


# === Dataclass Models ===


@dataclass
class TariffBand:
    """Current tariff band with rate information."""

    name: str  # peak / standard / off_peak
    rate_per_kwh: float  # ZAR/kWh (converted from c/kWh)
    season: str  # summer / winter
    network_charge_per_kwh: float = 0.0  # ZAR/kWh
    total_rate_per_kwh: float = 0.0  # energy + network
    period_start: str = ""  # HH:MM
    period_end: str = ""  # HH:MM

    def to_dict(self) -> dict[str, Any]:
        return {
            "name": self.name,
            "rate_per_kwh": round(self.rate_per_kwh, 4),
            "network_charge_per_kwh": round(self.network_charge_per_kwh, 4),
            "total_rate_per_kwh": round(self.total_rate_per_kwh, 4),
            "season": self.season,
            "period_start": self.period_start,
            "period_end": self.period_end,
        }


@dataclass
class ArbitrageValue:
    """Revenue calculation from buy-low sell-high arbitrage."""

    charge_kwh: float
    discharge_kwh: float
    charge_cost_zar: float  # cost to charge
    discharge_revenue_zar: float  # value of discharged energy
    net_savings_zar: float  # revenue - cost
    round_trip_efficiency: float = 0.90  # 90% battery round-trip
    charge_rate_per_kwh: float = 0.0
    discharge_rate_per_kwh: float = 0.0

    def to_dict(self) -> dict[str, Any]:
        return {
            "charge_kwh": round(self.charge_kwh, 1),
            "discharge_kwh": round(self.discharge_kwh, 1),
            "charge_cost_zar": round(self.charge_cost_zar, 2),
            "discharge_revenue_zar": round(self.discharge_revenue_zar, 2),
            "net_savings_zar": round(self.net_savings_zar, 2),
            "round_trip_efficiency": self.round_trip_efficiency,
            "charge_rate_per_kwh": round(self.charge_rate_per_kwh, 4),
            "discharge_rate_per_kwh": round(self.discharge_rate_per_kwh, 4),
        }


@dataclass
class DispatchSlot:
    """A time window in the dispatch schedule with BESS action."""

    start: str  # HH:MM
    end: str  # HH:MM
    action: str  # charge / discharge / idle / solar_priority
    power_kw: float = 0.0
    target_soc_pct: float | None = None
    tariff_band: str = ""
    rate_per_kwh: float = 0.0
    note: str = ""

    def to_dict(self) -> dict[str, Any]:
        result: dict[str, Any] = {
            "start": self.start,
            "end": self.end,
            "action": self.action,
            "power_kw": round(self.power_kw, 0),
            "tariff_band": self.tariff_band,
            "rate_per_kwh": round(self.rate_per_kwh, 4),
        }
        if self.target_soc_pct is not None:
            result["target_soc_pct"] = round(self.target_soc_pct, 1)
        if self.note:
            result["note"] = self.note
        return result


@dataclass
class DispatchSchedule:
    """Day-ahead BESS dispatch plan with 24-hour slots."""

    site_id: str
    date: str  # YYYY-MM-DD
    season: str
    slots: list[DispatchSlot] = field(default_factory=list)
    load_shedding_adjustment: dict[str, Any] | None = None
    projected_savings_zar: float = 0.0

    def to_dict(self) -> dict[str, Any]:
        return {
            "site_id": self.site_id,
            "date": self.date,
            "season": self.season,
            "slots": [s.to_dict() for s in self.slots],
            "load_shedding_adjustment": self.load_shedding_adjustment,
            "projected_savings_zar": round(self.projected_savings_zar, 2),
        }


@dataclass
class DispatchAction:
    """Real-time dispatch recommendation: what BESS should do RIGHT NOW."""

    action: str  # charge / discharge / idle / solar_priority
    power_kw: float
    reason: str
    tariff_band: str
    rate_per_kwh: float
    current_soc_pct: float
    target_soc_pct: float | None = None
    load_shedding_active: bool = False
    next_action_change: str | None = None  # ISO timestamp

    def to_dict(self) -> dict[str, Any]:
        result: dict[str, Any] = {
            "action": self.action,
            "power_kw": round(self.power_kw, 0),
            "reason": self.reason,
            "tariff_band": self.tariff_band,
            "rate_per_kwh": round(self.rate_per_kwh, 4),
            "current_soc_pct": round(self.current_soc_pct, 1),
            "load_shedding_active": self.load_shedding_active,
        }
        if self.target_soc_pct is not None:
            result["target_soc_pct"] = round(self.target_soc_pct, 1)
        if self.next_action_change:
            result["next_action_change"] = self.next_action_change
        return result


@dataclass
class DailySavings:
    """Actual vs no-BESS cost comparison for a day."""

    site_id: str
    date: str
    period: str  # day / week / month
    with_bess_zar: float
    without_bess_zar: float
    savings_zar: float
    savings_pct: float
    peak_kwh_avoided: float
    off_peak_kwh_charged: float
    solar_self_consumed_kwh: float
    currency: str = "ZAR"

    def to_dict(self) -> dict[str, Any]:
        return {
            "site_id": self.site_id,
            "date": self.date,
            "period": self.period,
            "with_bess_zar": round(self.with_bess_zar, 2),
            "without_bess_zar": round(self.without_bess_zar, 2),
            "savings_zar": round(self.savings_zar, 2),
            "savings_pct": round(self.savings_pct, 1),
            "peak_kwh_avoided": round(self.peak_kwh_avoided, 0),
            "off_peak_kwh_charged": round(self.off_peak_kwh_charged, 0),
            "solar_self_consumed_kwh": round(self.solar_self_consumed_kwh, 0),
            "currency": self.currency,
        }


# === Engine ===


class SolarArbitrageEngine:
    """TOU tariff optimisation and BESS dispatch scheduling engine.

    Loads City Power tariff structure and generates optimal dispatch
    schedules that charge BESS during off-peak and discharge during peak.
    Integrates with EskomSePush for load shedding reserve management.
    """

    # BESS constraints (from Site-002 LUNA2000-200KWH-2H1 config)
    BESS_CAPACITY_KWH = 200.0  # Huawei LUNA2000-200KWH-2H1
    BESS_RATED_POWER_KW = 100.0  # 0.5C rate
    BESS_MIN_SOC_PCT = 10.0
    BESS_MAX_SOC_PCT = 95.0
    BESS_ROUND_TRIP_EFF = 0.90
    BESS_LS_RESERVE_SOC_PCT = 80.0  # minimum SOC before load shedding

    def __init__(self):
        self._tariff: dict[str, Any] = {}
        self._load_tariff()
        try:
            cfg = get_site_solar_config()
            self.BESS_CAPACITY_KWH = cfg.bess.capacity_kwh
            self.BESS_RATED_POWER_KW = cfg.bess.rated_power_kw
        except Exception:
            pass

    def _load_tariff(self) -> None:
        """Load City Power TOU tariff from JSON configuration."""
        tariff_path = Path(__file__).parent.parent / "data" / "solar" / "tariffs" / "city_power_2026.json"
        try:
            with open(tariff_path) as f:
                self._tariff = json.load(f)
            logger.info("Loaded City Power tariff from %s", tariff_path.name)
        except Exception as e:
            logger.error("Failed to load tariff: %s", e)
            self._tariff = {}

    # === Season detection ===

    def _get_season(self, dt: datetime | None = None) -> str:
        """Determine tariff season from date. Winter = Jul/Aug (high demand)."""
        dt = dt or datetime.now(UTC)
        winter_months = self._tariff.get("time_bands", {}).get("winter", {}).get("months", [7, 8])
        return Season.WINTER.value if dt.month in winter_months else Season.SUMMER.value

    # === Tariff band lookup ===

    def get_current_tariff_band(self, timestamp: datetime | None = None) -> TariffBand:
        """Return the current TOU tariff band with rate.

        Checks timestamp against City Power time bands for the appropriate
        season (summer/winter) and returns the matching band with energy
        and network charges converted from c/kWh to ZAR/kWh.
        """
        ts = timestamp or datetime.now(UTC)
        # Shift to SAST (UTC+2) for tariff band determination
        sast = ts + timedelta(hours=2)
        current_time = sast.time()
        season = self._get_season(ts)

        time_bands = self._tariff.get("time_bands", {}).get(season, {})
        energy_charges = self._tariff.get("energy_charge_c_kwh", {}).get(season, {})
        network_charges = self._tariff.get("network_charge_c_kwh", {}).get(season, {})

        # Check each band
        for band_name in ["peak", "standard", "off_peak"]:
            periods = time_bands.get(band_name, [])
            for period in periods:
                start_str = period.get("start", "00:00")
                end_str = period.get("end", "00:00")
                start_t = time.fromisoformat(start_str)
                end_t = time.fromisoformat(end_str)

                # Handle overnight periods (e.g. 22:00 -> 06:00)
                if start_t > end_t:
                    in_band = current_time >= start_t or current_time < end_t
                else:
                    in_band = start_t <= current_time < end_t

                if in_band:
                    energy_c = energy_charges.get(band_name, 0)
                    network_c = network_charges.get(band_name, 0)
                    energy_zar = energy_c / 100.0  # c/kWh -> ZAR/kWh
                    network_zar = network_c / 100.0

                    return TariffBand(
                        name=band_name,
                        rate_per_kwh=energy_zar,
                        network_charge_per_kwh=network_zar,
                        total_rate_per_kwh=energy_zar + network_zar,
                        season=season,
                        period_start=start_str,
                        period_end=end_str,
                    )

        # Fallback to off-peak if no match (shouldn't happen with complete config)
        off_peak_c = energy_charges.get("off_peak", 170.95)
        off_peak_net_c = network_charges.get("off_peak", 6.0)
        return TariffBand(
            name="off_peak",
            rate_per_kwh=off_peak_c / 100.0,
            network_charge_per_kwh=off_peak_net_c / 100.0,
            total_rate_per_kwh=(off_peak_c + off_peak_net_c) / 100.0,
            season=season,
            period_start="22:00",
            period_end="06:00",
        )

    def _get_band_rate(self, band_name: str, season: str) -> float:
        """Get total rate (energy + network) in ZAR/kWh for a band."""
        energy_c = self._tariff.get("energy_charge_c_kwh", {}).get(season, {}).get(band_name, 0)
        network_c = self._tariff.get("network_charge_c_kwh", {}).get(season, {}).get(band_name, 0)
        return (energy_c + network_c) / 100.0

    # === Arbitrage calculation ===

    def calculate_arbitrage_value(
        self,
        charge_kwh: float,
        discharge_kwh: float,
        charge_band: str = "off_peak",
        discharge_band: str = "peak",
        season: str | None = None,
    ) -> ArbitrageValue:
        """Calculate revenue from buying energy at low rate and selling at high rate.

        Args:
            charge_kwh: Energy bought from grid during off-peak.
            discharge_kwh: Energy discharged during peak (after round-trip losses).
            charge_band: Tariff band during charging (default off_peak).
            discharge_band: Tariff band during discharging (default peak).
            season: Override season; auto-detected if None.
        """
        season = season or self._get_season()
        charge_rate = self._get_band_rate(charge_band, season)
        discharge_rate = self._get_band_rate(discharge_band, season)

        charge_cost = charge_kwh * charge_rate
        # Account for round-trip efficiency
        effective_discharge = min(discharge_kwh, charge_kwh * self.BESS_ROUND_TRIP_EFF)
        discharge_revenue = effective_discharge * discharge_rate
        net_savings = discharge_revenue - charge_cost

        return ArbitrageValue(
            charge_kwh=charge_kwh,
            discharge_kwh=effective_discharge,
            charge_cost_zar=charge_cost,
            discharge_revenue_zar=discharge_revenue,
            net_savings_zar=net_savings,
            round_trip_efficiency=self.BESS_ROUND_TRIP_EFF,
            charge_rate_per_kwh=charge_rate,
            discharge_rate_per_kwh=discharge_rate,
        )

    # === Dispatch schedule generation ===

    def generate_dispatch_schedule(
        self,
        site_id: str,
        target_date: date | None = None,
        forecast_cloudy: bool | None = None,
    ) -> DispatchSchedule:
        """Generate day-ahead BESS dispatch plan optimised for TOU arbitrage.

        Strategy:
          - Off-peak (22:00-06:00): Charge BESS from grid at lowest rate
          - Morning peak (07:00-10:00 summer / 06:00-09:00 winter): Discharge
          - Standard (10:00-18:00 summer / 09:00-17:00 winter): Solar priority,
            excess to BESS
          - Evening peak (18:00-20:00 summer / 17:00-19:00 winter): Discharge
          - Standard evening (20:00-22:00 summer / 19:00-22:00 winter): Idle

        Forecast-aware adjustments (when forecast_cloudy is provided):
          - Cloudy forecast: Charge BESS more aggressively overnight (full rate)
            because solar won't be sufficient to charge during standard hours.
          - Sunny forecast: Moderate overnight charge; rely on solar midday.

        Respects BESS constraints:
          - Min SOC 10%, Max SOC 95%
          - Max charge/discharge rate 250 kW (0.5C)
        """
        d = target_date or date.today()
        dt = datetime(d.year, d.month, d.day, tzinfo=UTC)
        season = self._get_season(dt)
        time_bands = self._tariff.get("time_bands", {}).get(season, {})

        # Usable capacity
        usable_kwh = self.BESS_CAPACITY_KWH * ((self.BESS_MAX_SOC_PCT - self.BESS_MIN_SOC_PCT) / 100.0)

        slots: list[DispatchSlot] = []

        # Build dispatch slots from tariff time bands
        # Sort all periods chronologically for a 24h schedule
        band_schedule = []
        for band_name in ["off_peak", "peak", "standard"]:
            periods = time_bands.get(band_name, [])
            for period in periods:
                start_str = period["start"]
                end_str = period["end"]
                band_schedule.append((start_str, end_str, band_name))

        # Sort by start time, handling overnight (22:00 sorts after 20:00)
        band_schedule.sort(key=lambda x: x[0])

        total_savings = 0.0
        off_peak_rate = self._get_band_rate("off_peak", season)
        peak_rate = self._get_band_rate("peak", season)
        _std_rate = self._get_band_rate("standard", season)

        for start_str, end_str, band_name in band_schedule:
            rate = self._get_band_rate(band_name, season)

            if band_name == "off_peak":
                # Charge BESS during off-peak
                # Calculate hours (handle overnight)
                hours = self._period_hours(start_str, end_str)

                # Forecast-aware charging strategy
                if forecast_cloudy is True:
                    # Cloudy tomorrow: charge aggressively to full capacity
                    # because solar won't provide enough to charge during standard hours
                    charge_power = self.BESS_RATED_POWER_KW
                    target_soc = self.BESS_MAX_SOC_PCT
                    note = "Cloudy forecast: aggressive overnight charge (solar insufficient tomorrow)"
                elif forecast_cloudy is False:
                    # Sunny tomorrow: moderate charge; solar will top up during standard
                    charge_power = min(
                        self.BESS_RATED_POWER_KW * 0.6,  # 60% charge rate
                        usable_kwh * 0.6 / hours if hours > 0 else self.BESS_RATED_POWER_KW * 0.6,
                    )
                    target_soc = 70.0  # Only charge to 70%; solar handles the rest
                    note = "Sunny forecast: moderate overnight charge (solar will top up midday)"
                else:
                    # No forecast available: standard strategy
                    charge_power = min(
                        self.BESS_RATED_POWER_KW,
                        usable_kwh / hours if hours > 0 else self.BESS_RATED_POWER_KW,
                    )
                    target_soc = self.BESS_MAX_SOC_PCT
                    note = ""

                slots.append(
                    DispatchSlot(
                        start=start_str,
                        end=end_str,
                        action=DispatchActionType.CHARGE.value,
                        power_kw=charge_power,
                        target_soc_pct=target_soc,
                        tariff_band=band_name,
                        rate_per_kwh=rate,
                        note=note,
                    )
                )

            elif band_name == "peak":
                # Discharge BESS during peak
                hours = self._period_hours(start_str, end_str)
                discharge_power = min(
                    self.BESS_RATED_POWER_KW,
                    (usable_kwh / 2) / hours if hours > 0 else self.BESS_RATED_POWER_KW,
                )
                # Calculate savings for this peak slot
                discharged_kwh = discharge_power * hours
                slot_savings = discharged_kwh * (peak_rate - off_peak_rate) * self.BESS_ROUND_TRIP_EFF
                total_savings += slot_savings

                slots.append(
                    DispatchSlot(
                        start=start_str,
                        end=end_str,
                        action=DispatchActionType.DISCHARGE.value,
                        power_kw=discharge_power,
                        tariff_band=band_name,
                        rate_per_kwh=rate,
                    )
                )

            elif band_name == "standard":
                # During standard: solar priority (BESS absorbs excess solar)
                # For morning/afternoon standard, go solar priority
                # For evening standard (after 20:00), idle
                start_h = int(start_str.split(":")[0])
                is_midday = (start_h >= 10 and start_h < 18) or (start_h >= 9 and start_h < 17)

                if is_midday:
                    # Forecast-aware standard period behaviour
                    if forecast_cloudy is True:
                        # Cloudy: BESS conserves energy, doesn't expect solar top-up
                        slots.append(
                            DispatchSlot(
                                start=start_str,
                                end=end_str,
                                action=DispatchActionType.IDLE.value,
                                power_kw=0,
                                tariff_band=band_name,
                                rate_per_kwh=rate,
                                note="Cloudy forecast: BESS conserving for evening peak",
                            )
                        )
                    else:
                        slots.append(
                            DispatchSlot(
                                start=start_str,
                                end=end_str,
                                action=DispatchActionType.SOLAR_PRIORITY.value,
                                power_kw=0,
                                tariff_band=band_name,
                                rate_per_kwh=rate,
                                note="BESS absorbs excess solar generation",
                            )
                        )
                else:
                    # Early morning or evening standard: idle
                    slots.append(
                        DispatchSlot(
                            start=start_str,
                            end=end_str,
                            action=DispatchActionType.IDLE.value,
                            power_kw=0,
                            tariff_band=band_name,
                            rate_per_kwh=rate,
                        )
                    )

        # Sort slots by start time for clean output
        slots.sort(key=lambda s: s.start)

        return DispatchSchedule(
            site_id=site_id,
            date=d.isoformat(),
            season=season,
            slots=slots,
            projected_savings_zar=total_savings,
        )

    @staticmethod
    def _period_hours(start_str: str, end_str: str) -> float:
        """Calculate hours between two HH:MM times (handles overnight)."""
        sh, sm = map(int, start_str.split(":"))
        eh, em = map(int, end_str.split(":"))
        start_min = sh * 60 + sm
        end_min = eh * 60 + em
        if end_min <= start_min:
            end_min += 24 * 60  # overnight
        return (end_min - start_min) / 60.0

    # === Real-time dispatch action ===

    def get_realtime_dispatch_action(
        self,
        site_id: str,
        current_soc_pct: float = 50.0,
        solar_gen_kw: float = 0.0,
        site_load_kw: float = 0.0,
        load_shedding_active: bool = False,
        timestamp: datetime | None = None,
    ) -> DispatchAction:
        """Determine what BESS should do RIGHT NOW based on current state.

        Decision logic:
          1. Load shedding active -> discharge to sustain critical loads
          2. SOC below minimum -> charge immediately
          3. Off-peak -> charge from grid
          4. Peak -> discharge
          5. Standard + excess solar -> absorb excess
          6. Standard + no excess -> idle
        """
        band = self.get_current_tariff_band(timestamp)
        _ts = timestamp or datetime.now(UTC)

        # Priority 1: Load shedding -- discharge to sustain building
        if load_shedding_active:
            discharge_power = min(self.BESS_RATED_POWER_KW, site_load_kw)
            if current_soc_pct <= self.BESS_MIN_SOC_PCT:
                return DispatchAction(
                    action=DispatchActionType.IDLE.value,
                    power_kw=0,
                    reason="Load shedding active but BESS at minimum SOC; generator should cover",
                    tariff_band=band.name,
                    rate_per_kwh=band.total_rate_per_kwh,
                    current_soc_pct=current_soc_pct,
                    load_shedding_active=True,
                )
            return DispatchAction(
                action=DispatchActionType.DISCHARGE.value,
                power_kw=discharge_power,
                reason=f"Load shedding active; discharging to sustain {site_load_kw:.0f} kW critical load",
                tariff_band=band.name,
                rate_per_kwh=band.total_rate_per_kwh,
                current_soc_pct=current_soc_pct,
                load_shedding_active=True,
            )

        # Priority 2: SOC critically low -- charge regardless of band
        if current_soc_pct < self.BESS_MIN_SOC_PCT + 2:
            return DispatchAction(
                action=DispatchActionType.CHARGE.value,
                power_kw=self.BESS_RATED_POWER_KW,
                reason=f"SOC critically low ({current_soc_pct:.1f}%); emergency charge",
                tariff_band=band.name,
                rate_per_kwh=band.total_rate_per_kwh,
                current_soc_pct=current_soc_pct,
                target_soc_pct=self.BESS_MIN_SOC_PCT + 10,
            )

        # Priority 3: Band-based dispatch
        if band.name == "off_peak":
            if current_soc_pct >= self.BESS_MAX_SOC_PCT:
                return DispatchAction(
                    action=DispatchActionType.IDLE.value,
                    power_kw=0,
                    reason=f"Off-peak but BESS fully charged ({current_soc_pct:.1f}%)",
                    tariff_band=band.name,
                    rate_per_kwh=band.total_rate_per_kwh,
                    current_soc_pct=current_soc_pct,
                )
            return DispatchAction(
                action=DispatchActionType.CHARGE.value,
                power_kw=self.BESS_RATED_POWER_KW,
                reason=f"Off-peak tariff @ R{band.total_rate_per_kwh:.2f}/kWh; charging to 95%",
                tariff_band=band.name,
                rate_per_kwh=band.total_rate_per_kwh,
                current_soc_pct=current_soc_pct,
                target_soc_pct=self.BESS_MAX_SOC_PCT,
            )

        elif band.name == "peak":
            if current_soc_pct <= self.BESS_MIN_SOC_PCT:
                return DispatchAction(
                    action=DispatchActionType.IDLE.value,
                    power_kw=0,
                    reason=f"Peak tariff but BESS at minimum SOC ({current_soc_pct:.1f}%)",
                    tariff_band=band.name,
                    rate_per_kwh=band.total_rate_per_kwh,
                    current_soc_pct=current_soc_pct,
                )
            discharge_power = min(self.BESS_RATED_POWER_KW, site_load_kw or self.BESS_RATED_POWER_KW)
            return DispatchAction(
                action=DispatchActionType.DISCHARGE.value,
                power_kw=discharge_power,
                reason=f"Peak tariff @ R{band.total_rate_per_kwh:.2f}/kWh; discharging to offset grid import",
                tariff_band=band.name,
                rate_per_kwh=band.total_rate_per_kwh,
                current_soc_pct=current_soc_pct,
            )

        else:
            # Standard band -- solar priority
            excess_solar = max(0, solar_gen_kw - site_load_kw)
            if excess_solar > 50 and current_soc_pct < self.BESS_MAX_SOC_PCT:
                charge_power = min(excess_solar, self.BESS_RATED_POWER_KW)
                return DispatchAction(
                    action=DispatchActionType.SOLAR_PRIORITY.value,
                    power_kw=charge_power,
                    reason=f"Standard tariff; absorbing {excess_solar:.0f} kW excess solar",
                    tariff_band=band.name,
                    rate_per_kwh=band.total_rate_per_kwh,
                    current_soc_pct=current_soc_pct,
                    target_soc_pct=self.BESS_MAX_SOC_PCT,
                )
            return DispatchAction(
                action=DispatchActionType.IDLE.value,
                power_kw=0,
                reason="Standard tariff; no excess solar; BESS idle",
                tariff_band=band.name,
                rate_per_kwh=band.total_rate_per_kwh,
                current_soc_pct=current_soc_pct,
            )

    # === Load shedding adjustment ===

    def adjust_for_load_shedding(
        self,
        schedule: DispatchSchedule,
        ls_stage: int,
        ls_start: str,
        ls_end: str,
    ) -> DispatchSchedule:
        """Adjust dispatch schedule when load shedding is announced.

        Strategy:
          - Before LS window: ensure BESS SOC >= 80%
          - During LS: discharge to sustain critical loads
          - After LS: resume normal dispatch schedule
        """
        if ls_stage <= 0:
            return schedule

        ls_adjustment = {
            "stage": ls_stage,
            "window_start": ls_start,
            "window_end": ls_end,
            "reserve_soc_pct": self.BESS_LS_RESERVE_SOC_PCT,
            "strategy": "Pre-charge to 80% SOC, discharge during outage, resume after",
        }

        # Modify slots that overlap with pre-LS period (1 hour before)
        ls_start_h, ls_start_m = map(int, ls_start.split(":"))
        pre_ls_start_min = (ls_start_h * 60 + ls_start_m) - 60  # 1 hour before
        if pre_ls_start_min < 0:
            pre_ls_start_min += 24 * 60

        # Create modified schedule
        modified_slots = []
        for slot in schedule.slots:
            sh = int(slot.start.split(":")[0])
            slot_start_min = sh * 60 + int(slot.start.split(":")[1])

            # Check if this slot is just before LS window
            if abs(slot_start_min - pre_ls_start_min) < 120:
                # Force charge to LS reserve SOC
                modified_slots.append(
                    DispatchSlot(
                        start=slot.start,
                        end=ls_start,
                        action=DispatchActionType.CHARGE.value,
                        power_kw=self.BESS_RATED_POWER_KW,
                        target_soc_pct=self.BESS_LS_RESERVE_SOC_PCT,
                        tariff_band=slot.tariff_band,
                        rate_per_kwh=slot.rate_per_kwh,
                        note=f"Pre-LS charge: ensure SOC >= {self.BESS_LS_RESERVE_SOC_PCT}% before Stage {ls_stage}",
                    )
                )
                # Add LS discharge slot
                modified_slots.append(
                    DispatchSlot(
                        start=ls_start,
                        end=ls_end,
                        action=DispatchActionType.DISCHARGE.value,
                        power_kw=self.BESS_RATED_POWER_KW,
                        tariff_band="load_shedding",
                        rate_per_kwh=0,
                        note=f"Load shedding Stage {ls_stage}: discharging to sustain critical loads",
                    )
                )
            else:
                modified_slots.append(slot)

        return DispatchSchedule(
            site_id=schedule.site_id,
            date=schedule.date,
            season=schedule.season,
            slots=modified_slots,
            load_shedding_adjustment=ls_adjustment,
            projected_savings_zar=schedule.projected_savings_zar,
        )

    # === Daily savings calculation ===

    def calculate_daily_savings(
        self,
        site_id: str,
        target_date: date | None = None,
        period: str = "day",
    ) -> DailySavings:
        """Calculate actual vs no-BESS cost comparison.

        Simulates a typical day profile for the Site-002 campus:
          - Building base load: ~1,800 kW
          - Peak demand: ~2,500 kW
          - Solar generation: ~2,800 kWh/day (typical for 3.9 MWp)
          - BESS cycles: 1 full cycle per day (off-peak charge, peak discharge)
        """
        d = target_date or date.today()
        dt = datetime(d.year, d.month, d.day, tzinfo=UTC)
        season = self._get_season(dt)

        # Rates in ZAR/kWh
        peak_rate = self._get_band_rate("peak", season)
        std_rate = self._get_band_rate("standard", season)
        off_peak_rate = self._get_band_rate("off_peak", season)

        # Usable BESS capacity
        usable_kwh = self.BESS_CAPACITY_KWH * ((self.BESS_MAX_SOC_PCT - self.BESS_MIN_SOC_PCT) / 100.0)
        dischargeable_kwh = usable_kwh * self.BESS_ROUND_TRIP_EFF

        # Simulated daily profile for Site-002
        # Peak hours: 5h (07:00-10:00 + 18:00-20:00 summer)
        peak_hours = 5.0
        std_hours = 10.0  # 06:00-07:00, 10:00-18:00, 20:00-22:00
        off_peak_hours = 8.0  # 22:00-06:00

        base_load_kw = 1800.0
        peak_load_kw = 2500.0
        solar_daily_kwh = 15800.0  # ~3.9 MWp * 4.05 PSH

        # Without BESS: all peak demand from grid
        peak_grid_kwh = peak_load_kw * peak_hours
        std_grid_kwh = base_load_kw * std_hours - solar_daily_kwh * 0.7  # 70% solar during standard
        off_peak_grid_kwh = base_load_kw * off_peak_hours

        cost_without_bess = (
            peak_grid_kwh * peak_rate + max(0, std_grid_kwh) * std_rate + off_peak_grid_kwh * off_peak_rate
        )

        # With BESS: discharge during peak, charge during off-peak
        peak_kwh_avoided = min(dischargeable_kwh, peak_grid_kwh)
        off_peak_charge_kwh = peak_kwh_avoided / self.BESS_ROUND_TRIP_EFF

        cost_with_bess = (
            (peak_grid_kwh - peak_kwh_avoided) * peak_rate
            + max(0, std_grid_kwh) * std_rate
            + (off_peak_grid_kwh + off_peak_charge_kwh) * off_peak_rate
        )

        savings = cost_without_bess - cost_with_bess

        # Scale for period
        multiplier = 1.0
        if period == "week":
            multiplier = 5.0  # weekdays only (weekend profile different)
        elif period == "month":
            multiplier = 22.0  # ~22 business days

        return DailySavings(
            site_id=site_id,
            date=d.isoformat(),
            period=period,
            with_bess_zar=cost_with_bess * multiplier,
            without_bess_zar=cost_without_bess * multiplier,
            savings_zar=savings * multiplier,
            savings_pct=(savings / cost_without_bess * 100) if cost_without_bess > 0 else 0,
            peak_kwh_avoided=peak_kwh_avoided * multiplier,
            off_peak_kwh_charged=off_peak_charge_kwh * multiplier,
            solar_self_consumed_kwh=solar_daily_kwh * 0.7 * multiplier,
        )


# === Singleton ===

_solar_arbitrage_engine: SolarArbitrageEngine | None = None


def get_solar_arbitrage_engine() -> SolarArbitrageEngine:
    """Get the singleton solar arbitrage engine instance."""
    global _solar_arbitrage_engine
    if _solar_arbitrage_engine is None:
        _solar_arbitrage_engine = SolarArbitrageEngine()
    return _solar_arbitrage_engine
