"""Load Forecast Models — 15-minute building demand forecast dataclasses.

Used by LoadForecastService to return structured forecast data.
"""

from dataclasses import dataclass, field
from typing import Any


@dataclass
class LoadInterval:
    """A single 15-minute load forecast interval."""

    timestamp: str  # ISO format
    demand_kw: float
    confidence_high_kw: float
    confidence_low_kw: float
    is_peak_hour: bool = False
    tariff_band: str = "standard"

    def to_dict(self) -> dict[str, Any]:
        return {
            "timestamp": self.timestamp,
            "demand_kw": round(self.demand_kw, 1),
            "confidence_high_kw": round(self.confidence_high_kw, 1),
            "confidence_low_kw": round(self.confidence_low_kw, 1),
            "is_peak_hour": self.is_peak_hour,
            "tariff_band": self.tariff_band,
        }


@dataclass
class LoadForecast:
    """Complete 15-minute load forecast response."""

    site_id: str
    generated_at: str  # ISO timestamp
    model: str  # gradient_boosting
    intervals: list[LoadInterval] = field(default_factory=list)
    peak_demand_kw: float = 0.0
    avg_demand_kw: float = 0.0
    total_energy_kwh: float = 0.0
    accuracy: dict[str, float] | None = None

    def to_dict(self) -> dict[str, Any]:
        result: dict[str, Any] = {
            "site_id": self.site_id,
            "generated_at": self.generated_at,
            "model": self.model,
            "intervals": [i.to_dict() for i in self.intervals],
            "peak_demand_kw": round(self.peak_demand_kw, 1),
            "avg_demand_kw": round(self.avg_demand_kw, 1),
            "total_energy_kwh": round(self.total_energy_kwh, 1),
        }
        if self.accuracy:
            result["accuracy"] = {k: round(v, 3) for k, v in self.accuracy.items()}
        return result
