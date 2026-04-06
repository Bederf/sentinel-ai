"""Startup and shutdown event handlers for FastAPI application.

This module contains all startup and shutdown logic, extracted from main.py
to improve maintainability and separation of concerns.
"""

import asyncio
import logging
import os
from contextlib import asynccontextmanager
from datetime import UTC, datetime, timedelta

from fastapi import FastAPI

from app.config.settings import apply_edge_mode_overrides, settings
from app.services.background_scheduler import scheduler_service
from app.services.health_simulation_service import health_simulation_service  # Supabase health simulation
from app.services.simbiot_service import simbiot_service  # SIMBIOT Concept Evolution connector

_logger = logging.getLogger("sentinel.startup")
_SIMULATION_RECOVERY_WINDOW = timedelta(minutes=30)


@asynccontextmanager
async def app_lifespan(app: FastAPI):
    """Lifespan adapter used by FastAPI app factory."""
    await startup_event(app)
    try:
        yield
    finally:
        await shutdown_event(app)


def _parse_task_timestamp(value: object) -> datetime | None:
    """Parse ISO timestamps from persisted simulation tasks."""
    if not value:
        return None
    try:
        parsed = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
    except (TypeError, ValueError):
        return None
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=UTC)
    return parsed.astimezone(UTC)


def _task_is_recoverable(task: dict) -> bool:
    """Only recover tasks that were active recently enough to represent a real restart."""
    timestamps = [
        _parse_task_timestamp(task.get("updated_at")),
        _parse_task_timestamp(task.get("created_at")),
    ]
    valid = [ts for ts in timestamps if ts is not None]
    if not valid:
        return False
    latest = max(valid)
    return latest >= (datetime.now(UTC) - _SIMULATION_RECOVERY_WINDOW)


async def startup_event(app: FastAPI) -> None:
    """Initialize background services on startup.

    This function is called when the FastAPI application starts up.
    It performs security checks, initializes services, and starts
    background tasks.
    """
    apply_edge_mode_overrides()
    testing_mode = os.getenv("TESTING", "").lower() == "true"

    # === Security startup checks ===

    _logger.info(f"Auth configuration: is_live_mode={settings.is_live_mode}")

    # Require JWT secret (C-2: Secure JWT signing)
    if not settings.jwt_secret_key and not settings.supabase_key:
        raise RuntimeError(
            "JWT_SECRET_KEY (or SUPABASE_KEY) must be set. "
            'Generate a 256-bit secret: python -c "import secrets; print(secrets.token_hex(32))" '
            "and set JWT_SECRET_KEY in your .env file."
        )

    # Warn about weak JWT secrets (less than 32 characters)
    _jwt_key = settings.jwt_secret_key or settings.supabase_key
    if _jwt_key and len(_jwt_key) < 32:
        _logger.warning(
            "JWT_SECRET_KEY is shorter than 32 characters — consider using a "
            '256-bit secret: python -c "import secrets; print(secrets.token_hex(32))"'
        )

    # Warn about missing dedicated JWT key
    if not settings.jwt_secret_key:
        _logger.warning(
            "JWT_SECRET_KEY not set - falling back to SUPABASE_KEY for JWT signing. "
            "Set JWT_SECRET_KEY for a dedicated signing secret."
        )

    # Bootstrap ADMIN_EMAILS into sentinel_users table
    _admin_emails_raw = os.environ.get("ADMIN_EMAILS", "").strip()
    if _admin_emails_raw:
        from app.database.repositories.user_repository import get_user_repository

        _user_repo = get_user_repository()
        _admin_list = [e.strip().lower() for e in _admin_emails_raw.split(",") if e.strip()]
        _user_repo.ensure_admin_emails(_admin_list)
        _logger.info("ADMIN_EMAILS bootstrap complete: %s", ", ".join(_admin_list))

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
            "║                                                        ║\n"
            "║  Real hardware reads are ACTIVE.                       ║\n"
            "║  Kill switch: POST /api/dispatch-optimizer/kill-switch  ║\n"
            "╚══════════════════════════════════════════════════════════╝",
            settings.modbus_bess_ip or "(not set)",
            "OPEN" if settings.aegis_bess_writer_enabled else "CLOSED",
        )

    # === EDGE MODE BANNER ===
    if settings.edge_mode:
        _logger.warning("🔧 EDGE MODE — ML training, simulation queue, AEGIS evidence disabled")

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

    _logger.info(
        "Runtime config loaded: version=%s environment=%s config_checksum=%s",
        settings.app_version,
        settings.environment,
        settings.config_checksum,
    )
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

    # Pre-warm embedding model + auto-load RAG knowledge in background
    def _warm_embedding_and_rag():
        try:
            from app.services.embedding_service import get_embedding_service

            svc = get_embedding_service()
            svc.warmup()
            _logger.info("✅ Embedding model pre-warmed")
        except Exception as e:
            _logger.warning(f"⚠️ Embedding model warmup failed (will load on first use): {e}")

        # Auto-ingest RAG knowledge if store is empty/sparse
        try:
            from app.services.rag_auto_loader import auto_load_rag

            auto_load_rag()
        except Exception as e:
            _logger.warning(f"⚠️ RAG auto-load failed (non-fatal): {e}")

    import threading

    threading.Thread(target=_warm_embedding_and_rag, daemon=True).start()

    # Initialize device manager with reference devices + building equipment
    from app.api.devices import startup_event as devices_startup

    try:
        await asyncio.wait_for(devices_startup(), timeout=15.0)
        _logger.info("✅ Device manager initialized successfully")
    except TimeoutError:
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

    # Dashboard generator subscriber — auto-generate on site onboard (Phase 141)
    from app.services.dashboard_gen_subscriber import register_dashboard_gen_subscribers

    register_dashboard_gen_subscribers()
    _logger.info("Dashboard generator subscribers registered")

    # Decision Moment subscribers — pre-warm crisis page cache on CRITICAL events (Phase 164)
    from app.services.event_bus_subscribers import register_decision_subscribers

    register_decision_subscribers()
    _logger.info("Decision moment subscribers registered")

    # Pre-warm decision cache for site-002 at startup (no cold-start 422 errors)
    try:
        from app.api.decisions import cache_decision_payload
        from app.services.decision_moment_aggregator import DecisionMomentAggregator

        aggregator = DecisionMomentAggregator()
        payload = aggregator.assemble(
            building_id="site-002",
            asset_id="S002-CHILLER-B1-001",
            severity="critical",
            fault_type="chiller_fault",
            trigger_reason="startup",
            current_hour=datetime.now().hour,
        )
        cache_decision_payload("site-002", payload.to_dict())
        _logger.info("✅ Decision cache pre-warmed for site-002")
    except Exception as e:
        _logger.warning(f"⚠️ Decision cache pre-warm failed (non-fatal): {e}")

    # Background notification tasks (escalation checker, digest scheduler)
    from app.services.notification_tasks import start_notification_tasks

    await start_notification_tasks()

    # Capture the main event loop for cross-thread scheduling (simulation tasks)
    scheduler_service.set_main_loop(asyncio.get_event_loop())

    # Start background scheduler
    scheduler_service.start()

    # NOTE: Fake audit data generator removed — audit trail must only contain
    # real control actions, not synthetic noise.

    # --- Sim-time-gated AI jobs ---
    # Jobs poll every 30 real seconds but only execute when enough *simulated*
    # time has elapsed (default: 4 sim-hours).  When no simulation is running,
    # they fall back to the real-time interval passed here.
    # At 10x sim speed: 4 sim-hours = 24 real seconds → fires ~6× per sim-day.

    # Start AI optimization analysis job (LLM-driven, sim-time gated)
    scheduler_service.add_optimization_analysis_job(interval_seconds=900)  # 15 min real-time fallback

    # Start prediction generation job (no LLM, can run more often)
    scheduler_service.add_prediction_generation_job(interval_seconds=300)  # 5 min

    # Start AI recommendation generation job (rule-based, sim-time gated)
    scheduler_service.add_recommendation_generation_job(interval_seconds=600)  # 10 min real-time fallback
    scheduler_service.add_ghost_room_monitor_job(interval_seconds=60)

    # Optional ESP32 MQTT listener for room-presence nodes
    from app.services.space_mqtt_listener import get_space_mqtt_listener

    await get_space_mqtt_listener().start()

    # Optional: Fuel tank MQTT listener
    try:
        from app.services.fuel_mqtt_listener import get_fuel_mqtt_listener

        await get_fuel_mqtt_listener().start()
    except Exception as e:
        _logger.warning(f"Fuel MQTT listener startup failed: {e}")

    # Fuel alert service — subscribes to fuel.* events for notifications (Phase 150)
    if settings.fuel_monitoring_enabled:
        try:
            from app.services.event_bus import get_event_bus
            from app.services.fuel_alert_service import get_fuel_alert_service

            _fuel_alert_svc = get_fuel_alert_service()
            _fuel_bus = get_event_bus()
            for _fuel_event_type in [
                "fuel.theft_alert",
                "fuel.leak_detected",
                "fuel.low_fuel",
                "fuel.temp_alert",
                "fuel.sensor_fault",
            ]:
                _fuel_bus.subscribe(_fuel_event_type, _fuel_alert_svc.handle_fuel_event)
            _logger.info("Fuel alert service registered on event bus (5 event types)")
        except Exception as e:
            _logger.warning(f"Fuel alert service registration failed: {e}")

    # Optional: Fuel event processor — subscribes to fuel.telemetry events (Phase 149)
    if settings.fuel_event_processor_enabled:
        try:
            from app.services.event_bus import get_event_bus
            from app.services.fuel_event_processor import get_fuel_event_processor

            processor = get_fuel_event_processor()
            bus = get_event_bus()
            bus.subscribe("fuel.telemetry", processor.handle_telemetry_event)
            _logger.info("Fuel event processor registered on event bus (fuel.telemetry)")
        except Exception as e:
            _logger.warning(f"Fuel event processor registration failed: {e}")

    # Start outcome verification job (checks executed recs after 30-min settling)
    scheduler_service.add_outcome_verification_job(interval_seconds=300)  # 5 min

    # Start integration sync job (runs every 15 minutes)
    # Updates last_sync_at on all active log sources so System Health dashboard stays fresh
    scheduler_service.add_integration_sync_job(interval_seconds=900)  # 15 minutes

    # Deterministic mode policy dry-run (runs every 5 minutes per site)
    # Observability only: evaluates stage thresholds and logs would-promote/demote actions
    from app.core.site_resolver import get_registered_site_ids as _get_site_ids

    _policy_site_ids = _get_site_ids()
    if _policy_site_ids:
        for _site_id in _policy_site_ids:
            try:
                scheduler_service.add_site_mode_policy_dry_run_job(interval_seconds=300, site_id=_site_id)
                _logger.info("Site mode policy dry-run initialized for %s", _site_id)
            except Exception as e:
                _logger.warning(f"Site mode policy dry-run initialization failed for {_site_id}: {e}")
    else:
        _logger.info("No registered buildings — skipping site mode policy dry-run")

    # Start demand-aware coordinator (runs every 5 minutes)
    # Phase 081: Cross-module peak demand management
    # Monitors NMD headroom and coordinates HVAC + BESS + energy actions for shaving
    scheduler_service.add_demand_aware_coordination_job(interval_seconds=300)  # 5 minutes

    # Initialize bounded autonomy system (Phase 9)
    # Autonomous decision engine with safety boundaries and escalation management
    import asyncio as aio  # Local import to avoid scoping issues

    from app.services.autonomous_decision_engine import autonomous_decision_engine
    from app.services.escalation_engine import escalation_engine
    from app.services.safety_boundary_service import safety_boundary_service

    try:
        # Wrap with timeout to prevent startup hang (10 second limit)
        await aio.wait_for(autonomous_decision_engine.initialize(load_seed_data=True), timeout=10.0)
        _logger.info("Autonomous decision engine initialized successfully")

        if not escalation_engine._initialized:
            await aio.wait_for(escalation_engine.initialize(), timeout=5.0)
            _logger.info("Escalation engine initialized successfully")

        if not safety_boundary_service._initialized:
            await aio.wait_for(safety_boundary_service.initialize(), timeout=5.0)
            _logger.info("Safety boundary service initialized successfully")
    except TimeoutError:
        _logger.warning("⏱️ Autonomous system initialization timed out - continuing without full initialization")
    except Exception as e:
        _logger.error(f"Failed to initialize autonomous system: {e}")

    # Start Sentry notification processing (runs every 30 seconds)
    # When equipment health drops to warning/critical, technicians receive Telegram notifications
    # This background job ensures notifications are sent promptly even if Sentry bot polling is delayed
    if hasattr(scheduler_service, "add_sentry_notification_job"):
        scheduler_service.add_sentry_notification_job(interval_seconds=30)  # 30 seconds

    # Phase 176: Outlook calendar polling — creates Visit records from external-attendee events
    if hasattr(scheduler_service, "add_outlook_polling_job"):
        scheduler_service.add_outlook_polling_job(interval_minutes=5)
        _logger.info("Outlook calendar polling job initialized (every 5 minutes)")

    # Phase 177: Graph webhook subscription renewal
    if hasattr(scheduler_service, "add_graph_subscription_renewal_job"):
        scheduler_service.add_graph_subscription_renewal_job(interval_hours=1)
        _logger.info("Graph subscription renewal job initialized (every 1 hour)")

    # Phase 178-06: MRI Evolution polling scheduler (every 15 minutes)
    from app.api.mri_connector import start_scheduler as start_mri_scheduler

    start_mri_scheduler()

    # Phase 177: Ensure Graph subscription exists on startup
    try:
        from app.services.graph_subscription_service import graph_subscription_service

        async def _ensure_graph_subscription():
            sub = await graph_subscription_service.get_or_create_subscription()
            if sub:
                _logger.info(
                    "Graph subscription active: id=%s expires=%s", sub.subscription_id, sub.expiration_datetime
                )
            else:
                _logger.warning(
                    "Graph subscription not created — set GRAPH_WEBHOOK_URL, "
                    "OUTLOOK_CLIENT_ID, OUTLOOK_CLIENT_SECRET, OUTLOOK_TENANT_ID"
                )

        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        try:
            loop.run_until_complete(_ensure_graph_subscription())
        finally:
            loop.close()
    except Exception as e:
        _logger.warning("Graph subscription startup check failed: %s", e)

    # ML background training jobs — gated by ML_BACKGROUND_TRAINING_ENABLED
    # Disabled by default: training is CPU-intensive and starves the API on constrained VPS
    if settings.edge_mode:
        _logger.info("ℹ️ ML training jobs disabled (EDGE_MODE=true)")
    elif settings.ml_background_training_enabled:
        try:
            scheduler_service.add_ml_retraining_job(interval_seconds=86400)  # 24 hours
            _logger.info("✅ ML model retraining job initialized - checks daily for stale/underperforming models")
        except Exception as e:
            _logger.warning(f"⚠️ ML retraining job initialization failed: {e}")

        try:
            scheduler_service.add_drift_detection_job(interval_seconds=3600)  # 1 hour
            _logger.info("✅ Drift detection job initialized - monitors hourly for model/data drift")
        except Exception as e:
            _logger.warning(f"⚠️ Drift detection job initialization failed: {e}")
    else:
        _logger.info("⏸️ ML background training disabled (ML_BACKGROUND_TRAINING_ENABLED=false)")

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

    # Feedback-driven retraining — also gated by ML_BACKGROUND_TRAINING_ENABLED
    if not settings.edge_mode and settings.ml_background_training_enabled:
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

    # Daily AI cost report email (23:55 every day)
    try:
        scheduler_service.add_ai_cost_report_job()
        _logger.info("✅ Daily AI cost report email job initialized (23:55 → info@sentinel-ai.co.za)")
    except Exception as e:
        _logger.warning(f"⚠️ AI cost report job initialization failed: {e}")

    # Ensure all sites have the 15 mandatory base modules (Phase 142)
    try:
        from app.services.module_registry_service import module_registry as _mod_registry

        _seeded = _mod_registry.ensure_base_modules_all_sites()
        if _seeded:
            _logger.info(f"✅ Base module auto-seed: backfilled modules for {len(_seeded)} site(s)")
        else:
            _logger.info("✅ Base modules verified for all sites")
    except Exception as e:
        _logger.warning(f"⚠️ Base module auto-seed failed: {e}")

    # AEGIS Phase 0 — dispatch cycle (5 min) + daily evidence collector (24h)
    # Gated by solar module being active per site (AEGIS is the Solar/BESS dispatch optimizer)
    _aegis_site_ids = _get_site_ids()
    _aegis_any_started = False
    for _site_id in _aegis_site_ids:
        _aegis_enabled = False
        try:
            from app.services.module_registry_service import ModuleRegistryService

            _registry = ModuleRegistryService()
            _aegis_enabled = _registry.is_module_active(_site_id, "solar")
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
                        for m in _mods_data.get(_site_id, {}).get("active_modules", [])
                    )
            except Exception:
                pass

        if _aegis_enabled:
            try:
                scheduler_service.add_aegis_cycle_job(interval_seconds=300, site_id=_site_id)
                _logger.info("AEGIS dispatch cycle job initialized for %s (5 min interval)", _site_id)
            except Exception as e:
                _logger.warning(f"AEGIS cycle job initialization failed for {_site_id}: {e}")

            if not settings.edge_mode:
                try:
                    scheduler_service.add_aegis_evidence_collector_job(interval_seconds=86400, site_id=_site_id)
                    _logger.info("AEGIS evidence collector job initialized for %s (24h interval)", _site_id)
                except Exception as e:
                    _logger.warning(f"AEGIS evidence collector job initialization failed for {_site_id}: {e}")
            else:
                _logger.info("ℹ️ AEGIS evidence collector disabled for %s (EDGE_MODE=true)", _site_id)
            _aegis_any_started = True

    if not _aegis_any_started:
        _logger.info("AEGIS dispatch cycle SKIPPED — no sites with active solar module")

    # BESS dispatch consumer — drained via AEGIS cycle job (add_aegis_cycle_job)
    # note: add_bess_dispatch_job not yet implemented — commented out pending bridge integration
    # try:
    #     from app.core.site_resolver import get_registered_site_ids as _bess_site_ids_fn
    #     for _site_id in _bess_site_ids_fn() or []:
    #         scheduler_service.add_bess_dispatch_job(interval_seconds=60, site_id=_site_id)
    #     _logger.info("✅ BESS dispatch consumer initialized (60s interval, DRY_RUN by default)")
    # except Exception as e:
    #     _logger.warning("⚠️ BESS dispatch consumer initialization failed: %s", e)

    # Phase 130: Occupancy-driven HVAC + lighting control loop
    if settings.occupancy_poll_enabled:
        _occ_site_ids = _get_site_ids()
        if _occ_site_ids:
            for _site_id in _occ_site_ids:
                try:
                    scheduler_service.add_occupancy_control_job(
                        interval_seconds=settings.occupancy_poll_interval_seconds,
                        site_id=_site_id,
                    )
                    _logger.info(
                        "Occupancy control loop initialized for %s (%ds interval)",
                        _site_id,
                        settings.occupancy_poll_interval_seconds,
                    )
                except Exception as e:
                    _logger.warning(f"Occupancy control loop initialization failed for {_site_id}: {e}")
        else:
            _logger.info("No registered buildings — skipping occupancy control loop")

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
        Only the newest task with a valid checkpoint is re-queued per site.
        All other crashed tasks are marked stopped.
        """
        try:
            from app.services.simulation_store import get_simulation_store

            for _sim_site_id in _get_site_ids():
                store = get_simulation_store(_sim_site_id)
                all_tasks = store.get_all_tasks()

                # Find tasks with status='running' (crashed)
                crashed = [(tid, tdata) for tid, tdata in all_tasks.items() if tdata.get("status") == "running"]

                if not crashed:
                    continue

                _logger.info("Found %d crashed simulation(s) to recover for %s", len(crashed), _sim_site_id)

                # Sort by created_at descending — newest first
                crashed.sort(key=lambda x: x[1].get("created_at", ""), reverse=True)

                resumed_one = False
                for task_id, task in crashed:
                    state_snapshot = task.get("state_snapshot")

                    if not _task_is_recoverable(task):
                        store.update_task_progress(task_id, {"status": "stopped"})
                        _logger.info("Marked stale crashed task %s as stopped", task_id)
                        continue

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

            if not _get_site_ids():
                _logger.info("No registered buildings — skipping crash recovery")

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

            for _sim_site_id in _get_site_ids():
                store = get_simulation_store(_sim_site_id)
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
                    _logger.info("Stopped %d running simulation(s) for %s", stopped_count, _sim_site_id)
                if deactivated_count:
                    _logger.info(
                        "Deactivated %d queued simulation(s) from before startup for %s",
                        deactivated_count,
                        _sim_site_id,
                    )

            if not _get_site_ids():
                _logger.info("No registered buildings — skipping simulation deactivation")

            # Re-queue the best in-progress task per site so the queue processor
            # resumes from the checkpoint on next tick (crash recovery path).
            for _sim_site_id in _get_site_ids():
                store = get_simulation_store(_sim_site_id)
                all_tasks = store.get_all_tasks()

                best_task_id = None
                best_days = 0
                for task_id, task_data in all_tasks.items():
                    if (
                        task_data.get("status") == "stopped"
                        and task_data.get("state_snapshot")
                        and (task_data.get("days_completed") or 0) > best_days
                    ):
                        best_days = task_data["days_completed"]
                        best_task_id = task_id

                if best_task_id:
                    store.update_task_progress(best_task_id, {"status": "queued"})
                    _logger.info(
                        "Re-queued simulation %s for %s (checkpoint day %d/365)",
                        best_task_id,
                        _sim_site_id,
                        best_days,
                    )

        except Exception as e:
            _logger.error(f"Failed to deactivate simulations on startup: {e}")

    # === Simulation Engine (gated by ENABLE_SITE002_SOURCE) ===
    # Check persistent "simulationStopped" flag — if admin stopped simulation via Settings,
    # do not auto-start on restart.
    _simulation_stopped = False
    try:
        import json as _json
        from pathlib import Path as _Path

        _settings_path = _Path(__file__).parent.parent / "data" / "settings.json"
        if _settings_path.exists():
            _sim_settings = _json.loads(_settings_path.read_text())
            _simulation_stopped = _sim_settings.get("simulationStopped", False)
    except Exception:
        pass

    if _simulation_stopped:
        _logger.info("Simulation stopped by admin (simulationStopped=true in settings.json) — skipping auto-start")

    if settings.site002_source_enabled and not _simulation_stopped and not settings.edge_mode:
        # Keep the API responsive on restart by deactivating stale persisted
        # simulation tasks instead of auto-resuming or auto-starting them.
        if not testing_mode:
            try:
                await deactivate_all_simulations()
            except Exception as e:
                _logger.error(f"Error during startup simulation deactivation: {e}")

        # Manual lifecycle start endpoints still rely on the queue processor.
        try:
            scheduler_service.add_simulation_queue_processor_job(interval_seconds=10)
            _logger.info("Simulation queue processor initialized (10s interval, manual queue only)")
        except Exception as e:
            _logger.error(f"Simulation queue processor initialization failed: {e}", exc_info=True)

        _logger.info("Lifecycle simulations are manual-start only on backend startup")
    else:
        if settings.edge_mode and settings.site002_source_enabled:
            _logger.info("ℹ️ Simulation queue disabled (EDGE_MODE=true)")
        else:
            _logger.info("Site 002 data source disabled — simulation engine inactive")

    # Shadow mode bridge polling — runs when simulation engine is disabled.
    # Polls the live bridge (10.99.0.1:8080) every 5 minutes and feeds data to
    # SentinelMLFeeder so ML models stay current with real site telemetry.
    if not settings.site002_source_enabled and not settings.edge_mode:
        try:
            scheduler_service.add_shadow_mode_polling_job(interval_seconds=300, site_id="site-002")
            _logger.info("Shadow mode bridge polling initialized (5min interval)")
        except Exception as e:
            _logger.error(f"Shadow mode polling initialization failed: {e}", exc_info=True)

        # Phase 179: Document MRI sync — polls Concept API every N hours (default 4)
        try:
            scheduler_service.add_document_mri_sync_job(
                interval_hours=settings.document_sync_interval_hours,
                site_id="site-002",
            )
            _logger.info(
                "Document MRI sync job initialized (every %d hours)",
                settings.document_sync_interval_hours,
            )
        except Exception as e:
            _logger.error(f"Document MRI sync initialization failed: {e}", exc_info=True)

    # Phase 182-02: Compiler queue worker — processes pending compiler_queue entries (every 5 min)
    try:
        scheduler_service.add_compiler_worker_job(interval_minutes=5)
        _logger.info("Compiler queue worker job initialized (5 min interval)")
    except Exception as e:
        _logger.error(f"Compiler worker job initialization failed: {e}", exc_info=True)

    # Anomaly model weekly retraining — trains Isolation Forest on zone temp + HVAC power
    # data every Sunday at 02:00. Works with as little as 72h of data (vs LSTM's 500h).
    try:
        scheduler_service.add_anomaly_weekly_retrain_job(interval_hours=168)
        _logger.info("Anomaly weekly retrain job initialized (weekly at 02:00)")
    except Exception as e:
        _logger.error(f"Anomaly weekly retrain job initialization failed: {e}", exc_info=True)

    # Sync ML model registry JSON → ml_models Supabase table (best-effort)
    try:
        import concurrent.futures as _cf

        from app.services.ml_registry_sync import sync_registry_to_db

        _cf.ThreadPoolExecutor(max_workers=1).submit(sync_registry_to_db)
        _logger.info("ML registry sync queued (background)")
    except Exception as e:
        _logger.warning(f"ML registry sync skipped: {e}")

    # System health snapshot job (every 5 minutes)
    scheduler_service.add_health_snapshot_job(interval_seconds=300)

    # Autoencoder anomaly detection — note: add_anomaly_detection_job not yet implemented
    # pending bridge integration; commented out to eliminate warning
    # try:
    #     from app.core.site_resolver import get_registered_site_ids as _anomaly_site_ids_fn
    #     for _site_id in _anomaly_site_ids_fn() or []:
    #         scheduler_service.add_anomaly_detection_job(interval_seconds=1800, site_id=_site_id)
    #     _logger.info("✅ Anomaly detection jobs initialized (30 min interval)")
    # except Exception as e:
    #     _logger.warning("⚠️ Anomaly detection job initialization failed: %s", e)

    # Error auto-resolution job (daily) - resolves errors if component healthy for 24+ hours
    scheduler_service.add_error_auto_resolve_job(interval_seconds=86400)

    # Database archival (daily) - removes resolved alerts/predictions older than 90 days
    scheduler_service.add_db_archival_job(interval_seconds=86400)

    # Audit log archival (monthly) - archives and deletes audit logs older than 30 days
    # Implements AUDIT-001 control: immutable audit trail with atomic delete on success
    # Protected by asyncio mutex to prevent concurrent archival races (Phase 168-03)
    try:
        from app.services.audit_logger import AuditLogger

        audit_logger = AuditLogger()
        asyncio.create_task(audit_logger.audit_archival_job(interval_days=30))
        _logger.info("✅ Audit log archival job initialized (30-day interval, runs monthly)")
    except Exception as e:
        _logger.warning(f"⚠️ Audit archival job initialization failed: {e}")

    # Space Occupancy POC — sensor health monitor (every 60 seconds)
    try:
        scheduler_service.add_space_sensor_health_job(interval_seconds=60, site_id="FLN02")
        _logger.info("Space sensor health monitor initialized for FLN02 (60s interval)")
    except Exception as e:
        _logger.warning(f"Space sensor health monitor initialization failed: {e}")

    # Focus room relay reconciliation (every 30 seconds)
    try:
        scheduler_service.add_focus_relay_reconcile_job(interval_seconds=30)
        _logger.info("Focus relay reconcile initialized (30s interval)")
    except Exception as e:
        _logger.warning(f"Focus relay reconcile initialization failed: {e}")

    # Event Intelligence evaluation (every 2 minutes)
    # Converts raw telemetry into structured operational events (temp deviations,
    # energy spikes, sensor failures, comfort violations, ML anomalies).
    # Read-only: detects conditions and emits to event bus. No control actions.
    try:
        scheduler_service.add_event_intelligence_job(interval_seconds=120)
        _logger.info("Event intelligence job initialized (2 min interval)")
    except Exception as e:
        _logger.warning(f"Event intelligence job initialization failed: {e}")

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

    # SIMBIOT Concept Evolution connector (MRI Evolution / CAFM work-order integration)
    # Only initializes when CAFM subscription credentials are fully configured.
    # BMS data comes through the bridge; this connector is for SIMBIOT -> MRI WO creation only.
    if (
        settings.simbiot_api_url
        and settings.simbiot_api_key
        and getattr(settings, "simbiot_subscription_key", "")
        and getattr(settings, "simbiot_customer_site_code", "")
    ):
        try:
            from simbiot_concept import ConceptConfig

            config = ConceptConfig(
                api_base_url=settings.simbiot_api_url,
                api_key=settings.simbiot_api_key,
                api_username=settings.simbiot_username,
                api_password=settings.simbiot_password,
                subscription_key=settings.simbiot_subscription_key,
                customer_site_code=settings.simbiot_customer_site_code,
                segments=getattr(settings, "simbiot_segments", []) or None,
                severity_mapping=getattr(settings, "simbiot_severity_mapping", {}) or None,
                trade_mapping=getattr(settings, "simbiot_trade_mapping", {}) or None,
            )
            await simbiot_service.initialise(config)
            print(f"[SIMBIOT] Connected to {settings.simbiot_api_url}")
        except Exception as e:
            print(f"[SIMBIOT] Failed to initialize: {e}")
    else:
        print("[SIMBIOT] CAFM credentials not configured — connector skipped (BMS bridge operates independently)")


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

    from app.services.space_mqtt_listener import get_space_mqtt_listener

    await get_space_mqtt_listener().stop()

    try:
        from app.services.fuel_mqtt_listener import get_fuel_mqtt_listener

        await get_fuel_mqtt_listener().stop()
    except Exception:
        pass

    # Event bus cleanup (Phase 139)
    from app.services.event_bus import reset_event_bus

    reset_event_bus()

    # Phase 178-06: MRI Evolution polling scheduler shutdown
    from app.api.mri_connector import stop_scheduler as stop_mri_scheduler

    stop_mri_scheduler()

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
