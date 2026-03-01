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
        _logger.warning("DEMO_MODE is enabled - auth bypassed, requests get OPERATOR role. Do NOT use in production.")

    # Warn about missing methodology password
    if not settings.demo_mode and not settings.jwt_secret_key:
        _logger.warning(
            "JWT_SECRET_KEY not set - falling back to SUPABASE_KEY for JWT signing. "
            "Set JWT_SECRET_KEY for a dedicated signing secret."
        )

    # === SENTINEL LIVE MODE BANNER ===
    # Sprint 0 hardening: loud banner when hardware writes are possible
    if settings.solar_connector_mode == "live":
        _logger.critical(
            "\n"
            "╔══════════════════════════════════════════════════════════╗\n"
            "║            ⚡ SENTINEL IS LIVE ⚡                       ║\n"
            "║  SOLAR_CONNECTOR_MODE = live                            ║\n"
            "║  MODBUS_BESS_IP       = %-30s  ║\n"
            "║  AEGIS WRITE GATE     = %-30s  ║\n"
            "║  DEMO_MODE            = %-30s  ║\n"
            "║                                                        ║\n"
            "║  Real hardware reads are ACTIVE.                       ║\n"
            "║  Kill switch: POST /api/dispatch-optimizer/kill-switch  ║\n"
            "╚══════════════════════════════════════════════════════════╝",
            settings.modbus_bess_ip or "(not set)",
            "OPEN" if settings.aegis_bess_writer_enabled else "CLOSED",
            str(settings.demo_mode),
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

    # Pre-warm embedding model in background so first doc search doesn't pay 11s load cost
    def _warm_embedding_model():
        try:
            from app.services.embedding_service import get_embedding_service

            svc = get_embedding_service()
            svc.warmup()
            _logger.info("✅ Embedding model pre-warmed")
        except Exception as e:
            _logger.warning(f"⚠️ Embedding model warmup failed (will load on first use): {e}")

    import threading

    threading.Thread(target=_warm_embedding_model, daemon=True).start()

    # Initialize device manager with reference devices + building equipment
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

    # Event bus subscribers (Phase 139)
    from app.services.event_subscribers import register_default_subscribers

    register_default_subscribers()
    _logger.info("Event bus subscribers registered")

    # n8n webhook bridge (Phase 140)
    from app.services.n8n_event_subscriber import register_n8n_subscribers

    register_n8n_subscribers()

    # Sentry notification router — importance-based delivery (Phase 140)
    from app.services.sentry_event_subscriber import register_sentry_subscribers

    register_sentry_subscribers()

    # Background notification tasks (escalation checker, digest scheduler)
    from app.services.notification_tasks import start_notification_tasks

    await start_notification_tasks()

    # Capture the main event loop for cross-thread scheduling (simulation tasks)
    scheduler_service.set_main_loop(asyncio.get_event_loop())

    # Start background scheduler
    scheduler_service.start()

    # NOTE: Fake audit data generator removed — audit trail must only contain
    # real control actions, not synthetic noise.

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

    # POPIA retention enforcement (daily by default)
    if settings.popia_retention_enabled:
        try:
            scheduler_service.add_popia_retention_job(interval_seconds=settings.popia_retention_job_interval_seconds)
            _logger.info("✅ POPIA retention enforcement job initialized")
        except Exception as e:
            _logger.warning(f"⚠️ POPIA retention job initialization failed: {e}")

    # AEGIS Phase 0 — dispatch cycle (5 min) + daily evidence collector (24h)
    # Gated by solar module being active (AEGIS is the Solar/BESS dispatch optimizer)
    _aegis_enabled = False
    try:
        from app.services.module_registry_service import ModuleRegistryService

        _registry = ModuleRegistryService()
        _aegis_enabled = _registry.is_module_active("site-002", "solar")
    except Exception:
        # Fallback: check JSON directly
        try:
            import json as _json
            from pathlib import Path as _Path

            _mods_path = _Path(settings.data_dir) / "modules" / "site_modules.json"
            if _mods_path.exists():
                _mods_data = _json.loads(_mods_path.read_text())
                _aegis_enabled = any(
                    m.get("module_type") == "solar" and m.get("status") == "active"
                    for m in _mods_data.get("site-002", {}).get("active_modules", [])
                )
        except Exception:
            pass

    if _aegis_enabled:
        try:
            scheduler_service.add_aegis_cycle_job(interval_seconds=300, site_id="site-002")
            _logger.info("✅ AEGIS dispatch cycle job initialized (5 min interval)")
        except Exception as e:
            _logger.warning(f"⚠️ AEGIS cycle job initialization failed: {e}")

        try:
            scheduler_service.add_aegis_evidence_collector_job(interval_seconds=86400, site_id="site-002")
            _logger.info("✅ AEGIS evidence collector job initialized (24h interval)")
        except Exception as e:
            _logger.warning(f"⚠️ AEGIS evidence collector job initialization failed: {e}")
    else:
        _logger.info("⏸️ AEGIS dispatch cycle SKIPPED — solar module not active for site-002")

    # Phase 130: Occupancy-driven HVAC + lighting control loop
    if settings.occupancy_poll_enabled:
        try:
            scheduler_service.add_occupancy_control_job(
                interval_seconds=settings.occupancy_poll_interval_seconds,
                site_id="site-002",
            )
            _logger.info(
                "✅ Occupancy control loop initialized (%ds interval)",
                settings.occupancy_poll_interval_seconds,
            )
        except Exception as e:
            _logger.warning(f"⚠️ Occupancy control loop initialization failed: {e}")

    # Phase 131: Email intake pipeline status
    if settings.email_intake_enabled:
        _logger.info("✅ Email intake pipeline ENABLED (Phase 131)")
    else:
        _logger.info("ℹ Email intake pipeline disabled (set EMAIL_INTAKE_ENABLED=true to activate)")

    # Phase 083: Recover crashed simulations from JSON store
    # Queries for any tasks marked as 'running' and resumes from checkpoint
    async def recover_crashed_simulations():
        """
        Recover simulations that were running when server crashed/restarted.
        Only the newest task with a valid checkpoint is re-queued.
        All other crashed tasks are marked stopped.
        """
        try:
            from app.services.simulation_store import get_simulation_store

            store = get_simulation_store("site-002")
            all_tasks = store.get_all_tasks()

            # Find tasks with status='running' (crashed)
            crashed = [(tid, tdata) for tid, tdata in all_tasks.items() if tdata.get("status") == "running"]

            if not crashed:
                _logger.info("No crashed simulations to recover")
                return

            _logger.info(f"Found {len(crashed)} crashed simulation(s) to recover...")

            # Sort by created_at descending — newest first
            crashed.sort(key=lambda x: x[1].get("created_at", ""), reverse=True)

            resumed_one = False
            for task_id, task in crashed:
                state_snapshot = task.get("state_snapshot")

                if not resumed_one and state_snapshot:
                    # Resume the newest task that has a checkpoint
                    try:
                        store.update_task_progress(task_id, {"status": "queued", "error_message": None})
                        days_simulated = state_snapshot.get("days_simulated", 0)
                        simulated_time = state_snapshot.get("simulated_time", "unknown")
                        _logger.info(
                            f"Queued recovery for task {task_id}: day {days_simulated}/365, time {simulated_time}"
                        )
                        resumed_one = True
                    except Exception as e:
                        _logger.error(f"Failed to queue recovery for task {task_id}: {e}")
                else:
                    # Mark all others as stopped
                    store.update_task_progress(task_id, {"status": "stopped"})
                    _logger.info(f"Marked stale task {task_id} as stopped")

        except Exception as e:
            _logger.error(f"Crash recovery initialization failed: {e}")

    # DEACTIVATE ALL SIMULATIONS ON STARTUP
    # Ensures clean state: no simulations auto-running after restart
    async def deactivate_all_simulations():
        """
        Deactivate all running and queued simulations on startup.
        This ensures clean state and prevents auto-resuming of simulations.
        """
        try:
            from datetime import datetime, timedelta
            from app.services.simulation_store import get_simulation_store

            store = get_simulation_store("site-002")
            all_tasks = store.get_all_tasks()
            cutoff_time = (datetime.utcnow() - timedelta(seconds=5)).isoformat()

            stopped_count = 0
            deactivated_count = 0

            for task_id, task_data in all_tasks.items():
                status = task_data.get("status")

                if status == "running":
                    store.update_task_progress(task_id, {"status": "stopped"})
                    stopped_count += 1

                elif status == "queued":
                    created_at = task_data.get("created_at", "")
                    if created_at < cutoff_time:
                        store.update_task_progress(task_id, {"status": "inactive"})
                        deactivated_count += 1

            if stopped_count:
                _logger.info(f"Stopped {stopped_count} running simulation(s)")
            if deactivated_count:
                _logger.info(f"Deactivated {deactivated_count} queued simulation(s) from before startup")
            if not stopped_count and not deactivated_count:
                _logger.info("No active simulations to deactivate")

        except Exception as e:
            _logger.error(f"Failed to deactivate simulations on startup: {e}")

    # === Site-002 Simulation Engine (gated by ENABLE_SITE002_SOURCE) ===
    if settings.site002_source_enabled:
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

        # Start simulation queue processor job
        # Polls JSON store for queued lifecycle simulations every 10s
        try:
            scheduler_service.add_simulation_queue_processor_job(interval_seconds=10)
            _logger.info("Simulation queue processor initialized (10s interval, JSON store)")
        except Exception as e:
            _logger.error(f"Simulation queue processor initialization failed: {e}", exc_info=True)

        # Auto-start sentinel_annual simulation for site-002 if none is active
        async def auto_start_sentinel_simulation():
            """Auto-queue sentinel_annual for site-002 if no active simulation exists."""
            try:
                import uuid
                from datetime import datetime

                from app.services.simulation_store import get_simulation_store

                store = get_simulation_store("site-002")
                all_tasks = store.get_all_tasks()

                # Check for any active simulation (running or queued)
                active = any(
                    t.get("status") in ("running", "queued") and t.get("simulation_type", "lifecycle") == "lifecycle"
                    for t in all_tasks.values()
                )

                if active:
                    _logger.info("Active simulation already exists, skipping auto-start")
                    return

                # Queue sentinel_annual for site-002
                task_id = str(uuid.uuid4())
                store.update_task_progress(
                    task_id,
                    {
                        "task_id": task_id,
                        "site_id": "site-002",
                        "scenario": "sentinel_annual",
                        "simulation_type": "lifecycle",
                        "status": "queued",
                        "progress_pct": 0,
                        "days_completed": 0,
                        "duration_minutes": 3650.0,
                        "created_at": datetime.utcnow().isoformat() + "Z",
                    },
                )

                _logger.info(f"Auto-queued sentinel_annual simulation: {task_id}")
            except Exception as e:
                _logger.error(f"Failed to auto-start sentinel_annual simulation: {e}")

        # Auto-resume: if crash recovery queued a simulation it will be picked up
        # by the queue processor. If nothing is queued/running, auto-start fresh.
        try:
            await auto_start_sentinel_simulation()
        except Exception as e:
            _logger.error(f"Error during sentinel auto-start: {e}")
    else:
        _logger.info("Site 002 data source disabled — simulation engine inactive")

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

    # Notification tasks cleanup (Phase 140)
    from app.services.notification_tasks import stop_notification_tasks

    await stop_notification_tasks()

    # n8n client cleanup (Phase 140)
    from app.services.n8n_service import shutdown_n8n_service

    await shutdown_n8n_service()

    # ServiceNow client cleanup (Phase 138)
    from app.services.servicenow_service import shutdown_servicenow_service

    await shutdown_servicenow_service()

    # Event bus cleanup (Phase 139)
    from app.services.event_bus import reset_event_bus

    reset_event_bus()

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
