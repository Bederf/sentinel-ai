"""MIP Dispatch Optimizer — CP-SAT BESS dispatch scheduling.

Uses Google OR-Tools CP-SAT solver to find the cost-minimizing BESS
charge/discharge schedule over 96 15-minute intervals.

Decision variables (per interval t=0..95):
  - charge_kw[t], discharge_kw[t], soc_kwh[t], grid_import_kw[t]
  - is_charging[t], is_discharging[t]  (binary)

Objective: MINIMIZE
  sum(grid_import[t] * tariff[t] * 0.25)      # energy cost
  + peak_demand * demand_charge_rate            # demand charge (R395.48/kVA)
  + cycles * degradation_cost                   # battery wear

Constraints:
  1. Energy balance: load[t] = solar[t] + grid[t] + discharge[t] - charge[t]
  2. SOC tracking: soc[t+1] = soc[t] + charge[t]*eff*0.25 - discharge[t]/eff*0.25
  3. SOC bounds: min_soc <= soc[t] <= max_soc
  4. Mutual exclusion: is_charging[t] + is_discharging[t] <= 1
  5. Power limits (rated capacity)
  6. Export limit, NMD constraint
  7. Load shedding override

Timeout: 10s (falls back to rules-based if solver fails)
"""

import logging
import time
from datetime import UTC, datetime, timedelta
from typing import Any

from ortools.sat.python import cp_model

from app.models.dispatch_schedule import DispatchInterval, OptimalDispatchSchedule

logger = logging.getLogger(__name__)

# Scaling factor: CP-SAT works with integers, so we scale kW/kWh by this factor
SCALE = 100  # 0.01 kW resolution

# Default TOU tariff rates (c/kWh converted to ZAR/kWh) — winter/summer averages.
# Used when no SiteConfig is available. Preserved for backward compat with tests.
_DEFAULT_TARIFF_RATES = {
    "off_peak": 0.6490,
    "standard": 1.2457,
    "peak": 3.7641,
}

# Legacy aliases — existing test imports reference these names
_TARIFF_RATES = _DEFAULT_TARIFF_RATES

# Default peak hours (SAST) — used when no SiteConfig time bands available
_DEFAULT_PEAK_HOURS = {7, 8, 9, 18, 19}
_DEFAULT_OFF_PEAK_HOURS = {22, 23, 0, 1, 2, 3, 4, 5}

# Legacy aliases
_PEAK_HOURS = _DEFAULT_PEAK_HOURS
_OFF_PEAK_HOURS = _DEFAULT_OFF_PEAK_HOURS


def _tariff_for_hour(hour: int, site_config=None, month: int | None = None) -> tuple:
    """Return (rate_zar_per_kwh, band_name) for a SAST hour.

    When site_config (SiteConfig) is provided, uses verified invoice tariff
    rates and time band definitions. Otherwise falls back to hardcoded defaults.
    """
    if site_config is not None:
        try:
            m = month if month is not None else datetime.now().month
            period = site_config.time_bands.get_period(hour, m)
            season = site_config.time_bands.get_season(m)
            rate = site_config.tariff.rate_r_kwh(period, season)
            return rate, period
        except Exception:
            pass  # Fall through to defaults

    if hour in _DEFAULT_PEAK_HOURS:
        return _DEFAULT_TARIFF_RATES["peak"], "peak"
    elif hour in _DEFAULT_OFF_PEAK_HOURS:
        return _DEFAULT_TARIFF_RATES["off_peak"], "off_peak"
    else:
        return _DEFAULT_TARIFF_RATES["standard"], "standard"


def _build_ls_schedule_from_eskom(
    area_events: list,
    sast_start: datetime,
    n: int = 96,
) -> list[bool]:
    """Convert EskomSePush AreaEvent list into a 96-slot boolean schedule.

    Each slot represents a 15-minute interval starting from sast_start.
    A slot is True if any load shedding event (stage > 0) overlaps it.
    """
    from datetime import datetime as _dt

    schedule = [False] * n

    for event in area_events:
        if event.stage <= 0:
            continue
        try:
            ev_start = _dt.fromisoformat(event.start)
            ev_end = _dt.fromisoformat(event.end)
        except (ValueError, TypeError):
            continue

        for t in range(n):
            slot_start = sast_start + timedelta(minutes=t * 15)
            slot_end = slot_start + timedelta(minutes=15)
            # Overlap check: event overlaps slot if event starts before slot ends
            # AND event ends after slot starts
            if ev_start < slot_end and ev_end > slot_start:
                schedule[t] = True

    return schedule


class MIPDispatchOptimizer:
    """CP-SAT BESS dispatch optimizer.

    Accepts load and solar forecasts (96 intervals each) and produces
    an optimal charge/discharge schedule that minimizes total cost
    (energy + demand charge + battery degradation).
    """

    # BESS specifications (Site-002 LUNA2000-200KWH-2H1)
    BESS_CAPACITY_KWH = 200.0
    BESS_RATED_POWER_KW = 100.0
    BESS_EFFICIENCY = 0.90
    BESS_MIN_SOC_KWH = 40.0  # 20% of 200 kWh
    BESS_MAX_SOC_KWH = 190.0  # 95% of 200 kWh
    BESS_DEGRADATION_COST_PER_CYCLE = 15.0  # ZAR per full cycle

    # Grid constraints
    NMD_LIMIT_KVA = 1820.0
    DEMAND_CHARGE_RATE = 395.48  # R/kVA/month — prorated per day: /30
    EXPORT_LIMIT_KW = 50.0  # 50% of rated power

    # Solver
    SOLVER_TIMEOUT_S = 10

    def __init__(self):
        self._last_schedule: dict[str, OptimalDispatchSchedule] = {}
        self._site_config = None
        try:
            from app.services.solar_config_service import get_site_solar_config

            self._site_config = get_site_solar_config()
        except Exception:
            logger.debug("SiteConfig not available — using default tariffs")

    def optimize(
        self,
        site_id: str,
        initial_soc_kwh: float = 100.0,
        load_forecast: list[float] | None = None,
        solar_forecast: list[float] | None = None,
        ls_schedule: list[bool] | None = None,
    ) -> OptimalDispatchSchedule:
        """Solve the optimal BESS dispatch schedule.

        Args:
            site_id: Site identifier
            initial_soc_kwh: Starting SOC in kWh
            load_forecast: 96 values of predicted load (kW) per 15-min interval
            solar_forecast: 96 values of predicted solar gen (kW) per 15-min interval
            ls_schedule: 96 booleans — True if load shedding active in that interval

        Returns:
            OptimalDispatchSchedule with 96 intervals
        """
        n = 96  # 15-min intervals in 24h
        now = datetime.now(UTC)
        sast_now = now + timedelta(hours=2)

        # Default forecasts if not provided
        if load_forecast is None:
            load_forecast = [1500.0] * n
        if solar_forecast is None:
            solar_forecast = [0.0] * n
        if ls_schedule is None:
            ls_schedule = [False] * n

        # Pad/trim to exactly n intervals
        load_forecast = (load_forecast + [load_forecast[-1]] * n)[:n]
        solar_forecast = (solar_forecast + [solar_forecast[-1]] * n)[:n]
        ls_schedule = (ls_schedule + [False] * n)[:n]

        # Build tariff schedule (use verified invoice rates when SiteConfig available)
        tariff_rates = []
        tariff_bands = []
        for t in range(n):
            interval_dt = sast_now + timedelta(minutes=t * 15)
            rate, band = _tariff_for_hour(interval_dt.hour, self._site_config, interval_dt.month)
            tariff_rates.append(rate)
            tariff_bands.append(band)

        start_time = time.monotonic()

        try:
            schedule = self._solve_cpsat(
                n,
                initial_soc_kwh,
                load_forecast,
                solar_forecast,
                tariff_rates,
                tariff_bands,
                ls_schedule,
                sast_now,
            )
        except Exception as e:
            logger.warning("CP-SAT solver failed: %s — falling back to rules", e)
            schedule = self._rules_fallback(
                site_id,
                n,
                initial_soc_kwh,
                load_forecast,
                solar_forecast,
                tariff_rates,
                tariff_bands,
                sast_now,
                ls=ls_schedule,
            )

        solve_time_ms = (time.monotonic() - start_time) * 1000
        schedule.site_id = site_id
        schedule.solve_time_ms = solve_time_ms
        schedule.generated_at = now.isoformat()

        # Cache for dispatch service consumption
        self._last_schedule[site_id] = schedule

        logger.info(
            "MIP dispatch optimized: site=%s status=%s cost=R%.2f peak=%.0f kW cycles=%.2f time=%.0f ms",
            site_id,
            schedule.solver_status,
            schedule.total_cost_zar,
            schedule.peak_grid_import_kw,
            schedule.cycles,
            solve_time_ms,
        )

        return schedule

    def _solve_cpsat(
        self,
        n: int,
        initial_soc_kwh: float,
        load: list[float],
        solar: list[float],
        tariff: list[float],
        bands: list[str],
        ls: list[bool],
        sast_start: datetime,
    ) -> OptimalDispatchSchedule:
        """Solve using CP-SAT with integer-scaled variables."""
        model = cp_model.CpModel()

        rated_s = int(self.BESS_RATED_POWER_KW * SCALE)
        min_soc_s = int(self.BESS_MIN_SOC_KWH * SCALE)
        max_soc_s = int(self.BESS_MAX_SOC_KWH * SCALE)
        eff_pct = int(self.BESS_EFFICIENCY * 100)  # 90

        # Decision variables
        charge = [model.new_int_var(0, rated_s, f"charge_{t}") for t in range(n)]
        discharge = [model.new_int_var(0, rated_s, f"discharge_{t}") for t in range(n)]
        soc = [model.new_int_var(min_soc_s, max_soc_s, f"soc_{t}") for t in range(n + 1)]
        is_charging = [model.new_bool_var(f"is_charging_{t}") for t in range(n)]
        is_discharging = [model.new_bool_var(f"is_discharging_{t}") for t in range(n)]

        # Grid import: load + charge - solar - discharge (can be negative = export)
        grid_import = [model.new_int_var(-rated_s * 10, int(2500 * SCALE), f"grid_{t}") for t in range(n)]

        # Peak demand variable
        peak_demand = model.new_int_var(0, int(self.NMD_LIMIT_KVA * SCALE), "peak_demand")

        # Initial SOC constraint
        model.add(soc[0] == int(initial_soc_kwh * SCALE))

        for t in range(n):
            load_s = int(load[t] * SCALE)
            solar_s = int(solar[t] * SCALE)

            # 1. Mutual exclusion
            model.add(is_charging[t] + is_discharging[t] <= 1)

            # 2. Link binary to continuous
            model.add(charge[t] <= rated_s * is_charging[t])
            model.add(discharge[t] <= rated_s * is_discharging[t])

            # 3. Energy balance: grid = load + charge - solar - discharge
            model.add(grid_import[t] == load_s + charge[t] - solar_s - discharge[t])

            # 4. SOC tracking (0.25h per interval, efficiency applied)
            # soc[t+1] = soc[t] + charge[t]*eff*0.25 - discharge[t]/eff*0.25
            # Scale: charge is in SCALE units of kW, multiply by 25 (0.25h * 100 for eff_pct)
            # soc_delta_charge = charge[t] * eff_pct * 25 / (100 * 100)
            # = charge[t] * eff_pct / 400
            # For integer math: soc[t+1]*400 = soc[t]*400 + charge[t]*eff_pct - discharge[t]*10000/eff_pct
            # Simpler: use auxiliary variables
            # Approximate: soc[t+1] ~= soc[t] + (charge[t]*eff_pct - discharge[t]*100/eff_pct) / 400
            # Multiply everything by 400 to avoid fractions:
            # soc[t+1]*400 = soc[t]*400 + charge[t]*eff_pct*25/100 - discharge[t]*25*100/eff_pct
            # Actually let's simplify with a single scaling:
            # delta_charge_energy = charge[t] * 0.25 * eff = charge[t] * 0.225 (for 90%)
            # delta_discharge_energy = discharge[t] * 0.25 / eff = discharge[t] * 0.2778
            # In scaled units (SCALE=100): multiply kW by 0.25 = divide by 4
            # charge_energy_s = charge[t] * eff_pct / (4 * 100)
            # = charge[t] * 90 / 400
            # discharge_energy_s = discharge[t] * 100 / (eff_pct * 4)
            # = discharge[t] * 100 / 360

            # Linear: 400*soc[t+1] = 400*soc[t] + charge*eff_pct - discharge*(10000//eff_pct)
            # That keeps it integer. eff_pct=90, 10000//90=111
            inv_eff = 10000 // eff_pct  # 111 for 90%

            model.add(400 * soc[t + 1] == 400 * soc[t] + eff_pct * charge[t] - inv_eff * discharge[t])

            # 5. Export limit (grid import can go negative = export)
            export_limit_s = int(self.EXPORT_LIMIT_KW * SCALE)
            model.add(grid_import[t] >= -export_limit_s)

            # 6. Peak demand tracking
            model.add(peak_demand >= grid_import[t])

            # 7. Load shedding: force discharge to help sustain load
            if ls[t]:
                model.add(is_discharging[t] == 1)
                # Minimum 10 kW discharge during LS (or whatever SOC allows)
                min_ls_discharge = int(10.0 * SCALE)
                model.add(discharge[t] >= min_ls_discharge)

        # NMD constraint: peak demand <= NMD limit
        nmd_s = int(self.NMD_LIMIT_KVA * SCALE)
        model.add(peak_demand <= nmd_s)

        # Objective: minimize total cost
        # Energy cost = sum(grid_import[t] * tariff[t] * 0.25)
        # Scale tariff by 10000 for integer math
        energy_cost_terms = []
        for t in range(n):
            tariff_scaled = int(tariff[t] * 10000)
            # cost = grid_import * tariff_scaled * 25 / (SCALE * 10000 * 100)
            # = grid_import * tariff_scaled / (SCALE * 40000)
            # Keep as objective coefficient: grid_import[t] * tariff_scaled
            energy_cost_terms.append((grid_import[t], tariff_scaled))

        # Demand charge: prorated per day
        # demand_charge = peak_demand * DEMAND_CHARGE_RATE / 30
        demand_charge_scaled = int(self.DEMAND_CHARGE_RATE * 10000 / 30)

        # Cycle cost: approximated by total discharge energy
        # cycles = total_discharge_kwh / capacity_kwh
        # cost = cycles * degradation_cost
        deg_scaled = int(self.BESS_DEGRADATION_COST_PER_CYCLE * 10000 / self.BESS_CAPACITY_KWH)

        # Build objective as weighted sum
        objective_terms = []
        for var, coeff in energy_cost_terms:
            objective_terms.append(coeff * var)
        objective_terms.append(demand_charge_scaled * peak_demand)
        for t in range(n):
            objective_terms.append(deg_scaled * discharge[t])

        model.minimize(sum(objective_terms))

        # Solve
        solver = cp_model.CpSolver()
        solver.parameters.max_time_in_seconds = self.SOLVER_TIMEOUT_S

        status = solver.solve(model)

        if status not in (cp_model.OPTIMAL, cp_model.FEASIBLE):
            raise RuntimeError(f"Solver status: {solver.status_name(status)}")

        solver_status = "optimal" if status == cp_model.OPTIMAL else "feasible"

        # Extract solution
        intervals = []
        total_cost = 0.0
        peak_grid = 0.0
        total_energy = 0.0
        total_solar = 0.0
        total_discharge_kwh = 0.0

        for t in range(n):
            interval_dt = sast_start + timedelta(minutes=t * 15)
            c_kw = solver.value(charge[t]) / SCALE
            d_kw = solver.value(discharge[t]) / SCALE
            s_kwh = solver.value(soc[t]) / SCALE
            g_kw = solver.value(grid_import[t]) / SCALE

            interval_cost = max(0, g_kw) * tariff[t] * 0.25

            intervals.append(
                DispatchInterval(
                    timestamp=interval_dt.strftime("%Y-%m-%dT%H:%M"),
                    charge_kw=c_kw,
                    discharge_kw=d_kw,
                    soc_kwh=s_kwh,
                    grid_import_kw=g_kw,
                    solar_kw=solar[t],
                    load_kw=load[t],
                    tariff_rate=tariff[t],
                    tariff_band=bands[t],
                    interval_cost_zar=interval_cost,
                )
            )

            total_cost += interval_cost
            peak_grid = max(peak_grid, g_kw)
            total_energy += max(0, g_kw) * 0.25
            total_solar += solar[t] * 0.25
            total_discharge_kwh += d_kw * 0.25

        # Demand charge
        demand_charge = peak_grid * self.DEMAND_CHARGE_RATE / 30
        total_cost += demand_charge

        # Degradation cost
        cycles = total_discharge_kwh / self.BESS_CAPACITY_KWH
        degradation_cost = cycles * self.BESS_DEGRADATION_COST_PER_CYCLE
        total_cost += degradation_cost

        return OptimalDispatchSchedule(
            site_id="",  # Filled by caller
            generated_at="",  # Filled by caller
            solver_status=solver_status,
            intervals=intervals,
            total_cost_zar=total_cost,
            peak_grid_import_kw=peak_grid,
            total_energy_kwh=total_energy,
            total_solar_kwh=total_solar,
            cycles=cycles,
            demand_charge_zar=demand_charge,
            degradation_cost_zar=degradation_cost,
        )

    def _rules_fallback(
        self,
        site_id: str,
        n: int,
        initial_soc_kwh: float,
        load: list[float],
        solar: list[float],
        tariff: list[float],
        bands: list[str],
        sast_start: datetime,
        ls: list[bool] | None = None,
    ) -> OptimalDispatchSchedule:
        """Simple rules-based fallback when solver fails.

        Wraps existing solar_arbitrage_engine logic into OptimalDispatchSchedule format.
        """
        if ls is None:
            ls = [False] * n

        intervals = []
        soc = initial_soc_kwh
        total_cost = 0.0
        peak_grid = 0.0
        total_energy = 0.0
        total_solar = 0.0
        total_discharge_kwh = 0.0

        for t in range(n):
            interval_dt = sast_start + timedelta(minutes=t * 15)
            band = bands[t]
            rate = tariff[t]

            c_kw = 0.0
            d_kw = 0.0

            # Load shedding override: discharge to sustain load
            if ls[t] and soc > self.BESS_MIN_SOC_KWH:
                d_kw = min(self.BESS_RATED_POWER_KW, (soc - self.BESS_MIN_SOC_KWH) * self.BESS_EFFICIENCY / 0.25)
                soc_delta = d_kw * 0.25 / self.BESS_EFFICIENCY
                soc = max(self.BESS_MIN_SOC_KWH, soc - soc_delta)
                total_discharge_kwh += d_kw * 0.25
            # Rules: charge off-peak, discharge peak, idle standard
            elif band == "off_peak" and soc < self.BESS_MAX_SOC_KWH:
                c_kw = min(self.BESS_RATED_POWER_KW, (self.BESS_MAX_SOC_KWH - soc) / (0.25 * self.BESS_EFFICIENCY))
                soc_delta = c_kw * 0.25 * self.BESS_EFFICIENCY
                soc = min(self.BESS_MAX_SOC_KWH, soc + soc_delta)
            elif band == "peak" and soc > self.BESS_MIN_SOC_KWH:
                d_kw = min(self.BESS_RATED_POWER_KW, (soc - self.BESS_MIN_SOC_KWH) * self.BESS_EFFICIENCY / 0.25)
                soc_delta = d_kw * 0.25 / self.BESS_EFFICIENCY
                soc = max(self.BESS_MIN_SOC_KWH, soc - soc_delta)
                total_discharge_kwh += d_kw * 0.25

            # Grid import
            g_kw = load[t] + c_kw - solar[t] - d_kw
            interval_cost = max(0, g_kw) * rate * 0.25

            intervals.append(
                DispatchInterval(
                    timestamp=interval_dt.strftime("%Y-%m-%dT%H:%M"),
                    charge_kw=c_kw,
                    discharge_kw=d_kw,
                    soc_kwh=soc,
                    grid_import_kw=g_kw,
                    solar_kw=solar[t],
                    load_kw=load[t],
                    tariff_rate=rate,
                    tariff_band=band,
                    interval_cost_zar=interval_cost,
                )
            )

            total_cost += interval_cost
            peak_grid = max(peak_grid, g_kw)
            total_energy += max(0, g_kw) * 0.25
            total_solar += solar[t] * 0.25

        demand_charge = peak_grid * self.DEMAND_CHARGE_RATE / 30
        total_cost += demand_charge
        cycles = total_discharge_kwh / self.BESS_CAPACITY_KWH
        degradation_cost = cycles * self.BESS_DEGRADATION_COST_PER_CYCLE
        total_cost += degradation_cost

        return OptimalDispatchSchedule(
            site_id="",
            generated_at="",
            solver_status="rules_fallback",
            intervals=intervals,
            total_cost_zar=total_cost,
            peak_grid_import_kw=peak_grid,
            total_energy_kwh=total_energy,
            total_solar_kwh=total_solar,
            cycles=cycles,
            demand_charge_zar=demand_charge,
            degradation_cost_zar=degradation_cost,
        )

    async def optimize_async(
        self,
        site_id: str,
        initial_soc_kwh: float = 100.0,
        load_forecast: list[float] | None = None,
        solar_forecast: list[float] | None = None,
        ls_schedule: list[bool] | None = None,
    ) -> OptimalDispatchSchedule:
        """Async wrapper that enriches ls_schedule from EskomSePush if available.

        Falls back to synchronous optimize() with whatever data is available.
        """
        if ls_schedule is None:
            # Check manual override first, then EskomSePush API
            from app.config.settings import settings as _settings

            override = _settings.load_shedding_stage_override
            if override > 0:
                # Manual override: build a synthetic 24h load-shedding schedule
                ls_schedule = [True] * 96  # All intervals flagged
                logger.info("MIP using manual load-shedding override (stage %d)", override)
            elif override == -1:
                # Use EskomSePush API if configured (paid, optional)
                try:
                    from app.services.eskomsepush_service import eskomsepush_service

                    if eskomsepush_service.is_configured:
                        status = await eskomsepush_service.get_combined_status()
                        sast_start = datetime.now(UTC) + timedelta(hours=2)
                        ls_schedule = _build_ls_schedule_from_eskom(
                            status.area_events,
                            sast_start,
                        )
                except Exception as e:
                    logger.debug("EskomSePush enrichment failed (non-fatal): %s", e)

        return self.optimize(site_id, initial_soc_kwh, load_forecast, solar_forecast, ls_schedule)

    def get_cached_schedule(self, site_id: str) -> OptimalDispatchSchedule | None:
        """Return the most recent cached schedule, or None."""
        return self._last_schedule.get(site_id)

    def get_comparison(
        self,
        site_id: str,
        initial_soc_kwh: float = 100.0,
        load_forecast: list[float] | None = None,
        solar_forecast: list[float] | None = None,
    ) -> dict[str, Any]:
        """Compare MIP schedule vs rules-based side-by-side."""
        n = 96
        now = datetime.now(UTC)
        sast_now = now + timedelta(hours=2)

        if load_forecast is None:
            load_forecast = [1500.0] * n
        if solar_forecast is None:
            solar_forecast = [0.0] * n

        load_forecast = (load_forecast + [load_forecast[-1]] * n)[:n]
        solar_forecast = (solar_forecast + [solar_forecast[-1]] * n)[:n]

        tariff_rates = []
        tariff_bands = []
        for t in range(n):
            interval_dt = sast_now + timedelta(minutes=t * 15)
            rate, band = _tariff_for_hour(interval_dt.hour, self._site_config, interval_dt.month)
            tariff_rates.append(rate)
            tariff_bands.append(band)

        # MIP schedule
        mip_schedule = self.optimize(
            site_id,
            initial_soc_kwh,
            load_forecast,
            solar_forecast,
        )

        # Rules schedule
        rules_schedule = self._rules_fallback(
            site_id,
            n,
            initial_soc_kwh,
            load_forecast,
            solar_forecast,
            tariff_rates,
            tariff_bands,
            sast_now,
        )
        rules_schedule.site_id = site_id
        rules_schedule.generated_at = now.isoformat()

        savings_zar = rules_schedule.total_cost_zar - mip_schedule.total_cost_zar
        savings_pct = (savings_zar / rules_schedule.total_cost_zar * 100) if rules_schedule.total_cost_zar > 0 else 0

        return {
            "site_id": site_id,
            "mip": mip_schedule.to_dict(),
            "rules": rules_schedule.to_dict(),
            "savings_zar": round(savings_zar, 2),
            "savings_pct": round(savings_pct, 1),
            "mip_peak_kw": round(mip_schedule.peak_grid_import_kw, 1),
            "rules_peak_kw": round(rules_schedule.peak_grid_import_kw, 1),
        }


# === Singleton ===

_mip_dispatch_optimizer: MIPDispatchOptimizer | None = None


def get_mip_dispatch_optimizer() -> MIPDispatchOptimizer:
    """Get the singleton MIP dispatch optimizer instance."""
    global _mip_dispatch_optimizer
    if _mip_dispatch_optimizer is None:
        _mip_dispatch_optimizer = MIPDispatchOptimizer()
    return _mip_dispatch_optimizer
