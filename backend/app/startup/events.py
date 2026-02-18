"""Startup and shutdown event handlers for FastAPI application.

This module contains all startup and shutdown logic, extracted from main.py
to improve maintainability and separation of concerns.
"""

import asyncio
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
    try:
        await asyncio.wait_for(devices_startup(), timeout=15.0)
        _logger.info("✅ Device manager initialized successfully")
    except asyncio.TimeoutError:
        _logger.warning("⏱️ Device manager initialization timed out - continuing without it")
    except Exception as e:
        _logger.error(f"❌ Device manager initialization failed: {e}")

    # Initialize Sentry bot JWT authentication (non-blocking)
    from app.services.sentry_auth_service import initialize_sentry_auth, get_sentry_auth_service

    sentry_auth = initialize_sentry_auth(api_url=settings.backend_url or "http://localhost:9095")

    # Skip Sentry login during startup to avoid blocking
    # Sentry will attempt login on first use via get_token_or_refresh()
    _logger.info("ℹ Sentry bot JWT authentication deferred to first use")

    # Capture the main event loop for cross-thread scheduling (simulation tasks)
    scheduler_service.set_main_loop(asyncio.get_event_loop())

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

    # Start AI recommendation generation job (runs every 10 minutes, or 2 minutes in DEMO_MODE)
    # Scans ALL equipment and generates recommendations:
    # - Healthy equipment (>=90%): Optimization & preventive maintenance
    # - At-risk equipment (<90%): Maintenance & repair recommendations
    scheduler_service.add_recommendation_generation_job(interval_seconds=settings.recommendation_interval)

    # Start integration sync job (runs every 15 minutes)
    # Updates last_sync_at on all active log sources so System Health dashboard stays fresh
    scheduler_service.add_integration_sync_job(interval_seconds=900)  # 15 minutes

    # Start demand-aware coordinator (runs every 5 minutes)
    # Phase 081: Cross-module peak demand management
    # Monitors NMD headroom and coordinates HVAC + BESS + energy actions for shaving
    scheduler_service.add_demand_aware_coordination_job(interval_seconds=300)  # 5 minutes

    # Initialize bounded autonomy system (Phase 9)
    # Autonomous decision engine with safety boundaries and escalation management
    from app.services.autonomous_decision_engine import autonomous_decision_engine
    from app.services.escalation_engine import escalation_engine
    from app.services.safety_boundary_service import safety_boundary_service
    import asyncio as aio  # Local import to avoid scoping issues

    try:
        # Wrap with timeout to prevent startup hang (10 second limit)
        await aio.wait_for(
            autonomous_decision_engine.initialize(load_demo_data=True),
            timeout=10.0
        )
        _logger.info("Autonomous decision engine initialized successfully")

        if not escalation_engine._initialized:
            await aio.wait_for(
                escalation_engine.initialize(),
                timeout=5.0
            )
            _logger.info("Escalation engine initialized successfully")

        if not safety_boundary_service._initialized:
            await aio.wait_for(
                safety_boundary_service.initialize(),
                timeout=5.0
            )
            _logger.info("Safety boundary service initialized successfully")
    except aio.TimeoutError:
        _logger.warning("⏱️ Autonomous system initialization timed out - continuing without full initialization")
    except Exception as e:
        _logger.error(f"Failed to initialize autonomous system: {e}")

    # Start Sentry notification processing (runs every 30 seconds)
    # When equipment health drops to warning/critical, technicians receive Telegram notifications
    # This background job ensures notifications are sent promptly even if Sentry bot polling is delayed
    # TEMPORARILY DISABLED for testing - uncomment to re-enable
    # if hasattr(scheduler_service, "add_sentry_notification_job"):
    #     scheduler_service.add_sentry_notification_job(interval_seconds=30)  # 30 seconds

    # Start ML model retraining job (runs daily)
    # Phase 45-01: Checks model age (>30 days) and R² score (<0.65), auto-retrains stale models
    # Retrains ONE model per cycle to avoid system overload. Models prioritized by age and performance.
    try:
        scheduler_service.add_ml_retraining_job(interval_seconds=86400)  # 24 hours
        _logger.info("✅ ML model retraining job initialized - checks daily for stale/underperforming models")
    except Exception as e:
        _logger.warning(f"⚠️ ML retraining job initialization failed: {e}")

    # Start drift detection job (runs hourly)
    # Phase 45-03: Monitors for data/model drift, auto-triggers retraining when patterns change
    # Detects when 3+ features drift or prediction accuracy drops >10%
    try:
        scheduler_service.add_drift_detection_job(interval_seconds=3600)  # 1 hour
        _logger.info("✅ Drift detection job initialized - monitors hourly for model/data drift")
    except Exception as e:
        _logger.warning(f"⚠️ Drift detection job initialization failed: {e}")

    # Phase 083: Recover crashed simulations from database
    # Queries for any tasks marked as 'running' and resumes from checkpoint
    async def recover_crashed_simulations():
        """
        Recover any simulations that were running when server crashed.
        Deserializes state from database and resumes from checkpoint.
        """
        try:
            from app.database.supabase_client import Supabase
            from app.services.simulation_orchestrator import (
                create_orchestrator,
                register_simulation,
            )

            client = Supabase.instance()

            # Query for any crashed tasks (status='running')
            response = await client.table("lifecycle_simulation_tasks") \
                .select("*") \
                .eq("status", "running") \
                .eq("simulation_type", "lifecycle") \
                .execute()

            if not response.data:
                _logger.info("✅ No crashed simulations to recover")
                return

            _logger.info(f"🔄 Found {len(response.data)} crashed simulation(s) to recover...")

            # Recover each crashed simulation
            for task in response.data:
                task_id = str(task["task_id"])
                state_snapshot = task.get("state_snapshot", {})

                if not state_snapshot:
                    _logger.warning(f"⚠️ Task {task_id} has no state snapshot - cannot recover")
                    # Mark as failed since we can't resume
                    await client.table("lifecycle_simulation_tasks") \
                        .update({
                            "status": "failed",
                            "error_message": "No checkpoint state available for recovery"
                        }) \
                        .eq("task_id", task_id) \
                        .execute()
                    continue

                try:
                    # Mark task as "queued" so queue processor will resume it
                    # Queue processor will deserialize state and continue from checkpoint
                    await client.table("lifecycle_simulation_tasks") \
                        .update({
                            "status": "queued",
                            "error_message": None
                        }) \
                        .eq("task_id", task_id) \
                        .execute()

                    # Extract checkpoint details for logging
                    simulated_time = state_snapshot.get("simulated_time", "unknown")
                    days_simulated = state_snapshot.get("days_simulated", 0)

                    _logger.info(
                        f"✅ Queued recovery for task {task_id}: "
                        f"day {days_simulated}/365, "
                        f"time {simulated_time}"
                    )

                except Exception as e:
                    _logger.error(f"❌ Failed to queue recovery for task {task_id}: {e}")

        except Exception as e:
            _logger.error(f"Crash recovery initialization failed: {e}")

    # DEACTIVATE ALL SIMULATIONS ON STARTUP
    # Ensures clean state: no simulations auto-running after restart
    # Explicitly stop any running simulations and mark queued ones as inactive
    async def deactivate_all_simulations():
        """
        Deactivate all running and queued simulations on startup.
        This ensures clean state and prevents auto-resuming of simulations.
        """
        try:
            from app.database.supabase_client import Supabase

            client = Supabase.instance()

            # Stop any running simulations (set status to 'stopped')
            running_tasks = client.table("lifecycle_simulation_tasks") \
                .select("task_id") \
                .eq("status", "running") \
                .execute()

            if running_tasks.data:
                _logger.info(f"🛑 Stopping {len(running_tasks.data)} running simulation(s)...")
                for task in running_tasks.data:
                    try:
                        client.table("lifecycle_simulation_tasks") \
                            .update({"status": "stopped"}) \
                            .eq("task_id", task["task_id"]) \
                            .execute()
                    except Exception as update_err:
                        _logger.warning(f"Could not update task {task['task_id']}: {update_err}")
                _logger.info(f"✅ Stopped {len(running_tasks.data)} running simulation(s)")

            # Mark any queued simulations as 'inactive' (don't auto-start)
            # Only deactivate tasks from BEFORE this startup (older than 5 seconds)
            # This prevents deactivating tasks created during the current startup
            from datetime import datetime, timedelta
            cutoff_time = (datetime.utcnow() - timedelta(seconds=5)).isoformat()

            queued_tasks = client.table("lifecycle_simulation_tasks") \
                .select("task_id, created_at") \
                .eq("status", "queued") \
                .lt("created_at", cutoff_time) \
                .execute()

            if queued_tasks.data:
                _logger.info(f"⏸️  Deactivating {len(queued_tasks.data)} queued simulation(s) from before startup...")
                for task in queued_tasks.data:
                    try:
                        client.table("lifecycle_simulation_tasks") \
                            .update({"status": "inactive"}) \
                            .eq("task_id", task["task_id"]) \
                            .execute()
                    except Exception as update_err:
                        _logger.warning(f"Could not deactivate task {task['task_id']}: {update_err}")
                _logger.info(f"✅ Deactivated {len(queued_tasks.data)} queued simulation(s)")
            else:
                _logger.info("✅ No old queued simulations to deactivate")

            if not running_tasks.data and not queued_tasks.data:
                _logger.info("✅ No active simulations to deactivate")

        except Exception as e:
            _logger.error(f"⚠️ Failed to deactivate simulations on startup: {e}")

    # Run deactivation on startup
    if not testing_mode:
        try:
            await deactivate_all_simulations()
        except Exception as e:
            _logger.error(f"Error during simulation deactivation: {e}")

    # Run crash recovery on startup - DISABLED to prevent auto-start of simulations
    # if not testing_mode:
    #     import asyncio
    #     try:
    #         await recover_crashed_simulations()
    #     except Exception as e:
    #         _logger.error(f"Error during crash recovery: {e}")

    # Start simulation queue processor job - Phase 094 ENABLED
    # Phase 083: Process queued lifecycle simulations from database
    # Enables concurrent simulations and crash recovery via task queue
    _logger.info("[DEBUG] About to initialize simulation queue processor...")
    try:
        _logger.info("[DEBUG] Calling add_simulation_queue_processor_job()...")
        scheduler_service.add_simulation_queue_processor_job(interval_seconds=10)
        _logger.info("✅ Simulation queue processor initialized - checks every 10s for queued simulations")
        _logger.info(f"[DEBUG] Scheduler status - running: {scheduler_service.scheduler.running}")
        _logger.info(f"[DEBUG] Total jobs in scheduler: {len(scheduler_service.scheduler.get_jobs())}")
    except Exception as e:
        _logger.error(f"❌ Simulation queue processor initialization failed: {e}", exc_info=True)
        _logger.warning(f"⚠️ Simulations will not be auto-processed. Manual intervention required.")

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

    # Start health simulation service (writes to Supabase, triggers Sentry alerts)
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
    # Stop Sentry JWT token refresh
    from app.services.sentry_auth_service import get_sentry_auth_service
    sentry_auth = get_sentry_auth_service()
    if sentry_auth:
        await sentry_auth.stop_background_refresh()

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
