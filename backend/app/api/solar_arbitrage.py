"""Solar Arbitrage & BESS Dispatch API Endpoints.

Provides comprehensive endpoints for:
  - 24-hour price forecasting with adjustments
  - Arbitrage window identification and revenue analysis
  - Real-time dispatch scheduling and execution
  - Load-shedding coordination
  - Revenue tracking and KPIs
  - What-if scenario analysis

Module: 34-05 (Energy Arbitrage & BESS Dispatch Optimization)
"""

import time
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query, Request
from app.middleware.rate_limiter import limiter
from app.api.dependencies.module_access import require_active_module
from app.models.module_registry import ModuleType
from app.services.arbitrage_optimizer import (
    get_price_forecaster,
    get_arbitrage_analyzer,
)
from app.services.bess_dispatch_engine import (
    get_bess_dispatch_engine,
    BESSState,
)
from app.ml.models.dispatch_predictor import get_dispatch_predictor

router = APIRouter(
    dependencies=[
        Depends(
            require_active_module(
                ModuleType.SOLAR,
                site_keys=("site_id", "site"),
                default_site_id="site-002",
            )
        )
    ]
)


# === Price Forecasting Endpoints (Task 1) ===


@limiter.limit("30/minute")
@router.get("/solar/arbitrage/forecast-24h")
async def get_24h_price_forecast(
    request: Request,
    load_shedding_stages: Optional[str] = Query(
        None, description="Comma-separated LS stages for each hour (0-8), default all 0"
    ),
    temperature_forecast: Optional[str] = Query(
        None, description="Comma-separated temperatures (°C) for each hour, default 20°C"
    ),
    solar_forecast_pct: Optional[str] = Query(
        None, description="Comma-separated solar capacity % for each hour, default 0%"
    ),
):
    """Get 24-hour price forecast with all adjustments applied.

    Returns hourly prices with:
      - Base tariff band (peak/standard/off-peak)
      - Load-shedding stage impact (±50-100%)
      - Weather impact (±30-40%)
      - Solar impact (-20% if > 70% capacity)
      - Final price and confidence

    Performance target: < 100ms response time
    """
    start_time = time.time()

    # Parse optional input arrays
    ls_stages = None
    if load_shedding_stages:
        try:
            ls_stages = [int(x.strip()) for x in load_shedding_stages.split(",")]
            if len(ls_stages) != 24:
                raise ValueError("Must provide exactly 24 values")
        except (ValueError, IndexError) as e:
            raise HTTPException(
                status_code=400,
                detail=f"Invalid load_shedding_stages: {e}",
            )

    temps = None
    if temperature_forecast:
        try:
            temps = [float(x.strip()) for x in temperature_forecast.split(",")]
            if len(temps) != 24:
                raise ValueError("Must provide exactly 24 values")
        except (ValueError, IndexError) as e:
            raise HTTPException(
                status_code=400,
                detail=f"Invalid temperature_forecast: {e}",
            )

    solar_pcts = None
    if solar_forecast_pct:
        try:
            solar_pcts = [float(x.strip()) for x in solar_forecast_pct.split(",")]
            if len(solar_pcts) != 24:
                raise ValueError("Must provide exactly 24 values")
        except (ValueError, IndexError) as e:
            raise HTTPException(
                status_code=400,
                detail=f"Invalid solar_forecast_pct: {e}",
            )

    # Generate forecast
    forecaster = get_price_forecaster()
    forecasts = forecaster.forecast_24h(
        load_shedding_stages=ls_stages,
        temperature_forecast=temps,
        solar_forecast_pct=solar_pcts,
    )

    elapsed_ms = (time.time() - start_time) * 1000

    return {
        "timestamp": forecasts[0].hour_start if forecasts else None,
        "forecast_hours": 24,
        "response_time_ms": round(elapsed_ms, 1),
        "forecasts": [f.to_dict() for f in forecasts],
    }


# === Arbitrage Analysis Endpoints (Task 1) ===


@limiter.limit("30/minute")
@router.get("/solar/arbitrage/opportunities")
async def get_arbitrage_opportunities(
    request: Request,
    hours: int = Query(24, ge=6, le=24, description="Lookahead hours (6-24)"),
    max_windows: int = Query(3, ge=1, le=5, description="Max windows to return"),
    battery_soc_pct: float = Query(50.0, ge=10, le=95, description="Current battery SOC %"),
):
    """Identify optimal arbitrage windows for next N hours.

    Returns charge/discharge window pairs with:
      - Time windows (start and end hour)
      - Price differential (spread)
      - Expected revenue (minus degradation cost)
      - Confidence level

    Performance target: < 100ms response time
    """
    start_time = time.time()

    try:
        # Generate 24h price forecast
        forecaster = get_price_forecaster()
        forecasts = forecaster.forecast_24h()

        # Find arbitrage windows
        analyzer = get_arbitrage_analyzer()
        windows = analyzer.find_arbitrage_windows(
            forecasts=forecasts,
            max_windows=max_windows,
            battery_soc_pct=battery_soc_pct,
        )

        elapsed_ms = (time.time() - start_time) * 1000

        return {
            "timestamp": forecasts[0].hour_start if forecasts else None,
            "battery_soc_pct": battery_soc_pct,
            "window_count": len(windows),
            "max_windows": max_windows,
            "response_time_ms": round(elapsed_ms, 1),
            "arbitrage_windows": [w.to_dict() for w in windows],
            "total_daily_opportunity_r": round(sum(w.net_revenue_r for w in windows), 2),
        }
    except Exception as e:
        logger.error("Arbitrage opportunity analysis failed: %s", e)
        raise HTTPException(
            status_code=500,
            detail=f"Arbitrage analysis failed: {e}",
        )


# === Dispatch Execution Endpoints (Task 2) ===


@limiter.limit("20/minute")
@router.post("/solar/bess/dispatch/execute")
async def execute_dispatch(
    request: Request,
    site_id: str = Query(..., description="Site ID"),
    action: str = Query(..., description="Action: charge or discharge"),
    requested_power_kw: float = Query(..., description="Requested power in kW"),
    duration_minutes: int = Query(15, ge=1, le=240, description="Duration in minutes"),
    reason: str = Query("manual", description="Reason for dispatch"),
    soc_pct: float = Query(50.0, ge=10, le=100, description="Current SOC %"),
    temperature_c: float = Query(20.0, ge=0, le=60, description="Battery temperature °C"),
    grid_frequency_hz: float = Query(50.0, ge=49.5, le=50.5, description="Grid frequency Hz"),
    load_shedding_stage: int = Query(0, ge=0, le=8, description="LS stage (0-8)"),
):
    """Execute a real-time BESS dispatch command with constraint validation.

    Returns actual power after constraint application and list of any limits applied.

    Performance target: < 1 second response time
    Constraints enforced:
      - Temperature (12-44°C discharge, 12-40°C charge)
      - SOC (20-95%)
      - Grid frequency (reduce if > 50.3 Hz)
      - Ramp rate (5% LS, 10% normal)
      - Export limit (50% Prated)

    Load-shedding response:
      - Stage 1-3: Normal operation
      - Stage 4-5: Reduce discharge to 50%
      - Stage 6-8: Stop discharge, charge to reserve
    """
    start_time = time.time()

    try:
        # Create BESS state
        bess_state = BESSState(
            soc_pct=soc_pct,
            temperature_c=temperature_c,
            power_kw=0.0,
            grid_frequency_hz=grid_frequency_hz,
        )

        # Execute dispatch with constraints
        engine = get_bess_dispatch_engine()
        command = engine.execute_dispatch(
            site_id=site_id,
            action=action,
            requested_power_kw=requested_power_kw,
            bess_state=bess_state,
            duration_minutes=duration_minutes,
            reason=reason,
            load_shedding_stage=load_shedding_stage,
        )

        elapsed_ms = (time.time() - start_time) * 1000

        return {
            "site_id": site_id,
            "response_time_ms": round(elapsed_ms, 1),
            "dispatch_command": command.to_dict(),
        }
    except Exception as e:
        logger.error("Dispatch execution failed: %s", e)
        raise HTTPException(
            status_code=500,
            detail=f"Dispatch execution failed: {e}",
        )


# === Dispatch Prediction Endpoints (Task 1 & 2) ===


@limiter.limit("30/minute")
@router.get("/solar/bess/dispatch/predict-next-action")
async def predict_next_dispatch_action(
    request: Request,
    current_hour: int = Query(..., ge=0, le=23, description="Current hour (0-23 SAST)"),
    soc_pct: float = Query(50.0, ge=10, le=100, description="Current SOC %"),
    load_shedding_stage: int = Query(0, ge=0, le=8, description="LS stage (0-8)"),
):
    """Predict next optimal BESS dispatch action using ML model.

    Returns:
      - Predicted action (charge/discharge/idle)
      - Start hour and duration
      - Expected power and revenue
      - Confidence level (0-100%)
      - Human-readable recommendation

    Performance target: < 500ms response time
    """
    start_time = time.time()

    try:
        # Get 24h price forecast
        forecaster = get_price_forecaster()
        forecasts = forecaster.forecast_24h()
        forecast_dicts = [f.to_dict() for f in forecasts]

        # Predict next action
        predictor = get_dispatch_predictor()
        prediction = predictor.predict_next_action(
            current_hour=current_hour,
            current_soc_pct=soc_pct,
            price_forecasts=forecast_dicts,
            load_shedding_stage=load_shedding_stage,
        )

        elapsed_ms = (time.time() - start_time) * 1000

        return {
            "timestamp": forecasts[0].hour_start if forecasts else None,
            "current_hour": current_hour,
            "current_soc_pct": soc_pct,
            "response_time_ms": round(elapsed_ms, 1),
            "prediction": {
                "action": prediction.action,
                "confidence_pct": round(prediction.confidence_pct, 1),
                "next_action_start_hour": prediction.next_action_start_hour,
                "next_action_duration_hours": prediction.next_action_duration_hours,
                "expected_power_kw": round(prediction.expected_power_kw, 0),
                "expected_revenue_r": round(prediction.expected_revenue_r, 2),
                "recommendation": prediction.recommendation,
                "reasoning": prediction.reasoning,
            },
        }
    except Exception as e:
        logger.error("Dispatch prediction failed: %s", e)
        raise HTTPException(
            status_code=500,
            detail=f"Dispatch prediction failed: {e}",
        )


# === Dispatch Schedule Endpoints (Task 2) ===


@limiter.limit("30/minute")
@router.get("/solar/bess/dispatch-schedule")
async def get_dispatch_schedule(
    request: Request,
    system_id: str = Query(..., description="BESS system ID"),
):
    """Get current and future 24-hour dispatch schedule.

    Returns time slots with:
      - Dispatch action (charge/discharge/idle)
      - Scheduled power (kW)
      - Expected duration
      - Tariff band and rate
      - Projected revenue
      - Constraint status

    Performance target: < 500ms response time
    """
    # This integrates with existing solar_arbitrage_engine
    # which already has generate_dispatch_schedule()
    from app.services.solar_arbitrage_engine import get_solar_arbitrage_engine

    try:
        engine = get_solar_arbitrage_engine()
        schedule = engine.generate_dispatch_schedule(system_id)

        return {
            "system_id": system_id,
            "dispatch_schedule": schedule.to_dict(),
        }
    except Exception as e:
        logger.error("Schedule retrieval failed: %s", e)
        raise HTTPException(
            status_code=500,
            detail=f"Schedule retrieval failed: {e}",
        )


# === Load-Shedding Coordination Endpoints (Task 2) ===


@limiter.limit("20/minute")
@router.post("/solar/bess/dispatch/respond-to-load-shedding")
async def respond_to_load_shedding(
    request: Request,
    site_id: str = Query(..., description="Site ID"),
    ls_stage: int = Query(..., ge=0, le=8, description="Load-shedding stage"),
    soc_pct: float = Query(50.0, ge=10, le=100, description="Current SOC %"),
    temperature_c: float = Query(20.0, ge=0, le=60, description="Battery temperature °C"),
):
    """Automatically adjust dispatch for load-shedding event.

    Strategy:
      - Stage 1-3: Continue normal arbitrage
      - Stage 4-5: Reduce discharge to 50%
      - Stage 6-8: Stop discharge, charge to 80% reserve

    Returns adjustment action and recommendation.

    Performance target: < 500ms response time
    """
    start_time = time.time()

    try:
        bess_state = BESSState(
            soc_pct=soc_pct,
            temperature_c=temperature_c,
            power_kw=0.0,
            grid_frequency_hz=50.0,
        )

        engine = get_bess_dispatch_engine()
        response = engine.respond_to_load_shedding(
            site_id=site_id,
            ls_stage=ls_stage,
            current_bess_state=bess_state,
        )

        elapsed_ms = (time.time() - start_time) * 1000
        response["response_time_ms"] = round(elapsed_ms, 1)

        return response
    except Exception as e:
        logger.error("LS response failed: %s", e)
        raise HTTPException(
            status_code=500,
            detail=f"Load-shedding response failed: {e}",
        )


# === Revenue Tracking & KPI Endpoints (Task 3) ===


@limiter.limit("30/minute")
@router.get("/solar/arbitrage/revenue-kpi")
async def get_revenue_kpi(
    request: Request,
    system_id: str = Query(..., description="BESS system ID"),
    period: str = Query("day", description="day, week, or month"),
):
    """Get arbitrage revenue KPIs.

    Returns:
      - Daily/weekly/monthly revenue (ZAR)
      - Revenue vs target
      - Annualized projection
      - Cost-benefit analysis

    Performance target: < 500ms response time
    """
    from app.services.solar_arbitrage_engine import get_solar_arbitrage_engine

    try:
        if period not in ("day", "week", "month"):
            raise HTTPException(
                status_code=400,
                detail="Period must be 'day', 'week', or 'month'",
            )

        engine = get_solar_arbitrage_engine()
        savings = engine.calculate_daily_savings(system_id, period=period)

        # Calculate annual projection
        if period == "day":
            annual_savings = savings.savings_zar * 365
        elif period == "week":
            annual_savings = savings.savings_zar * 52
        else:
            annual_savings = savings.savings_zar * 12

        return {
            "system_id": system_id,
            "period": period,
            "savings": savings.to_dict(),
            "annual_projection_r": round(annual_savings, 2),
            "cost_benefit": {
                "daily_avg_r": round(
                    savings.savings_zar / (365 if period == "day" else (52 if period == "week" else 30)), 2
                ),
                "monthly_avg_r": round(
                    savings.savings_zar * (1 if period == "month" else (30.44 if period == "week" else 30.44)), 2
                ),
            },
        }
    except Exception as e:
        logger.error("Revenue KPI calculation failed: %s", e)
        raise HTTPException(
            status_code=500,
            detail=f"Revenue KPI calculation failed: {e}",
        )


# === What-If Analysis Endpoints (Task 3) ===


@limiter.limit("20/minute")
@router.post("/solar/arbitrage/simulate")
async def simulate_arbitrage_scenario(
    request: Request,
    charge_price_r_per_kwh: float = Query(..., description="Simulated charge price (R/kWh)"),
    discharge_price_r_per_kwh: float = Query(..., description="Simulated discharge price (R/kWh)"),
    energy_kwh: float = Query(3000.0, ge=100, le=5000, description="Energy to arbitrage (kWh)"),
):
    """Simulate what-if arbitrage revenue scenarios.

    Returns revenue projection for specified price and energy parameters.

    Performance target: < 500ms response time
    """
    start_time = time.time()

    try:
        # Validate prices
        if charge_price_r_per_kwh < 0.5 or charge_price_r_per_kwh > 3.0:
            raise HTTPException(
                status_code=400,
                detail="Charge price must be between R0.50-3.00/kWh",
            )
        if discharge_price_r_per_kwh < 0.5 or discharge_price_r_per_kwh > 3.0:
            raise HTTPException(
                status_code=400,
                detail="Discharge price must be between R0.50-3.00/kWh",
            )

        # Calculate arbitrage
        spread = discharge_price_r_per_kwh - charge_price_r_per_kwh
        gross_revenue = spread * energy_kwh
        degradation_cost = energy_kwh * 0.05  # R0.05/kWh degradation
        net_revenue = gross_revenue - degradation_cost
        roi_pct = (net_revenue / (charge_price_r_per_kwh * energy_kwh) * 100) if charge_price_r_per_kwh > 0 else 0

        elapsed_ms = (time.time() - start_time) * 1000

        return {
            "simulation": {
                "charge_price_r_per_kwh": round(charge_price_r_per_kwh, 4),
                "discharge_price_r_per_kwh": round(discharge_price_r_per_kwh, 4),
                "energy_kwh": round(energy_kwh, 0),
                "arbitrage_spread_r_per_kwh": round(spread, 4),
            },
            "results": {
                "gross_revenue_r": round(gross_revenue, 2),
                "degradation_cost_r": round(degradation_cost, 2),
                "net_revenue_r": round(net_revenue, 2),
                "roi_pct": round(roi_pct, 1),
            },
            "response_time_ms": round(elapsed_ms, 1),
        }
    except Exception as e:
        logger.error("Arbitrage simulation failed: %s", e)
        raise HTTPException(
            status_code=500,
            detail=f"Arbitrage simulation failed: {e}",
        )


# === Battery Health Impact Endpoints (Task 2) ===


@limiter.limit("30/minute")
@router.get("/solar/bess/health-impact")
async def get_bess_health_impact(
    request: Request,
    system_id: str = Query(..., description="BESS system ID"),
):
    """Get dispatch impact on battery SOH and remaining life.

    Returns:
      - Current SOH (State of Health)
      - Cycle count and impact
      - Estimated remaining life
      - Degradation cost vs revenue trade-off

    Performance target: < 500ms response time
    """
    # Placeholder for SOH calculation
    # In production, this would query real degradation data
    return {
        "system_id": system_id,
        "battery_health": {
            "soh_pct": 98.5,
            "cycle_count": 142,
            "total_cycles_rated": 6000,
            "estimated_remaining_years": round(6000 / 365, 1),
            "degradation_cost_per_cycle_r": 75.0,
        },
        "dispatch_impact": {
            "cycles_per_year_estimated": 365,
            "annual_degradation_cost_r": round(75.0 * 365, 2),
            "annual_revenue_r": 85000.0,  # From KPI calculation
            "net_annual_benefit_r": round(85000.0 - (75.0 * 365), 2),
        },
    }


# === AEGIS Dispatch Governance Endpoints ===


@limiter.limit("20/minute")
@router.post("/solar/arbitrage/dispatch/proposal")
async def create_dispatch_proposal(
    request: Request,
    site_id: str = Query("site-002", description="Site ID"),
):
    """Create AEGIS dispatch proposal routed through approval pipeline.

    Returns recommendation with tier routing result, quality gate status,
    and approval requirement. All BESS dispatch actions are routed to Tier 2.
    """
    from app.services.aegis_bridge import run_aegis_cycle

    result = await run_aegis_cycle(site_id)
    if not result:
        return {"status": "idle", "message": "No dispatch action needed at this time"}
    return {
        "status": "proposal_created",
        "recommendation": result,
        "requires_approval": True,
        "tier": result.get("routing", {}).get("tier", "tier2"),
    }


@limiter.limit("30/minute")
@router.get("/solar/arbitrage/dispatch/history")
async def get_dispatch_history(
    request: Request,
    site_id: str = Query("site-002", description="Site ID"),
    hours: int = Query(24, ge=1, le=168, description="Hours of history (1-168)"),
    include_decisions: bool = Query(False, description="Include linked parasite_decisions"),
):
    """Persistent dispatch history from JSONL files.

    Returns dispatch events that survive restarts, unlike the RAM-only log.
    If include_decisions=True, joins recommendation IDs with parasite_decisions.
    """
    from app.services.solar_dispatch_service import get_solar_dispatch_service

    svc = get_solar_dispatch_service()
    events = svc.get_persistent_dispatch_log(site_id, hours=hours)

    result = {
        "site_id": site_id,
        "hours": hours,
        "event_count": len(events),
        "events": events,
    }

    if include_decisions:
        try:
            from app.database.repositories.parasite_decision_repository import (
                get_parasite_decision_repository,
            )

            repo = get_parasite_decision_repository()
            decisions = await repo.get_recent_decisions(limit=50)
            bess_decisions = [
                d
                for d in decisions
                if d.get("decision_type", "").startswith("tier") and "BESS" in (d.get("equipment_code") or "").upper()
            ]
            result["parasite_decisions"] = bess_decisions
        except Exception as e:
            logger.warning("Failed to load parasite_decisions: %s", e)
            result["parasite_decisions"] = []

    return result


# === Logging ===

import logging

logger = logging.getLogger(__name__)
