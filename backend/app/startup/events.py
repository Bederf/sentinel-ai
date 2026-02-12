"""Startup and shutdown event handlers for FastAPI application.

This module contains all startup and shutdown logic, extracted from main.py
to improve maintainability and separation of concerns.
"""

import logging
import os

from fastapi import FastAPI

from app.config.settings import settings
from app.services.background_scheduler import scheduler_service
from app.services.health_simulation_service import health_simulation_service  # Supabase health simulation
from app.services.simbiot_service import simbiot_service  # SIMBIOT Concept Evolution connector

_logger = logging.getLogger("sentinel.startup")


async def startup_event(app: FastAPI) -> None:
    """Initialize background services on startup.

    This function is called when the FastAPI application starts up.
    It performs security checks, initializes services, and starts
    background tasks.
    """
    testing_mode = os.getenv("TESTING", "").lower() == "true"

    # === Security startup checks ===

    # Block DEMO_MODE in production
    if settings.environment == "production" and settings.demo_mode:
        raise RuntimeError(
            "DEMO_MODE cannot be enabled in production environment. "
            "Set DEMO_MODE=false or ENVIRONMENT=development."
        )

    # Require JWT secret when not in DEMO_MODE (C-2: Secure JWT signing)
    if not settings.demo_mode and not settings.jwt_secret_key and not settings.supabase_key:
        raise RuntimeError(
            "JWT_SECRET_KEY (or SUPABASE_KEY) must be set when DEMO_MODE is disabled. "
            "Generate a 256-bit secret: python -c \"import secrets; print(secrets.token_hex(32))\" "
            "and set JWT_SECRET_KEY in your .env file."
        )

    # Warn about weak JWT secrets (less than 32 characters)
    _jwt_key = settings.jwt_secret_key or settings.supabase_key
    if _jwt_key and len(_jwt_key) < 32 and not settings.demo_mode:
        _logger.warning(
            "JWT_SECRET_KEY is shorter than 32 characters — consider using a "
            "256-bit secret: python -c \"import secrets; print(secrets.token_hex(32))\""
        )

    # Warn about DEMO_MODE
    if settings.demo_mode:
        _logger.warning(
            "DEMO_MODE is enabled - authentication is bypassed, "
            "all requests get ADMIN role. Do NOT use in production."
        )

    # Warn about missing methodology password
    if not settings.demo_mode and not settings.jwt_secret_key:
        _logger.warning(
            "JWT_SECRET_KEY not set - falling back to SUPABASE_KEY for JWT signing. "
            "Set JWT_SECRET_KEY for a dedicated signing secret."
        )

    _logger.info(f"Environment: {settings.environment}, Demo mode: {settings.demo_mode}")

    if testing_mode:
        _logger.info("TESTING mode: skipping background scheduler initialization")
        from app.api.devices import startup_event as devices_startup
        await devices_startup()
        return

    # Initialize Redis cache connection
    from app.services.cache_service import cache
    if cache.is_connected:
        print("Redis cache connected successfully")
    else:
        print("Redis cache unavailable - running without caching")

    # Initialize device manager with mock devices + building equipment
    from app.api.devices import startup_event as devices_startup
    await devices_startup()

    # Start background scheduler for demo data generation
    scheduler_service.start()

    # Generate initial demo data and schedule periodic updates (60 seconds)
    scheduler_service.add_demo_data_job(interval_seconds=60)

    # Start AI optimization analysis job (runs every 15 minutes)
    # Scans all sites with optimization_enabled=true and generates recommendations
    # When a recommendation is generated, the flashing lightbulb appears on dashboard
    scheduler_service.add_optimization_analysis_job(interval_seconds=900)  # 15 minutes

    # Start prediction generation job (runs every 5 minutes)
    # Scans equipment health scores and creates predictions for at-risk equipment
    # When equipment health drops below 90%, a prediction is auto-generated
    scheduler_service.add_prediction_generation_job(interval_seconds=300)  # 5 minutes

    # Start AI recommendation generation job (runs every 10 minutes)
    # Scans ALL equipment and generates recommendations:
    # - Healthy equipment (>=90%): Optimization & preventive maintenance
    # - At-risk equipment (<90%): Maintenance & repair recommendations
    scheduler_service.add_recommendation_generation_job(interval_seconds=600)  # 10 minutes

    # Start demand-aware coordinator (runs every 5 minutes)
    # Phase 081: Cross-module peak demand management
    # Monitors NMD headroom and coordinates HVAC + BESS + energy actions for shaving
    scheduler_service.add_demand_aware_coordination_job(interval_seconds=300)  # 5 minutes

    # Start model freshness check (runs daily)
    # Phase 45-01: Checks model age and R² score, auto-retrains stale models
    if hasattr(scheduler_service, "add_model_check_job"):
        scheduler_service.add_model_check_job(interval_seconds=86400)  # 24 hours

    # Start performance monitor (runs hourly)
    # Phase 45-01: Evaluates prediction accuracy against actual alerts
    if hasattr(scheduler_service, "add_performance_monitor_job"):
        scheduler_service.add_performance_monitor_job(interval_seconds=3600)  # 1 hour

    # Start system health snapshot job (runs every 5 minutes)
    # Stores point-in-time health snapshots for trend analysis and historical reporting
    from app.services.system_health_service import SystemHealthService
    health_service = SystemHealthService()
    
    async def store_health_snapshot():
        """Store current health snapshot to database."""
        try:
            snapshot = await health_service.get_current_health()
            await health_service.store_health_snapshot(snapshot)
            _logger.debug("Health snapshot stored successfully")
        except Exception as e:
            _logger.error(f"Failed to store health snapshot: {e}")
    
    # Wrap in try-except as add_job method may not be available
    try:
        scheduler_service.add_job(
            store_health_snapshot,
            interval_seconds=300,  # 5 minutes
            job_name="system_health_snapshot",
        )
    except (AttributeError, TypeError) as e:
        _logger.warning(f"Could not schedule health snapshot job: {e}")

    # Start error auto-resolution job (runs daily)
    # Auto-resolves errors if component is now healthy for 24+ hours
    async def auto_resolve_errors():
        """Auto-resolve errors if component is now healthy."""
        try:
            resolved_count = await health_service.auto_resolve_stale_errors()
            if resolved_count > 0:
                _logger.info(f"Auto-resolved {resolved_count} stale errors")
        except Exception as e:
            _logger.error(f"Failed to auto-resolve errors: {e}")
    
    # Wrap in try-except as add_job method may not be available
    try:
        scheduler_service.add_job(
            auto_resolve_errors,
            interval_seconds=86400,  # 24 hours
            job_name="system_error_auto_resolve",
        )
    except (AttributeError, TypeError) as e:
        _logger.warning(f"Could not schedule error auto-resolve job: {e}")

    # BMS simulation service - DISABLED for demo stability
    # try:
    #     await simulation_service.start_simulation()
    #     print("BMS Simulation service started successfully")
    # except Exception as e:
    #     print(f"Failed to start simulation service: {e}")

    # Start health simulation service (writes to Supabase, triggers Clawd alerts)
    # Runs every hour between 08:00-17:00
    # DISABLED: Start manually via POST /api/simulation/health-sim/start
    # try:
    #     await health_simulation_service.start()
    #     print("Health simulation service started (hourly, 08:00-17:00)")
    # except Exception as e:
    #     print(f"Failed to start health simulation service: {e}")

    # SIMBIOT Concept Evolution connector
    # Auto-initializes when SIMBIOT_API_URL and SIMBIOT_API_KEY env vars are set
    if hasattr(simbiot_service, 'initialise_from_settings'):
        await simbiot_service.initialise_from_settings()
    elif settings.simbiot_api_url and settings.simbiot_api_key:
        try:
            from simbiot_concept import ConceptConfig
            config = ConceptConfig(
                api_url=settings.simbiot_api_url,
                api_key=settings.simbiot_api_key,
                username=settings.simbiot_username,
                password=settings.simbiot_password,
            )
            await simbiot_service.initialise(config)
            print(f"[SIMBIOT] Connected to {settings.simbiot_api_url}")
        except Exception as e:
            print(f"[SIMBIOT] Failed to initialize: {e}")


async def shutdown_event(app: FastAPI) -> None:
    """Cleanup background services on shutdown.

    This function is called when the FastAPI application shuts down.
    It stops background services and closes connections.
    """
    scheduler_service.stop()
    await health_simulation_service.stop()
    await simbiot_service.shutdown()


def register_events(app: FastAPI) -> None:
    """Register startup and shutdown event handlers.

    Args:
        app: The FastAPI application instance
    """
    @app.on_event("startup")
    async def _startup_event():
        await startup_event(app)

    @app.on_event("shutdown")
    async def _shutdown_event():
        await shutdown_event(app)
