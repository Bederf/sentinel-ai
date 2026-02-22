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
            "DEMO_MODE cannot be enabled in production environment. Set DEMO_MODE=false or ENVIRONMENT=development."
        )

    # Require JWT secret when not in DEMO_MODE (C-2: Secure JWT signing)
    if not settings.demo_mode and not settings.jwt_secret_key and not settings.supabase_key:
        raise RuntimeError(
            "JWT_SECRET_KEY (or SUPABASE_KEY) must be set when DEMO_MODE is disabled. "
            'Generate a 256-bit secret: python -c "import secrets; print(secrets.token_hex(32))" '
            "and set JWT_SECRET_KEY in your .env file."
        )

    # Warn about weak JWT secrets (less than 32 characters)
    _jwt_key = settings.jwt_secret_key or settings.supabase_key
    if _jwt_key and len(_jwt_key) < 32 and not settings.demo_mode:
        _logger.warning(
            "JWT_SECRET_KEY is shorter than 32 characters — consider using a "
            '256-bit secret: python -c "import secrets; print(secrets.token_hex(32))"'
        )

    # Warn about DEMO_MODE
    if settings.demo_mode:
        _logger.warning(
            "DEMO_MODE is enabled - authentication is bypassed, all requests get ADMIN role. Do NOT use in production."
        )

    # Warn about missing methodology password
    if not settings.demo_mode and not settings.jwt_secret_key:
        _logger.warning(
            "JWT_SECRET_KEY not set - falling back to SUPABASE_KEY for JWT signing. "
            "Set JWT_SECRET_KEY for a dedicated signing secret."
        )

    # === PARASITE Autonomous Control Safety Checks ===
    # Phase 100 Security: Prevent accidental Tier 3 autonomous control in production
    if settings.parasite_tier3_enabled and settings.environment == "production":
        _logger.critical(
            "🚨 PARASITE Tier 3 autonomous control is ENABLED in production — "
            "refusing to start. Set PARASITE_TIER3_ENABLED=false in your .env file."
        )
        raise RuntimeError(
            "PARASITE Tier 3 autonomous control cannot be enabled in production. Set PARASITE_TIER3_ENABLED=false"
        )

    if not settings.parasite_enabled:
        _logger.info("✅ PARASITE autonomous control: DISABLED (safe mode)")
    elif settings.parasite_enabled and not settings.parasite_tier3_enabled:
        _logger.warning(
            "⚠️ PARASITE autonomous control: ENABLED (Tier 1-2 supervised only) — "
            "device control requires manual approval"
        )
    elif settings.parasite_tier3_enabled:
        _logger.warning(
            "⚠️ PARASITE Tier 3 autonomous control: ENABLED — "
            "BMS devices may be controlled without human approval. "
            "Ensure safety boundaries are properly configured."
        )

    _logger.info(f"Environment: {settings.environment}, Demo mode: {settings.demo_mode}")
    if settings.is_live_mode and not settings.sentry_webhook_secret:
        raise RuntimeError("SENTRY_WEBHOOK_SECRET must be configured when INGESTION_MODE is shadow_live/live_control")

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
    from app.services.sentry_auth_service import initialize_sentry_auth

    initialize_sentry_auth(api_url=settings.backend_url or "http://localhost:9095")

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

    # Site-002 deterministic mode policy dry-run (runs every 5 minutes)
    # Observability only: evaluates stage thresholds and logs would-promote/demote actions
    try:
        scheduler_service.add_site_mode_policy_dry_run_job(interval_seconds=300, site_id="site-002")
        _logger.info("✅ Site mode policy dry-run initialized for site-002")
    except Exception as e:
        _logger.warning(f"⚠️ Site mode policy dry-run initialization failed: {e}")

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
        await aio.wait_for(autonomous_decision_engine.initialize(load_demo_data=True), timeout=10.0)
        _logger.info("Autonomous decision engine initialized successfully")

        if not escalation_engine._initialized:
            await aio.wait_for(escalation_engine.initialize(), timeout=5.0)
            _logger.info("Escalation engine initialized successfully")

        if not safety_boundary_service._initialized:
            await aio.wait_for(safety_boundary_service.initialize(), timeout=5.0)
            _logger.info("Safety boundary service initialized successfully")
    except aio.TimeoutError:
        _logger.warning("⏱️ Autonomous system initialization timed out - continuing without full initialization")
    except Exception as e:
        _logger.error(f"Failed to initialize autonomous system: {e}")

    # Start Sentry notification processing (runs every 30 seconds)
    # When equipment health drops to warning/critical, technicians receive Telegram notifications
    # This background job ensures notifications are sent promptly even if Sentry bot polling is delayed
    if hasattr(scheduler_service, "add_sentry_notification_job"):
        scheduler_service.add_sentry_notification_job(interval_seconds=30)  # 30 seconds

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

    # Start M&V verification job (runs every 15 minutes)
    # Verifies expected-vs-actual outcomes for applied optimization recommendations
    try:
        scheduler_service.add_mv_verification_job(interval_seconds=900)  # 15 minutes
        _logger.info("✅ M&V verification job initialized - checks pending verification windows")
    except Exception as e:
        _logger.warning(f"⚠️ M&V verification job initialization failed: {e}")

    # Start feedback scoring refresh job (runs every 15 minutes)
    # Rebuilds feedback-derived module score multipliers used by recommendation ranking
    try:
        scheduler_service.add_feedback_scoring_refresh_job(interval_seconds=900)  # 15 minutes
        _logger.info("✅ Feedback scoring refresh job initialized - updates module multipliers")
    except Exception as e:
        _logger.warning(f"⚠️ Feedback scoring refresh job initialization failed: {e}")

    # Start feedback-driven retraining trigger job (runs hourly)
    # Triggers model retraining when realized module outcomes degrade below threshold
    try:
        scheduler_service.add_feedback_retraining_job(
            interval_seconds=3600,  # 1 hour
            min_records=10,
            min_success_rate=70.0,
            cooldown_hours=24,
        )
        _logger.info("✅ Feedback retraining job initialized - monitors module outcome success rates")
    except Exception as e:
        _logger.warning(f"⚠️ Feedback retraining job initialization failed: {e}")

    # Phase 083: Recover crashed simulations from database
    # Queries for any tasks marked as 'running' and resumes from checkpoint
    async def recover_crashed_simulations():
        """
        Recover simulations that were running when server crashed/restarted.
        Tasks with a valid checkpoint are re-queued for the queue processor.
        Tasks running >48 hours wall-clock with no checkpoint are marked failed.
        """
        try:
            from datetime import datetime as dt
            from datetime import timedelta

            from app.database.supabase_client import Supabase

            client = Supabase.instance()

            # Query for any crashed tasks (status='running')
            response = client.table("lifecycle_simulation_tasks").select("*").eq("status", "running").execute()

            if not response.data:
                _logger.info("No crashed simulations to recover")
                return

            _logger.info(f"Found {len(response.data)} crashed simulation(s) to recover...")

            # Age guard: tasks running >48 hours with no checkpoint are stale
            max_age = timedelta(hours=48)
            now = dt.utcnow()

            for task in response.data:
                task_id = str(task["task_id"])
                state_snapshot = task.get("state_snapshot")
                created_at = task.get("created_at", "")

                # Parse created_at for age check
                try:
                    task_age = now - dt.fromisoformat(created_at.replace("Z", "+00:00").replace("+00:00", ""))
                except Exception:
                    task_age = max_age  # If we can't parse, treat as old

                if not state_snapshot:
                    if task_age > max_age:
                        _logger.warning(f"Task {task_id} has no checkpoint and is >{max_age} old — marking failed")
                        try:
                            client.table("lifecycle_simulation_tasks").update(
                                {"status": "failed", "error_message": "Stale: no checkpoint after 48h"}
                            ).eq("task_id", task_id).execute()
                        except Exception as e:
                            _logger.error(f"Failed to mark stale task {task_id}: {e}")
                    else:
                        _logger.warning(f"Task {task_id} has no checkpoint — marking failed")
                        try:
                            client.table("lifecycle_simulation_tasks").update(
                                {"status": "failed", "error_message": "No checkpoint state available for recovery"}
                            ).eq("task_id", task_id).execute()
                        except Exception as e:
                            _logger.error(f"Failed to mark task {task_id}: {e}")
                    continue

                try:
                    # Re-queue for the queue processor to resume from checkpoint
                    client.table("lifecycle_simulation_tasks").update({"status": "queued", "error_message": None}).eq(
                        "task_id", task_id
                    ).execute()

                    days_simulated = state_snapshot.get("days_simulated", 0)
                    simulated_time = state_snapshot.get("simulated_time", "unknown")
                    _logger.info(f"Queued recovery for task {task_id}: day {days_simulated}/365, time {simulated_time}")
                except Exception as e:
                    _logger.error(f"Failed to queue recovery for task {task_id}: {e}")

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
            running_tasks = (
                client.table("lifecycle_simulation_tasks").select("task_id").eq("status", "running").execute()
            )

            if running_tasks.data:
                _logger.info(f"🛑 Stopping {len(running_tasks.data)} running simulation(s)...")
                for task in running_tasks.data:
                    try:
                        client.table("lifecycle_simulation_tasks").update({"status": "stopped"}).eq(
                            "task_id", task["task_id"]
                        ).execute()
                    except Exception as update_err:
                        _logger.warning(f"Could not update task {task['task_id']}: {update_err}")
                _logger.info(f"✅ Stopped {len(running_tasks.data)} running simulation(s)")

            # Mark any queued simulations as 'inactive' (don't auto-start)
            # Only deactivate tasks from BEFORE this startup (older than 5 seconds)
            # This prevents deactivating tasks created during the current startup
            from datetime import datetime, timedelta

            cutoff_time = (datetime.utcnow() - timedelta(seconds=5)).isoformat()

            queued_tasks = (
                client.table("lifecycle_simulation_tasks")
                .select("task_id, created_at")
                .eq("status", "queued")
                .lt("created_at", cutoff_time)
                .execute()
            )

            if queued_tasks.data:
                _logger.info(f"⏸️  Deactivating {len(queued_tasks.data)} queued simulation(s) from before startup...")
                for task in queued_tasks.data:
                    try:
                        client.table("lifecycle_simulation_tasks").update({"status": "inactive"}).eq(
                            "task_id", task["task_id"]
                        ).execute()
                    except Exception as update_err:
                        _logger.warning(f"Could not deactivate task {task['task_id']}: {update_err}")
                _logger.info(f"✅ Deactivated {len(queued_tasks.data)} queued simulation(s)")
            else:
                _logger.info("✅ No old queued simulations to deactivate")

            if not running_tasks.data and not queued_tasks.data:
                _logger.info("✅ No active simulations to deactivate")

        except Exception as e:
            _logger.error(f"⚠️ Failed to deactivate simulations on startup: {e}")

    # Run crash recovery on startup (replaces old deactivate_all_simulations)
    # Re-queues simulations that have valid checkpoints, fails those without
    if not testing_mode:
        try:
            await recover_crashed_simulations()
        except Exception as e:
            _logger.error(f"Error during crash recovery: {e}")
            # Fallback: deactivate everything if recovery itself fails
            try:
                await deactivate_all_simulations()
            except Exception as e2:
                _logger.error(f"Fallback deactivation also failed: {e2}")

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
        _logger.warning("⚠️ Simulations will not be auto-processed. Manual intervention required.")

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
    if hasattr(simbiot_service, "initialise_from_settings"):
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

    # Save checkpoints for all active simulations before stopping
    try:
        from app.services.simulation_orchestrator import get_all_active_simulations

        active_sims = get_all_active_simulations()
        if active_sims:
            _logger.info(f"Saving checkpoints for {len(active_sims)} active simulation(s)...")
            for task_id, orchestrator in active_sims.items():
                try:
                    if orchestrator.running:
                        await orchestrator.save_checkpoint()
                        _logger.info(f"Checkpoint saved for task {task_id} (day {orchestrator.days_simulated})")
                except Exception as cp_err:
                    _logger.error(f"Failed to save checkpoint for {task_id}: {cp_err}")
    except Exception as e:
        _logger.error(f"Error saving simulation checkpoints on shutdown: {e}")

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
