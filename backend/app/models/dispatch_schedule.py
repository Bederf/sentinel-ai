"""Dispatch Schedule Models — MIP-optimized BESS dispatch schedule dataclasses.

Used by MIPDispatchOptimizer to return structured optimal schedules.
"""

from dataclasses import dataclass, field
from typing import Any


@dataclass
class DispatchInterval:
    """A single 15-minute dispatch interval in the optimal schedule."""

    timestamp: str  # ISO format
    charge_kw: float
    discharge_kw: float
    soc_kwh: float
    grid_import_kw: float
    solar_kw: float
    load_kw: float
    tariff_rate: float
    tariff_band: str
    interval_cost_zar: float

    def to_dict(self) -> dict[str, Any]:
        return {
            "timestamp": self.timestamp,
            "charge_kw": round(self.charge_kw, 1),
            "discharge_kw": round(self.discharge_kw, 1),
            "soc_kwh": round(self.soc_kwh, 1),
            "grid_import_kw": round(self.grid_import_kw, 1),
            "solar_kw": round(self.solar_kw, 1),
            "load_kw": round(self.load_kw, 1),
            "tariff_rate": round(self.tariff_rate, 4),
            "tariff_band": self.tariff_band,
            "interval_cost_zar": round(self.interval_cost_zar, 2),
        }


@dataclass
class OptimalDispatchSchedule:
    """Complete MIP-optimized dispatch schedule."""

    site_id: str
    generated_at: str  # ISO timestamp
    solver_status: str  # optimal / feasible / timeout / infeasible / rules_fallback
    intervals: list[DispatchInterval] = field(default_factory=list)
    total_cost_zar: float = 0.0
    peak_grid_import_kw: float = 0.0
    total_energy_kwh: float = 0.0
    total_solar_kwh: float = 0.0
    cycles: float = 0.0
    solve_time_ms: float = 0.0
    demand_charge_zar: float = 0.0
    degradation_cost_zar: float = 0.0

    def to_dict(self) -> dict[str, Any]:
        return {
            "site_id": self.site_id,
            "generated_at": self.generated_at,
            "solver_status": self.solver_status,
            "intervals": [i.to_dict() for i in self.intervals],
            "total_cost_zar": round(self.total_cost_zar, 2),
            "peak_grid_import_kw": round(self.peak_grid_import_kw, 1),
            "total_energy_kwh": round(self.total_energy_kwh, 1),
            "total_solar_kwh": round(self.total_solar_kwh, 1),
            "cycles": round(self.cycles, 2),
            "solve_time_ms": round(self.solve_time_ms, 1),
            "demand_charge_zar": round(self.demand_charge_zar, 2),
            "degradation_cost_zar": round(self.degradation_cost_zar, 2),
        }
