"""
Sustainability & ESG Module Data Models

South African context:
- Eskom grid emission factor: 1.06 kg CO2/kWh (2023 IRP)
- Diesel: 2.68 kg CO2/L
- Green Star SA Office v1.1 rating tool

Scopes:
- Scope 1: Direct emissions (diesel generators)
- Scope 2: Indirect emissions (grid electricity)
- Scope 3: Other indirect (water, waste, commuting estimates)
"""

from dataclasses import dataclass, field
from datetime import date
from typing import Dict, List, Optional


@dataclass
class EmissionFactors:
    """South Africa-specific emission factors."""

    grid_kg_co2_per_kwh: float = 1.06  # Eskom grid (2023 IRP)
    diesel_kg_co2_per_litre: float = 2.68  # Diesel combustion
    water_kg_co2_per_kl: float = 0.708  # Water treatment & pumping
    waste_kg_co2_per_ton: float = 580.0  # Landfill waste
    commute_kg_co2_per_person_day: float = 4.2  # Average SA commute

    def to_dict(self) -> Dict:
        return {
            "grid_kg_co2_per_kwh": self.grid_kg_co2_per_kwh,
            "diesel_kg_co2_per_litre": self.diesel_kg_co2_per_litre,
            "water_kg_co2_per_kl": self.water_kg_co2_per_kl,
            "waste_kg_co2_per_ton": self.waste_kg_co2_per_ton,
            "commute_kg_co2_per_person_day": self.commute_kg_co2_per_person_day,
        }

    @classmethod
    def from_dict(cls, data: Dict) -> "EmissionFactors":
        return cls(
            grid_kg_co2_per_kwh=data.get("grid_kg_co2_per_kwh", 1.06),
            diesel_kg_co2_per_litre=data.get("diesel_kg_co2_per_litre", 2.68),
            water_kg_co2_per_kl=data.get("water_kg_co2_per_kl", 0.708),
            waste_kg_co2_per_ton=data.get("waste_kg_co2_per_ton", 580.0),
            commute_kg_co2_per_person_day=data.get("commute_kg_co2_per_person_day", 4.2),
        )


@dataclass
class EmissionsSnapshot:
    """Monthly emissions snapshot."""

    month: str  # YYYY-MM
    site_id: str
    scope1_kg_co2: float = 0.0  # Diesel generators
    scope2_kg_co2: float = 0.0  # Grid electricity
    scope3_kg_co2: float = 0.0  # Water, waste, commuting
    grid_kwh: float = 0.0
    diesel_litres: float = 0.0
    carbon_intensity_kg_per_sqm: float = 0.0
    energy_intensity_kwh_per_sqm: float = 0.0
    breakdown_by_system: Dict[str, float] = field(default_factory=dict)

    # Per-system carbon breakdown (plan 111-02)
    hvac_kg_co2: float = 0.0
    lighting_kg_co2: float = 0.0
    other_kg_co2: float = 0.0
    solar_offset_kg_co2: float = 0.0
    net_scope2_kg_co2: float = 0.0  # scope2 after solar offset

    # Source data — replaces hardcoded estimates (plan 111-02)
    actual_diesel_liters: Optional[float] = None  # From daily_sustainability_metrics
    actual_water_kl: Optional[float] = None  # From daily_sustainability_metrics
    solar_generation_kwh: Optional[float] = None  # From daily_sustainability_metrics
    data_source: str = "estimated"  # "estimated" | "measured" | "simulation"

    @property
    def total_kg_co2(self) -> float:
        return self.scope1_kg_co2 + self.scope2_kg_co2 + self.scope3_kg_co2

    def to_dict(self) -> Dict:
        return {
            "month": self.month,
            "site_id": self.site_id,
            "scope1_kg_co2": round(self.scope1_kg_co2, 2),
            "scope2_kg_co2": round(self.scope2_kg_co2, 2),
            "scope3_kg_co2": round(self.scope3_kg_co2, 2),
            "total_kg_co2": round(self.total_kg_co2, 2),
            "grid_kwh": round(self.grid_kwh, 2),
            "diesel_litres": round(self.diesel_litres, 2),
            "carbon_intensity_kg_per_sqm": round(self.carbon_intensity_kg_per_sqm, 2),
            "energy_intensity_kwh_per_sqm": round(self.energy_intensity_kwh_per_sqm, 2),
            "breakdown_by_system": {k: round(v, 2) for k, v in self.breakdown_by_system.items()},
            # Per-system carbon breakdown
            "hvac_kg_co2": round(self.hvac_kg_co2, 2),
            "lighting_kg_co2": round(self.lighting_kg_co2, 2),
            "other_kg_co2": round(self.other_kg_co2, 2),
            "solar_offset_kg_co2": round(self.solar_offset_kg_co2, 2),
            "net_scope2_kg_co2": round(self.net_scope2_kg_co2, 2),
            # Source data
            "actual_diesel_liters": round(self.actual_diesel_liters, 2)
            if self.actual_diesel_liters is not None
            else None,
            "actual_water_kl": round(self.actual_water_kl, 2) if self.actual_water_kl is not None else None,
            "solar_generation_kwh": round(self.solar_generation_kwh, 2)
            if self.solar_generation_kwh is not None
            else None,
            "data_source": self.data_source,
        }


@dataclass
class GreenStarCategory:
    """Green Star SA Office v1.1 category."""

    category_id: str  # ENE, WAT, IEQ, etc.
    name: str
    max_points: int
    achieved_points: int = 0
    target_points: int = 0
    notes: str = ""

    def to_dict(self) -> Dict:
        return {
            "category_id": self.category_id,
            "name": self.name,
            "max_points": self.max_points,
            "achieved_points": self.achieved_points,
            "target_points": self.target_points,
            "notes": self.notes,
        }

    @classmethod
    def from_dict(cls, data: Dict) -> "GreenStarCategory":
        return cls(
            category_id=data["category_id"],
            name=data["name"],
            max_points=data["max_points"],
            achieved_points=data.get("achieved_points", 0),
            target_points=data.get("target_points", 0),
            notes=data.get("notes", ""),
        )


@dataclass
class GreenStarAssessment:
    """Green Star SA self-assessment tracker."""

    site_id: str
    tool_version: str = "Green Star SA Office v1.1"
    target_rating: str = "5-Star"
    categories: List[GreenStarCategory] = field(default_factory=list)

    @property
    def total_achieved(self) -> int:
        return sum(c.achieved_points for c in self.categories)

    @property
    def total_max(self) -> int:
        return sum(c.max_points for c in self.categories)

    @property
    def total_target(self) -> int:
        return sum(c.target_points for c in self.categories)

    @property
    def estimated_star_rating(self) -> str:
        pts = self.total_achieved
        if pts >= 75:
            return "6-Star"
        elif pts >= 60:
            return "5-Star"
        elif pts >= 45:
            return "4-Star"
        else:
            return "Below 4-Star"

    def to_dict(self) -> Dict:
        return {
            "site_id": self.site_id,
            "tool_version": self.tool_version,
            "target_rating": self.target_rating,
            "categories": [c.to_dict() for c in self.categories],
            "total_achieved": self.total_achieved,
            "total_max": self.total_max,
            "total_target": self.total_target,
            "estimated_star_rating": self.estimated_star_rating,
        }

    @classmethod
    def from_dict(cls, data: Dict) -> "GreenStarAssessment":
        return cls(
            site_id=data["site_id"],
            tool_version=data.get("tool_version", "Green Star SA Office v1.1"),
            target_rating=data.get("target_rating", "5-Star"),
            categories=[GreenStarCategory.from_dict(c) for c in data.get("categories", [])],
        )


@dataclass
class SustainabilityConfig:
    """Site sustainability configuration."""

    site_id: str
    emission_factors: EmissionFactors = field(default_factory=EmissionFactors)
    site_sqm: float = 4500.0
    occupancy_capacity: int = 150
    target_reduction_pct: float = 10.0  # Year-on-year reduction target
    monthly_water_kl: float = 45.0  # Estimated monthly water usage
    monthly_waste_tons: float = 2.5  # Estimated monthly waste
    working_days_per_month: int = 22
    avg_occupancy_pct: float = 75.0  # Average occupancy percentage

    def to_dict(self) -> Dict:
        return {
            "site_id": self.site_id,
            "emission_factors": self.emission_factors.to_dict(),
            "site_sqm": self.site_sqm,
            "occupancy_capacity": self.occupancy_capacity,
            "target_reduction_pct": self.target_reduction_pct,
            "monthly_water_kl": self.monthly_water_kl,
            "monthly_waste_tons": self.monthly_waste_tons,
            "working_days_per_month": self.working_days_per_month,
            "avg_occupancy_pct": self.avg_occupancy_pct,
        }

    @classmethod
    def from_dict(cls, data: Dict) -> "SustainabilityConfig":
        ef_data = data.get("emission_factors", {})
        return cls(
            site_id=data["site_id"],
            emission_factors=EmissionFactors.from_dict(ef_data) if ef_data else EmissionFactors(),
            site_sqm=data.get("site_sqm", 4500.0),
            occupancy_capacity=data.get("occupancy_capacity", 150),
            target_reduction_pct=data.get("target_reduction_pct", 10.0),
            monthly_water_kl=data.get("monthly_water_kl", 45.0),
            monthly_waste_tons=data.get("monthly_waste_tons", 2.5),
            working_days_per_month=data.get("working_days_per_month", 22),
            avg_occupancy_pct=data.get("avg_occupancy_pct", 75.0),
        )


@dataclass
class BenchmarkComparison:
    """SA office building benchmarks."""

    # Energy intensity (kWh/sqm/year)
    energy_typical_kwh_per_sqm_yr: float = 170.0
    energy_efficient_kwh_per_sqm_yr: float = 120.0
    # Carbon intensity (kg CO2/sqm/year)
    carbon_typical_kg_per_sqm_yr: float = 180.0
    carbon_efficient_kg_per_sqm_yr: float = 127.0

    def to_dict(self) -> Dict:
        return {
            "energy_typical_kwh_per_sqm_yr": self.energy_typical_kwh_per_sqm_yr,
            "energy_efficient_kwh_per_sqm_yr": self.energy_efficient_kwh_per_sqm_yr,
            "carbon_typical_kg_per_sqm_yr": self.carbon_typical_kg_per_sqm_yr,
            "carbon_efficient_kg_per_sqm_yr": self.carbon_efficient_kg_per_sqm_yr,
        }


# ---------------------------------------------------------------------------
# Daily sustainability metrics — written by SustainabilityMetricsCollector
# (plan 111-01)
# ---------------------------------------------------------------------------


@dataclass
class DailySustainabilityWrite:
    """Write model for daily_sustainability_metrics table.

    Contains only user-supplied fields (no GENERATED ALWAYS columns).
    Used by SustainabilityMetricsCollector.persist() for Supabase upserts
    and JSON-fallback writes.
    """

    site_id: str
    date: date  # YYYY-MM-DD

    # Energy breakdown (kWh)
    grid_kwh: float = 0.0
    hvac_kwh: float = 0.0
    lighting_kwh: float = 0.0
    other_kwh: float = 0.0
    solar_generation_kwh: float = 0.0
    solar_export_kwh: float = 0.0

    # Water (liters)
    water_liters: float = 0.0

    # Fuel
    diesel_liters: float = 0.0
    generator_runtime_hours: float = 0.0

    # Occupancy
    avg_occupancy_pct: float = 0.0
    peak_occupancy_count: int = 0

    # Computed emissions (kg CO2e)
    scope1_kg_co2: float = 0.0
    scope2_kg_co2: float = 0.0
    scope3_kg_co2: float = 0.0

    # Metadata
    source: str = "simulation"
    site_uuid: Optional[str] = None  # UUID as string for JSON compat

    def to_dict(self) -> Dict:
        """Convert to dict for Supabase upsert / JSON write."""
        d: Dict = {
            "site_id": self.site_id,
            "date": self.date.isoformat() if isinstance(self.date, date) else str(self.date),
            "grid_kwh": round(self.grid_kwh, 2),
            "hvac_kwh": round(self.hvac_kwh, 2),
            "lighting_kwh": round(self.lighting_kwh, 2),
            "other_kwh": round(self.other_kwh, 2),
            "solar_generation_kwh": round(self.solar_generation_kwh, 2),
            "solar_export_kwh": round(self.solar_export_kwh, 2),
            "water_liters": round(self.water_liters, 1),
            "diesel_liters": round(self.diesel_liters, 2),
            "generator_runtime_hours": round(self.generator_runtime_hours, 2),
            "avg_occupancy_pct": round(self.avg_occupancy_pct, 1),
            "peak_occupancy_count": self.peak_occupancy_count,
            "scope1_kg_co2": round(self.scope1_kg_co2, 2),
            "scope2_kg_co2": round(self.scope2_kg_co2, 2),
            "scope3_kg_co2": round(self.scope3_kg_co2, 2),
            "source": self.source,
        }
        if self.site_uuid:
            d["site_uuid"] = self.site_uuid
        return d


@dataclass
class DailySustainabilityMetrics(DailySustainabilityWrite):
    """Full read model including server-generated columns.

    Extends DailySustainabilityWrite with columns that Postgres computes
    via GENERATED ALWAYS AS ... STORED.
    """

    id: Optional[str] = None  # UUID from Postgres
    net_grid_kwh: float = 0.0  # grid_kwh - solar_generation_kwh
    water_kl: float = 0.0  # water_liters / 1000
    total_kg_co2: float = 0.0  # scope1 + scope2 + scope3
    created_at: Optional[str] = None  # ISO timestamp

    def to_dict(self) -> Dict:
        d = super().to_dict()
        d["id"] = self.id
        d["net_grid_kwh"] = round(self.net_grid_kwh, 2)
        d["water_kl"] = round(self.water_kl, 3)
        d["total_kg_co2"] = round(self.total_kg_co2, 2)
        d["created_at"] = self.created_at
        return d

    @classmethod
    def from_dict(cls, data: Dict) -> "DailySustainabilityMetrics":
        """Create from Supabase row or JSON record."""
        dt = data.get("date")
        if isinstance(dt, str):
            from datetime import date as _date

            dt = _date.fromisoformat(dt)
        return cls(
            id=data.get("id"),
            site_id=data["site_id"],
            date=dt,
            grid_kwh=float(data.get("grid_kwh") or 0),
            hvac_kwh=float(data.get("hvac_kwh") or 0),
            lighting_kwh=float(data.get("lighting_kwh") or 0),
            other_kwh=float(data.get("other_kwh") or 0),
            solar_generation_kwh=float(data.get("solar_generation_kwh") or 0),
            solar_export_kwh=float(data.get("solar_export_kwh") or 0),
            net_grid_kwh=float(data.get("net_grid_kwh") or 0),
            water_liters=float(data.get("water_liters") or 0),
            water_kl=float(data.get("water_kl") or 0),
            diesel_liters=float(data.get("diesel_liters") or 0),
            generator_runtime_hours=float(data.get("generator_runtime_hours") or 0),
            avg_occupancy_pct=float(data.get("avg_occupancy_pct") or 0),
            peak_occupancy_count=int(data.get("peak_occupancy_count") or 0),
            scope1_kg_co2=float(data.get("scope1_kg_co2") or 0),
            scope2_kg_co2=float(data.get("scope2_kg_co2") or 0),
            scope3_kg_co2=float(data.get("scope3_kg_co2") or 0),
            total_kg_co2=float(data.get("total_kg_co2") or 0),
            source=data.get("source", "simulation"),
            site_uuid=data.get("site_uuid"),
            created_at=data.get("created_at"),
        )
