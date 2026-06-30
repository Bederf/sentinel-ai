"""Startup and shutdown event handlers for FastAPI application.

This module contains all startup and shutdown logic, extracted from main.py
to improve maintainability and separation of concerns.
"""

import asyncio
import contextlib
import logging
import os
from contextlib import asynccontextmanager
from datetime import UTC, datetime, timedelta

from fastapi import FastAPI

from app.config.settings import apply_edge_mode_overrides, settings
from app.services.background_scheduler import scheduler_service
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
        with contextlib.suppress(asyncio.CancelledError):
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


async def startup_event(_: FastAPI) -> None:
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

    # === Required Site Configuration ===
    _logger.info(
        "✓ Site config: site_id=%s, plant=%s, building=%s",
        settings.space_default_site_id,
        settings.plant_site_id,
        settings.plant_building_name,
    )

    # === Run database migrations (fail-fast) ===
    if os.getenv("MIGRATION_SKIP", "").lower() != "true":
        from app.migrations.runner import run_pending_migrations

        try:
            dry_run = os.getenv("MIGRATION_DRY_RUN", "false").lower() == "true"
            applied = run_pending_migrations(dry_run=dry_run)
            if dry_run:
                _logger.warning("MIGRATION DRY RUN — no files were applied")
            else:
                _logger.info("Migrations applied: %s", applied if applied else "none (all locked)")
        except Exception as e:
            _logger.critical("Migration failed: %s. Halting startup.", e)
            raise RuntimeError(f"Migration failure: {e}") from e

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

    # Warm token blacklist local cache from Redis (Phase 61.9)
    # Ensures process restart doesn't create revocation gap for already-revoked tokens
    from app.services.token_blacklist_service import token_blacklist

    try:
        warm_result = await token_blacklist.warm_cache()
        if warm_result > 0:
            _logger.info(f"Token blacklist cache warmed: {warm_result} entries")
    except Exception as e:
        _logger.warning(f"Token blacklist warm_cache failed (non-fatal): {e}")

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

    _logger.warning("SHADOW_DEBUG: about to start notification tasks")
    await start_notification_tasks()
    _logger.warning("SHADOW_DEBUG: notification tasks started")

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
    scheduler_service.add_optimization_analysis_job(interval_seconds=1800)  # 30 min real-time fallback

    # Start prediction generation job (no LLM, can run more often)
    scheduler_service.add_prediction_generation_job(interval_seconds=300)  # 5 min

    # Start AI recommendation generation job (rule-based, sim-time gated)
    scheduler_service.add_recommendation_generation_job(interval_seconds=1800)  # 30 min

    # Recommendation lifecycle: expire stale + dedup duplicates (every 6h)
    scheduler_service.add_recommendation_expiry_job(interval_seconds=21600)  # 6h

    # Recommendation processing: route pending recs through tier engine, handle
    # Tier 2 approval requests / Tier 3 auto-execution, fill outcome={} placeholders.
    # Without this job, recommendations expire after 48h before any outcome is written.
    scheduler_service.add_recommendation_processing_job(interval_seconds=300)  # 5 min

    scheduler_service.add_ghost_room_monitor_job(interval_seconds=60)
    if hasattr(scheduler_service, "add_focus_overstay_check_job"):
        _logger.warning("REGISTERING: Focus overstay check job (every 2 min)")
        scheduler_service.add_focus_overstay_check_job(interval_seconds=120)  # Every 2 minutes
        _logger.warning("REGISTERED: Focus overstay check job")
    else:
        _logger.error("MISSING: add_focus_overstay_check_job method not found")

    # Phase 207 SLA monitoring — milestone timer (fires every 5 min)
    scheduler_service.add_milestone_timer_job(interval_seconds=300)
    scheduler_service.add_wo_sla_breach_job(interval_seconds=300)

    # Phase 207 fire pump compliance — daily check
    scheduler_service.add_fire_pump_compliance_job(interval_seconds=86400)

    # Phase 209: RAG documentation sync — every 12h, incrementally updates changed docs
    scheduler_service.add_rag_doc_sync_job(interval_hours=12)

    # ESP32 MQTT listener for room-presence nodes (LD2410C radar)
    from app.services.space_mqtt_listener import get_space_mqtt_listener

    _logger.warning("SHADOW_DEBUG: about to start Space MQTT listener")
    await get_space_mqtt_listener().start()
    _logger.warning("SHADOW_DEBUG: Space MQTT listener started")

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

    # Phase 189: Email intake IMAP polling (every 5 minutes)
    # Warns at startup if IMAP is not configured (poller skips silently when unconfigured)
    if not settings.intelligence_intake_imap_host:
        _logger.warning("[EmailIntake] intelligence_intake_imap_host not set — email intake polling disabled")
    else:
        if hasattr(scheduler_service, "add_email_intake_poll_job"):
            scheduler_service.add_email_intake_poll_job(interval_minutes=5)
            _logger.info("Email intake IMAP polling job initialized (every 5 minutes)")

    # Rooms mailbox IMAP poller (replaces n8n block-booking email ingest)
    if not settings.rooms_imap_host:
        _logger.warning("[RoomsEmail] rooms_imap_host not set — rooms email intake polling disabled")
    elif hasattr(scheduler_service, "add_rooms_email_intake_poll_job"):
        scheduler_service.add_rooms_email_intake_poll_job(interval_minutes=5)
        _logger.info("[RoomsEmail] Rooms email IMAP polling job initialized (every 5 minutes)")
    else:
        _logger.warning("[RoomsEmail] scheduler_service missing add_rooms_email_intake_poll_job method")

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

        sub = await graph_subscription_service.get_or_create_subscription()
        if sub:
            _logger.info("Graph subscription active: id=%s expires=%s", sub.subscription_id, sub.expiration_datetime)
        else:
            _logger.warning(
                "Graph subscription not created — set GRAPH_WEBHOOK_URL, "
                "OUTLOOK_CLIENT_ID, OUTLOOK_CLIENT_SECRET, OUTLOOK_TENANT_ID"
            )
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

    # Site peak demand refresh — keeps per-site HVAC gating thresholds grounded
    try:
        scheduler_service.add_site_peak_demand_refresh_job(interval_seconds=21600, lookback_days=90)  # 6 hours
        _logger.info("✅ Site peak demand refresh job initialized - updates site-specific HVAC thresholds")
    except Exception as e:
        _logger.warning(f"⚠️ Site peak demand refresh job initialization failed: {e}")

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

    # Supabase SQL table retention (POPIA S14 — ML data 10d, snapshots 30d, audit 5y)
    if settings.popia_retention_enabled:
        try:
            scheduler_service.add_supabase_retention_job(interval_seconds=settings.popia_retention_job_interval_seconds)
            _logger.info("✅ Supabase SQL retention enforcement job initialized (cron: daily 02:00 UTC)")
        except Exception as e:
            _logger.warning(f"⚠️ Supabase retention job initialization failed: {e}")

        # Catch-up run: if last enforcement log is older than 24h, run immediately on startup.
        # Prevents data piling up when the process restarts frequently.
        try:
            import psycopg2
            from datetime import UTC, datetime, timedelta

            conn = psycopg2.connect(
                host="127.0.0.1", port=55322, dbname="postgres", user="postgres", password="postgres"
            )
            with conn.cursor() as cur:
                cur.execute("SELECT MAX(executed_at) FROM retention_enforcement_log WHERE dry_run = false")
                row = cur.fetchone()
            conn.close()
            last_run = row[0] if row and row[0] else None
            if last_run is None or (datetime.now(UTC) - last_run.replace(tzinfo=UTC)) > timedelta(hours=24):
                _logger.info("🔄 Retention catch-up: last run >24h ago — running Supabase retention now")
                scheduler_service._run_supabase_retention_enforcement()
            else:
                _logger.info("✅ Retention catch-up: last run recent (%s UTC) — skipping", last_run.isoformat())
        except Exception as e:
            _logger.warning(f"⚠️ Retention catch-up check failed: {e}")

    # Telemetry tiered aggregation (tier1->tier2 nightly, tier2->tier3 weekly)
    try:
        scheduler_service.add_tier1_tier2_aggregation_job()
        _logger.info("✅ Tier1->Tier2 telemetry aggregation job initialized (daily 00:00 UTC)")
    except Exception as e:
        _logger.warning(f"⚠️ Tier1->Tier2 aggregation job initialization failed: {e}")

    try:
        scheduler_service.add_tier2_tier3_aggregation_job()
        _logger.info("✅ Tier2->Tier3 telemetry aggregation job initialized (weekly Sun 01:00 UTC)")
    except Exception as e:
        _logger.warning(f"⚠️ Tier2->Tier3 aggregation job initialization failed: {e}")

    # Periodic AI usage flush (every 5 min — bounds data loss on ungraceful kill)
    try:
        scheduler_service.add_ai_usage_flush_job(interval_minutes=5)
        _logger.info("✅ AI usage flush job initialized (5min interval)")
    except Exception as e:
        _logger.warning(f"⚠️ AI usage flush job initialization failed: {e}")

    # Daily AI cost report email (23:55 every day)
    try:
        scheduler_service.add_ai_cost_report_job()
        _logger.info("✅ Daily AI cost report email job initialized (23:55 → info@sentinel-ai.co.za)")
    except Exception as e:
        _logger.warning(f"⚠️ AI cost report job initialization failed: {e}")

    # Weekly Sentry staff/tech feedback digest email (Monday 07:00 SAST)
    try:
        scheduler_service.add_sentry_feedback_digest_job()
        _logger.info("✅ Sentry feedback digest job initialized (Monday 07:00 SAST → info@sentinel-ai.co.za)")
    except Exception as e:
        _logger.warning(f"⚠️ Sentry feedback digest job initialization failed: {e}")

    # LLM Judge evaluation (every 60 min, INTERIM — replace with iDNa AI Testing Framework)
    try:
        scheduler_service.add_llm_judge_job()
        _logger.info("✅ LLM judge evaluation job initialized (top of every hour)")
    except Exception as e:
        _logger.warning(f"⚠️ LLM judge job initialization failed: {e}")

    # Daily health sweep — generates recommendations for all equipment below health threshold
    # Runs weekdays at 08:00 SAST (06:00 UTC). Bypasses occupancy gate to catch issues outside hours.
    try:
        scheduler_service.add_daily_health_sweep_job()
        _logger.info("✅ Daily health sweep job initialized (06:00 UTC Mon-Fri = 08:00 SAST)")
    except Exception as e:
        _logger.warning(f"⚠️ Daily health sweep job initialization failed: {e}")

    # Orphan alert cleanup — purges stale fault alerts every 30 min to prevent alert-table pollution
    try:
        scheduler_service.add_orphan_alert_cleanup_job(interval_minutes=30)
        _logger.info("✅ Orphan alert cleanup job initialized (every 30 min)")
    except Exception as e:
        _logger.warning(f"⚠️ Orphan alert cleanup job initialization failed: {e}")

    # Morning recommendation digest — top 5 pending by severity, sent to FM Telegram at 07:00 SAST Mon-Fri
    try:
        scheduler_service.add_recommendation_digest_job()
        _logger.info("✅ Recommendation digest job initialized (07:00 SAST Mon-Fri → FM Telegram)")
    except Exception as e:
        _logger.warning(f"⚠️ Recommendation digest job initialization failed: {e}")

    # Overnight advisory email fallback — email FM when high/critical advisory unacknowledged >2h
    try:
        scheduler_service.add_overnight_advisory_email_fallback_job()
        _logger.info("✅ Overnight advisory email fallback initialized (every 30 min, after-hours only)")
    except Exception as e:
        _logger.warning(f"⚠️ Overnight advisory email fallback initialization failed: {e}")

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

    # Phase 186: Seed settings admin password from Supabase
    def _ensure_settings_password():
        """Seed default admin password hash if settings_admin_password is not configured.

        Phase 186: Supabase-backed settings password (replaces ADMIN_PIN_HASH env var).
        Default PIN: SENTINEL_ADMIN — user must change it via Settings UI after first login.
        """
        try:
            import bcrypt

            from app.database.repositories.system_settings_repository import SystemSettingsRepository

            repo = SystemSettingsRepository()
            existing = repo.get_value("settings_admin_password")
            if existing:
                _logger.info("settings_admin_password already configured")
                return

            default_pin = "SENTINEL_ADMIN"
            default_hash = bcrypt.hashpw(default_pin.encode("utf-8"), bcrypt.gensalt()).decode("utf-8")

            repo.upsert_value(
                key="settings_admin_password",
                value=default_hash,
                category="security",
                description="Bcrypt hash of the admin settings password. Change from default after first use.",
                data_type="string",
                is_public=False,
                is_editable=True,
                updated_by="system",
            )
            _logger.critical(
                "\n"
                "╔══════════════════════════════════════════════════════════╗\n"
                "║         ⚠️  DEFAULT ADMIN PASSWORD ACTIVE  ⚠️          ║\n"
                "║  settings_admin_password seeded with default PIN       ║\n"
                "║  Change it via Settings → Unlock → Update               ║\n"
                "╚══════════════════════════════════════════════════════════╝\n"
            )
        except Exception as exc:
            _logger.warning(f"Failed to seed settings_admin_password: {exc}")

    _ensure_settings_password()

    def _validate_block_booking_config():
        """Validate block booking configuration at startup."""
        if not settings.block_booking_enabled:
            _logger.info("ℹ Block booking detection disabled")
            return
        import json
        from pathlib import Path

        config_path = Path(__file__).parent.parent / "data" / "block_booking_sites.json"
        if not config_path.exists():
            _logger.warning("block_booking_sites.json not found — block booking will use env var defaults")
            return
        try:
            data = json.loads(config_path.read_text())
            if not data:
                _logger.warning("block_booking_sites.json is empty")
                return
            _logger.info("✅ Block booking detection enabled (%d sites configured)", len(data))
        except Exception as exc:
            _logger.warning("Failed to parse block_booking_sites.json: %s", exc)

    _validate_block_booking_config()

    # === Shadow Mode Bridge Polling (only active bridge integration) ===
    # ENABLE_SITE002_SOURCE was deprecated 2026-06 — simulator removed.
    # Shadow polling runs independently, always-on for live site-002 bridge.
    # Simulation auto-start block was removed with simulator.

    # Shadow mode bridge polling — runs whenever edge mode is disabled.
    # Polls the live bridge (10.99.0.1:8080) every 5 minutes and feeds data to
    # SentinelMLFeeder so ML models stay current with real site telemetry.
    # ML training runs in ALL modes (shadow, advisory, supervised, auto) continuously.
    # Note: This runs INDEPENDENTLY of simulation settings — it's for live bridge data.
    if not settings.edge_mode:
        _logger.warning("SHADOW_MODE_DEBUG: condition TRUE, about to add shadow mode job")
        try:
            scheduler_service.add_shadow_mode_polling_job(interval_seconds=300, site_id="site-002")
            _logger.info("Shadow mode bridge polling initialized (5min interval)")
        except Exception as e:
            _logger.error(f"Shadow mode polling initialization failed: {e}", exc_info=True)

        # BACnet discovery polling — register one job per enabled bridge adapter.
        # Queries the bridge object catalog every 6 hours and compares against
        # known equipment records. New/missing devices are logged for review.
        # Uses the same dynamic site iteration pattern as the poll coordinator.
        try:
            from app.database.supabase_client import get_supabase_client

            _sb_bacnet = get_supabase_client()
            _bridge_sites = (
                _sb_bacnet.table("site_adapter_config")
                .select("site_id, connection_config")
                .eq("protocol", "bridge")
                .eq("enabled", True)
                .execute()
            )
            _bacnet_registered = 0
            for _row in _bridge_sites.data or []:
                _cfg = _row.get("connection_config", {})
                if _cfg.get("base_url") and _cfg.get("token"):
                    scheduler_service.add_bacnet_discovery_polling_job(
                        interval_seconds=21600,  # 6 hours
                        site_id=_row["site_id"],
                    )
                    _bacnet_registered += 1
            if _bacnet_registered:
                _logger.info("BACnet discovery polling initialized for %d site(s) (6h interval)", _bacnet_registered)
        except Exception as e:
            _logger.error(f"BACnet discovery polling initialization failed: {e}", exc_info=True)

        # Phase promotion evaluator — hourly Trust Ladder promotion check
        try:
            scheduler_service.add_phase_promotion_job(interval_hours=1)
            _logger.info("✅ Phase promotion evaluator initialized (hourly, coalesce=True)")
        except Exception as e:
            _logger.error(f"⚠️ Phase promotion evaluator initialization failed: {e}")

        # IPMVP data sync — hourly fetch of energy, OAT, events, occupancy, tariff
        try:
            scheduler_service.add_ipmvp_sync_job(interval_hours=1)
            _logger.info("IPMVP data sync initialized (hourly)")
        except Exception as e:
            _logger.warning("IPMVP data sync initialization failed: %s", e)

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

    # Equipment health snapshot job (every 15 minutes) — first run ~30s after registration
    # (next_run_time=30s is set inside add_equipment_health_snapshot_job)
    try:
        scheduler_service.add_equipment_health_snapshot_job(interval_minutes=15)
        _logger.info("Equipment health snapshot job registered")
    except Exception as e:
        _logger.error(f"Equipment health snapshot job failed: {e}", exc_info=True)

    # Adapter health monitor — SLI Tier 1: checks all BACnet/Niagara/OBIX/bridge adapters every 60s
    scheduler_service.add_adapter_health_monitor_job(interval_seconds=60)

    # Data freshness monitor — SLI Tier 2: tracks age of normalized data every 5 minutes
    scheduler_service.add_data_freshness_monitor_job(interval_seconds=300)

    # Uptime aggregator — SLI Tier 4: daily (01:00 SAST) + monthly (1st 02:00 SAST)
    scheduler_service.add_uptime_aggregator_jobs()

    # Critical path monitor — SLI Tier 3: hourly aggregation of PARASITE decision latencies
    scheduler_service.add_critical_path_monitor_job()

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

    # Baseline capture job (5 min) - captures age-only baselines for newly discovered or replaced equipment
    scheduler_service.add_baseline_capture_job(interval_minutes=5)

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

    # Zone occupancy trigger event recording (every minute)
    # Read-only/inert: records zone occupancy transitions only. It does not
    # invoke optimization; future ReflexReconciliationService will consume it.
    try:
        scheduler_service.add_zone_occupancy_trigger_job(interval_seconds=60)
        _logger.info("Zone occupancy trigger job initialized (60s interval)")
    except Exception as e:
        _logger.warning(f"Zone occupancy trigger job initialization failed: {e}")

    # Reflex reconciliation current-state scan (every 5 minutes)
    # Deterministic zone/system mismatch checks. This is separate from AI
    # optimization and does not call analyze_building().
    try:
        scheduler_service.add_reflex_reconciliation_job(interval_seconds=300)
        _logger.info("Reflex reconciliation job initialized (300s interval)")
    except Exception as e:
        _logger.warning(f"Reflex reconciliation job initialization failed: {e}")

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


async def shutdown_event(_: FastAPI) -> None:
    """Cleanup background services on shutdown.

    This function is called when the FastAPI application shuts down.
    It stops background services and closes connections.
    """
    # Persist buffered AI usage before anything else — the tracker holds the
    # day's calls in an in-memory cache that is otherwise only flushed at 23:55.
    # Without this, every restart silently discards the day's usage rows.
    try:
        from app.services.ai_usage_tracker import usage_tracker

        usage_tracker.flush()
    except Exception:
        _logger.warning("Failed to flush AI usage tracker on shutdown", exc_info=True)

    # Stop Sentry JWT token refresh
    from app.services.sentry_auth_service import get_sentry_auth_service

    sentry_auth = get_sentry_auth_service()
    if sentry_auth:
        await sentry_auth.stop_background_refresh()

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
