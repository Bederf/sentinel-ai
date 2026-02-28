"""Sustainability & ESG Module API endpoints.

8 endpoints for carbon emissions tracking, ESG metrics, and benchmarking:
1. GET /buildings/{building_id}/emissions/monthly - Monthly breakdown
2. GET /buildings/{building_id}/emissions/summary - Current year summary
3. GET /buildings/{building_id}/emissions/by-source - Pie chart breakdown
4. GET /portfolio/emissions/benchmark - Benchmarking
5. GET /buildings/{building_id}/esg-metrics - ESG score
6. GET /buildings/{building_id}/certifications - Green Star/LEED progress
7. POST /buildings/{building_id}/update-emissions - Record emissions data
8. GET /buildings/{building_id}/emissions/forecast - 12-month projection
"""

import csv
import io
import logging
from datetime import date, datetime, timedelta
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from fastapi.responses import HTMLResponse, StreamingResponse
from pydantic import BaseModel

from app.api.dependencies.module_access import require_active_module
from app.models.module_registry import ModuleType
from app.services.sustainability_service import sustainability_service
from app.services.carbon_calculator import get_carbon_calculator
from app.database.supabase_client import get_supabase_client

router = APIRouter(
    prefix="/sustainability",
    dependencies=[
        Depends(
            require_active_module(
                ModuleType.COMPLIANCE,
                site_keys=("site_id", "site", "building_id"),
                default_site_id="site-002",
            )
        )
    ],
)
logger = logging.getLogger(__name__)


class GreenStarUpdateRequest(BaseModel):
    """Request to update a Green Star category score."""

    achieved_points: int
    notes: Optional[str] = None


class ConfigUpdateRequest(BaseModel):
    """Request to update sustainability config."""

    building_sqm: Optional[float] = None
    occupancy_capacity: Optional[int] = None
    target_reduction_pct: Optional[float] = None
    monthly_water_kl: Optional[float] = None
    monthly_waste_tons: Optional[float] = None
    working_days_per_month: Optional[int] = None
    avg_occupancy_pct: Optional[float] = None
    emission_factors: Optional[dict] = None


@router.get("/{site_id}/summary")
async def get_sustainability_summary(site_id: str):
    """Dashboard summary: current month, YTD, trend, targets, Green Star progress."""
    try:
        return sustainability_service.get_summary(site_id)
    except Exception as e:
        logger.error(f"Error getting sustainability summary: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/{site_id}/emissions")
async def get_emissions_history(
    site_id: str,
    months: int = Query(default=12, ge=1, le=36),
):
    """Monthly emissions history with scope 1/2/3 breakdown."""
    try:
        history = sustainability_service.get_emissions_history(site_id, months)
        return {
            "site_id": site_id,
            "months": months,
            "data": [s.to_dict() for s in history],
        }
    except Exception as e:
        logger.error(f"Error getting emissions history: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/{site_id}/emissions/current")
async def get_current_emissions(site_id: str):
    """Current month emissions snapshot."""
    try:
        snapshot = sustainability_service.calculate_current_emissions(site_id)
        return snapshot.to_dict()
    except Exception as e:
        logger.error(f"Error calculating current emissions: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/{site_id}/emissions/breakdown")
async def get_emissions_breakdown(site_id: str):
    """Emissions breakdown by scope and system."""
    try:
        current = sustainability_service.calculate_current_emissions(site_id)
        return {
            "site_id": site_id,
            "month": current.month,
            "by_scope": {
                "scope1_diesel": round(current.scope1_kg_co2, 2),
                "scope2_grid": round(current.scope2_kg_co2, 2),
                "scope3_other": round(current.scope3_kg_co2, 2),
                "total": round(current.total_kg_co2, 2),
            },
            "by_system": current.breakdown_by_system,
            "scope_percentages": {
                "scope1_pct": round(
                    (current.scope1_kg_co2 / current.total_kg_co2 * 100) if current.total_kg_co2 > 0 else 0, 1
                ),
                "scope2_pct": round(
                    (current.scope2_kg_co2 / current.total_kg_co2 * 100) if current.total_kg_co2 > 0 else 0, 1
                ),
                "scope3_pct": round(
                    (current.scope3_kg_co2 / current.total_kg_co2 * 100) if current.total_kg_co2 > 0 else 0, 1
                ),
            },
        }
    except Exception as e:
        logger.error(f"Error getting emissions breakdown: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/{site_id}/efficiency")
async def get_efficiency_metrics(site_id: str):
    """Energy and carbon intensity with SA office benchmarks."""
    try:
        return sustainability_service.get_efficiency_metrics(site_id)
    except Exception as e:
        logger.error(f"Error getting efficiency metrics: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/{site_id}/green-star")
async def get_green_star_assessment(site_id: str):
    """Green Star SA self-assessment tracker."""
    try:
        assessment = sustainability_service.get_green_star_assessment(site_id)
        return assessment.to_dict()
    except Exception as e:
        logger.error(f"Error getting Green Star assessment: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.put("/{site_id}/green-star/{category_id}")
async def update_green_star_score(
    site_id: str,
    category_id: str,
    request: GreenStarUpdateRequest,
):
    """Update a Green Star category score."""
    try:
        assessment = sustainability_service.update_green_star_score(
            site_id, category_id.upper(), request.achieved_points, request.notes
        )
        return assessment.to_dict()
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        logger.error(f"Error updating Green Star score: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/{site_id}/config")
async def get_sustainability_config(site_id: str):
    """Get site sustainability configuration."""
    try:
        config = sustainability_service.get_config(site_id)
        return config.to_dict()
    except Exception as e:
        logger.error(f"Error getting sustainability config: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.put("/{site_id}/config")
async def update_sustainability_config(
    site_id: str,
    request: ConfigUpdateRequest,
):
    """Update site sustainability configuration."""
    try:
        updates = request.model_dump(exclude_none=True)
        config = sustainability_service.update_config(site_id, updates)
        return config.to_dict()
    except Exception as e:
        logger.error(f"Error updating sustainability config: {e}")
        raise HTTPException(status_code=500, detail=str(e))


# =====================================================
# Phase 29-01: New emissions and ESG API endpoints
# =====================================================


class EmissionsUpdateRequest(BaseModel):
    """Request to record emissions data."""

    source_type: str
    month: date
    value: float
    unit: str


class DailyMetricsUpdateRequest(BaseModel):
    """Request to record daily sustainability metrics."""

    date: date
    grid_kwh: float = 0.0
    hvac_kwh: float = 0.0
    lighting_kwh: float = 0.0
    other_kwh: float = 0.0
    diesel_liters: float = 0.0
    water_liters: float = 0.0
    solar_generation_kwh: float = 0.0
    data_source: str = "measured"  # measured | simulation | estimated


@router.get("/buildings/{building_id}/emissions/monthly")
async def get_monthly_emissions(
    building_id: str,
    start_date: Optional[date] = Query(None),
    end_date: Optional[date] = Query(None),
):
    """
    Get monthly emissions breakdown by scope.

    Returns array of monthly records with Scope 1/2/3 breakdown.
    Default: last 12 months.
    """
    try:
        supabase = get_supabase_client()

        # Default to last 12 months
        if not end_date:
            end_date = date.today()
        if not start_date:
            start_date = end_date - timedelta(days=365)

        # Query emissions_sources, group by month and scope
        response = (
            supabase.table("emissions_sources")
            .select("measurement_date,scope,co2e_kg")
            .eq("building_id", building_id)
            .gte("measurement_date", start_date.isoformat())
            .lte("measurement_date", end_date.isoformat())
            .order("measurement_date")
            .execute()
        )

        monthly = {}
        data_source = "emissions_sources"

        if response.data:
            # Group by month from emissions_sources
            for row in response.data:
                month = row["measurement_date"][:7]  # YYYY-MM
                if month not in monthly:
                    monthly[month] = {
                        "month": month,
                        "scope1_kg_co2e": 0,
                        "scope2_kg_co2e": 0,
                        "scope3_kg_co2e": 0,
                        "total_kg_co2e": 0,
                    }

                scope = row["scope"]
                co2e = row.get("co2e_kg", 0)
                key = f"scope{scope}_kg_co2e"
                monthly[month][key] += co2e
                monthly[month]["total_kg_co2e"] += co2e
        else:
            # Fallback: aggregate from daily_sustainability_metrics
            data_source = "daily_sustainability_metrics"
            try:
                daily_response = (
                    supabase.table("daily_sustainability_metrics")
                    .select("date,grid_kwh,diesel_liters,water_liters,solar_generation_kwh")
                    .eq("site_id", building_id)
                    .gte("date", start_date.isoformat())
                    .lte("date", end_date.isoformat())
                    .order("date")
                    .execute()
                )

                if daily_response.data:
                    # SA emission factors for aggregation
                    grid_factor = 0.95  # kg CO2e/kWh
                    diesel_factor = 2.68  # kg CO2e/L
                    water_factor = 0.45  # kg CO2e/m3

                    for row in daily_response.data:
                        month = row["date"][:7]
                        if month not in monthly:
                            monthly[month] = {
                                "month": month,
                                "scope1_kg_co2e": 0,
                                "scope2_kg_co2e": 0,
                                "scope3_kg_co2e": 0,
                                "total_kg_co2e": 0,
                            }

                        grid_kwh = float(row.get("grid_kwh", 0) or 0)
                        diesel_l = float(row.get("diesel_liters", 0) or 0)
                        water_l = float(row.get("water_liters", 0) or 0)
                        solar_kwh = float(row.get("solar_generation_kwh", 0) or 0)

                        # Scope 1: diesel
                        s1 = diesel_l * diesel_factor
                        # Scope 2: grid minus solar offset
                        net_grid = max(0, grid_kwh - solar_kwh)
                        s2 = net_grid * grid_factor
                        # Scope 3: water (simplified)
                        s3 = (water_l / 1000) * water_factor

                        monthly[month]["scope1_kg_co2e"] += s1
                        monthly[month]["scope2_kg_co2e"] += s2
                        monthly[month]["scope3_kg_co2e"] += s3
                        monthly[month]["total_kg_co2e"] += s1 + s2 + s3
            except Exception as daily_err:
                logger.debug(f"daily_sustainability_metrics fallback failed: {daily_err}")

        if not monthly:
            return {
                "status": "no_data",
                "message": "No emissions data found for this period",
                "timestamp": date.today().isoformat(),
            }

        # Round values
        for month_data in monthly.values():
            for key in ("scope1_kg_co2e", "scope2_kg_co2e", "scope3_kg_co2e", "total_kg_co2e"):
                month_data[key] = round(month_data[key], 2)

        # Calculate intensity if floor area available
        try:
            building = supabase.table("buildings").select("floor_area_m2").eq("id", building_id).execute()
            floor_area = building.data[0]["floor_area_m2"] if building.data else None
        except Exception:
            floor_area = None

        for month_data in monthly.values():
            if floor_area and floor_area > 0:
                month_data["intensity_kg_per_m2"] = round(month_data["total_kg_co2e"] / floor_area / 30, 4)

        return {
            "status": "success",
            "building_id": building_id,
            "period_start": start_date.isoformat(),
            "period_end": end_date.isoformat(),
            "data_source": data_source,
            "data": sorted(monthly.values(), key=lambda x: x["month"]),
            "timestamp": date.today().isoformat(),
        }

    except Exception as e:
        logger.error(f"Error getting monthly emissions: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/buildings/{building_id}/emissions/summary")
async def get_emissions_summary(building_id: str):
    """
    Get current year emissions summary with scope totals and source breakdown.
    """
    try:
        calculator = get_carbon_calculator()
        supabase = get_supabase_client()

        # Get current year
        today = date.today()
        year_start = date(today.year, 1, 1)
        year_end = date(today.year, 12, 31)

        # Calculate totals
        emissions = calculator.calculate_total_emissions(building_id, year_start, year_end)

        if not emissions or emissions["total_kg_co2e"] == 0:
            return {
                "status": "no_data",
                "message": (
                    "No emissions data available yet. Please start by uploading energy, generator, and water data."
                ),
                "timestamp": date.today().isoformat(),
            }

        # Get source breakdown
        response = (
            supabase.table("emissions_sources")
            .select("source_type,co2e_kg")
            .eq("building_id", building_id)
            .gte("measurement_date", year_start.isoformat())
            .lte("measurement_date", year_end.isoformat())
            .execute()
        )

        sources_breakdown = {}
        for row in response.data:
            source = row["source_type"]
            co2e = row.get("co2e_kg", 0)
            if source not in sources_breakdown:
                sources_breakdown[source] = 0
            sources_breakdown[source] += co2e

        total = sum(sources_breakdown.values())
        sources_list = [
            {
                "source": k,
                "kg_co2e": round(v, 2),
                "pct_of_total": round(v / total * 100, 1) if total > 0 else 0,
            }
            for k, v in sorted(sources_breakdown.items(), key=lambda x: x[1], reverse=True)
        ]

        return {
            "status": "success",
            "building_id": building_id,
            "year": today.year,
            "scope1_total": emissions["scope1_kg_co2e"],
            "scope2_total": emissions["scope2_kg_co2e"],
            "scope3_total": emissions["scope3_kg_co2e"],
            "total": emissions["total_kg_co2e"],
            "total_tonnes": round(emissions["total_kg_co2e"] / 1000, 2),
            "sources_breakdown": sources_list,
            "timestamp": date.today().isoformat(),
        }

    except Exception as e:
        logger.error(f"Error getting emissions summary: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/buildings/{building_id}/emissions/by-source")
async def get_emissions_by_source(
    building_id: str,
    months: int = Query(12, ge=1, le=36),
):
    """
    Get emissions breakdown by source for pie chart.
    Ordered by magnitude (largest first).
    """
    try:
        supabase = get_supabase_client()

        # Last N months
        today = date.today()
        start_date = today - timedelta(days=months * 30)

        response = (
            supabase.table("emissions_sources")
            .select("source_type,co2e_kg,scope")
            .eq("building_id", building_id)
            .gte("measurement_date", start_date.isoformat())
            .order("co2e_kg", desc=True)
            .execute()
        )

        sources = {}
        for row in response.data:
            source = row["source_type"]
            co2e = row.get("co2e_kg", 0)
            scope = row["scope"]

            if source not in sources:
                sources[source] = {"co2e_kg": 0, "scope": scope}
            sources[source]["co2e_kg"] += co2e

        total = sum(s["co2e_kg"] for s in sources.values())

        breakdown = [
            {
                "source_type": k,
                "kg_co2e": round(v["co2e_kg"], 2),
                "pct_of_total": round(v["co2e_kg"] / total * 100, 1) if total > 0 else 0,
                "scope": v["scope"],
            }
            for k, v in sorted(sources.items(), key=lambda x: x[1]["co2e_kg"], reverse=True)
        ]

        return {
            "status": "success",
            "building_id": building_id,
            "months": months,
            "data": breakdown,
            "timestamp": date.today().isoformat(),
        }

    except Exception as e:
        logger.error(f"Error getting emissions by source: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/portfolio/emissions/benchmark")
async def get_emissions_benchmark(building_id: str):
    """
    Compare building carbon intensity to portfolio average and industry benchmark.
    Returns percentile ranking (0-100, where 0 is worst).
    """
    try:
        calculator = get_carbon_calculator()

        # Calculate this building's intensity
        today = date.today()
        year_start = date(today.year, 1, 1)

        building_intensity = calculator.calculate_carbon_intensity(building_id, year_start, today)

        if not building_intensity:
            return {
                "status": "no_data",
                "message": "Insufficient data for benchmarking",
                "timestamp": date.today().isoformat(),
            }

        # SA office benchmark: 0.15 kg/m²/day
        sa_benchmark = 0.15
        building_value = building_intensity["intensity_kg_per_m2_per_day"]

        # Percentile: 0 = highest emissions, 100 = lowest emissions
        percentile = max(0, min(100, 100 * (1 - (building_value / (sa_benchmark * 2)))))

        return {
            "status": "success",
            "building_id": building_id,
            "building_intensity": round(building_value, 4),
            "portfolio_avg_intensity": sa_benchmark,
            "industry_avg_intensity": sa_benchmark,
            "percentile": round(percentile, 0),
            "rating": "excellent"
            if percentile >= 80
            else "good"
            if percentile >= 60
            else "average"
            if percentile >= 40
            else "needs_improvement",
            "timestamp": date.today().isoformat(),
        }

    except Exception as e:
        logger.error(f"Error getting emissions benchmark: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/buildings/{building_id}/esg-metrics")
async def get_esg_metrics(building_id: str):
    """
    Get overall ESG score and component metrics.
    Weighted: Carbon 40%, Energy 30%, Waste 20%, Water 10%
    """
    try:
        calculator = get_carbon_calculator()

        today = date.today()
        year_start = date(today.year, 1, 1)

        scores = calculator.calculate_esg_score(building_id, year_start, today)

        if not scores:
            return {
                "status": "no_data",
                "message": "Insufficient data for ESG scoring",
                "timestamp": date.today().isoformat(),
            }

        return {
            "status": "success",
            "building_id": building_id,
            "carbon_intensity_score": scores["carbon_intensity_score"],
            "energy_efficiency_score": scores["energy_efficiency_score"],
            "waste_diversion_score": scores["waste_diversion_score"],
            "water_efficiency_score": scores["water_efficiency_score"],
            "overall_esg_score": scores["overall_esg_score"],
            "rating": scores["rating"],
            "target_score": 80,
            "target_year": 2026,
            "timestamp": date.today().isoformat(),
        }

    except Exception as e:
        logger.error(f"Error getting ESG metrics: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/buildings/{building_id}/certifications")
async def get_certifications(building_id: str):
    """
    Get Green Star/LEED/Carbon Trust certification progress.
    """
    try:
        supabase = get_supabase_client()

        response = supabase.table("certification_progress").select("*").eq("building_id", building_id).execute()

        certs = []
        for row in response.data:
            certs.append(
                {
                    "cert_type": row["cert_type"],
                    "current_score": row["current_score"],
                    "target_score": row["target_score"],
                    "pct_progress": row.get("pct_progress", 0),
                    "status": row["status"],
                    "categories": row.get("categories", []),
                }
            )

        if not certs:
            return {
                "status": "no_data",
                "message": "No certifications tracked",
                "timestamp": date.today().isoformat(),
            }

        return {
            "status": "success",
            "building_id": building_id,
            "certifications": certs,
            "timestamp": date.today().isoformat(),
        }

    except Exception as e:
        logger.error(f"Error getting certifications: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/buildings/{building_id}/update-emissions")
async def update_emissions(
    building_id: str,
    request: EmissionsUpdateRequest,
):
    """
    Record emissions data from energy systems.
    Validates against schema, calculates CO2e, stores in database.
    """
    try:
        supabase = get_supabase_client()

        # Validate source type
        valid_sources = [
            "generator_diesel",
            "generator_lpg",
            "grid_electricity",
            "water_supply",
            "waste_landfill",
            "employee_commute",
        ]
        if request.source_type not in valid_sources:
            raise HTTPException(status_code=400, detail=f"Invalid source_type. Must be one of: {valid_sources}")

        # Get emission factor
        factors_response = (
            supabase.table("emission_factors")
            .select("factor_value")
            .eq("source_type", request.source_type)
            .eq("unit", request.unit)
            .execute()
        )

        if not factors_response.data:
            raise HTTPException(
                status_code=400, detail=f"Unknown source_type/unit combination: {request.source_type}/{request.unit}"
            )

        co2_factor = factors_response.data[0]["factor_value"]

        # Insert emissions_sources record
        record = {
            "building_id": building_id,
            "source_type": request.source_type,
            "measurement_date": request.month.isoformat(),
            "monthly_value": request.value,
            "unit": request.unit,
            "scope": 1
            if request.source_type.startswith("generator")
            else (2 if "electricity" in request.source_type else 3),
            "co2_factor": co2_factor,
            "data_quality": "measured",
        }

        supabase.table("emissions_sources").insert(record).execute()

        return {
            "status": "success",
            "message": "Emissions data recorded",
            "building_id": building_id,
            "source_type": request.source_type,
            "value": request.value,
            "unit": request.unit,
            "calculated_co2e_kg": round(request.value * co2_factor, 2),
            "timestamp": date.today().isoformat(),
        }

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error updating emissions: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/buildings/{building_id}/daily-metrics")
async def update_daily_metrics(
    building_id: str,
    request: DailyMetricsUpdateRequest,
):
    """
    Record daily sustainability metrics to daily_sustainability_metrics table.
    Accepts energy breakdown, diesel, water, and solar generation for a single day.
    """
    try:
        supabase = get_supabase_client()

        record = {
            "site_id": building_id,
            "date": request.date.isoformat(),
            "grid_kwh": request.grid_kwh,
            "hvac_kwh": request.hvac_kwh,
            "lighting_kwh": request.lighting_kwh,
            "other_kwh": request.other_kwh,
            "diesel_liters": request.diesel_liters,
            "water_liters": request.water_liters,
            "solar_generation_kwh": request.solar_generation_kwh,
            "data_source": request.data_source,
        }

        supabase.table("daily_sustainability_metrics").upsert(
            record,
            on_conflict="site_id,date",
        ).execute()

        return {
            "status": "success",
            "message": "Daily metrics recorded",
            "building_id": building_id,
            "date": request.date.isoformat(),
            "data_source": request.data_source,
            "timestamp": date.today().isoformat(),
        }

    except Exception as e:
        logger.error(f"Error recording daily metrics: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/buildings/{building_id}/emissions/forecast")
async def get_emissions_forecast(building_id: str):
    """
    12-month emissions projection based on seasonal patterns.
    Assumes 10% year-over-year reduction target.
    """
    try:
        calculator = get_carbon_calculator()

        today = date.today()

        # Get last year's baseline
        baseline_year = today.year - 1
        baseline = calculator.calculate_emissions_baseline(building_id, baseline_year)

        if not baseline or baseline.get("total_kg_co2e", 0) == 0:
            return {
                "status": "no_data",
                "message": "Insufficient historical data for forecasting",
                "timestamp": date.today().isoformat(),
            }

        # Generate 12-month forecast with seasonal adjustment and reduction target
        monthly_baseline = baseline["total_kg_co2e"] / 12
        forecast = []
        reduction_rate = 0.10 / 12  # 10% annual reduction, monthly rate

        for month in range(1, 13):
            # Seasonal adjustment (heating/cooling peaks)
            seasonal_factor = 1.0
            if month in [1, 6, 7, 12]:  # Winter and summer peaks in SA
                seasonal_factor = 1.2

            projected = monthly_baseline * seasonal_factor * (1 - reduction_rate * month)

            forecast.append(
                {
                    "month": f"{today.year:04d}-{month:02d}",
                    "projected_kg_co2e": round(projected, 2),
                    "baseline_trend": round(monthly_baseline * seasonal_factor, 2),
                }
            )

        return {
            "status": "success",
            "building_id": building_id,
            "forecast_year": today.year,
            "reduction_target_pct": 10,
            "data": forecast,
            "timestamp": date.today().isoformat(),
        }

    except Exception as e:
        logger.error(f"Error generating forecast: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/{site_id}/report/export")
async def export_sustainability_report(
    site_id: str,
    format: str = Query("csv", pattern="^(csv|html)$"),
    months: int = Query(12, ge=1, le=36),
):
    """Export sustainability report as CSV or HTML."""
    try:
        if format == "csv":
            history = sustainability_service.get_emissions_history(site_id, months)
            output = io.StringIO()
            writer = csv.writer(output)
            writer.writerow(
                [
                    "Month",
                    "Scope 1 (kg CO2)",
                    "Scope 2 (kg CO2)",
                    "Scope 3 (kg CO2)",
                    "Total (kg CO2)",
                    "Grid kWh",
                    "Diesel L",
                    "HVAC CO2",
                    "Lighting CO2",
                    "Other CO2",
                    "Solar Offset CO2",
                    "Data Source",
                ]
            )
            for snap in history:
                d = snap.to_dict() if hasattr(snap, "to_dict") else snap
                writer.writerow(
                    [
                        d.get("month"),
                        d.get("scope1_kg_co2", 0),
                        d.get("scope2_kg_co2", 0),
                        d.get("scope3_kg_co2", 0),
                        d.get("scope1_kg_co2", 0) + d.get("scope2_kg_co2", 0) + d.get("scope3_kg_co2", 0),
                        d.get("grid_kwh", 0),
                        d.get("diesel_litres", 0),
                        d.get("hvac_kg_co2", 0),
                        d.get("lighting_kg_co2", 0),
                        d.get("other_kg_co2", 0),
                        d.get("solar_offset_kg_co2", 0),
                        d.get("data_source", "estimated"),
                    ]
                )
            output.seek(0)
            return StreamingResponse(
                output,
                media_type="text/csv",
                headers={"Content-Disposition": f"attachment; filename=sustainability_{site_id}_{months}m.csv"},
            )

        elif format == "html":
            summary = sustainability_service.get_summary(site_id)
            green_star = sustainability_service.get_green_star_assessment(site_id)
            efficiency = sustainability_service.get_efficiency_metrics(site_id)

            gs_dict = green_star.to_dict() if hasattr(green_star, "to_dict") else green_star
            ytd_tonnes = summary.get("ytd", {}).get("total_co2_tonnes", 0)
            carbon_intensity = summary.get("carbon_intensity_kg_per_sqm", 0)
            energy_intensity = summary.get("energy_intensity_kwh_per_sqm", 0)
            gs_achieved = gs_dict.get("total_achieved", 0)
            gs_max = gs_dict.get("total_max", 118)
            eff_intensity = efficiency.get("energy_intensity_kwh_per_sqm_yr", 0)

            html = f"""<!DOCTYPE html>
<html><head><title>Sustainability Report - {site_id}</title>
<style>
body{{font-family:Arial,sans-serif;margin:40px;color:#333}}
table{{border-collapse:collapse;width:100%}}
th,td{{border:1px solid #ddd;padding:8px;text-align:left}}
th{{background:#f5f5f5}}
.kpi{{display:inline-block;margin:10px;padding:20px;border:1px solid #ddd;border-radius:8px;text-align:center}}
.kpi h3{{margin:0;font-size:24px}}
.kpi p{{margin:4px 0 0;color:#666}}
hr{{border:none;border-top:1px solid #ddd;margin:20px 0}}
</style>
</head><body>
<h1>SENTINEL Sustainability Report</h1>
<p>Site: {site_id} | Generated: {datetime.now().strftime("%Y-%m-%d %H:%M")}</p>
<hr>
<h2>Key Performance Indicators</h2>
<div class="kpi"><h3>{ytd_tonnes:.1f}t</h3><p>YTD CO2 Emissions</p></div>
<div class="kpi"><h3>{carbon_intensity:.2f}</h3><p>kg CO2/m2/month</p></div>
<div class="kpi"><h3>{energy_intensity:.0f}</h3><p>kWh/m2/year (EUI)</p></div>
<h2>Green Star SA Progress</h2>
<p>Score: {gs_achieved}/{gs_max} points</p>
<h2>Benchmarks</h2>
<p>Energy intensity: {eff_intensity:.0f} kWh/m2/yr (SA typical: 170, efficient: 120)</p>
</body></html>"""
            return HTMLResponse(content=html)

    except Exception as e:
        logger.error(f"Error exporting sustainability report: {e}")
        raise HTTPException(status_code=500, detail=str(e))
