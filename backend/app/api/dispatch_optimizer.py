"""Dispatch Optimizer API — MIP-optimized BESS dispatch endpoints.

Endpoints:
  GET  /api/dispatch-optimizer/{site_id}/schedule  — Current optimal schedule
  GET  /api/dispatch-optimizer/{site_id}/compare    — MIP vs rules side-by-side
  POST /api/dispatch-optimizer/{site_id}/solve      — Trigger fresh optimization
  POST /api/dispatch-optimizer/kill-switch           — Emergency stop all writes
"""

import logging
from datetime import datetime, timezone
from typing import Optional

from fastapi import APIRouter, Depends, Query

from app.middleware.auth_middleware import require_site_access
from app.models.auth import AuthContext
from app.config.settings import settings
from app.services.mip_dispatch_optimizer import get_mip_dispatch_optimizer

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/dispatch-optimizer", tags=["dispatch-optimizer"])


@router.get("/{site_id}/schedule")
async def get_dispatch_schedule(site_id: str, auth: AuthContext = Depends(require_site_access("site_id"))):
    """Get the current optimal dispatch schedule.

    Returns the cached MIP-optimized schedule if available,
    otherwise triggers a fresh solve.
    """
    optimizer = get_mip_dispatch_optimizer()
    schedule = optimizer.get_cached_schedule(site_id)

    if not schedule:
        # No cached schedule — trigger a solve with default inputs
        schedule = optimizer.optimize(site_id)

    return schedule.to_dict()


@router.get("/{site_id}/compare")
async def compare_dispatch_strategies(site_id: str, auth: AuthContext = Depends(require_site_access("site_id"))):
    """Compare MIP-optimized vs rules-based dispatch side by side.

    Returns both schedules with total cost comparison and savings.
    """
    optimizer = get_mip_dispatch_optimizer()

    # Get load and solar forecasts for comparison
    try:
        from app.services.load_forecast_service import get_load_forecast_service

        load_svc = get_load_forecast_service()
        load_forecast_obj = load_svc.get_forecast(site_id, intervals_ahead=96)
        load_forecast = [i.demand_kw for i in load_forecast_obj.intervals]
    except Exception:
        load_forecast = None

    try:
        from app.services.solar_forecast_service import get_solar_forecast_service

        solar_svc = get_solar_forecast_service()
        solar_forecast_obj = solar_svc.get_forecast(site_id, hours_ahead=24)
        # Solar forecast is hourly — expand to 15-min
        solar_forecast = []
        for h in solar_forecast_obj.hourly:
            solar_forecast.extend([h.generation_kw] * 4)
        solar_forecast = solar_forecast[:96]
    except Exception:
        solar_forecast = None

    comparison = optimizer.get_comparison(
        site_id,
        load_forecast=load_forecast,
        solar_forecast=solar_forecast,
    )

    return comparison


@router.post("/{site_id}/solve")
async def solve_dispatch(
    site_id: str,
    initial_soc_kwh: Optional[float] = Query(100.0, ge=0, le=200, description="Initial SOC in kWh"),
    auth: AuthContext = Depends(require_site_access("site_id")),
):
    """Trigger a fresh MIP optimization solve.

    Uses current load and solar forecasts as inputs.
    """
    optimizer = get_mip_dispatch_optimizer()

    # Get forecasts
    load_forecast = None
    solar_forecast = None

    try:
        from app.services.load_forecast_service import get_load_forecast_service

        load_svc = get_load_forecast_service()
        forecast = load_svc.get_forecast(site_id, intervals_ahead=96)
        load_forecast = [i.demand_kw for i in forecast.intervals]
    except Exception as e:
        logger.warning("Could not get load forecast for MIP solve: %s", e)

    try:
        from app.services.solar_forecast_service import get_solar_forecast_service

        solar_svc = get_solar_forecast_service()
        solar_obj = solar_svc.get_forecast(site_id, hours_ahead=24)
        solar_forecast = []
        for h in solar_obj.hourly:
            solar_forecast.extend([h.generation_kw] * 4)
        solar_forecast = solar_forecast[:96]
    except Exception as e:
        logger.warning("Could not get solar forecast for MIP solve: %s", e)

    schedule = optimizer.optimize(
        site_id,
        initial_soc_kwh=initial_soc_kwh,
        load_forecast=load_forecast,
        solar_forecast=solar_forecast,
    )

    return schedule.to_dict()


@router.post("/kill-switch")
async def kill_switch():
    """Emergency kill switch — set idle, close AEGIS, switch to simulation, log.

    This is a one-shot emergency stop that:
    1. Sends idle (0 kW) to BESS
    2. Closes the AEGIS write gate
    3. Switches connector mode to simulation
    4. Logs everything to audit trail

    To re-enable, set env vars and restart the backend.
    """
    from app.services.modbus_bess_writer import get_modbus_bess_writer

    logger.critical("KILL SWITCH ACTIVATED — disabling all hardware writes")

    actions = []
    errors = []

    # 1. Send idle to BESS (best-effort — may fail if already disconnected)
    try:
        writer = get_modbus_bess_writer()
        result = await writer.write_idle(reason="kill_switch", who="operator_kill_switch")
        actions.append(f"idle_sent: success={result.success}")
    except Exception as e:
        errors.append(f"idle_send_failed: {e}")
        logger.error("Kill switch: idle command failed: %s", e)

    # 2. Close AEGIS gate (runtime override — reverts on restart)
    try:
        settings.aegis_bess_writer_enabled = False
        actions.append("aegis_gate: CLOSED")
    except Exception as e:
        errors.append(f"aegis_close_failed: {e}")

    # 3. Switch to simulation mode (runtime override — reverts on restart)
    try:
        settings.solar_connector_mode = "simulation"
        actions.append("connector_mode: simulation")
    except Exception as e:
        errors.append(f"mode_switch_failed: {e}")

    # 4. Disconnect Modbus TCP
    try:
        writer = get_modbus_bess_writer()
        await writer.disconnect()
        actions.append("modbus_disconnected: true")
    except Exception as e:
        errors.append(f"disconnect_failed: {e}")

    # 5. Audit log
    timestamp = datetime.now(timezone.utc).isoformat()
    logger.critical(
        "KILL SWITCH COMPLETE at %s — actions: %s, errors: %s",
        timestamp,
        actions,
        errors,
    )

    return {
        "status": "killed",
        "timestamp": timestamp,
        "actions": actions,
        "errors": errors,
        "message": "All hardware writes disabled. Restart backend to re-enable.",
    }
