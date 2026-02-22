"""
Solar Annual Simulation API
Endpoints for 365-day solar/BESS simulation results and aggregations.
"""

import logging
from typing import Optional, Dict, Any
from fastapi import APIRouter, BackgroundTasks, HTTPException
from datetime import datetime
import asyncio

from app.services.solar_annual_aggregator import (
    get_solar_annual_aggregator,
    AnnualSummary,
    HourlySnapshot,
)
from app.database.supabase_client import get_supabase_client

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/solar/annual", tags=["solar-annual"])

# Background task tracking
_simulation_tasks: Dict[str, Dict[str, Any]] = {}


@router.get("/{site_id}/summary")
async def get_annual_summary(
    site_id: str,
    year: Optional[int] = None,
    current_user: Dict = None,
) -> AnnualSummary:
    """
    Get cached 365-day simulation results.

    Returns:
    - 12 monthly summaries (solar, BESS, costs, savings)
    - 4 seasonal summaries
    - ML learning curve (0-18% savings progression)
    - Annual totals and metrics

    Performance: < 100ms if cached
    """
    try:
        # Query Supabase for cached results (year is optional for flexibility)
        supabase = get_supabase_client()
        query = (
            supabase.table("solar_annual_simulations")
            .select("*")
            .eq("site_id", site_id)
            .eq("scenario", "grant_solar_bess_ai_annual")
        )

        # If year specified, filter by it. Otherwise, get the most recent
        if year is not None:
            query = query.eq("year", year)

        response = query.execute()

        if not response.data:
            # Not cached, return 404 to signal client to trigger simulation
            raise HTTPException(status_code=404, detail="Simulation results not cached. POST /simulate to generate.")

        # Get the most recent result (or the one matching the year if specified)
        if len(response.data) > 1 and year is None:
            # Return the most recent if no year specified
            results_row = sorted(response.data, key=lambda x: x.get("created_at", ""), reverse=True)[0]
        else:
            results_row = response.data[0]

        results_row = response.data[0]
        results_json = results_row.get("results", {})

        return AnnualSummary(**results_json)

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to fetch annual summary: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/{site_id}/simulate")
async def start_annual_simulation(
    site_id: str,
    scenario: str = "grant_solar_bess_ai_annual",
    duration_minutes: float = 30.0,
    background_tasks: BackgroundTasks = None,
    current_user: Dict = None,
) -> Dict[str, Any]:
    """
    Start 365-day simulation in background (30 minutes real-time by default).

    Returns immediately with task_id.
    Client should poll GET /status/{task_id} for progress.

    When complete, results cached in Supabase table `solar_annual_simulations`.
    """
    try:
        if not background_tasks:
            background_tasks = BackgroundTasks()

        task_id = f"{site_id}_{datetime.now().timestamp()}"

        # Register task
        _simulation_tasks[task_id] = {
            "status": "queued",
            "progress_pct": 0,
            "days_completed": 0,
            "started_at": datetime.now().isoformat(),
            "error": None,
        }

        # Schedule background simulation
        background_tasks.add_task(
            _run_annual_simulation,
            task_id=task_id,
            site_id=site_id,
            scenario=scenario,
            duration_minutes=duration_minutes,
        )

        logger.info(f"Queued annual simulation: task_id={task_id}, duration={duration_minutes}min")

        return {
            "task_id": task_id,
            "site_id": site_id,
            "scenario": scenario,
            "status": "queued",
            "queued_at": datetime.now().isoformat(),
        }

    except Exception as e:
        logger.error(f"Failed to start annual simulation: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/{site_id}/status/{task_id}")
async def get_simulation_status(
    site_id: str,
    task_id: str,
    current_user: Dict = None,
) -> Dict[str, Any]:
    """
    Poll simulation progress.

    Returns:
    - status: queued | running | completed | failed
    - progress_pct: 0-100
    - days_completed: 0-365
    - estimated_time_remaining_seconds: int (or -1 if unknown)
    """
    try:
        if task_id not in _simulation_tasks:
            raise HTTPException(status_code=404, detail="Task not found")

        task = _simulation_tasks[task_id]

        # Calculate estimated time remaining
        if task["status"] == "running":
            elapsed = (datetime.now() - datetime.fromisoformat(task["started_at"])).total_seconds()
            progress = task["progress_pct"]
            if progress > 0:
                total_estimated = (elapsed / progress) * 100
                remaining = total_estimated - elapsed
            else:
                remaining = -1
        else:
            remaining = -1

        return {
            "task_id": task_id,
            "status": task["status"],
            "progress_pct": task["progress_pct"],
            "days_completed": task["days_completed"],
            "estimated_time_remaining_seconds": int(remaining),
            "started_at": task["started_at"],
            "error": task.get("error"),
        }

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to fetch simulation status: {e}")
        raise HTTPException(status_code=500, detail=str(e))


async def _run_annual_simulation(
    task_id: str,
    site_id: str,
    scenario: str,
    duration_minutes: float,
) -> None:
    """
    Background task: Run 365-day simulation and aggregate results.

    Steps:
    1. Force-reset orchestrator singleton (in case it's stuck)
    2. Generate 8760 hourly snapshots for 365 days (paced over duration_minutes)
    3. Aggregate via SolarAnnualAggregator
    4. Cache results in Supabase

    Parameters:
    - duration_minutes: How many real-time minutes to spend on simulation (default 30)
    """
    try:
        from datetime import datetime as dt

        task = _simulation_tasks[task_id]
        task["status"] = "running"
        task["started_at"] = dt.now().isoformat()

        logger.info(f"✅ Background task started: task_id={task_id}, duration={duration_minutes}min")

        # CRITICAL: Force-reset orchestrator singleton (may be stuck from previous tests)
        try:
            logger.info("Step 1: Importing orchestrator...")
            from app.services.lifecycle_orchestrator import get_lifecycle_orchestrator

            logger.info("Step 2: Getting orchestrator singleton...")
            orchestrator = get_lifecycle_orchestrator()
            logger.info(f"Step 3: Orchestrator state BEFORE reset: running={orchestrator.running}")
            orchestrator.running = False
            logger.info(f"Step 4: Orchestrator state AFTER reset: running={orchestrator.running}")
        except Exception as reset_error:
            logger.error(f"❌ Could not reset orchestrator: {reset_error}", exc_info=True)
            raise

        # Generate synthetic hourly snapshots for 365 days
        # (In production, these would come from actual telemetry)
        logger.info(f"Step 5: Generating 365 days of hourly snapshots (spread over {duration_minutes}min)...")
        try:
            # Calculate pace: sleep between batches to spread over duration_minutes
            hourly_data = await _generate_hourly_snapshots_paced(None, duration_minutes, task)
            logger.info(f"Step 6: ✅ Generated {len(hourly_data)} hourly snapshots")
        except Exception as gen_error:
            logger.error(f"❌ Failed during snapshot generation: {gen_error}", exc_info=True)
            raise

        # Update progress as we enter aggregation phase
        task["progress_pct"] = 70
        task["days_completed"] = 256
        logger.info(f"📈 Progress: {task['progress_pct']}%, Days: {task['days_completed']}/365")

        logger.info("⚙️ Aggregating results...")

        # Aggregate via SolarAnnualAggregator
        logger.info("🔄 Creating aggregator...")
        aggregator = get_solar_annual_aggregator()
        logger.info("🔄 Running aggregation...")
        annual_summary = await aggregator.aggregate_annual_results(
            hourly_data=hourly_data,
            scenario=scenario,
        )
        logger.info(f"✅ Aggregation complete: {annual_summary.annual_savings_pct:.1f}% savings")

        # Cache results in Supabase (including hourly snapshots)
        logger.info("💾 Caching results...")
        await _cache_results(site_id, annual_summary, hourly_data=hourly_data)
        logger.info("✅ Results cached in Supabase")

        task["status"] = "completed"
        task["progress_pct"] = 100
        task["days_completed"] = 365

        logger.info(
            f"🎉 Annual simulation complete: {annual_summary.annual_savings_pct:.1f}% savings, R{annual_summary.annual_savings_zar:,.0f}"
        )

    except Exception as e:
        logger.error(f"Simulation failed: {e}", exc_info=True)
        task = _simulation_tasks.get(task_id, {})
        task["status"] = "failed"
        task["error"] = str(e)


async def _generate_hourly_snapshots_paced(orchestrator, duration_minutes: float, task: Dict) -> list:
    """
    Generate 8760 hourly snapshots paced over duration_minutes for realistic progress feedback.

    Updates task progress as snapshots are generated.
    """
    from app.services.seasonal_modeler import SeasonalModeler
    from datetime import datetime as dt, timedelta
    import time as time_module

    snapshots = []
    modeler = SeasonalModeler(seed=42)

    start_date = dt(2024, 1, 1, 6, 0, 0)
    start_time = time_module.time()
    total_seconds = duration_minutes * 60  # Convert to seconds

    for hour in range(8760):
        current_time = start_date + timedelta(hours=hour)
        day_of_year = (current_time.timetuple().tm_yday - 1) % 365 + 1
        current_hour = current_time.hour

        # Solar generation (0 at night, peaks at noon)
        solar_efficiency = modeler.get_solar_generation_factor(current_time.date(), cloud_cover=0.2)
        hour_factor = max(0, 1 - abs(current_hour - 12) / 6)
        solar_gen_kw = 3900 * solar_efficiency * hour_factor * 0.8

        # Building load (higher during day, occupancy-dependent)
        occupancy_factor = modeler.get_occupancy_factor(
            current_time.date(),
            current_hour,
            rain_today=False,
        )
        base_load = 500
        occupancy_load = 300 * occupancy_factor
        hvac_load = 200 * max(0, 1 - abs(current_hour - 14) / 8)
        building_load_kw = base_load + occupancy_load + hvac_load

        # BESS dynamics (charge at night, discharge during peak)
        if current_hour < 7 or current_hour > 20:
            bess_charge_kw = max(0, solar_gen_kw - building_load_kw)
            bess_discharge_kw = 0
        elif current_hour > 17:
            bess_discharge_kw = min(500, building_load_kw - solar_gen_kw)
            bess_charge_kw = 0
        else:
            bess_charge_kw = 0
            bess_discharge_kw = 0

        # BESS SOC (simple model)
        bess_soc_pct = 50 + (bess_charge_kw - bess_discharge_kw) * 0.1
        bess_soc_pct = max(10, min(90, bess_soc_pct))

        # Grid import/export
        net_solar = solar_gen_kw - building_load_kw - bess_charge_kw + bess_discharge_kw
        grid_export_kw = max(0, net_solar)
        grid_import_kw = max(0, -net_solar)

        # Tariff band (peak/standard/off_peak)
        if current_hour in [7, 8, 9, 18, 19]:
            tariff_band = "peak"
            rate = 3.45
        elif current_hour in [10, 11, 12, 13, 14, 15, 16, 17]:
            tariff_band = "standard"
            rate = 2.12
        else:
            tariff_band = "off_peak"
            rate = 1.05

        snapshot = HourlySnapshot(
            hour=hour,
            date=current_time,
            month=current_time.month,
            day_of_year=day_of_year,
            solar_gen_kw=solar_gen_kw,
            building_load_kw=building_load_kw,
            bess_soc_pct=bess_soc_pct,
            bess_charge_kw=bess_charge_kw,
            bess_discharge_kw=bess_discharge_kw,
            grid_import_kw=grid_import_kw,
            grid_export_kw=grid_export_kw,
            tariff_band=tariff_band,
            tariff_rate_c_kwh=rate,
        )

        snapshots.append(snapshot)

        # Update progress and sleep to pace over duration_minutes
        if (hour + 1) % 24 == 0:  # Every 24 hours (1 day)
            days_done = (hour + 1) // 24
            task["progress_pct"] = min(60, int(days_done / 365 * 50) + 10)  # 10%-60%
            task["days_completed"] = days_done

            # Calculate how long we should sleep to maintain pace
            elapsed = time_module.time() - start_time
            expected_time = (days_done / 365) * total_seconds
            sleep_time = max(0, expected_time - elapsed)

            if sleep_time > 0:
                await asyncio.sleep(sleep_time)

            logger.debug(f"Generated day {days_done}/365, progress {task['progress_pct']}%")

    logger.info(f"Generated {len(snapshots)} hourly snapshots over {duration_minutes}min")
    return snapshots


def _generate_hourly_snapshots(orchestrator) -> list:
    """
    Generate 8760 hourly snapshots from simulation data.

    In production, these would be actual telemetry from equipment.
    For now, we generate synthetic data based on seasonal patterns.
    """
    from app.services.seasonal_modeler import SeasonalModeler
    from datetime import datetime as dt, timedelta

    snapshots = []
    modeler = SeasonalModeler(seed=42)

    start_date = dt(2024, 1, 1, 6, 0, 0)

    for hour in range(8760):
        current_time = start_date + timedelta(hours=hour)
        # Calculate day_of_year (1-365, even in leap years)
        day_of_year = (current_time.timetuple().tm_yday - 1) % 365 + 1
        current_hour = current_time.hour

        # Solar generation (0 at night, peaks at noon)
        solar_efficiency = modeler.get_solar_generation_factor(
            current_time.date(),
            cloud_cover=0.2,  # Assume 20% cloud cover
        )

        # Solar peaks at noon (12:00)
        hour_factor = max(0, 1 - abs(current_hour - 12) / 6)  # Gaussian-like curve
        solar_gen_kw = 3900 * solar_efficiency * hour_factor * 0.8  # 3.9 MWp capacity

        # Building load (higher during day, occupancy-dependent)
        occupancy_factor = modeler.get_occupancy_factor(
            current_time.date(),
            current_hour,
            rain_today=False,
        )
        base_load = 500  # 500 kW base load
        occupancy_load = 300 * occupancy_factor
        hvac_load = 200 * max(0, 1 - abs(current_hour - 14) / 8)  # HVAC peaks at 14:00
        building_load_kw = base_load + occupancy_load + hvac_load

        # BESS dynamics (charge at night, discharge during peak)
        if current_hour < 7 or current_hour > 20:  # Night: charge from solar surplus
            bess_charge_kw = max(0, solar_gen_kw - building_load_kw)
            bess_discharge_kw = 0
        elif current_hour > 17:  # Evening peak: discharge
            bess_discharge_kw = min(500, building_load_kw - solar_gen_kw)
            bess_charge_kw = 0
        else:
            bess_charge_kw = 0
            bess_discharge_kw = 0

        # BESS SOC (simple model)
        bess_soc_pct = 50 + (bess_charge_kw - bess_discharge_kw) * 0.1  # Simplified
        bess_soc_pct = max(10, min(90, bess_soc_pct))  # Keep between 10-90%

        # Grid import/export
        net_solar = solar_gen_kw - building_load_kw - bess_charge_kw + bess_discharge_kw
        grid_export_kw = max(0, net_solar)
        grid_import_kw = max(0, -net_solar)

        # Tariff band (peak/standard/off_peak)
        if current_hour in [7, 8, 9, 18, 19]:  # Peak hours
            tariff_band = "peak"
            rate = 3.45  # c/kWh
        elif current_hour in [10, 11, 12, 13, 14, 15, 16, 17]:  # Standard
            tariff_band = "standard"
            rate = 2.12
        else:  # Off-peak
            tariff_band = "off_peak"
            rate = 1.05

        snapshot = HourlySnapshot(
            hour=hour,
            date=current_time,
            month=current_time.month,
            day_of_year=day_of_year,
            solar_gen_kw=solar_gen_kw,
            building_load_kw=building_load_kw,
            bess_soc_pct=bess_soc_pct,
            bess_charge_kw=bess_charge_kw,
            bess_discharge_kw=bess_discharge_kw,
            grid_import_kw=grid_import_kw,
            grid_export_kw=grid_export_kw,
            tariff_band=tariff_band,
            tariff_rate_c_kwh=rate,
        )

        snapshots.append(snapshot)

        # Log progress every 24 hours
        if (hour + 1) % 24 == 0:
            logger.debug(f"Generated hourly snapshots: {hour + 1}/8760")

    logger.info(f"Generated {len(snapshots)} hourly snapshots")
    return snapshots


async def _cache_results(site_id: str, annual_summary: AnnualSummary, hourly_data: list = None) -> None:
    """Cache annual results and daily aggregates in Supabase."""
    try:
        supabase = get_supabase_client()

        # Store daily aggregates (instead of hourly snapshots)
        if hourly_data:
            logger.info(f"Aggregating {len(hourly_data)} hourly snapshots into daily records for {site_id}...")

            # Aggregate hourly data by day (365 records instead of 8760)
            daily_records = {}
            for snap in hourly_data:
                day_key = snap.date.date().isoformat()

                if day_key not in daily_records:
                    daily_records[day_key] = {
                        "site_id": site_id,
                        "scenario": annual_summary.scenario,
                        "year": annual_summary.year,
                        "date": day_key,
                        "month": snap.month,
                        "day_of_year": snap.day_of_year,
                        "solar_gen_kwh": 0,
                        "building_load_kwh": 0,
                        "grid_import_kwh": 0,
                        "grid_export_kwh": 0,
                        "bess_charge_kwh": 0,
                        "bess_discharge_kwh": 0,
                        "peak_generation_kw": 0,
                        "avg_bess_soc_pct": [],
                    }

                # Sum hourly values for daily total (kW × 1 hour = kWh)
                daily_records[day_key]["solar_gen_kwh"] += snap.solar_gen_kw
                daily_records[day_key]["building_load_kwh"] += snap.building_load_kw
                daily_records[day_key]["grid_import_kwh"] += snap.grid_import_kw
                daily_records[day_key]["grid_export_kwh"] += snap.grid_export_kw
                daily_records[day_key]["bess_charge_kwh"] += snap.bess_charge_kw
                daily_records[day_key]["bess_discharge_kwh"] += snap.bess_discharge_kw
                daily_records[day_key]["peak_generation_kw"] = max(
                    daily_records[day_key]["peak_generation_kw"], snap.solar_gen_kw
                )
                daily_records[day_key]["avg_bess_soc_pct"].append(snap.bess_soc_pct)

            # Calculate average SOC and prepare final records
            daily_insert_records = []
            for day_key, daily in daily_records.items():
                avg_soc = sum(daily.pop("avg_bess_soc_pct")) / 24 if daily.get("avg_bess_soc_pct") else 50
                daily["avg_bess_soc_pct"] = round(avg_soc, 1)

                # Round to 1 decimal place
                for key in [
                    "solar_gen_kwh",
                    "building_load_kwh",
                    "grid_import_kwh",
                    "grid_export_kwh",
                    "bess_charge_kwh",
                    "bess_discharge_kwh",
                    "peak_generation_kw",
                ]:
                    daily[key] = round(daily[key], 1)

                daily_insert_records.append(daily)

            # Insert 365 daily records (much smaller than 8760 hourly)
            supabase.table("solar_daily_aggregates").insert(daily_insert_records).execute()
            logger.info(f"✅ Stored {len(daily_insert_records)} daily aggregates for {site_id}")

        # Prepare and cache aggregated results JSON
        results_json = {
            "site_id": annual_summary.site_id,
            "year": annual_summary.year,
            "scenario": annual_summary.scenario,
            "monthly_data": [
                {
                    "month": m.month,
                    "month_name": m.month_name,
                    "season": m.season,
                    "solar_generated_kwh": m.solar_generated_kwh,
                    "grid_import_kwh": m.grid_import_kwh,
                    "total_cost_standard_ems_zar": m.total_cost_standard_ems_zar,
                    "total_cost_sentinel_ai_zar": m.total_cost_sentinel_ai_zar,
                    "savings_zar": m.savings_zar,
                    "savings_pct": m.savings_pct,
                    "learning_factor": m.learning_factor,
                }
                for m in annual_summary.monthly_data
            ],
            "total_solar_kwh": annual_summary.total_solar_kwh,
            "total_cost_standard_ems_zar": annual_summary.total_cost_standard_ems_zar,
            "total_cost_sentinel_ai_zar": annual_summary.total_cost_sentinel_ai_zar,
            "annual_savings_zar": annual_summary.annual_savings_zar,
            "annual_savings_pct": annual_summary.annual_savings_pct,
            "learning_curve": annual_summary.learning_curve,
            "capacity_factor_pct": annual_summary.capacity_factor_pct,
            "self_consumption_pct": annual_summary.self_consumption_pct,
        }

        # Upsert annual simulation into Supabase (replace if exists)
        response = (
            supabase.table("solar_annual_simulations")
            .upsert(
                {
                    "site_id": site_id,
                    "year": annual_summary.year,
                    "scenario": annual_summary.scenario,
                    "results": results_json,
                    "simulation_started_at": annual_summary.simulation_started_at,
                    "simulation_completed_at": annual_summary.simulation_completed_at,
                    "simulation_duration_seconds": annual_summary.simulation_duration_seconds,
                }
            )
            .execute()
        )

        logger.info(f"Cached annual summary for {site_id}: {response.data}")

    except Exception as e:
        logger.error(f"Failed to cache results: {e}")
        raise
