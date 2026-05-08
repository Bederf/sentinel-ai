"""Background Scheduler Service.

Handles periodic background tasks such as:
- Generating demo audit data
- Running AI optimization analysis
- Cleaning up old logs
- Running scheduled maintenance tasks
"""

import asyncio
import logging
from datetime import UTC, datetime, timedelta
from pathlib import Path

from apscheduler.schedulers.background import BackgroundScheduler
from apscheduler.triggers.interval import IntervalTrigger

from app.services.ai_optimizer import get_ai_optimizer
from app.services.audit_logger import AuditLogger
from app.services.phase_promotion_evaluator import get_phase_promotion_evaluator

EXPIRY_HOURS = 168  # 7 days — gives Evans a full week to review before expiry

logger = logging.getLogger(__name__)


class BackgroundSchedulerService:
    """Singleton background scheduler service."""

    _instance = None
    _scheduler = None

    def __new__(cls):
        """Ensure singleton pattern."""
        if cls._instance is None:
            cls._instance = super().__new__(cls)
        return cls._instance

    def __init__(self):
        """Initialize background scheduler."""
        if hasattr(self, "_initialized"):
            return

        self._initialized = True
        self.scheduler = BackgroundScheduler()
        self._main_loop = None  # Will be set during startup
        self._feedback_retraining_last_trigger: dict[str, datetime] = {}
        self._feedback_retraining_policy = {
            "min_records": 10,
            "min_success_rate": 70.0,
            "cooldown_hours": 24,
        }
        logger.info("Background scheduler initialized")

    def set_main_loop(self, loop: asyncio.AbstractEventLoop):
        """Store reference to the main (uvicorn) event loop for cross-thread scheduling."""
        self._main_loop = loop
        logger.info(f"Main event loop captured: {loop}")

    def start(self):
        """Start the background scheduler."""
        if not self.scheduler.running:
            self.scheduler.start()
            logger.info("Background scheduler started")

    def stop(self):
        """Stop the background scheduler."""
        if self.scheduler.running:
            self.scheduler.shutdown()
            logger.info("Background scheduler stopped")

    def add_demo_data_job(self, interval_seconds: int = 60):
        """
        Add a job to generate demo audit data periodically.

        Args:
            interval_seconds: How often to generate demo data (default: 60 seconds)
        """
        # Remove existing job if it exists
        if self.scheduler.get_job("generate_demo_audit_data"):
            self.scheduler.remove_job("generate_demo_audit_data")
            logger.info("Removed existing demo data job")

        # Add new job
        self.scheduler.add_job(
            func=self._generate_demo_audit_data,
            trigger=IntervalTrigger(seconds=interval_seconds),
            id="generate_demo_audit_data",
            name="Generate Demo Audit Data",
            replace_existing=True,
        )
        logger.info(f"Added demo data job with {interval_seconds}s interval")

    def _generate_demo_audit_data(self):
        """Wrapper to generate demo audit data (runs in background)."""
        try:
            # Import here to avoid circular imports
            import random

            from app.database.repositories.equipment_repository import EquipmentRepository
            from app.models.audit_log import AuditResultType as ART

            logger.debug("Generating periodic demo audit data...")

            # Get real equipment IDs from registered sites
            from app.core.site_resolver import get_registered_site_ids

            demo_devices = []
            try:
                equipment_repo = EquipmentRepository()
                site_ids = get_registered_site_ids()
                for site_id in site_ids:
                    equipment_list = equipment_repo.get_by_site_code(site_id)
                    if equipment_list:
                        # Sample controllable equipment types for realistic audit logs
                        controllable_types = [
                            "fcu",
                            "ahu",
                            "vav",
                            "chiller",
                            "pump",
                            "dali_controller",
                            "luminaire",
                            "luminaire_group",
                            "generator",
                            "ups",
                            "ats",
                            "transformer",
                            "lv_switchboard",
                            "power_meter",
                        ]
                        demo_devices.extend(
                            [
                                eq.get("code") or eq.get("equipment_id") or eq.get("id")
                                for eq in equipment_list
                                if any(t in (eq.get("type", "") or "").lower() for t in controllable_types)
                            ][:20]  # Limit to 20 devices per site
                        )
                    if demo_devices:
                        break  # Enough devices for demo data
            except Exception as e:
                logger.warning(f"Could not fetch equipment for registered sites: {e}")

            if not demo_devices:
                logger.debug("No equipment found for demo audit data — skipping")
                return

            demo_users = ["operator-1", "operator-2", "system", "scheduler", "admin", "SENTINEL"]
            demo_points_by_type = {
                "CHILLER": ["chw_supply_temp", "setpoint", "status", "mode", "runtime_hours"],
                "AHU": ["supply_air_temp", "fan_speed", "setpoint", "status", "damper_position"],
                "FCU": ["setpoint", "fan_speed", "status", "mode"],
                "VAV": ["setpoint", "damper_position", "airflow", "status"],
                "DALI": ["brightness", "scene", "status", "mode"],
                "LUM": ["brightness", "status", "dimmer_level"],
                "CO2": ["status", "calibration", "threshold"],
                "GEN": ["status", "mode", "load_percent", "runtime_hours"],
                "UPS": ["status", "mode", "load_percent", "battery_charge_pct"],
                "ATS": ["status", "position", "mode"],
                "TX": ["status", "load_percent", "oil_temp_c"],
                "MTR": ["status", "active_power_kw", "power_factor"],
            }

            audit_logger = AuditLogger()
            entries_created = 0

            # Generate 2-5 new entries per cycle to simulate real activity
            for _ in range(random.randint(2, 5)):
                device_id = random.choice(demo_devices)
                user = random.choice(demo_users)
                # v2.0 IDs: S###-TYPE-FLOOR-ZONE — type is second segment
                device_prefix = device_id.split("-")[1] if "-" in device_id else device_id
                point_name = random.choice(demo_points_by_type.get(device_prefix, ["status", "setpoint"]))

                old_value = random.randint(20, 25) if "setpoint" in point_name else random.randint(50, 100)
                new_value = old_value + random.randint(-5, 5)

                # SENTINEL entries are always success (AI validates before applying)
                if user == "SENTINEL":
                    result = ART.SUCCESS
                else:
                    result = random.choices(
                        [ART.SUCCESS, ART.WARNING, ART.BLOCKED, ART.FAILED], weights=[70, 15, 10, 5]
                    )[0]

                safety_validation = None
                error_message = None

                if result == ART.BLOCKED:
                    safety_validation = {
                        "rules_checked": ["temperature_range", "pressure_limits"],
                        "passed_rules": ["temperature_range"],
                        "failed_rules": ["pressure_limits"],
                        "details": "Pressure exceeds safe operating limits",
                    }
                    error_message = "Safety validation failed: Pressure limit exceeded"
                elif result == ART.WARNING:
                    safety_validation = {
                        "rules_checked": ["temperature_range", "minimum_runtime"],
                        "passed_rules": ["temperature_range"],
                        "warnings": ["minimum_runtime"],
                        "details": "Minimum runtime requirement not met (warning only)",
                    }
                elif result == ART.SUCCESS:
                    safety_validation = {
                        "rules_checked": ["temperature_range", "pressure_limits"],
                        "passed_rules": ["temperature_range", "pressure_limits"],
                        "details": "All safety checks passed",
                    }

                # Build metadata - SENTINEL entries include AI optimization context
                entry_metadata: dict = {
                    "demo_data": True,
                    "generated_at": datetime.now().isoformat(),
                    "priority": random.randint(8, 16),
                }
                if user == "SENTINEL":
                    entry_metadata["source"] = "sentinel_auto_optimization"
                    entry_metadata["confidence"] = round(random.uniform(0.72, 0.95), 2)

                audit_logger.log_control_action(
                    device_id=device_id,
                    point_name=point_name,
                    user=user,
                    old_value=old_value,
                    new_value=new_value,
                    result=result,
                    safety_validation=safety_validation,
                    error_message=error_message,
                    metadata=entry_metadata,
                )
                entries_created += 1

            # Flush to disk
            audit_logger.flush()

            logger.info(f"Generated {entries_created} periodic demo audit entries")

        except Exception as e:
            logger.error(f"Failed to generate periodic demo audit data: {e}")

    # Sim-time tracking for optimization/recommendation gates
    _last_optimization_sim_time: datetime | None = None
    _last_recommendation_sim_time: datetime | None = None
    # Target interval in simulated hours between optimization cycles
    OPTIMIZATION_SIM_HOURS: float = 8.0
    # Target interval in simulated hours between recommendation cycles
    RECOMMENDATION_SIM_HOURS: float = 8.0

    def add_optimization_analysis_job(self, interval_seconds: int = 900):
        """
        Add a job to run optimization analysis periodically.

        When the simulator is running at accelerated speed, the job polls every
        30 real seconds but only executes when enough *simulated* time has
        elapsed (OPTIMIZATION_SIM_HOURS).  When no simulation is running, it
        uses the real-time interval_seconds as before.

        Args:
            interval_seconds: Real-time interval when no simulation is running
                              (default: 900 seconds = 15 minutes)
        """
        # Remove existing job if it exists
        if self.scheduler.get_job("run_optimization_analysis"):
            self.scheduler.remove_job("run_optimization_analysis")
            logger.info("Removed existing optimization analysis job")

        # Store the real-time interval for non-simulation mode
        self._optimization_real_interval = interval_seconds

        # Poll every 300s (5 min) — sim-time gate decides whether to actually run.
        # Real-time fallback was previously 30s (sim stress-test artifact).
        # 5 min is appropriate for production without simulator active.
        poll_seconds = 300
        first_run = datetime.now() + timedelta(seconds=60)  # 60s warmup

        self.scheduler.add_job(
            func=self._run_optimization_analysis_gated,
            trigger=IntervalTrigger(seconds=poll_seconds),
            id="run_optimization_analysis",
            name="Run Optimization Analysis (sim-aware)",
            replace_existing=True,
            next_run_time=first_run,
            max_instances=1,
        )
        logger.info(
            f"Added optimization analysis job: poll every {poll_seconds}s, "
            f"sim-gate={self.OPTIMIZATION_SIM_HOURS}h, "
            f"real-fallback={interval_seconds}s "
            f"(first run at {first_run.strftime('%H:%M:%S')})"
        )

    def _run_optimization_analysis_gated(self):
        """Sim-time gate wrapper around _run_optimization_analysis.

        Checks whether enough simulated time has elapsed since the last run.
        If the simulator is running, uses simulated-time intervals.
        If no simulator, falls back to real-time interval.
        """
        import app.services.lifecycle_orchestrator as _orch_mod

        now_eff = _orch_mod.get_effective_now()
        orch = _orch_mod._orchestrator_instance
        sim_running = orch is not None and orch.running

        if sim_running:
            # Sim-time gate: skip if insufficient simulated time elapsed
            if self._last_optimization_sim_time is not None:
                elapsed = (now_eff - self._last_optimization_sim_time).total_seconds()
                threshold = self.OPTIMIZATION_SIM_HOURS * 3600
                if elapsed < threshold:
                    return  # Silent skip — fires every 30s, would flood logs
                logger.warning(
                    f"[SIM-GATE] Optimization PASSED: {elapsed / 3600:.1f} sim-hours elapsed "
                    f"(threshold={self.OPTIMIZATION_SIM_HOURS}h), "
                    f"sim-time={now_eff.strftime('%m-%d %H:%M')}"
                )
            else:
                logger.warning(f"[SIM-GATE] Optimization first run, sim-time={now_eff.strftime('%m-%d %H:%M')}")
            self._last_optimization_sim_time = now_eff

            # Occupied-hours gate: skip LLM call during simulated off-hours
            sim_hour = now_eff.hour
            sim_weekday = now_eff.weekday()
            if sim_weekday >= 5 or sim_hour < 6 or sim_hour >= 19:
                logger.info(
                    f"[SIM-GATE] Optimization SKIPPED: simulated off-hours (hour={sim_hour}, weekday={sim_weekday})"
                )
                return
        else:
            # Real-time gate: use wall-clock interval
            if self._last_optimization_sim_time is not None:
                elapsed = (datetime.now() - self._last_optimization_sim_time).total_seconds()
                if elapsed < self._optimization_real_interval:
                    return
            self._last_optimization_sim_time = datetime.now()

        self._run_optimization_analysis()

    def _is_optimization_enabled(self, site_id: str) -> bool:
        """Check if optimization_enabled is True for a given site.

        Checks Supabase first, falls back to sites.json.
        Returns False if the flag is missing or explicitly False.
        """
        try:
            from app.database.supabase_client import get_supabase_client

            client = get_supabase_client()
            resp = client.table("sites").select("optimization_enabled").eq("code", site_id).limit(1).execute()
            if resp.data:
                return bool(resp.data[0].get("optimization_enabled"))
        except Exception:
            pass

        # JSON fallback
        try:
            import json
            from pathlib import Path

            sites_path = Path(__file__).parent.parent / "data" / "sites.json"
            if sites_path.exists():
                with open(sites_path) as f:
                    sites = json.load(f)
                for site in sites:
                    if site.get("code") == site_id:
                        return bool(site.get("optimization_enabled"))
        except Exception:
            pass

        return False

    def _run_optimization_analysis(self):
        """
        Run AI optimization analysis for all registered sites and persist
        recommendations to Supabase (or JSON fallback).

        Uses site_resolver to discover sites (data-source-agnostic), then
        ai_optimizer.analyze_building() to generate recommendations, then
        recommendation_repo.create() to persist them.  Deduplicates against
        existing PENDING recommendations for the same equipment+action+value
        within the last 24 hours.

        Schedule-aware: HVAC comfort recs are skipped outside occupied hours
        (weekdays 05:30-17:30 SAST). BESS/solar/generator/meter recs flow 24/7.
        """
        try:
            logger.debug("Running periodic optimization analysis...")

            # Schedule gate: determine if HVAC comfort recs should be suppressed
            # Use simulated time when simulator is running (accelerated clock),
            # otherwise fall back to real wall-clock time.
            from app.services.lifecycle_orchestrator import get_effective_now

            now = get_effective_now()
            hour = now.hour
            weekday = now.weekday()  # 0=Mon, 6=Sun
            # Skip HVAC comfort recs outside occupied window (07:00-17:59 weekdays)
            skip_hvac_comfort = weekday >= 5 or hour < 7 or hour >= 18
            if skip_hvac_comfort:
                logger.info(
                    f"Outside occupied hours (hour={hour}, weekday={weekday}) — "
                    "HVAC comfort recs will be suppressed; BESS/solar/generator still active"
                )

            from app.core.site_resolver import get_registered_site_ids
            from app.database.repositories.recommendation_repository import (
                get_recommendation_repository,
            )
            from app.models.recommendation import (
                ActionRiskLevel,
                Recommendation,
                RecommendationStatus,
            )

            site_ids = get_registered_site_ids()
            if not site_ids:
                logger.debug("No registered sites found, skipping optimization analysis")
                return

            logger.info(f"Running optimization analysis for {len(site_ids)} registered sites")

            recommendation_repo = get_recommendation_repository()
            created_count = 0
            skipped_count = 0
            error_count = 0

            for site_id in site_ids:
                try:
                    # Mode gate: Supabase onboarding_phase is authoritative.
                    # Use effective_phase() which reads sites.onboarding_phase and
                    # normalises legacy names (shadow→shadow_live, auto→automatic).
                    try:
                        from app.models.onboarding_phase import effective_phase

                        _loop = asyncio.new_event_loop()
                        asyncio.set_event_loop(_loop)
                        try:
                            current_stage = _loop.run_until_complete(effective_phase(site_id))
                        finally:
                            _loop.close()
                    except Exception:
                        current_stage = "commissioning"

                    GENERATION_ALLOWED = {"shadow_live", "advisory", "supervised", "automatic"}
                    if current_stage not in GENERATION_ALLOWED:
                        logger.info(
                            "[AI-OPT] Skipping — site=%s mode=%s (generation requires %s)",
                            site_id,
                            current_stage,
                            GENERATION_ALLOWED,
                        )
                        continue

                    # Optimization toggle gate: skip if optimization_enabled is off
                    if not self._is_optimization_enabled(site_id):
                        logger.info(
                            f"[AI-OPT] Skipping LLM optimization for {site_id} "
                            f"(optimization_enabled=False in site settings)"
                        )
                        continue

                    loop = asyncio.new_event_loop()
                    asyncio.set_event_loop(loop)

                    try:
                        optimization_result = loop.run_until_complete(get_ai_optimizer().analyze_building(site_id))
                    finally:
                        loop.close()

                    recs_len = len(optimization_result.recommendations)
                    logger.warning(
                        "[AI-OPT DEBUG] recs count=%d, recs=%s", recs_len, optimization_result.recommendations
                    )

                    if not optimization_result.recommendations:
                        logger.warning(f"[AI-OPT] {site_id}: 0 recommendations (building at optimal)")
                        continue

                    # Validate recommendations
                    loop = asyncio.new_event_loop()
                    asyncio.set_event_loop(loop)
                    try:
                        validation = loop.run_until_complete(
                            get_ai_optimizer().validate_recommendation(site_id, optimization_result)
                        )
                    finally:
                        loop.close()

                    # === FIX 1: Filter maintenance BEFORE validate_recommendation ===
                    # Maintenance recs don't need device_manager validation — write directly.
                    # This must happen before validate_recommendation call so maintenance
                    # recs never block on device_manager lookup failures.
                    MAINTENANCE_ACTIONS = {"maintenance_schedule", "maintenance", "inspect", "replace", "repair"}
                    maintenance_recs = []
                    control_recs = []
                    for rec_dict in optimization_result.recommendations:
                        if rec_dict.get("action_type", "") in MAINTENANCE_ACTIONS or "maintenance" in rec_dict.get(
                            "point_name", ""
                        ):
                            maintenance_recs.append(rec_dict)
                        else:
                            control_recs.append(rec_dict)

                    # Persist maintenance recs immediately — no validation needed
                    for rec_dict in maintenance_recs:
                        equipment_id = rec_dict.get("equipment_id", "")
                        rec_action_type = rec_dict.get("action_type", "")
                        logger.info(
                            "[AI-OPT] Persisting %s rec for %s — maintenance (no validation)",
                            rec_action_type,
                            equipment_id,
                        )
                        loop = asyncio.new_event_loop()
                        asyncio.set_event_loop(loop)
                        try:
                            rec = Recommendation(
                                site_id=site_id,
                                timestamp=datetime.utcnow(),
                                action_type=rec_action_type or "health_maintenance",
                                risk_level=ActionRiskLevel.LOW,
                                target_equipment=equipment_id,
                                action={
                                    "point": rec_dict.get("point_name", ""),
                                    "value": rec_dict.get("recommended_value"),
                                },
                                reason=rec_dict.get("reason", ""),
                                expected_impact={
                                    "current_value": rec_dict.get("current_value"),
                                    "recommended_value": rec_dict.get("recommended_value"),
                                    "unit": rec_dict.get("unit", ""),
                                    "energy_savings_percent": rec_dict.get("savings_kwh", 5),
                                },
                                confidence="0.7",
                                confidence_score=0.7,
                                profile=optimization_result.profile or "",
                                source="ai_optimizer",
                                source_type="ml_model",
                                status=RecommendationStatus.PENDING,
                                requires_approval=True,
                            )
                            loop.run_until_complete(recommendation_repo.create(rec))
                            created_count += 1
                        except Exception as e:
                            logger.warning(f"[AI-OPT] Failed to persist maintenance rec for {equipment_id}: {e}")
                            error_count += 1
                        finally:
                            loop.close()

                    if not control_recs:
                        logger.info(f"[AI-OPT] {site_id}: all recs were maintenance, skipping validation")
                        continue

                    # Build a filtered recommendation for validation (maintenance stripped)
                    from app.models.optimization import OptimizationRecommendation as OptRec

                    filtered_recommendation = OptRec(
                        site_id=optimization_result.site_id,
                        timestamp=optimization_result.timestamp,
                        recommendations=control_recs,
                        confidence=optimization_result.confidence,
                        profile=optimization_result.profile,
                    )

                    # Validate only control/setpoint recs
                    loop = asyncio.new_event_loop()
                    asyncio.set_event_loop(loop)
                    try:
                        validation = loop.run_until_complete(
                            get_ai_optimizer().validate_recommendation(site_id, filtered_recommendation)
                        )
                    finally:
                        loop.close()

                    allowed_count = sum(
                        1 for vr in validation.get("validation_results", []) if vr.get("allowed", False)
                    )
                    logger.warning("[AI-OPT DEBUG] validation allowed_keys count=%d", allowed_count)
                    logger.warning(f"[AI-OPT DEBUG] validation results={validation.get('validation_results', [])}")

                    # Build set of individually-allowed recommendations
                    # (top-level "allowed" is an AND — one failure blocks all)
                    allowed_keys: set[tuple[str, str]] = set()
                    for vr in validation.get("validation_results", []):
                        if vr.get("allowed", False):
                            allowed_keys.add((vr.get("equipment_id", ""), vr.get("point_name", "")))

                    if not allowed_keys:
                        logger.info(f"No recommendations passed safety validation for {site_id}")
                        continue

                    # Fetch existing PENDING recs for dedup — 24h window, higher limit
                    loop = asyncio.new_event_loop()
                    asyncio.set_event_loop(loop)
                    try:
                        existing_pending = loop.run_until_complete(
                            recommendation_repo.get_by_status(site_id, RecommendationStatus.PENDING, limit=500)
                        )
                    finally:
                        loop.close()

                    # Build value-aware dedup set: (equipment, point, value) for recs < 48 sim-hours old
                    # Use effective time so dedup window matches simulated day boundaries
                    dedup_cutoff = get_effective_now().replace(tzinfo=None) - timedelta(hours=48)
                    recent_keys: set[tuple[str, str, str]] = set()
                    for existing in existing_pending:
                        ts = existing.timestamp
                        if isinstance(ts, str):
                            try:
                                ts = datetime.fromisoformat(ts)
                            except (ValueError, TypeError):
                                continue
                        # Strip timezone info for comparison (cutoff is UTC-naive)
                        if hasattr(ts, "tzinfo") and ts.tzinfo is not None:
                            ts = ts.replace(tzinfo=None)
                        if ts >= dedup_cutoff:
                            action_point = ""
                            action_value = ""
                            if isinstance(existing.action, dict):
                                action_point = existing.action.get("point", "")
                                action_value = str(existing.action.get("value", "")).strip().lower()
                            recent_keys.add((existing.target_equipment, action_point, action_value))

                    # Persist each recommendation
                    for rec_dict in control_recs:
                        equipment_id = rec_dict.get("equipment_id", "")
                        # Handle both flat format (point_name) and grouped format (action.point)
                        raw_point = rec_dict.get("point_name", "")
                        if not raw_point:
                            raw_point = rec_dict.get("action", {}).get("point", "")
                        point_name = raw_point
                        rec_action_type = rec_dict.get("action_type", "")

                        logger.warning(
                            "[AI-OPT DEBUG] Processing rec: equipment=%s, action_type=%r, point=%r",
                            equipment_id,
                            rec_action_type,
                            point_name,
                        )

                        # Safety check: skip recs that failed individual validation
                        if (equipment_id, point_name) not in allowed_keys:
                            skipped_count += 1
                            continue

                        # Schedule gate: skip HVAC comfort recs outside occupied hours
                        if skip_hvac_comfort:
                            system = rec_dict.get("system", "")
                            if system == "hvac" and "setpoint" in point_name:
                                skipped_count += 1
                                continue

                        # Value-aware dedup check: same equipment + point + value within 48h
                        # Handle both flat format (recommended_value) and grouped format (action.value)
                        raw_value = rec_dict.get("recommended_value", "")
                        if raw_value == "":
                            raw_value = rec_dict.get("action", {}).get("value", "")
                        rec_value = str(raw_value).strip().lower()
                        if (equipment_id, point_name, rec_value) in recent_keys:
                            skipped_count += 1
                            continue

                        # GROUPED REC DIPLEX: If this is a grouped rec (affected_equipment),
                        # check if any individual equipment in the group already has a pending rec.
                        # Skip the group rec if individual recs exist for the same point+value.
                        affected = rec_dict.get("affected_equipment", [])
                        is_grouped = bool(affected)
                        if is_grouped:
                            # Check each affected equipment for existing pending rec
                            group_conflict = False
                            for aff_eq in affected:
                                if (aff_eq, point_name, rec_value) in recent_keys:
                                    group_conflict = True
                                    logger.info(
                                        f"[DEDUP] Skipping ZONE_GROUP — individual rec already exists for {aff_eq}"
                                    )
                                    break
                            if group_conflict:
                                skipped_count += 1
                                continue

                        # Parse confidence from Claude response
                        confidence_raw = optimization_result.confidence
                        try:
                            confidence_num = float(confidence_raw)
                            confidence_num = max(0.0, min(1.0, confidence_num))
                        except (TypeError, ValueError):
                            confidence_num = 0.7

                        # Determine sim_hour for traceability
                        import app.services.lifecycle_orchestrator as _orch_mod_local

                        sim_now = get_effective_now()
                        orch = _orch_mod_local._orchestrator_instance
                        is_sim = orch is not None and orch.running

                        rec = Recommendation(
                            site_id=site_id,
                            timestamp=datetime.utcnow(),
                            action_type=rec_action_type or "ai_optimization",
                            risk_level=ActionRiskLevel.LOW,
                            target_equipment=equipment_id,
                            action={
                                "point": point_name,
                                "value": rec_dict.get("recommended_value"),
                                "sim_hour": sim_now.strftime("%Y-%m-%d %H:%M") if is_sim else None,
                            },
                            reason=rec_dict.get("reason", ""),
                            expected_impact={
                                "current_value": rec_dict.get("current_value"),
                                "recommended_value": rec_dict.get("recommended_value"),
                                "unit": rec_dict.get("unit", ""),
                                "energy_savings_percent": rec_dict.get("savings_kwh", 5),
                            },
                            confidence=str(confidence_num),
                            confidence_score=confidence_num,
                            profile=optimization_result.profile or "",
                            source="ai_optimizer",
                            source_type="ml_model",
                            status=RecommendationStatus.PENDING,
                            requires_approval=True,
                            metadata={
                                "group_recommendation": is_grouped,
                                "affected_equipment": affected,
                            }
                            if is_grouped
                            else {},
                        )

                        loop = asyncio.new_event_loop()
                        asyncio.set_event_loop(loop)
                        try:
                            loop.run_until_complete(recommendation_repo.create(rec))
                            created_count += 1
                            # Emit SSE toast event for new AI recommendation
                            try:
                                from app.services.event_emitter import get_event_emitter

                                emitter = get_event_emitter()
                                loop.run_until_complete(
                                    emitter.emit_recommendation_created(
                                        recommendation_id=rec.id,
                                        site_id=rec.site_id,
                                        action_type=rec.action_type,
                                        reason=rec.reason or "",
                                        confidence=rec.confidence or "medium",
                                        risk_level=rec.risk_level.value if rec.risk_level else "medium",
                                        target_equipment=rec.target_equipment,
                                    )
                                )
                            except Exception as emit_err:
                                logger.warning(f"Failed to emit recommendation_created SSE event: {emit_err}")
                        except Exception as e:
                            logger.warning(f"Failed to persist recommendation for {equipment_id}: {e}")
                            error_count += 1
                        finally:
                            loop.close()

                except Exception as e:
                    logger.error(f"Error analyzing site {site_id}: {e}")
                    error_count += 1

            # === RULE-BASED HEALTH RECOMMENDATIONS (no LLM) ===
            # Uses thresholds from settings page to generate maintenance recs
            try:
                health_created, health_deduped = self._generate_health_recommendations(site_ids, recommendation_repo)
                created_count += health_created
                skipped_count += health_deduped
            except Exception as e:
                logger.warning(f"[HEALTH-REC] Failed: {e}")

            logger.warning(
                f"[AI-OPT] Cycle complete: {created_count} created, {skipped_count} deduped, {error_count} errors"
            )

        except Exception as e:
            logger.error(f"Failed to run optimization analysis: {e}")

    def _generate_health_recommendations(self, site_ids, recommendation_repo) -> tuple[int, int]:
        """Generate maintenance recommendations for degraded equipment using configured thresholds.

        Rule-based — no LLM call. Reads health thresholds from settings page
        (Supabase system_settings → JSON settings → defaults).

        Also creates dashboard alerts and sends Sentry/Telegram notifications
        for critical and warning equipment.

        Returns:
            (created_count, deduped_count)
        """
        import app.services.lifecycle_orchestrator as _orch_mod
        from app.database.supabase_client import get_supabase_client
        from app.models.recommendation import (
            ActionRiskLevel,
            Recommendation,
            RecommendationStatus,
        )
        from app.services.equipment_alert_service import get_equipment_alert_service
        from app.services.health_threshold_service import get_health_thresholds
        from app.services.lifecycle_orchestrator import get_effective_now

        thresholds = get_health_thresholds()
        t_healthy = thresholds.get("healthy", 90)
        t_warning = thresholds.get("warning", 70)
        t_critical = thresholds.get("critical", 50)

        sb = get_supabase_client()
        now_eff = get_effective_now()
        created = 0
        deduped = 0

        # Maintenance actions by severity
        ACTIONS = {
            "critical": {
                "action": "urgent_inspection",
                "reason": "Health score below {t_critical}% — schedule urgent inspection and diagnostic. "
                "Equipment may be at risk of failure. Check sensor readings, vibration, "
                "and operating parameters.",
                "risk": ActionRiskLevel.MEDIUM,
            },
            "warning": {
                "action": "scheduled_maintenance",
                "reason": "Health score below {t_warning}% — schedule preventive maintenance. "
                "Inspect filters, bearings, connections, and calibration.",
                "risk": ActionRiskLevel.LOW,
            },
        }

        for site_id in site_ids:
            try:
                # Get site UUID
                site_resp = sb.table("sites").select("id").eq("code", site_id).execute()
                if not site_resp.data:
                    continue
                site_uuid = site_resp.data[0]["id"]

                # Get degraded equipment (below healthy threshold)
                eq_resp = (
                    sb.table("equipment")
                    .select("code,type,health_score,status")
                    .eq("site_id", site_uuid)
                    .lt("health_score", t_healthy)
                    .execute()
                )
                if not eq_resp.data:
                    continue

                # Fetch existing PENDING recs for dedup
                loop = asyncio.new_event_loop()
                asyncio.set_event_loop(loop)
                try:
                    existing_pending = loop.run_until_complete(
                        recommendation_repo.get_by_status(site_id, RecommendationStatus.PENDING, limit=500)
                    )
                finally:
                    loop.close()

                # Build dedup set: (equipment, action_point)
                dedup_cutoff = now_eff.replace(tzinfo=None) - timedelta(hours=48)
                existing_keys: set[tuple[str, str]] = set()
                for ex in existing_pending:
                    ts = ex.timestamp
                    if isinstance(ts, str):
                        try:
                            ts = datetime.fromisoformat(ts)
                        except (ValueError, TypeError):
                            continue
                    if hasattr(ts, "tzinfo") and ts.tzinfo is not None:
                        ts = ts.replace(tzinfo=None)
                    if ts >= dedup_cutoff:
                        action_point = ""
                        if isinstance(ex.action, dict):
                            action_point = ex.action.get("point", "")
                        existing_keys.add((ex.target_equipment, action_point))

                for eq in eq_resp.data:
                    code = eq["code"]
                    health = eq.get("health_score") or 100
                    eq_type = eq.get("type", "unknown")

                    # Determine severity
                    if health < t_critical:
                        severity = "critical"
                    elif health < t_warning:
                        severity = "warning"
                    else:
                        continue  # Between warning and healthy — monitor only

                    action_info = ACTIONS[severity]
                    point_name = f"health_{severity}"

                    # Dedup check
                    if (code, point_name) in existing_keys:
                        deduped += 1
                        continue

                    reason = action_info["reason"].format(t_critical=t_critical, t_warning=t_warning)

                    # Determine sim_hour for traceability
                    orch = _orch_mod._orchestrator_instance
                    is_sim = orch is not None and orch.running

                    rec = Recommendation(
                        site_id=site_id,
                        timestamp=datetime.utcnow(),
                        action_type="health_maintenance",
                        risk_level=action_info["risk"],
                        target_equipment=code,
                        action={
                            "point": point_name,
                            "value": severity,
                            "equipment_type": eq_type,
                            "sim_hour": now_eff.strftime("%Y-%m-%d %H:%M") if is_sim else None,
                        },
                        reason=f"{code} ({eq_type}): health={health}% — {reason}",
                        expected_impact={
                            "current_health": health,
                            "threshold": t_critical if severity == "critical" else t_warning,
                            "severity": severity,
                        },
                        confidence=str(0.95),  # Rule-based, high confidence
                        confidence_score=0.95,
                        profile="health_rules",
                        source="health_alert",
                        source_type="rule_based",
                        status=RecommendationStatus.PENDING,
                        requires_approval=True,
                    )

                    loop = asyncio.new_event_loop()
                    asyncio.set_event_loop(loop)
                    try:
                        loop.run_until_complete(recommendation_repo.create(rec))
                        created += 1
                        logger.warning(
                            f"[HEALTH-REC] {code}: health={health}% [{severity.upper()}] — recommendation created"
                        )
                        # Emit SSE toast event for new health recommendation
                        try:
                            from app.services.event_emitter import get_event_emitter

                            emitter = get_event_emitter()
                            loop.run_until_complete(
                                emitter.emit_recommendation_created(
                                    recommendation_id=rec.id,
                                    site_id=rec.site_id,
                                    action_type=rec.action_type,
                                    reason=rec.reason or "",
                                    confidence=rec.confidence or "medium",
                                    risk_level=rec.risk_level.value if rec.risk_level else "medium",
                                    target_equipment=rec.target_equipment,
                                )
                            )
                        except Exception as emit_err:
                            logger.warning(f"Failed to emit recommendation_created SSE event: {emit_err}")
                    except Exception as e:
                        logger.warning(f"[HEALTH-REC] Failed to persist for {code}: {e}")
                    finally:
                        loop.close()

                    # === DASHBOARD ALERT + SENTRY/TELEGRAM NOTIFICATION ===
                    # Critical: immediate Telegram push + dashboard alert
                    # Warning: dashboard alert + Telegram (cooldown-gated by alert_notifier)
                    try:
                        alert_svc = get_equipment_alert_service()
                        if severity == "critical":
                            threshold_msg = f"<{t_critical}% CRITICAL"
                        else:
                            threshold_msg = f"<{t_warning}% WARNING"
                        alert_msg = (
                            f"Health score {health}% (threshold: "
                            f"{threshold_msg}). "
                            f"{action_info['action'].replace('_', ' ').title()} recommended."
                        )
                        result = alert_svc.create_alert_for_equipment(
                            equipment_id=code,
                            site_id=site_id,
                            severity=severity,
                            message=alert_msg,
                            alert_type="health_maintenance",
                            notify_telegram=True,  # Both critical + warning; cooldown prevents spam
                        )
                        if result.get("error"):
                            logger.warning(f"[HEALTH-REC] Alert creation failed for {code}: {result['error']}")
                        else:
                            tg_status = "sent" if result.get("telegram_sent") else "skipped"
                            logger.warning(
                                f"[HEALTH-REC] Alert created for {code} [{severity.upper()}], telegram={tg_status}"
                            )
                    except Exception as e:
                        logger.warning(f"[HEALTH-REC] Notification failed for {code}: {e}")

            except Exception as e:
                logger.warning(f"[HEALTH-REC] Error for {site_id}: {e}")

        if created > 0:
            logger.warning(f"[HEALTH-REC] {created} health recs created, {deduped} deduped")

        return created, deduped

    def add_prediction_generation_job(self, interval_seconds: int = 300):
        """
        Add a job to generate predictions periodically.

        Scans equipment health scores and creates predictions for at-risk equipment.

        Args:
            interval_seconds: How often to run (default: 300 seconds = 5 minutes)
        """
        # Remove existing job if it exists
        if self.scheduler.get_job("generate_predictions"):
            self.scheduler.remove_job("generate_predictions")
            logger.info("Removed existing prediction generation job")

        # Delay first run by one full interval to avoid startup burst.
        first_run = datetime.now() + timedelta(seconds=interval_seconds)

        # Add new job
        self.scheduler.add_job(
            func=self._run_prediction_generation,
            trigger=IntervalTrigger(seconds=interval_seconds),
            id="generate_predictions",
            name="Generate Predictions for At-Risk Equipment",
            replace_existing=True,
            next_run_time=first_run,
            max_instances=1,
        )
        logger.info(f"Added prediction generation job with {interval_seconds}s interval")

    def _run_prediction_generation(self):
        """
        Wrapper to run prediction generation (runs in background).

        Handles async execution from sync scheduler context.
        """
        try:
            import asyncio

            from app.services.prediction_generator import get_prediction_generator

            logger.info("Running scheduled prediction generation...")

            generator = get_prediction_generator()

            # Run async function in new event loop
            loop = asyncio.new_event_loop()
            asyncio.set_event_loop(loop)

            try:
                result = loop.run_until_complete(generator.generate_predictions_for_all_sites())
                logger.info(
                    f"Prediction generation complete: {result['generated']} generated, "
                    f"{result['skipped_duplicate']} skipped (duplicate), "
                    f"{result['resolved']} resolved"
                )
            finally:
                loop.close()

        except Exception as e:
            logger.error(f"Failed to run prediction generation: {e}")

    def add_recommendation_generation_job(self, interval_seconds: int = 600):
        """
        Add a job to generate AI recommendations periodically.

        Sim-time aware: polls every 30s, only runs when enough simulated time
        has elapsed (RECOMMENDATION_SIM_HOURS).

        Args:
            interval_seconds: Real-time interval when no simulation is running
        """
        if self.scheduler.get_job("generate_recommendations"):
            self.scheduler.remove_job("generate_recommendations")
            logger.info("Removed existing recommendation generation job")

        self._recommendation_real_interval = interval_seconds

        poll_seconds = 30
        first_run = datetime.now() + timedelta(seconds=90)  # 90s warmup

        self.scheduler.add_job(
            func=self._run_recommendation_generation_gated,
            trigger=IntervalTrigger(seconds=poll_seconds),
            id="generate_recommendations",
            name="Generate AI Recommendations (sim-aware)",
            replace_existing=True,
            next_run_time=first_run,
            max_instances=1,
        )
        logger.info(
            f"Added recommendation generation job: poll every {poll_seconds}s, "
            f"sim-gate={self.RECOMMENDATION_SIM_HOURS}h, "
            f"real-fallback={interval_seconds}s "
            f"(first run at {first_run.strftime('%H:%M:%S')})"
        )

    def add_outcome_verification_job(self, interval_seconds: int = 300):
        """Add a job to verify recommendation outcomes periodically.

        Runs every 5 real minutes. Finds executed recommendations past the
        30-minute settling period and verifies whether they achieved their
        predicted impact by comparing actual sensor readings.

        Args:
            interval_seconds: Real-time interval between checks (default 5 min)
        """
        if self.scheduler.get_job("outcome_verification"):
            self.scheduler.remove_job("outcome_verification")

        first_run = datetime.now() + timedelta(seconds=120)  # 2-min warmup

        self.scheduler.add_job(
            func=self._run_outcome_verification,
            trigger=IntervalTrigger(seconds=interval_seconds),
            id="outcome_verification",
            name="Recommendation Outcome Verification",
            replace_existing=True,
            next_run_time=first_run,
            max_instances=1,
        )
        logger.info(
            "Added outcome verification job: every %ds (first run at %s)",
            interval_seconds,
            first_run.strftime("%H:%M:%S"),
        )

    def _run_outcome_verification(self):
        """Process pending outcome verifications for executed recommendations."""
        try:
            import asyncio

            from app.services.recommendation_outcome_service import (
                process_pending_verifications,
            )

            loop = asyncio.new_event_loop()
            asyncio.set_event_loop(loop)
            try:
                results = loop.run_until_complete(process_pending_verifications())
                if results:
                    logger.info(
                        "[OUTCOME] Verified %d recommendation outcomes",
                        len(results),
                    )
            finally:
                loop.close()
        except Exception as e:
            logger.error("Outcome verification job failed: %s", e)

    # -----------------------------------------------------------------
    # Recommendation Lifecycle — expiry + deduplication
    # -----------------------------------------------------------------

    def add_recommendation_processing_job(self, interval_seconds: int = 300):
        """Add a job to process pending recommendations through the tier router.

        Runs every 5 minutes. Fetches PENDING recommendations for each registered
        site, routes them through the recommendation graph to fill outcome={}
        placeholder records in parasite_decisions, and handles Tier 2 approval
        requests / Tier 3 auto-execution.

        This is the production pipeline that closes the recommendation loop —
        without it, recommendations expire after 48h before any outcome is written.

        Args:
            interval_seconds: How often to run (default 5 min)
        """
        from apscheduler.triggers.interval import IntervalTrigger

        if self.scheduler.get_job("recommendation_processing"):
            self.scheduler.remove_job("recommendation_processing")

        first_run = datetime.now() + timedelta(seconds=90)  # 90s warmup

        self.scheduler.add_job(
            func=self._run_recommendation_processing,
            trigger=IntervalTrigger(seconds=interval_seconds),
            id="recommendation_processing",
            name="Recommendation Lifecycle Processing (5min)",
            replace_existing=True,
            next_run_time=first_run,
            max_instances=1,
            coalesce=True,
        )
        logger.info(
            "Added recommendation processing job: every %ds (first run at %s)",
            interval_seconds,
            first_run.strftime("%H:%M:%S"),
        )

    def _run_recommendation_processing(self):
        """Process pending recommendations through the recommendation graph."""
        try:
            import asyncio

            loop = asyncio.new_event_loop()
            asyncio.set_event_loop(loop)
            try:
                processed = loop.run_until_complete(self._run_recommendation_processing_async())
                if processed:
                    logger.info("[REC-PROC] Processed %d recommendation batches", processed)
            finally:
                loop.close()
        except Exception as e:
            logger.error("Recommendation processing job failed: %s", e)

    async def _run_recommendation_processing_async(self) -> int:
        """Async version — process all registered sites."""
        from langchain_core.messages import HumanMessage

        from app.agents import get_recommendation_graph
        from app.core.site_resolver import get_registered_site_ids

        site_ids = get_registered_site_ids()
        if not site_ids:
            logger.debug("No registered sites for recommendation processing")
            return 0

        agent = get_recommendation_graph()
        processed = 0

        for site_id in site_ids:
            try:
                thread_id = f"rec_scheduler_{site_id}"
                config = {"configurable": {"thread_id": thread_id}}

                result = await agent.ainvoke(
                    {
                        "messages": [HumanMessage(content="process")],
                        "site_id": site_id,
                        "channel": "system",
                        "trigger": "scheduled",
                    },
                    config=config,
                )
                if result and result.get("processing_complete"):
                    processed += 1
                    logger.info(f"[REC-PROC] Completed processing for {site_id}")
                else:
                    logger.debug(f"[REC-PROC] No recommendations to process for {site_id}")
            except Exception as e:
                logger.warning(f"[REC-PROC] Failed to process {site_id}: {e}")

        return processed

    def add_milestone_timer_job(self, interval_seconds: int = 300):
        """Add job to check recommendation SLA milestone deadlines every 5 minutes.

        Args:
            interval_seconds: How often to check (default 300s = 5 min).
        """
        from apscheduler.triggers.interval import IntervalTrigger

        if self.scheduler.get_job("check_recommendation_milestone_timers"):
            self.scheduler.remove_job("check_recommendation_milestone_timers")

        self.scheduler.add_job(
            func=self._check_milestone_deadlines,
            trigger=IntervalTrigger(seconds=interval_seconds),
            id="check_recommendation_milestone_timers",
            name="Check Recommendation Milestone SLA Timers (5 min)",
            replace_existing=True,
            max_instances=1,
            coalesce=True,
        )
        logger.info("Added milestone timer job (every %ds)", interval_seconds)

    def _check_milestone_deadlines(self):
        """Background job: check SLA breaches and escalate."""
        try:
            from app.services.recommendation_milestone_service import (
                get_recommendation_milestone_service,
            )

            svc = get_recommendation_milestone_service()
            breaches = svc.check_breaches()
            for breach in breaches:
                rec = breach["recommendation"]
                logger.debug(
                    "SLA breach: rec=%s milestone=%s elapsed=%.0f%%",
                    rec.id[:8],
                    breach["milestone"],
                    breach["elapsed_pct"] * 100,
                )
                # Fire escalation (Sentry → Telegram)
                import asyncio

                asyncio.get_event_loop().run_until_complete(svc.escalate_breach(rec.id, breach))
        except Exception as e:
            logger.error("Milestone deadline check failed: %s", e)

    def add_recommendation_expiry_job(self, interval_seconds: int = 21600):
        """Add a job to expire stale recommendations and dedup duplicate noise.

        Runs every 6 hours by default. For each (site_id, action_type):
          - Keeps the 10 most recent pending recommendations
          - Expires any remaining pending recommendations older than 7 days

        Args:
            interval_seconds: How often to run (default 6h). Run daily via cron
                              for production: 0 3 * * * (03:00 SAST).
        """
        from apscheduler.triggers.interval import IntervalTrigger

        if self.scheduler.get_job("recommendation_expiry"):
            self.scheduler.remove_job("recommendation_expiry")

        first_run = datetime.now() + timedelta(minutes=5)
        self.scheduler.add_job(
            func=self._run_recommendation_expiry,
            trigger=IntervalTrigger(seconds=interval_seconds),
            id="recommendation_expiry",
            name="Recommendation Expiry + Dedup (6h)",
            replace_existing=True,
            next_run_time=first_run,
            max_instances=1,
            coalesce=True,
        )
        logger.info(
            "Added recommendation expiry job: dedup top-10 + expire >7d pending (every %ds)",
            interval_seconds,
        )

    def _run_recommendation_expiry(self):
        """Sync wrapper for async recommendation expiry."""
        try:
            import asyncio

            loop = asyncio.new_event_loop()
            asyncio.set_event_loop(loop)
            try:
                expired_count, dedup_count = loop.run_until_complete(self._run_recommendation_expiry_async())
                if expired_count or dedup_count:
                    logger.info(
                        "[REC-EXPIRY] expired=%d, dedup=%d",
                        expired_count,
                        dedup_count,
                    )
            finally:
                loop.close()
        except Exception as e:
            logger.error("Recommendation expiry job failed: %s", e)

    async def _run_recommendation_expiry_async(self) -> tuple[int, int]:
        """Expire stale pending recommendations and dedup noisy duplicates.

        Returns:
            Tuple of (expired_count, dedup_count)
        """
        import asyncio

        from app.database.supabase_client import get_supabase_client

        sb = get_supabase_client()
        expired_total = 0
        dedup_total = 0

        try:
            sites_result = await asyncio.to_thread(lambda: sb.table("sites").select("code").execute())
            site_ids = [s["code"] for s in (sites_result.data or [])]
        except Exception:
            logger.debug("Could not fetch site IDs for recommendation expiry")
            return 0, 0

        cutoff = datetime.now(UTC) - timedelta(hours=EXPIRY_HOURS)

        for site_id in site_ids:
            try:
                result = await asyncio.to_thread(
                    lambda sid=site_id: (
                        sb.table("recommendations")
                        .select("id, timestamp, action_type")
                        .eq("site_id", sid)
                        .eq("status", "pending")
                        .order("timestamp", desc=True)
                        .execute()
                    )
                )

                records = result.data or []
                if not records:
                    continue

                # Partition by action_type within this site
                by_type: dict[str, list[dict]] = {}
                for r in records:
                    by_type.setdefault(r["action_type"], []).append(r)

                ids_to_expire: set[str] = set()

                for _action_type, typed_records in by_type.items():
                    # Keep top 10 most recent regardless of age
                    for r in typed_records[10:]:
                        ts = datetime.fromisoformat(r["timestamp"].replace("Z", "+00:00"))
                        if ts < cutoff:
                            ids_to_expire.add(r["id"])

                if ids_to_expire:
                    expire_ids = list(ids_to_expire)
                    # Batch update in chunks of 100
                    for i in range(0, len(expire_ids), 100):
                        chunk = expire_ids[i : i + 100]
                        try:
                            await asyncio.to_thread(
                                lambda c=chunk: (
                                    sb.table("recommendations").update({"status": "expired"}).in_("id", c).execute()
                                )
                            )
                            expired_total += len(chunk)
                            dedup_total += len(chunk)
                        except Exception as exc:
                            logger.warning(
                                "[REC-EXPIRY] Failed to expire batch for %s: %s",
                                site_id,
                                exc,
                            )

            except Exception as e:
                logger.debug(
                    "[REC-EXPIRY] Error processing site %s: %s",
                    site_id,
                    e,
                )
                continue

        return expired_total, dedup_total

    def _run_recommendation_generation_gated(self):
        """Sim-time gate wrapper around _run_recommendation_generation."""
        import app.services.lifecycle_orchestrator as _orch_mod

        now_eff = _orch_mod.get_effective_now()
        orch = _orch_mod._orchestrator_instance
        sim_running = orch is not None and orch.running

        if sim_running:
            if self._last_recommendation_sim_time is not None:
                elapsed = (now_eff - self._last_recommendation_sim_time).total_seconds()
                threshold = self.RECOMMENDATION_SIM_HOURS * 3600
                if elapsed < threshold:
                    return  # Silent skip
                logger.warning(
                    f"[SIM-GATE] Recommendation PASSED: {elapsed / 3600:.1f} sim-hours elapsed, "
                    f"sim-time={now_eff.strftime('%m-%d %H:%M')}"
                )
            else:
                logger.warning(f"[SIM-GATE] Recommendation first run, sim-time={now_eff.strftime('%m-%d %H:%M')}")
            self._last_recommendation_sim_time = now_eff

            # Occupied-hours gate: skip during simulated off-hours
            sim_hour = now_eff.hour
            sim_weekday = now_eff.weekday()
            if sim_weekday >= 5 or sim_hour < 6 or sim_hour >= 19:
                logger.info(
                    f"[SIM-GATE] Recommendation SKIPPED: simulated off-hours (hour={sim_hour}, weekday={sim_weekday})"
                )
                return
        else:
            if self._last_recommendation_sim_time is not None:
                elapsed = (datetime.now() - self._last_recommendation_sim_time).total_seconds()
                if elapsed < self._recommendation_real_interval:
                    return
            self._last_recommendation_sim_time = datetime.now()

        self._run_recommendation_generation()

    def _run_recommendation_generation(self):
        """
        Generate AI recommendations for all equipment below health threshold.
        Uses real data: health scores, install dates, service history, alerts, predictions.
        """
        try:
            import uuid
            from datetime import datetime, timedelta

            from app.database.supabase_client import get_supabase_client
            from app.models.module_registry import (
                AIRecommendation,
                ModuleType,
                RecommendationPriority,
                RecommendationType,
            )
            from app.services.maintenance_recommender import get_maintenance_recommender
            from app.services.module_registry_service import ModuleRegistryService

            logger.info("Running scheduled AI recommendation generation...")

            # Mode gate: build sets for generation + visibility control
            # Generation runs for shadow_live/supervised/automatic (not commissioning)
            # Visibility is False in shadow_live (recommendations stored but hidden from UI)
            GENERATION_ALLOWED = {"shadow_live", "advisory", "supervised", "automatic"}
            generation_site_ids: set[str] = set()
            shadow_site_ids: set[str] = set()
            try:
                from app.core.site_resolver import get_registered_site_ids
                from app.models.onboarding_phase import effective_phase

                for sid in get_registered_site_ids():
                    try:
                        _loop2 = asyncio.new_event_loop()
                        asyncio.set_event_loop(_loop2)
                        try:
                            current_stage = _loop2.run_until_complete(effective_phase(sid))
                        finally:
                            _loop2.close()
                    except Exception:
                        current_stage = "commissioning"

                    if current_stage not in GENERATION_ALLOWED:
                        logger.info(
                            f"[AI-REC] Skipping — site={sid} mode={current_stage} "
                            f"(generation requires {GENERATION_ALLOWED})"
                        )
                        continue

                    if current_stage == "shadow_live":
                        shadow_site_ids.add(sid)

                    # Also check optimization_enabled toggle
                    if self._is_optimization_enabled(sid):
                        generation_site_ids.add(sid)
                    else:
                        logger.info(
                            f"[AI-REC] Skipping recommendations for {sid} (optimization_enabled=False in site settings)"
                        )
            except Exception as gate_err:
                logger.debug(f"[AI-REC] Mode gate check failed: {gate_err}")
                generation_site_ids = None  # Disable gate on error
                shadow_site_ids = set()

            client = get_supabase_client()
            recommender = get_maintenance_recommender(client)
            module_registry = ModuleRegistryService()

            # Get ALL equipment - generate recommendations for all, not just degraded
            response = (
                client.table("equipment")
                .select(
                    "id, code, name, type, health_score, site_id, status, "
                    "install_date, last_service, manufacturer, model"
                )
                .execute()
            )

            all_equipment = response.data if response.data else []
            at_risk = len([eq for eq in all_equipment if (eq.get("health_score") or 100) < 90])
            logger.info(f"Generating recommendations for {len(all_equipment)} equipment ({at_risk} at-risk)")

            generated = 0
            for eq in all_equipment:
                try:
                    health = eq.get("health_score") or 100
                    equipment_id = eq.get("id")

                    # Get building/site code
                    site_response = client.table("sites").select("code, name").eq("id", eq.get("site_id")).execute()
                    site_code = site_response.data[0]["code"] if site_response.data else "unknown"
                    site_name = site_response.data[0]["name"] if site_response.data else "Unknown Building"

                    # Mode gate: skip equipment belonging to non-generation sites
                    if generation_site_ids is not None:
                        # Convert site code (e.g. "S002") to site resolver format ("site-002")
                        resolver_id = site_code
                        if site_code.startswith("S") and site_code[1:].isdigit():
                            resolver_id = f"site-{site_code[1:]}"
                        if resolver_id not in generation_site_ids:
                            continue

                    # Get recent alerts for this equipment (last 30 days)
                    alerts_response = (
                        client.table("alerts")
                        .select("type, severity, created_at, message")
                        .eq("equipment_id", equipment_id)
                        .gte("created_at", (datetime.now() - timedelta(days=30)).isoformat())
                        .order("created_at", desc=True)
                        .limit(5)
                        .execute()
                    )
                    recent_alerts = alerts_response.data if alerts_response.data else []

                    # Get existing prediction for this equipment
                    prediction_response = (
                        client.table("predictions")
                        .select("probability_percent, contributing_factors, evidence, recommended_action")
                        .eq("equipment_id", equipment_id)
                        .eq("status", "active")
                        .limit(1)
                        .execute()
                    )
                    prediction = prediction_response.data[0] if prediction_response.data else None

                    # Calculate days since last service
                    days_since_service = None
                    if eq.get("last_service"):
                        try:
                            last_service_date = datetime.fromisoformat(eq["last_service"].replace("Z", "+00:00"))
                            days_since_service = (datetime.now(last_service_date.tzinfo) - last_service_date).days
                        except (ValueError, TypeError):
                            pass

                    # Calculate equipment age in years
                    equipment_age_years = None
                    if eq.get("install_date"):
                        try:
                            install_date = datetime.fromisoformat(eq["install_date"].replace("Z", "+00:00"))
                            equipment_age_years = (datetime.now(install_date.tzinfo) - install_date).days / 365
                        except (ValueError, TypeError):
                            pass

                    # Build context-aware description
                    context_parts = []
                    context_parts.append(f"Health score: {health}%")

                    if equipment_age_years:
                        context_parts.append(f"Equipment age: {equipment_age_years:.1f} years")

                    if days_since_service:
                        if days_since_service > 180:
                            context_parts.append(f"⚠️ Last serviced {days_since_service} days ago (overdue)")
                        else:
                            context_parts.append(f"Last serviced {days_since_service} days ago")
                    elif days_since_service is None:
                        context_parts.append("No service history recorded")

                    if recent_alerts:
                        alert_count = len(recent_alerts)
                        context_parts.append(f"{alert_count} alert(s) in last 30 days")

                    if prediction:
                        prob = prediction.get("probability_percent", 0)
                        if prob > 70:
                            context_parts.append(f"🔴 High failure probability: {prob}%")
                        elif prob > 50:
                            context_parts.append(f"🟡 Moderate failure probability: {prob}%")

                    # Determine recommendation type based on health
                    is_healthy = health >= 90

                    if is_healthy:
                        # HEALTHY equipment: Preventive maintenance & optimization
                        risk_level = "low"
                        rec_type = RecommendationType.OPTIMIZATION

                        # Generate preventive actions based on equipment type and service history
                        enhanced_actions = []
                        eq_type = eq.get("type", "").lower()

                        # Service-based recommendations
                        if days_since_service:
                            if days_since_service > 90:
                                enhanced_actions.append(
                                    f"Schedule preventive maintenance (last service {days_since_service} days ago)"
                                )
                            if days_since_service > 180:
                                enhanced_actions.append("Filter/belt inspection recommended")
                        else:
                            enhanced_actions.append("Establish maintenance schedule")

                        # Type-specific optimization suggestions
                        if "chiller" in eq_type:
                            enhanced_actions.extend(
                                [
                                    "Review chilled water setpoint for optimization",
                                    "Check condenser approach temperature",
                                ]
                            )
                        elif "ahu" in eq_type or "fcu" in eq_type:
                            enhanced_actions.extend(
                                [
                                    "Verify economizer operation",
                                    "Check supply air temperature setpoint",
                                ]
                            )
                        elif "vav" in eq_type:
                            enhanced_actions.append("Review zone airflow minimums")
                        elif "lighting" in eq_type or "luminaire" in eq_type:
                            enhanced_actions.append("Verify daylight harvesting settings")
                        elif "generator" in eq_type:
                            enhanced_actions.append("Schedule monthly test run")
                        else:
                            enhanced_actions.append("Verify operational parameters")

                        priority = RecommendationPriority.LOW
                        title_prefix = "Optimization"

                    else:
                        # DEGRADED equipment: Maintenance recommendations
                        risk_level = "critical" if health < 50 else ("high" if health < 70 else "medium")
                        rec_type = RecommendationType.MAINTENANCE

                        recommendation = recommender._generate_fallback_recommendation(
                            equipment_id=eq.get("code", eq["id"]),
                            equipment_type=eq.get("type", "unknown"),
                            risk_level=risk_level,
                            predicted_failure="health_degradation",
                        )

                        enhanced_actions = list(recommendation.immediate_actions)
                        if days_since_service and days_since_service > 180:
                            enhanced_actions.insert(0, "Schedule overdue preventive maintenance")
                        if recent_alerts and len(recent_alerts) >= 3:
                            enhanced_actions.insert(0, "Review recurring alert pattern")
                        if prediction and prediction.get("probability_percent", 0) > 70:
                            enhanced_actions.insert(
                                0, prediction.get("recommended_action", "Address predicted failure")
                            )

                        # Determine priority based on multiple factors
                        priority = RecommendationPriority.MEDIUM
                        if health < 50 or (prediction and prediction.get("probability_percent", 0) > 80):
                            priority = RecommendationPriority.CRITICAL
                        elif health < 70 or (days_since_service and days_since_service > 365):
                            priority = RecommendationPriority.HIGH

                        title_prefix = "Maintenance Required"

                    description = ". ".join(context_parts)
                    if enhanced_actions:
                        description += f". Recommended: {enhanced_actions[0]}"

                    ai_rec = AIRecommendation(
                        recommendation_id=str(uuid.uuid4()),
                        timestamp=datetime.now().isoformat(),
                        source_module=ModuleType.HVAC,
                        recommendation_type=rec_type,
                        priority=priority,
                        title=f"{title_prefix}: {eq['name']}",
                        description=description,
                        confidence=0.90 if prediction else 0.75,
                        related_modules=[],
                        telemetry_context={
                            "equipment_id": eq.get("code", eq["id"]),
                            "equipment_type": eq.get("type", "unknown"),
                            "health_score": health,
                            "site_id": site_code,
                            "site_name": site_name,
                            "manufacturer": eq.get("manufacturer"),
                            "model": eq.get("model"),
                            "install_date": eq.get("install_date"),
                            "last_service": eq.get("last_service"),
                            "days_since_service": days_since_service,
                            "equipment_age_years": round(equipment_age_years, 1) if equipment_age_years else None,
                            "recent_alert_count": len(recent_alerts),
                            "failure_probability": prediction.get("probability_percent") if prediction else None,
                            "contributing_factors": prediction.get("contributing_factors") if prediction else None,
                        },
                        suggested_action={
                            "type": "optimize" if is_healthy else "schedule_maintenance",
                            "priority": "low" if is_healthy else risk_level,
                            "immediate_actions": enhanced_actions[:5],
                            "evidence": [
                                f"Health at {health}%",
                                f"{len(recent_alerts)} alerts in 30 days" if recent_alerts else "No recent alerts",
                                f"Service overdue by {days_since_service - 180} days"
                                if days_since_service and days_since_service > 180
                                else None,
                                f"Failure probability {prediction.get('probability_percent')}%" if prediction else None,
                            ],
                        },
                        auto_actionable=False,
                        acknowledged=False,
                        resolved=False,
                    )

                    module_registry.add_recommendation(site_code, ai_rec)
                    self._notify_recommendation_alert(site_code, ai_rec)

                    # Persist to recommendations table for Cockpit UI
                    try:
                        from app.models.recommendation import ActionRiskLevel, RecommendationStatus

                        _priority_map = {
                            RecommendationPriority.LOW: ActionRiskLevel.LOW,
                            RecommendationPriority.MEDIUM: ActionRiskLevel.MEDIUM,
                            RecommendationPriority.HIGH: ActionRiskLevel.HIGH,
                            RecommendationPriority.CRITICAL: ActionRiskLevel.CRITICAL,
                        }
                        _conf_str = (
                            "high" if ai_rec.confidence >= 0.85 else "medium" if ai_rec.confidence >= 0.6 else "low"
                        )
                        _eq_id = ai_rec.telemetry_context.get("equipment_id", "") if ai_rec.telemetry_context else ""
                        _action_type = (
                            "optimization"
                            if ai_rec.recommendation_type and ai_rec.recommendation_type.name == "OPTIMIZATION"
                            else "maintenance"
                        )

                        client.table("recommendations").insert(
                            {
                                "id": str(uuid.uuid4()),
                                "site_id": site_code,
                                "timestamp": datetime.utcnow().isoformat(),
                                "action_type": _action_type,
                                "risk_level": _priority_map.get(ai_rec.priority, ActionRiskLevel.MEDIUM).value,
                                "target_equipment": _eq_id,
                                "action": ai_rec.suggested_action or {},
                                "reason": (ai_rec.title + ": " + ai_rec.description)[:500],
                                "expected_impact": {},
                                "confidence": _conf_str,
                                "confidence_score": ai_rec.confidence or 0.0,
                                "profile": "health_monitor",
                                "multi_objective_score": 0.0,
                                "status": RecommendationStatus.PENDING.value,
                                "requires_approval": True,
                                "shadow_mode": False,
                            }
                        ).execute()
                    except Exception as e:
                        logger.warning("Failed to persist recommendation to DB: %s", e)

                    generated += 1

                except Exception as e:
                    logger.warning(f"Failed to generate recommendation for {eq.get('name', 'unknown')}: {e}")

            logger.info(f"AI recommendation generation complete: {generated} generated")

        except Exception as e:
            logger.error(f"Failed to run recommendation generation: {e}")

    def _notify_recommendation_alert(self, site_code: str, ai_rec) -> None:
        """Send Telegram alert for critical/high severity recommendations (fire-and-forget via thread pool)."""
        priority = ai_rec.priority.name.lower() if hasattr(ai_rec.priority, "name") else "low"
        if priority not in ("critical", "high"):
            return

        equipment_id = (
            ai_rec.telemetry_context.get("equipment_id", "unknown") if ai_rec.telemetry_context else "unknown"
        )
        title = ai_rec.title[:100]
        confidence = ai_rec.confidence or 0
        enforcement = (
            ai_rec.suggested_action.get("type", "pending_approval") if ai_rec.suggested_action else "pending_approval"
        )

        level_icon = "\xf0\x9f\x94\xb4" if priority == "critical" else "\xf0\x9f\x9f\xa1"
        message = (
            f"{level_icon} *SENTINEL Advisory — {site_code.upper()}*\n"
            f"Equipment: `{equipment_id}`\n"
            f"Priority: {priority.upper()}\n"
            f"Finding: {title}\n"
            f"Confidence: {confidence:.0%}\n"
            f"Action: {enforcement}\n"
            f"→ Review in Cockpit approval queue"
        )

        # Fire-and-forget: dispatch to a background thread so it never blocks the scheduler cycle.
        try:
            import asyncio
            import concurrent.futures

            def _thread_target():
                try:

                    async def _send_async():
                        from app.services.telegram_message_sender import get_telegram_sender

                        sender = get_telegram_sender()
                        from app.config.settings import settings

                        chat_id = getattr(settings, "telegram_alert_chat_id", None) or getattr(
                            settings, "sentry_fm_chat_id", None
                        )
                        if chat_id:
                            await sender.send_text(str(chat_id), message, parse_mode="Markdown")

                    asyncio.run(_send_async())
                except Exception as e:
                    logger.warning(f"Failed to send Telegram alert for {equipment_id}: {e}")

            with concurrent.futures.ThreadPoolExecutor(max_workers=4, thread_name_prefix="telegram_alert") as pool:
                pool.submit(_thread_target)
        except Exception as e:
            logger.warning(f"Failed to dispatch Telegram alert for {equipment_id}: {e}")

    def add_recommendation_digest_job(self):
        """Send a recommendation digest to Telegram at 07:45 SAST Mon-Fri."""
        from apscheduler.triggers.cron import CronTrigger

        from app.services.background_scheduler import _run_recommendation_digest_sync

        if self.scheduler.get_job("recommendation_digest"):
            self.scheduler.remove_job("recommendation_digest")

        self.scheduler.add_job(
            func=_run_recommendation_digest_sync,
            trigger=CronTrigger(hour=5, minute=45, day_of_week="mon-fri"),
            id="recommendation_digest",
            name="Recommendation Digest (07:45 SAST)",
            replace_existing=True,
            misfire_grace_time=3600,
        )
        logger.info("recommendation_digest job registered — 07:45 SAST Mon-Fri")

    def add_daily_health_sweep_job(self):
        """Run a full equipment health sweep every weekday at 08:00 SAST.

        Generates recommendations for all equipment with health_score < 90 or
        elevated anomaly scores, bypassing the normal occupancy schedule gate.
        This ensures issues are caught even outside business hours.
        """
        from apscheduler.triggers.cron import CronTrigger

        if self.scheduler.get_job("daily_health_sweep"):
            self.scheduler.remove_job("daily_health_sweep")

        self.scheduler.add_job(
            func=_run_daily_health_sweep_sync,
            trigger=CronTrigger(hour=6, minute=0, day_of_week="mon-fri"),
            id="daily_health_sweep",
            name="Daily Health Sweep (08:00 SAST Mon-Fri)",
            replace_existing=True,
            misfire_grace_time=3600,
        )
        logger.info("daily_health_sweep job registered — 06:00 UTC (08:00 SAST) Mon-Fri")

    def add_demand_aware_coordination_job(self, interval_seconds: int = 300):
        """
        Add a job to run demand-aware coordination for peak shaving.

        Monitors NMD headroom and coordinates multi-module shaving actions.

        Args:
            interval_seconds: How often to run (default: 300 seconds = 5 minutes)
        """
        # Remove existing job if it exists
        if self.scheduler.get_job("demand_aware_coordination"):
            self.scheduler.remove_job("demand_aware_coordination")
            logger.info("Removed existing demand coordination job")

        # Add new job
        self.scheduler.add_job(
            func=self._run_demand_aware_coordination,
            trigger=IntervalTrigger(seconds=interval_seconds),
            id="demand_aware_coordination",
            name="Demand-Aware Coordination for Peak Shaving",
            replace_existing=True,
        )
        logger.info(f"Added demand coordination job with {interval_seconds}s interval")

    def _run_demand_aware_coordination(self):
        """
        Run demand-aware coordination for all sites.

        Evaluates current demand state and generates multi-module recommendations
        for peak shaving when NMD headroom is below thresholds.
        """
        try:
            import asyncio

            from app.services.demand_aware_coordinator import get_demand_aware_coordinator

            logger.debug("Running demand-aware coordination evaluation...")

            coordinator = get_demand_aware_coordinator()

            # Get all sites to evaluate
            sites = self._get_all_sites()

            if not sites:
                logger.debug("No sites configured for demand coordination")
                return

            # Evaluate demand state for each site
            for site in sites:
                site_id = site.get("id") or site.get("code")
                if not site_id:
                    continue

                try:
                    recommendation = asyncio.run(coordinator.evaluate_current_state(site_id))

                    if recommendation:
                        logger.info(
                            f"Site {site_id}: Generated {recommendation['type']} recommendation - "
                            f"Modules: {recommendation.get('modules_involved')}, "
                            f"Reduction: {recommendation.get('estimated_reduction_kw'):.0f}kW"
                        )

                except Exception as e:
                    logger.warning(f"Demand coordination failed for site {site_id}: {e}")

        except Exception as e:
            logger.error(f"Failed to run demand-aware coordination: {e}")

    def _get_all_sites(self):
        """Get all configured sites for demand coordination."""
        try:
            from app.core.site_resolver import get_registered_sites

            return get_registered_sites()
        except Exception as e:
            logger.debug(f"Could not load registered sites: {e}")
        return []

    def add_ml_retraining_job(self, interval_seconds: int = 86400):
        """
        Add a job to auto-retrain stale ML models periodically.

        Monitors model freshness and performance metrics. Triggers retraining
        when models are stale (>30 days) or underperforming (R² < 0.65).

        Only retrains ONE model per cycle to avoid overload.

        Args:
            interval_seconds: How often to check for stale models (default: 86400 = 24 hours)
        """
        # Remove existing job if it exists
        if self.scheduler.get_job("auto_retrain_stale_models"):
            self.scheduler.remove_job("auto_retrain_stale_models")
            logger.info("Removed existing ML retraining job")

        # Add new job
        self.scheduler.add_job(
            func=self._run_ml_retraining,
            trigger=IntervalTrigger(seconds=interval_seconds),
            id="auto_retrain_stale_models",
            name="Auto-Retrain Stale ML Models",
            replace_existing=True,
        )
        logger.info(f"Added ML retraining job with {interval_seconds}s interval (checks daily for stale models)")

    def add_anomaly_weekly_retrain_job(self, interval_hours: int = 168):
        """
        Add a weekly anomaly model retraining job (Isolation Forest on zone temp + HVAC power).

        Runs every Sunday at 02:00. Delegates to the existing drift detection job since
        that layer already handles anomaly detection and retraining governance.

        Args:
            interval_hours: Interval in hours (default: 168 = weekly). Ignored — always runs weekly.
        """
        from apscheduler.triggers.cron import CronTrigger

        if self.scheduler.get_job("anomaly_weekly_retrain"):
            self.scheduler.remove_job("anomaly_weekly_retrain")
            logger.info("Removed existing anomaly weekly retrain job")

        self.scheduler.add_job(
            func=self._run_drift_detection,
            trigger=CronTrigger(day_of_week="sun", hour=2, minute=0),
            id="anomaly_weekly_retrain",
            name="Anomaly Model Weekly Retrain (Isolation Forest)",
            replace_existing=True,
        )
        logger.info("Added anomaly weekly retrain job (Sunday 02:00, delegates to drift detection)")

    def add_drift_detection_job(self, interval_seconds: int = 3600):
        """
        Add a job to monitor for data/model drift and trigger retraining if detected.

        Detects when incoming data patterns have changed significantly from training data,
        or when model predictions are degrading. Automatically triggers retraining when:
        - 3+ features show statistical drift
        - Prediction accuracy drops >10%

        Runs every hour to catch drift early before models become stale.

        Args:
            interval_seconds: How often to check for drift (default: 3600 = 1 hour)
        """
        # Remove existing job if it exists
        if self.scheduler.get_job("drift_detection_monitor"):
            self.scheduler.remove_job("drift_detection_monitor")
            logger.info("Removed existing drift detection job")

        # Add new job
        self.scheduler.add_job(
            func=self._run_drift_detection,
            trigger=IntervalTrigger(seconds=interval_seconds),
            id="drift_detection_monitor",
            name="Drift Detection & Auto-Retrain Monitor",
            replace_existing=True,
        )
        logger.info(f"Added drift detection job with {interval_seconds}s interval (monitors for data/model drift)")

    def _run_drift_detection(self):
        """
        Check for data/model drift and trigger retraining if thresholds exceeded.

        Runs as background job - automatically triggers retraining when drift detected.
        Helps system adapt to changing building behaviors and conditions.
        """
        try:
            from ml.monitoring.triggers import RetrainingTrigger

            logger.debug("Running drift detection check...")

            trigger = RetrainingTrigger()
            result = trigger.evaluate_and_trigger()

            # Update Prometheus drift gauge (Phase 127)
            try:
                from app.api.metrics import sentinel_model_drift_alerts
                from app.core.site_resolver import get_registered_site_ids

                # Count triggers per model_type
                drift_counts: dict[str, int] = {}
                for t in result.get("triggered", []):
                    mt = t.get("model_type", "unknown").upper()
                    drift_counts[mt] = drift_counts.get(mt, 0) + 1

                # Set gauge for each registered site and model type
                for site_id in get_registered_site_ids():
                    for model_type in ["LSTM", "AUTOENCODER", "CLASSIFIER"]:
                        sentinel_model_drift_alerts.labels(site_id=site_id, model_type=model_type).set(
                            drift_counts.get(model_type, 0)
                        )
            except Exception as metrics_err:
                logger.debug(f"Drift metrics update skipped: {metrics_err}")

            if result.get("triggers_fired", 0) > 0:
                logger.info(
                    f"🔄 Drift detected! Triggered {result['triggers_fired']} retraining job(s). "
                    f"Skipped {result.get('triggers_skipped', 0)} (in cooldown)"
                )
            else:
                logger.debug("No drift detected - models performing normally")

        except Exception as e:
            logger.error(f"Failed to run drift detection check: {e}", exc_info=True)

    def _run_ml_retraining(self):
        """
        Check for stale ML models and trigger retraining if needed.

        Runs as background job - only retrains ONE model per cycle to avoid
        system overload. Models are prioritized by age and performance degradation.
        """
        try:
            from ml.training.retraining_scheduler import get_retraining_scheduler

            logger.info("Running scheduled ML model staleness check...")

            scheduler = get_retraining_scheduler()

            # Check all models for staleness/performance issues
            checks = scheduler.check_all_models()

            # Filter for models that need retraining
            stale_models = [c for c in checks if c.get("needs_retrain", False)]

            if not stale_models:
                logger.info("✅ All ML models are fresh and performing well - no retraining needed")
                return

            # Get priority model (oldest first, then worst performing)
            priority_model = sorted(
                stale_models,
                key=lambda m: (
                    -999 if m["status"] == "missing" else m.get("age_days", 0),  # Missing models highest priority
                    m.get("r2_score", 1.0),  # Then by R² score (lowest first)
                ),
            )[0]

            logger.info(
                f"Found {len(stale_models)} stale/underperforming models. "
                f"Retraining priority: {priority_model['equipment_type']} ({priority_model['model_type']}) - "
                f"Status: {priority_model['status']},"
                f" Age: {priority_model['age_days']}d,"
                f" R²: {priority_model.get('r2_score', 'N/A')}"
            )

            # Trigger retraining for ONE model only (others will be retrained in subsequent cycles)
            retrain_result = scheduler.trigger_retraining(
                model_type=priority_model["model_type"],
                equipment_type=priority_model["equipment_type"],
                reason=priority_model.get("reason", "scheduled_maintenance"),
            )

            if retrain_result.success:
                logger.info(
                    f"✅ Retraining triggered for {retrain_result.model_type}/{retrain_result.equipment_type}. "
                    f"New model ID: {retrain_result.new_model_id}"
                )
            else:
                logger.error(f"❌ Failed to trigger retraining: {retrain_result.error}")

            # Log summary of remaining stale models (for monitoring)
            if len(stale_models) > 1:
                remaining = stale_models[1:]
                remaining_strs = [f"{m['equipment_type']} ({m['status']})" for m in remaining]
                logger.info(f"Remaining stale models ({len(remaining)}): {', '.join(remaining_strs)}")

        except Exception as e:
            logger.error(f"Failed to run ML model retraining check: {e}", exc_info=True)

    def add_mv_verification_job(self, interval_seconds: int = 900):
        """Add periodic M&V verification job for applied recommendations."""
        if self.scheduler.get_job("mv_verification"):
            self.scheduler.remove_job("mv_verification")
            logger.info("Removed existing M&V verification job")

        self.scheduler.add_job(
            func=self._run_mv_verifications,
            trigger=IntervalTrigger(seconds=interval_seconds),
            id="mv_verification",
            name="Run Pending M&V Verifications",
            replace_existing=True,
        )
        logger.info(f"Added M&V verification job with {interval_seconds}s interval")

    def _run_mv_verifications(self):
        """Execute pending M&V verifications whose measurement window has elapsed."""
        try:
            from app.services.mv_verification_service import get_mv_verification_service

            mv_service = get_mv_verification_service()

            loop = asyncio.new_event_loop()
            asyncio.set_event_loop(loop)
            try:
                verified = loop.run_until_complete(mv_service.run_pending_verifications())
            finally:
                loop.close()

            if verified:
                logger.info(
                    "M&V verification cycle complete: verified=%s pending=%s",
                    len(verified),
                    mv_service.get_pending_count(),
                )
            else:
                logger.debug("M&V verification cycle complete: no tasks ready")

        except Exception as e:
            logger.error(f"Failed to run M&V verification cycle: {e}", exc_info=True)

    def add_feedback_scoring_refresh_job(self, interval_seconds: int = 900):
        """Add periodic refresh of feedback-derived scoring inputs."""
        if self.scheduler.get_job("feedback_scoring_refresh"):
            self.scheduler.remove_job("feedback_scoring_refresh")
            logger.info("Removed existing feedback scoring refresh job")

        self.scheduler.add_job(
            func=self._run_feedback_scoring_refresh,
            trigger=IntervalTrigger(seconds=interval_seconds),
            id="feedback_scoring_refresh",
            name="Refresh Feedback Scoring Inputs",
            replace_existing=True,
        )
        logger.info(f"Added feedback scoring refresh job with {interval_seconds}s interval")

    def _run_feedback_scoring_refresh(self):
        """Refresh module score multipliers from latest verified outcomes."""
        try:
            from app.services.ml_feedback_service import get_ml_feedback_service

            result = get_ml_feedback_service().refresh_scoring_inputs()
            refreshed_sites = result.get("refreshed_sites", 0)
            if refreshed_sites > 0:
                logger.info(
                    "Feedback scoring inputs refreshed for %s site(s): %s",
                    refreshed_sites,
                    ", ".join(result.get("site_ids", [])),
                )
            else:
                logger.debug("Feedback scoring inputs refresh skipped: no module outcomes yet")
        except Exception as e:
            logger.error(f"Failed to refresh feedback scoring inputs: {e}", exc_info=True)

    def add_feedback_retraining_job(
        self,
        interval_seconds: int = 3600,
        min_records: int = 10,
        min_success_rate: float = 70.0,
        cooldown_hours: int = 24,
    ):
        """Add periodic feedback-driven retraining trigger job."""
        if self.scheduler.get_job("feedback_retraining_trigger"):
            self.scheduler.remove_job("feedback_retraining_trigger")
            logger.info("Removed existing feedback-driven retraining job")

        self._feedback_retraining_policy = {
            "min_records": int(min_records),
            "min_success_rate": float(min_success_rate),
            "cooldown_hours": int(cooldown_hours),
        }

        self.scheduler.add_job(
            func=self._run_feedback_retraining,
            trigger=IntervalTrigger(seconds=interval_seconds),
            id="feedback_retraining_trigger",
            name="Feedback-Driven ML Retraining Trigger",
            replace_existing=True,
        )
        logger.info(
            "Added feedback retraining job: interval=%ss min_records=%s min_success_rate=%s%% cooldown=%sh",
            interval_seconds,
            min_records,
            min_success_rate,
            cooldown_hours,
        )

    def _run_feedback_retraining(self):
        """Trigger retraining when module outcome success drops below threshold."""
        try:
            from app.services.ml_feedback_service import get_ml_feedback_service
            from ml.training.retraining_scheduler import get_retraining_scheduler

            policy = self._feedback_retraining_policy
            min_records = int(policy["min_records"])
            min_success_rate = float(policy["min_success_rate"])
            cooldown_hours = int(policy["cooldown_hours"])
            cooldown_seconds = cooldown_hours * 3600

            summary = get_ml_feedback_service().get_module_feedback_summary()
            counts = summary.get("counts", {})
            success_rates = summary.get("success_rates", {})

            if not counts:
                logger.debug("Feedback retraining check skipped: no module outcomes")
                return

            # Map module outcomes to model equipment types supported by retraining scheduler.
            module_to_equipment = {
                "hvac": ["chiller", "ahu", "fcu", "vav", "pump"],
                "energy": ["generator", "ups", "pump"],
                "power": ["generator", "ups", "pump"],
                "bess": ["ups"],
                "solar": ["generator"],
            }

            candidates = []
            for module_name, total_records in counts.items():
                rate = float(success_rates.get(module_name, 0.0))
                if int(total_records) >= min_records and rate < min_success_rate:
                    candidates.append((module_name, int(total_records), rate))

            if not candidates:
                logger.debug("Feedback retraining check complete: no modules below success threshold")
                return

            candidates.sort(key=lambda item: item[2])  # lowest success rate first
            retraining = get_retraining_scheduler()

            # Trigger at most one retraining per cycle to avoid overload.
            for module_name, total_records, rate in candidates:
                equipment_types = module_to_equipment.get(module_name, [])
                if not equipment_types:
                    continue

                for equipment_type in equipment_types:
                    cooldown_key = f"{module_name}:{equipment_type}:lstm"
                    if self._is_feedback_retraining_in_cooldown(cooldown_key, cooldown_seconds):
                        continue

                    reason = (
                        f"feedback_loop_{module_name}: success_rate={rate:.1f}% "
                        f"records={total_records} threshold<{min_success_rate:.1f}%"
                    )
                    result = retraining.trigger_retraining(
                        model_type="lstm",
                        equipment_type=equipment_type,
                        reason=reason,
                    )

                    if result.success:
                        self._feedback_retraining_last_trigger[cooldown_key] = datetime.now()
                        logger.info(
                            "Feedback retraining triggered: module=%s equipment=%s success_rate=%.1f%% records=%s",
                            module_name,
                            equipment_type,
                            rate,
                            total_records,
                        )
                    else:
                        logger.warning(
                            "Feedback retraining trigger failed: module=%s equipment=%s error=%s",
                            module_name,
                            equipment_type,
                            result.error,
                        )
                    return

            logger.debug("Feedback retraining check complete: candidates exist but all in cooldown or unmapped")
        except Exception as e:
            logger.error(f"Failed to run feedback retraining check: {e}", exc_info=True)

    def _is_feedback_retraining_in_cooldown(self, key: str, cooldown_seconds: int) -> bool:
        """Return True when feedback-triggered retraining is still in cooldown window."""
        last_trigger = self._feedback_retraining_last_trigger.get(key)
        if not last_trigger:
            return False
        elapsed_seconds = (datetime.now() - last_trigger).total_seconds()
        return elapsed_seconds < float(cooldown_seconds)

    def add_sentry_notification_job(self, interval_seconds: int = 30):
        """
        Add a job to process pending Sentry notifications periodically.

        Ensures that when equipment health degrades to warning/critical,
        technicians receive Telegram notifications promptly.

        Args:
            interval_seconds: How often to check pending notifications (default: 30 seconds)
        """
        # Remove existing job if it exists
        if self.scheduler.get_job("process_sentry_notifications"):
            self.scheduler.remove_job("process_sentry_notifications")
            logger.info("Removed existing Sentry notification job")

        # Add new job
        self.scheduler.add_job(
            func=self._process_sentry_notifications,
            trigger=IntervalTrigger(seconds=interval_seconds),
            id="process_sentry_notifications",
            name="Process Sentry Notifications",
            replace_existing=True,
        )
        logger.info(f"Added Sentry notification job with {interval_seconds}s interval")

    def _process_sentry_notifications(self):
        """Process pending Sentry notifications directly (no HTTP self-call)."""
        try:
            logger.debug("Processing pending Sentry notifications...")

            from app.database.repositories.service_record_repository import ServiceRecordRepository

            service_repo = ServiceRecordRepository()

            # Direct async call instead of HTTP self-call to avoid timeout/loop issues
            async def _check_pending():
                pending = await service_repo.list(filters={"status": "notified"})
                return pending or []

            if self._main_loop and self._main_loop.is_running():
                future = asyncio.run_coroutine_threadsafe(_check_pending(), self._main_loop)
                pending = future.result(timeout=10)
            else:
                pending = asyncio.run(_check_pending())

            if pending:
                pending_codes = [sr.get("code") for sr in pending if sr.get("code")]
                if pending_codes:
                    logger.info(
                        "📲 %d pending notifications waiting for Sentry delivery (%s)",
                        len(pending_codes),
                        ", ".join(pending_codes[:5]),
                    )
            # No action needed — notifications are delivered via Sentry gateway interaction

        except Exception as e:
            logger.error(f"Failed to process Sentry notifications: {e}")

        # Clean up expired Telegram conversation sessions
        try:
            from app.services.telegram_conversation_manager import get_conversation_manager

            get_conversation_manager().cleanup_expired()
        except Exception as e:
            logger.debug(f"Telegram session cleanup: {e}")

    def add_fire_pump_compliance_job(self, interval_seconds: int = 86400) -> None:
        """
        Add a daily job to check fire pump compliance and emit overdue alerts.

        Args:
            interval_seconds: How often to check (default: 86400 = 1 day)
        """
        if self.scheduler.get_job("check_fire_pump_compliance"):
            self.scheduler.remove_job("check_fire_pump_compliance")
            logger.info("Removed existing fire pump compliance job")

        self.scheduler.add_job(
            func=self._check_fire_pump_compliance,
            trigger=IntervalTrigger(seconds=interval_seconds),
            id="check_fire_pump_compliance",
            name="Check Fire Pump Compliance",
            replace_existing=True,
        )
        logger.info(f"Added fire pump compliance job ({interval_seconds}s interval)")

    def _check_fire_pump_compliance(self) -> None:
        """Check all sites for overdue fire pump inspections and emit alerts."""
        try:
            from app.core.site_resolver import get_registered_site_ids
            from app.services.fire_pump_compliance_service import (
                get_fire_pump_compliance_service,
            )

            site_ids = get_registered_site_ids()
            if not site_ids:
                return

            async def _check():
                svc = get_fire_pump_compliance_service()
                for site_code in site_ids:
                    try:
                        alerts = await svc.get_overdue_alerts(site_code)
                        if alerts:
                            for alert in alerts:
                                logger.warning(
                                    f"Fire pump compliance alert | "
                                    f"equipment_id={alert.equipment_id} "
                                    f"site_code={alert.site_code} "
                                    f"last_test_date={alert.last_test_date} "
                                    f"days_overdue={alert.days_overdue} "
                                    f"regulatory_reference={alert.regulatory_reference}"
                                )
                    except Exception as site_err:
                        logger.warning(f"Fire pump compliance check failed for {site_code}: {site_err}")

            if self._main_loop and self._main_loop.is_running():
                future = asyncio.run_coroutine_threadsafe(_check(), self._main_loop)
                future.result(timeout=30)
            else:
                asyncio.run(_check())

        except Exception as e:
            logger.error(f"Failed to check fire pump compliance: {e}")

    def add_simulation_queue_processor_job(self, interval_seconds: int = 10) -> None:
        """
        Add background job to process queued lifecycle simulations.
        Runs every N seconds to start next queued simulation.

        Args:
            interval_seconds: How often to check queue (default 10s)
        """
        self.scheduler.add_job(
            func=self._process_simulation_queue,
            trigger="interval",
            seconds=interval_seconds,
            id="process_simulation_queue",
            name="Process Simulation Queue",
            replace_existing=True,
        )
        logger.info(f"Added simulation queue processor (interval: {interval_seconds}s)")

    def _process_simulation_queue(self) -> None:
        """
        Poll JSON store for queued simulations and start one.
        Prevents multiple concurrent simulations (max 1 at a time).

        Uses the main event loop so that background asyncio tasks
        (like the simulation loop) survive after this function returns.
        """
        try:
            if self._main_loop and self._main_loop.is_running():
                future = asyncio.run_coroutine_threadsafe(self._process_simulation_queue_async(), self._main_loop)
                future.result(timeout=300)
            else:
                asyncio.run(self._process_simulation_queue_async())
        except Exception as e:
            logger.error(f"Error processing simulation queue: {e}", exc_info=True)

    async def _process_simulation_queue_async(self) -> None:
        """Async implementation of queue processor.

        Reads queued tasks from JSON simulation store (not Supabase).
        The building simulation is independent of SENTINEL's database.
        """
        try:
            # Check all registered building stores for queued tasks
            from app.core.site_resolver import get_registered_site_ids
            from app.services.simulation_orchestrator import (
                create_orchestrator,
                get_simulation_by_task_id,
                register_simulation,
            )
            from app.services.simulation_store import get_simulation_store

            site_ids = get_registered_site_ids()
            if not site_ids:
                return  # No registered buildings — silent return

            queued_tasks = []
            store = None
            for _sid in site_ids:
                store = get_simulation_store(_sid)
                queued_tasks = store.find_queued_tasks(simulation_type="lifecycle")
                if queued_tasks:
                    break

            if not queued_tasks:
                return  # No queued tasks — silent return

            task = queued_tasks[0]  # FIFO: oldest first
            task_id = str(task["task_id"])
            scenario = task.get("scenario", "sentinel_annual")
            logger.info(f"Found queued simulation task: {task_id}, scenario: {scenario}")

            # Validate task has required fields
            if not scenario:
                logger.warning(f"Task {task_id} missing scenario, marking as stopped")
                store.update_task_progress(task_id, {"status": "stopped", "error_message": "Missing scenario"})
                return

            # Check if already running (prevent double-start)
            if get_simulation_by_task_id(task_id):
                logger.info(f"Task {task_id} already running, skipping")
                return

            # Mark as running in JSON store
            store.update_task_progress(task_id, {"status": "running"})
            logger.info(f"Starting lifecycle simulation task {task_id}")

            # Create a dedicated orchestrator per task/site.
            # The global lifecycle singleton is not safe for queued multi-site runs.
            site_id = task.get("site_id", site_ids[0] if site_ids else "unknown")
            orchestrator = create_orchestrator(task_id=task_id, site_id=site_id)
            register_simulation(task_id, orchestrator)

            # Start simulation
            await self._run_simulation_task(
                task_id,
                orchestrator,
                scenario=scenario,
                duration_minutes=float(task.get("duration_minutes", 3650.0)),
            )

        except Exception as e:
            logger.error(f"Error in simulation queue processor: {e}", exc_info=True)
            # If we marked a task as "running" but failed to start it, revert to stopped
            # to prevent stale "running" state that causes frontend looping
            if queued_tasks:
                failed_task_id = str(queued_tasks[0].get("task_id", ""))
                if failed_task_id and store:
                    try:
                        task_data = store.get_task_progress(failed_task_id)
                        if task_data.get("status") == "running":
                            store.update_task_progress(
                                failed_task_id,
                                {"status": "stopped", "error_message": f"Queue processor error: {e}"},
                            )
                            logger.info(f"Reverted failed task {failed_task_id} to stopped")
                    except Exception:
                        pass

    async def _run_simulation_task(self, task_id: str, orchestrator, scenario: str, duration_minutes: float) -> None:
        """
        Run a lifecycle simulation task and update JSON store on completion.
        Supports crash recovery by loading state from checkpoint if available.

        Args:
            task_id: Task identifier
            orchestrator: LifecycleOrchestrator instance
            scenario: Scenario name (fault_day, sentinel_annual, etc)
            duration_minutes: Simulation duration in real minutes
        """
        from datetime import datetime

        from app.services.lifecycle_orchestrator import ALL_SCENARIOS
        from app.services.simulation_orchestrator import unregister_simulation
        from app.services.simulation_store import get_simulation_store

        _fallback_site = "unknown"
        try:
            from app.core.site_resolver import get_registered_site_ids as _get_sids

            _sids = _get_sids()
            if _sids:
                _fallback_site = _sids[0]
        except Exception:
            pass
        _orch_site = orchestrator.site_id if hasattr(orchestrator, "site_id") else _fallback_site
        store = get_simulation_store(_orch_site)
        is_recovery = False

        try:
            # Check if this is a crash recovery (has state_snapshot in JSON store)
            task_data = store.get_task_progress(task_id)
            state_snapshot = task_data.get("state_snapshot")

            if state_snapshot:
                is_recovery = True
                logger.info(f"Recovering simulation from checkpoint: task {task_id}")

            if is_recovery and state_snapshot:
                # CRASH RECOVERY PATH: Restore full orchestrator state from checkpoint
                orchestrator.current_scenario = ALL_SCENARIOS.get(scenario, ALL_SCENARIOS["sentinel_annual"])

                is_annual_scenario = "annual" in scenario.lower()
                orchestrator.max_days = 365 if is_annual_scenario else 1
                orchestrator.max_cycles = 1
                orchestrator.speed_multiplier = max(
                    0.1, min(10000, float(state_snapshot.get("speed_multiplier", 10.0)))
                )

                # Restore all state from checkpoint via deserialize_state
                restored = orchestrator.deserialize_state(state_snapshot)
                orchestrator.simulated_time = restored.simulated_time
                orchestrator.days_simulated = restored.days_simulated
                orchestrator.time_multiplier = restored.time_multiplier
                orchestrator._occupancy_seed = restored._occupancy_seed
                orchestrator.active_faults = restored.active_faults
                orchestrator.pending_repairs = restored.pending_repairs
                orchestrator.events = restored.events
                # Energy accumulators
                orchestrator.total_energy_kwh = restored.total_energy_kwh
                orchestrator.current_hour_power_kw = restored.current_hour_power_kw
                orchestrator._cumulative_baseline_kwh = restored._cumulative_baseline_kwh
                orchestrator._cumulative_sentinel_kwh = restored._cumulative_sentinel_kwh
                orchestrator._cumulative_solar_gen_kwh = restored._cumulative_solar_gen_kwh
                orchestrator._cumulative_bess_discharge_kwh = restored._cumulative_bess_discharge_kwh
                orchestrator._solar_hour_index = restored._solar_hour_index
                # Proportional control actuator state
                orchestrator._actuator_state = restored._actuator_state
                if orchestrator._occupancy_seed:
                    orchestrator._scenario_rng.seed(orchestrator._occupancy_seed)

                if orchestrator.seasonal_modeler is None and orchestrator.days_simulated > 0:
                    from app.services.seasonal_modeler import SeasonalModeler

                    orchestrator.seasonal_modeler = SeasonalModeler(seed=orchestrator._occupancy_seed)

                orchestrator.real_start_time = datetime.now()
                orchestrator.running = True
                orchestrator.paused = False

                logger.info(
                    f"Restored checkpoint: day {orchestrator.days_simulated}/365, "
                    f"time {orchestrator.simulated_time.isoformat()}"
                )

                orchestrator._task = asyncio.create_task(orchestrator._run_simulation())

            else:
                # FRESH START PATH
                await orchestrator.start(scenario=scenario, duration_minutes=duration_minutes)

            # Attach completion watcher for persistent simulations
            if orchestrator._task:
                logger.info(f"Simulation task {task_id} started - running in background")
                store.update_task_progress(
                    task_id,
                    {
                        "status": "running",
                        "progress_pct": 0,
                        "days_completed": 0,
                    },
                )

                async def _watch_completion(sim_task_id: str, sim_async_task: asyncio.Task, sim_store):
                    try:
                        await sim_async_task
                        logger.info(f"Simulation task {sim_task_id} finished normally")
                    except asyncio.CancelledError:
                        logger.info(f"Simulation task {sim_task_id} was cancelled")
                    except Exception as sim_err:
                        logger.error(f"Simulation task {sim_task_id} failed: {sim_err}")
                        try:
                            from datetime import datetime as dt

                            sim_store.update_task_progress(
                                sim_task_id,
                                {
                                    "status": "failed",
                                    "error_message": str(sim_err)[:500],
                                    "completed_at": dt.now().isoformat(),
                                },
                            )
                        except Exception as store_err:
                            logger.error(f"Failed to write failure status: {store_err}")
                    finally:
                        unregister_simulation(sim_task_id)

                _watch_task = asyncio.create_task(_watch_completion(task_id, orchestrator._task, store))  # noqa: RUF006
                return

        except Exception as e:
            logger.error(f"Simulation task {task_id} failed during setup: {e}")

            store.update_task_progress(
                task_id,
                {
                    "status": "failed",
                    "error_message": str(e)[:500],
                    "completed_at": datetime.now().isoformat(),
                },
            )

            unregister_simulation(task_id)

    def add_integration_sync_job(self, interval_seconds: int = 900):
        """
        Add a job to update integration sync timestamps periodically.

        Touches all active log_sources to keep the System Health dashboard
        showing a fresh sync age. Also creates a sync_job record for history.

        Args:
            interval_seconds: How often to sync (default: 900 seconds = 15 minutes)
        """
        if self.scheduler.get_job("integration_sync"):
            self.scheduler.remove_job("integration_sync")
            logger.info("Removed existing integration sync job")

        self.scheduler.add_job(
            func=self._run_integration_sync,
            trigger=IntervalTrigger(seconds=interval_seconds),
            id="integration_sync",
            name="Integration Sync - Update log source timestamps",
            replace_existing=True,
        )
        logger.info(f"Added integration sync job with {interval_seconds}s interval")

    def _run_integration_sync(self):
        """
        Update last_sync_at on all active log sources and create sync job records.
        This keeps the System Health dashboard showing fresh sync status.
        """
        try:
            from app.database.repositories.integration_repository import IntegrationRepository

            repo = IntegrationRepository()

            # Get all active log sources
            try:
                response = repo.client.table("log_sources").select("id, name").eq("is_active", True).execute()
                sources = response.data or []
            except Exception:
                sources = []

            if not sources:
                logger.debug("No active log sources to sync")
                return

            synced = 0
            for source in sources:
                source_id = source.get("id")
                if not source_id:
                    continue
                try:
                    repo.update_sync_status(source_id, status="success", records=0)
                    synced += 1
                except Exception as e:
                    logger.warning(f"Failed to update sync for source {source.get('name')}: {e}")

            if synced > 0:
                logger.info(f"Integration sync complete: {synced} source(s) updated")

        except Exception as e:
            logger.error(f"Failed to run integration sync: {e}")

    def add_popia_retention_job(self, interval_seconds: int = 86400):
        """Add periodic POPIA retention enforcement job."""
        job_id = "popia_retention_enforcement"
        if self.scheduler.get_job(job_id):
            self.scheduler.remove_job(job_id)
            logger.info("Removed existing POPIA retention enforcement job")

        self.scheduler.add_job(
            func=self._run_popia_retention_enforcement,
            trigger=IntervalTrigger(seconds=interval_seconds),
            id=job_id,
            name="POPIA Retention Enforcement",
            replace_existing=True,
        )
        logger.info("Added POPIA retention enforcement job with %ss interval", interval_seconds)

    def _run_popia_retention_enforcement(self):
        """Execute POPIA retention enforcement and log summary."""
        try:
            from app.services.popia_retention_service import get_popia_retention_service

            service = get_popia_retention_service()
            summary = service.enforce_policies(dry_run=False)
            logger.info(
                "POPIA retention enforcement completed: deleted=%s reviewed=%s errors=%s",
                summary.get("total_deleted", 0),
                summary.get("total_reviewed", 0),
                len(summary.get("errors", [])),
            )

            try:
                from app.services.audit_logger import AuditLogger

                audit_logger = AuditLogger()
                audit_logger.log_system_event(
                    event_type="popia_retention_enforcement",
                    metadata={
                        "total_deleted": summary.get("total_deleted", 0),
                        "total_reviewed": summary.get("total_reviewed", 0),
                        "error_count": len(summary.get("errors", [])),
                        "dry_run": False,
                    },
                )
            except Exception as exc:
                logger.warning("Failed to write retention enforcement audit event: %s", exc)
        except Exception as e:
            logger.error(f"Failed to run POPIA retention enforcement: {e}", exc_info=True)

    def add_mip_dispatch_optimize_job(self, interval_seconds: int = 900):
        """Add a job to run MIP dispatch optimization every 15 minutes.

        Solves the CP-SAT optimal BESS schedule using current load and
        solar forecasts. The cached schedule is consumed by the dispatch
        service's 5-minute execution cycle.

        Args:
            interval_seconds: How often to re-optimize (default: 900 = 15 min)
        """
        job_id = "mip_dispatch_optimize"
        if self.scheduler.get_job(job_id):
            self.scheduler.remove_job(job_id)
            logger.info("Removed existing MIP dispatch optimize job")

        self.scheduler.add_job(
            func=self._run_mip_dispatch_optimize,
            trigger=IntervalTrigger(seconds=interval_seconds),
            id=job_id,
            name="MIP Dispatch Optimization",
            replace_existing=True,
        )
        logger.info(f"Added MIP dispatch optimize job with {interval_seconds}s interval")

    def _run_mip_dispatch_optimize(self):
        """Run MIP dispatch optimization for all registered sites."""
        try:
            from app.core.site_resolver import get_registered_site_ids
            from app.services.load_forecast_service import get_load_forecast_service
            from app.services.mip_dispatch_optimizer import get_mip_dispatch_optimizer

            site_ids = get_registered_site_ids()
            if not site_ids:
                logger.debug("No registered buildings — skipping MIP dispatch optimization")
                return

            optimizer = get_mip_dispatch_optimizer()
            load_svc = get_load_forecast_service()

            for site_id in site_ids:
                try:
                    # Get current load forecast
                    load_forecast = load_svc.get_forecast(site_id, intervals_ahead=96)
                    load_values = [i.demand_kw for i in load_forecast.intervals]

                    # Get solar forecast (optional)
                    solar_values = None
                    try:
                        from app.services.solar_forecast_service import get_solar_forecast_service

                        solar_svc = get_solar_forecast_service()
                        solar_obj = solar_svc.get_forecast(site_id, hours_ahead=24)
                        solar_values = []
                        for h in solar_obj.hourly:
                            solar_values.extend([h.generation_kw] * 4)
                        solar_values = solar_values[:96]
                    except Exception:
                        pass

                    schedule = optimizer.optimize(
                        site_id,
                        load_forecast=load_values,
                        solar_forecast=solar_values,
                    )

                    logger.info(
                        "MIP dispatch optimized: site=%s status=%s cost=R%.2f peak=%.0f kW cycles=%.2f solve=%.0f ms",
                        site_id,
                        schedule.solver_status,
                        schedule.total_cost_zar,
                        schedule.peak_grid_import_kw,
                        schedule.cycles,
                        schedule.solve_time_ms,
                    )
                except Exception as e:
                    logger.error(f"Failed to run MIP dispatch optimization for {site_id}: {e}", exc_info=True)
        except Exception as e:
            logger.error(f"Failed to run MIP dispatch optimization: {e}", exc_info=True)

    def add_load_forecast_job(self, interval_seconds: int = 900):
        """Add a job to refresh the 15-minute load forecast every 15 minutes.

        Re-generates the 96-interval demand forecast used by the MIP
        dispatch optimizer. Does NOT retrain the model (that happens daily).

        Args:
            interval_seconds: How often to refresh forecast (default: 900 = 15 min)
        """
        job_id = "load_forecast_15min"
        if self.scheduler.get_job(job_id):
            self.scheduler.remove_job(job_id)
            logger.info("Removed existing load forecast job")

        self.scheduler.add_job(
            func=self._run_load_forecast,
            trigger=IntervalTrigger(seconds=interval_seconds),
            id=job_id,
            name="15-Min Load Forecast Refresh",
            replace_existing=True,
        )
        logger.info(f"Added load forecast job with {interval_seconds}s interval")

    def _run_load_forecast(self):
        """Refresh 15-min load forecast for all registered sites."""
        try:
            from app.core.site_resolver import get_registered_site_ids
            from app.services.load_forecast_service import get_load_forecast_service

            service = get_load_forecast_service()
            site_ids = get_registered_site_ids()
            if not site_ids:
                logger.debug("No registered buildings — skipping load forecast refresh")
                return

            for site_id in site_ids:
                try:
                    forecast = service.get_forecast(site_id)
                    logger.info(
                        "Load forecast refreshed: site=%s intervals=%d peak=%.0f kW avg=%.0f kW",
                        site_id,
                        len(forecast.intervals),
                        forecast.peak_demand_kw,
                        forecast.avg_demand_kw,
                    )
                except Exception as e:
                    logger.error(f"Failed to refresh load forecast for {site_id}: {e}", exc_info=True)
        except Exception as e:
            logger.error(f"Failed to refresh load forecast: {e}", exc_info=True)

    def add_site_mode_policy_dry_run_job(self, interval_seconds: int = 300, site_id: str = ""):
        """Add periodic dry-run evaluation for deterministic site onboarding policy."""
        job_id = f"site_mode_policy_dry_run_{site_id}"
        if self.scheduler.get_job(job_id):
            self.scheduler.remove_job(job_id)
            logger.info(f"Removed existing site mode policy dry-run job ({site_id})")

        self.scheduler.add_job(
            func=self._run_site_mode_policy_dry_run,
            args=[site_id],
            trigger=IntervalTrigger(seconds=interval_seconds),
            id=job_id,
            name=f"Site Mode Policy Dry Run ({site_id})",
            replace_existing=True,
        )
        logger.info(f"Added site mode policy dry-run job for {site_id} with {interval_seconds}s interval")

    def add_phase_promotion_job(self, interval_hours: int = 1):
        """Add periodic Trust Ladder phase promotion evaluation.

        Evaluates all sites for promotion eligibility and auto-promotes
        via the PATCH /api/sites/{site_id}/phase endpoint when gates pass.
        """
        job_id = "phase_promotion_evaluator"
        if self.scheduler.get_job(job_id):
            self.scheduler.remove_job(job_id)
            logger.info("Removed existing phase promotion evaluator job")

        self.scheduler.add_job(
            func=self._run_phase_promotion,
            trigger=IntervalTrigger(hours=interval_hours),
            id=job_id,
            name="Phase Promotion Evaluator",
            replace_existing=True,
            max_instances=1,
            coalesce=True,
        )
        logger.info(f"Added phase promotion evaluator job (every {interval_hours}h, coalesce=True)")

    def _run_phase_promotion(self):
        """Sync wrapper: run phase promotion evaluation on main event loop."""
        try:
            evaluator = get_phase_promotion_evaluator()

            if self._main_loop and self._main_loop.is_running():
                future = asyncio.run_coroutine_threadsafe(
                    evaluator.evaluate_all_sites(),
                    self._main_loop,
                )
                results = future.result(timeout=120)
            else:
                results = asyncio.run(evaluator.evaluate_all_sites())

            promoted = [r for r in results if r.promoted]
            if promoted:
                logger.info(
                    "Phase promotion: %d site(s) promoted (%s)",
                    len(promoted),
                    ", ".join(f"{r.from_phase}→{r.to_phase}" for r in promoted),
                )
            else:
                logger.debug("Phase promotion evaluation complete: no sites promoted")
        except Exception as e:
            logger.error("Phase promotion evaluation failed: %s", e, exc_info=True)

    def _run_site_mode_policy_dry_run(self, site_id: str):
        """Sync wrapper: evaluate site mode policy on main loop and log result."""
        try:
            if self._main_loop and self._main_loop.is_running():
                future = asyncio.run_coroutine_threadsafe(
                    self._run_site_mode_policy_dry_run_async(site_id),
                    self._main_loop,
                )
                result = future.result(timeout=120)
            else:
                result = asyncio.run(self._run_site_mode_policy_dry_run_async(site_id))

            decision = result.get("decision", "hold")
            state_before = result.get("state_before")
            state_after = result.get("state_after")
            reasons = result.get("reasons", [])
            if decision == "hold":
                logger.debug(
                    "Site mode policy dry-run hold: site=%s stage=%s reasons=%s",
                    site_id,
                    state_before,
                    reasons,
                )
            else:
                logger.info(
                    "Site mode policy dry-run decision: site=%s decision=%s %s->%s reasons=%s write_action=%s",
                    site_id,
                    decision,
                    state_before,
                    state_after,
                    reasons,
                    result.get("write_action", "none"),
                )
        except Exception as e:
            logger.error(f"Failed site mode policy dry-run for {site_id}: {e}", exc_info=True)

    async def _run_site_mode_policy_dry_run_async(self, site_id: str) -> dict:
        """Async implementation for site mode policy dry-run."""
        from app.services.site_mode_policy_service import SiteModePolicyService

        service = SiteModePolicyService()
        return await service.evaluate_site(site_id)

    # -----------------------------------------------------------------------
    # AEGIS Phase 0 — dispatch cycle + daily evidence collector
    # -----------------------------------------------------------------------

    def add_aegis_cycle_job(self, interval_seconds: int = 300, site_id: str = ""):
        """Add a job to run one AEGIS dispatch cycle periodically.

        Creates proposals via the arbitrage engine, validates through BESS
        constraints, routes through the tier engine, and persists decisions.
        In Phase 0A all writes are hard-blocked by AEGIS gate.

        Args:
            interval_seconds: How often to run (default: 300 = 5 min)
            site_id: Target site ID (e.g. site-002)
        """
        job_id = f"aegis_cycle_{site_id}"
        if self.scheduler.get_job(job_id):
            self.scheduler.remove_job(job_id)
            logger.info(f"Removed existing AEGIS cycle job ({site_id})")

        self.scheduler.add_job(
            func=self._run_aegis_cycle,
            args=[site_id],
            trigger=IntervalTrigger(seconds=interval_seconds),
            id=job_id,
            name=f"AEGIS Dispatch Cycle ({site_id})",
            replace_existing=True,
        )
        logger.info(f"Added AEGIS cycle job for {site_id} with {interval_seconds}s interval")

    def _run_aegis_cycle(self, site_id: str):
        """Sync wrapper for async run_aegis_cycle."""
        try:
            if self._main_loop and self._main_loop.is_running():
                future = asyncio.run_coroutine_threadsafe(
                    self._run_aegis_cycle_async(site_id),
                    self._main_loop,
                )
                future.result(timeout=60)
            else:
                asyncio.run(self._run_aegis_cycle_async(site_id))
        except Exception as e:
            logger.error(f"AEGIS cycle job failed for {site_id}: {e}", exc_info=True)

    async def _run_aegis_cycle_async(self, site_id: str):
        """Run one AEGIS dispatch cycle."""
        from app.services.aegis_bridge import run_aegis_cycle

        result = await run_aegis_cycle(site_id=site_id)
        if result:
            logger.info(
                "AEGIS cycle produced proposal: action=%s tier=%s for %s",
                getattr(result, "action_type", "?"),
                getattr(getattr(result, "routing", {}), "tier", "?"),
                site_id,
            )

    def add_aegis_evidence_collector_job(self, interval_seconds: int = 86400, site_id: str = ""):
        """Add a daily job to collect AEGIS Phase 0 evidence into the tracker CSV.

        Runs once per day. Queries the AEGIS dashboard for 24h KPIs,
        checks tripwire logs, samples a decision for audit completeness,
        and appends one row to the 14-day tracker CSV.

        Args:
            interval_seconds: How often to run (default: 86400 = 24h)
            site_id: Target site ID (e.g. site-002)
        """
        job_id = f"aegis_evidence_{site_id}"
        if self.scheduler.get_job(job_id):
            self.scheduler.remove_job(job_id)
            logger.info(f"Removed existing AEGIS evidence collector job ({site_id})")

        self.scheduler.add_job(
            func=self._run_aegis_evidence_collector,
            args=[site_id],
            trigger=IntervalTrigger(seconds=interval_seconds),
            id=job_id,
            name=f"AEGIS Evidence Collector ({site_id})",
            replace_existing=True,
        )
        logger.info(f"Added AEGIS evidence collector job for {site_id} with {interval_seconds}s interval")

    def _run_aegis_evidence_collector(self, site_id: str):
        """Sync wrapper for async evidence collector."""
        try:
            if self._main_loop and self._main_loop.is_running():
                future = asyncio.run_coroutine_threadsafe(
                    self._run_aegis_evidence_collector_async(site_id),
                    self._main_loop,
                )
                future.result(timeout=120)
            else:
                asyncio.run(self._run_aegis_evidence_collector_async(site_id))
        except Exception as e:
            logger.error(
                f"AEGIS evidence collector failed for {site_id}: {e}",
                exc_info=True,
            )

    async def _run_aegis_evidence_collector_async(self, site_id: str):
        """Collect AEGIS evidence and append to tracker CSV.

        Steps:
        1. Query dashboard KPIs (proposals, approved, rejected, blocked)
        2. Check tripwire log for unresolved events > 24h
        3. Sample one decision to verify required audit fields
        4. Check for illegal states (writes in Phase 0)
        5. Append row to tracker CSV
        """
        import csv
        from datetime import datetime, timedelta

        tracker_path = Path(__file__).parent.parent.parent.parent / (
            "docs/10-operations/aegis-phase0-14day-tracker.csv"
        )

        # 1. Read tracker to determine current day number
        current_day = 1
        if tracker_path.exists():
            with open(tracker_path) as f:
                reader = csv.DictReader(f)
                for row in reader:
                    date_val = row.get("date", "")
                    if date_val and not date_val.startswith("YYYY"):
                        current_day = int(row.get("day", 0)) + 1

        if current_day > 14:
            logger.info("AEGIS Phase 0A: all 14 days collected, evidence complete")
            return

        today = datetime.now(UTC).strftime("%Y-%m-%d")

        # 2. Query AEGIS dashboard KPIs
        from app.database.repositories.parasite_decision_repository import (
            get_parasite_decision_repository,
        )

        repo = get_parasite_decision_repository()
        kpis = {"proposals_24h": 0, "approved_24h": 0, "rejected_24h": 0, "blocked_24h": 0}
        avg_response_s = ""
        sample_decision_id = ""
        all_fields_present = "yes"
        illegal_state = "no"
        pending_over_30m = 0
        open_tripwires = 0
        oldest_tripwire_age_min = 0
        tripwire_types = ""

        try:
            # Get all decisions from last 24h for this site
            cutoff = datetime.now(UTC) - timedelta(hours=24)
            recent = await repo.get_decisions_by_site(
                site_id=site_id,
                since=cutoff.isoformat(),
                limit=500,
            )

            kpis["proposals_24h"] = len(recent)
            for d in recent:
                outcome = (d.get("approval_outcome") or "").lower()
                if outcome == "approved":
                    kpis["approved_24h"] += 1
                elif outcome == "rejected":
                    kpis["rejected_24h"] += 1
                elif d.get("block_reason_code"):
                    kpis["blocked_24h"] += 1

                # Check for illegal states (writes in Phase 0)
                write_status = (d.get("write_status") or "").lower()
                if write_status in ("success", "failed"):
                    illegal_state = "yes"

                # Check pending > 30 min
                if outcome == "pending":
                    created = d.get("created_at", "")
                    if created:
                        try:
                            from dateutil.parser import parse as parse_dt

                            created_dt = parse_dt(created)
                            if (datetime.now(UTC) - created_dt).total_seconds() > 1800:
                                pending_over_30m += 1
                        except Exception:
                            pass

            # Sample decision for audit field verification
            if recent:
                sample = recent[0]
                sample_decision_id = sample.get("id", "")
                required_fields = [
                    "command_hash",
                    "approval_outcome",
                    "quality_gate_status",
                    "block_reason_code",
                ]
                cf = sample.get("contributing_factors") or {}
                for field in required_fields:
                    if not sample.get(field) and not cf.get(field):
                        all_fields_present = "no"
                        break

            # Approval SLA (average response time for approved decisions)
            approved_times = []
            for d in recent:
                if (d.get("approval_outcome") or "").lower() == "approved":
                    created = d.get("created_at", "")
                    approved_at = d.get("approved_at", "")
                    if created and approved_at:
                        try:
                            from dateutil.parser import parse as parse_dt

                            c_dt = parse_dt(created)
                            a_dt = parse_dt(approved_at)
                            approved_times.append((a_dt - c_dt).total_seconds())
                        except Exception:
                            pass
            if approved_times:
                avg_response_s = str(round(sum(approved_times) / len(approved_times), 1))

        except Exception as e:
            logger.warning(f"AEGIS evidence: error querying decisions: {e}")

        # 3. Check tripwire log
        try:
            decisions_log = Path("/var/log/sentinel/decisions.log")
            if decisions_log.exists():
                import json as _json

                cutoff_24h = (datetime.now(UTC) - timedelta(hours=24)).isoformat()
                tripwire_events = []
                with open(decisions_log) as f:
                    for line in f:
                        line = line.strip()
                        if not line:
                            continue
                        try:
                            evt = _json.loads(line)
                            stage = evt.get("stage", "")
                            ts = evt.get("timestamp", "")
                            if "aegis.tripwire" in stage and ts >= cutoff_24h:
                                tripwire_events.append(evt)
                        except _json.JSONDecodeError:
                            continue

                if tripwire_events:
                    open_tripwires = len(tripwire_events)
                    types_seen = set()
                    oldest_age = 0
                    for evt in tripwire_events:
                        types_seen.add(evt.get("stage", "").split(".")[-1])
                        try:
                            from dateutil.parser import parse as parse_dt

                            evt_dt = parse_dt(evt["timestamp"])
                            age = (datetime.now(UTC) - evt_dt).total_seconds() / 60
                            oldest_age = max(oldest_age, age)
                        except Exception:
                            pass
                    tripwire_types = ";".join(sorted(types_seen))
                    oldest_tripwire_age_min = round(oldest_age)
        except Exception as e:
            logger.warning(f"AEGIS evidence: error checking tripwire log: {e}")

        # 4. Build tracker row
        row = {
            "day": str(current_day),
            "date": today,
            "site_id": site_id,
            "data_mode": "simulation",
            "proposals_24h": str(kpis["proposals_24h"]),
            "approved_24h": str(kpis["approved_24h"]),
            "rejected_24h": str(kpis["rejected_24h"]),
            "blocked_24h": str(kpis["blocked_24h"]),
            "avg_response_time_s": avg_response_s,
            "pending_over_30m": str(pending_over_30m),
            "open_tripwires": str(open_tripwires),
            "oldest_tripwire_age_min": str(oldest_tripwire_age_min),
            "tripwire_types": tripwire_types,
            "audit_sample_decision_id": sample_decision_id,
            "all_required_fields_present": all_fields_present,
            "illegal_state_detected": illegal_state,
            "phase1_blocker": "no",
            "notes": f"Day {current_day} auto-collected by AEGIS evidence scheduler",
        }

        # 5. Write tracker — replace placeholder row or append
        if tracker_path.exists():
            with open(tracker_path) as f:
                lines = f.readlines()

            header = lines[0] if lines else ""
            fieldnames = header.strip().split(",")

            # Find and replace the placeholder row for this day
            new_lines = [header]
            replaced = False
            for line in lines[1:]:
                parts = line.strip().split(",", 2)
                if parts and parts[0] == str(current_day):
                    # Replace this placeholder row
                    new_lines.append(",".join(row.get(f, "") for f in fieldnames) + "\n")
                    replaced = True
                else:
                    new_lines.append(line)

            if not replaced:
                new_lines.append(",".join(row.get(f, "") for f in fieldnames) + "\n")

            with open(tracker_path, "w") as f:
                f.writelines(new_lines)
        else:
            logger.warning("AEGIS tracker CSV not found at %s", tracker_path)
            return

        logger.info(
            "AEGIS Phase 0A Day %d evidence collected: proposals=%d blocked=%d tripwires=%d illegal=%s",
            current_day,
            kpis["proposals_24h"],
            kpis["blocked_24h"],
            open_tripwires,
            illegal_state,
        )

    # -----------------------------------------------------------------------
    # Phase 130 — Occupancy-driven HVAC + lighting control loop
    # -----------------------------------------------------------------------

    def add_occupancy_control_job(self, interval_seconds: int = 60, site_id: str = ""):
        """Add a periodic job to poll occupancy and adjust HVAC/lighting.

        Reads DALI PIR sensors and badge readers, evaluates zone occupancy,
        and issues setpoint relaxations (HVAC) and brightness adjustments
        (lighting) when zones transition between occupied and unoccupied.

        Args:
            interval_seconds: How often to poll (default: 60s)
            site_id: Target site ID (e.g. site-002)
        """
        job_id = f"occupancy_control_{site_id}"
        if self.scheduler.get_job(job_id):
            self.scheduler.remove_job(job_id)
            logger.info(f"Removed existing occupancy control job ({site_id})")

        self.scheduler.add_job(
            func=self._run_occupancy_control,
            args=[site_id],
            trigger=IntervalTrigger(seconds=interval_seconds),
            id=job_id,
            name=f"Occupancy Control Loop ({site_id})",
            replace_existing=True,
        )
        logger.info(f"Added occupancy control job for {site_id} with {interval_seconds}s interval")

    def _run_occupancy_control(self, site_id: str):
        """Sync wrapper for async occupancy control cycle."""
        try:
            if self._main_loop and self._main_loop.is_running():
                future = asyncio.run_coroutine_threadsafe(
                    self._run_occupancy_control_async(site_id),
                    self._main_loop,
                )
                future.result(timeout=30)
            else:
                asyncio.run(self._run_occupancy_control_async(site_id))
        except Exception as e:
            logger.error(f"Occupancy control cycle failed for {site_id}: {e}", exc_info=True)

    async def _run_occupancy_control_async(self, site_id: str):
        """Run one occupancy control cycle."""
        from app.services.occupancy_control_service import get_occupancy_control_service

        service = get_occupancy_control_service()
        result = await service.run_cycle(site_id=site_id)

        if result.get("actions_taken", 0) > 0:
            logger.info(
                "Occupancy control: site=%s actions=%d zones=%d errors=%d",
                site_id,
                result["actions_taken"],
                result["zones_checked"],
                len(result.get("errors", [])),
            )

    # ── System Health jobs ──────────────────────────────────────────────

    def add_health_snapshot_job(self, interval_seconds: int = 300):
        """
        Add a job to store system health snapshots periodically.

        Args:
            interval_seconds: How often to store snapshots (default: 300 = 5 minutes)
        """
        job_id = "system_health_snapshot"
        if self.scheduler.get_job(job_id):
            self.scheduler.remove_job(job_id)
            logger.info("Removed existing health snapshot job")

        self.scheduler.add_job(
            func=self._run_health_snapshot,
            trigger=IntervalTrigger(seconds=interval_seconds),
            id=job_id,
            name="System Health Snapshot",
            replace_existing=True,
        )
        logger.info(f"Added health snapshot job with {interval_seconds}s interval")

    def _run_health_snapshot(self):
        """Sync wrapper for async health snapshot storage."""
        try:
            if self._main_loop and self._main_loop.is_running():
                future = asyncio.run_coroutine_threadsafe(
                    self._run_health_snapshot_async(),
                    self._main_loop,
                )
                future.result(timeout=30)
            else:
                asyncio.run(self._run_health_snapshot_async())
        except Exception as e:
            logger.error(f"Failed to store health snapshot: {e}", exc_info=True)

    async def _run_health_snapshot_async(self):
        """Store current health snapshot to database."""
        from app.services.system_health_service import SystemHealthService

        health_service = SystemHealthService()
        snapshot = await health_service.get_current_health()
        await health_service.store_health_snapshot(snapshot)
        logger.debug("Health snapshot stored successfully")

    # ── Equipment Health Snapshot jobs ──────────────────────────────────

    def add_equipment_health_snapshot_job(self, interval_hours: int = 2):
        """
        Add a job to compute and store equipment health snapshots periodically.

        Args:
            interval_hours: How often to recompute snapshots (default: 2 hours)
        """
        job_id = "equipment_health_snapshot"
        if self.scheduler.get_job(job_id):
            self.scheduler.remove_job(job_id)
            logger.info("Removed existing equipment health snapshot job")

        first_run = datetime.now(UTC) + timedelta(seconds=30)  # 30s warmup
        self.scheduler.add_job(
            func=self._run_equipment_health_snapshot,
            trigger=IntervalTrigger(hours=interval_hours),
            id=job_id,
            name="Equipment Health Snapshot",
            replace_existing=True,
            next_run_time=first_run,
            max_instances=1,
        )
        logger.info(
            "Added equipment health snapshot job (%dh interval, first run at %s)",
            interval_hours,
            first_run.strftime("%H:%M:%S"),
        )

    def _run_equipment_health_snapshot(self):
        """Sync wrapper for async equipment health snapshot recompute."""
        try:
            if self._main_loop and self._main_loop.is_running():
                future = asyncio.run_coroutine_threadsafe(
                    self._run_equipment_health_snapshot_async(),
                    self._main_loop,
                )
                future.result(timeout=120)
            else:
                asyncio.run(self._run_equipment_health_snapshot_async())
        except Exception as e:
            logger.error(f"[HEALTH-SNAP] Failed to run equipment health snapshot: {e}", exc_info=True)

    async def _run_equipment_health_snapshot_async(self):
        """Recompute health ratings for all registered sites and their equipment."""
        from app.database.repositories.site_repository import SiteRepository
        from app.services.health_snapshot_service import HealthSnapshotService

        site_repo = SiteRepository()
        sites = site_repo.get_all()

        if not sites:
            logger.debug("[HEALTH-SNAP] No registered sites found")
            return

        snapshot_service = HealthSnapshotService()

        for site in sites:
            site_uuid = site.get("id")
            if not site_uuid:
                continue
            try:
                result = await snapshot_service.recompute(scope="site", site_id=site_uuid)
                logger.info(
                    "[HEALTH-SNAP] site=%s processed=%d failed=%d duration_ms=%s",
                    site_uuid,
                    result.equipment_processed,
                    result.equipment_failed,
                    result.duration_ms,
                )
            except Exception as e:
                logger.warning(f"[HEALTH-SNAP] site={site_uuid} failed: {e}")

    def add_error_auto_resolve_job(self, interval_seconds: int = 86400):
        """
        Add a job to auto-resolve stale errors if component is now healthy.

        Runs daily to clean up errors where the component has been healthy for 24+ hours.

        Args:
            interval_seconds: How often to check for stale errors (default: 86400 = 24 hours)
        """
        job_id = "system_error_auto_resolve"
        if self.scheduler.get_job(job_id):
            self.scheduler.remove_job(job_id)
            logger.info("Removed existing error auto-resolve job")

        self.scheduler.add_job(
            func=self._run_error_auto_resolve,
            trigger=IntervalTrigger(seconds=interval_seconds),
            id=job_id,
            name="System Error Auto-Resolve",
            replace_existing=True,
        )
        logger.info(f"Added error auto-resolve job with {interval_seconds}s interval")

    def add_adapter_health_monitor_job(self, interval_seconds: int = 60):
        """
        Add a job to run adapter health checks every 60 seconds.

        Tracks BACnet, Niagara, OBIX, and ShadowModePolling bridge health.
        Writes to adapter_health table and emits alerts after 3 consecutive failures.

        Args:
            interval_seconds: How often to run health checks (default: 60 seconds)
        """
        job_id = "adapter_health_monitor"
        if self.scheduler.get_job(job_id):
            self.scheduler.remove_job(job_id)
            logger.info("Removed existing adapter health monitor job")

        first_run = datetime.now() + timedelta(seconds=10)  # 10s warmup

        self.scheduler.add_job(
            func=self._run_adapter_health_monitor,
            trigger=IntervalTrigger(seconds=interval_seconds),
            id=job_id,
            name="Adapter Health Monitor",
            replace_existing=True,
            next_run_time=first_run,
            max_instances=1,
        )
        logger.info(f"Added adapter health monitor job with {interval_seconds}s interval")

    def _run_adapter_health_monitor(self):
        """Sync wrapper for async adapter health monitoring."""
        try:
            if self._main_loop and self._main_loop.is_running():
                future = asyncio.run_coroutine_threadsafe(
                    self._run_adapter_health_monitor_async(),
                    self._main_loop,
                )
                future.result(timeout=30)
            else:
                asyncio.run(self._run_adapter_health_monitor_async())
        except Exception as e:
            logger.error(f"Failed to run adapter health monitor: {e}", exc_info=True)

    async def _run_adapter_health_monitor_async(self):
        """Run one adapter health check cycle."""
        from app.services.adapter_health_monitor import AdapterHealthMonitor

        monitor = AdapterHealthMonitor()
        await monitor.run_health_cycle()
        logger.debug("Adapter health monitor cycle completed")

    def _run_error_auto_resolve(self):
        """Sync wrapper for async error auto-resolution."""
        try:
            if self._main_loop and self._main_loop.is_running():
                future = asyncio.run_coroutine_threadsafe(
                    self._run_error_auto_resolve_async(),
                    self._main_loop,
                )
                future.result(timeout=60)
            else:
                asyncio.run(self._run_error_auto_resolve_async())
        except Exception as e:
            logger.error(f"Failed to auto-resolve errors: {e}", exc_info=True)

    async def _run_error_auto_resolve_async(self):
        """Auto-resolve errors if component is now healthy for 24+ hours."""
        from app.services.system_health_service import SystemHealthService

        health_service = SystemHealthService()
        resolved_count = await health_service.auto_resolve_stale_errors()
        if resolved_count > 0:
            logger.info(f"Auto-resolved {resolved_count} stale errors")

    # -----------------------------------------------------------------
    # Data Freshness Monitor (Tier 2 SLI)
    # -----------------------------------------------------------------

    def add_data_freshness_monitor_job(self, interval_seconds: int = 300):
        """
        Add a job to check data freshness every 5 minutes.

        Calculates age of normalized data per source (BMS telemetry, documents,
        anomalies, recommendations), updates SLI pass/fail, detects new breaches,
        and auto-resolves resolved ones.

        Args:
            interval_seconds: How often to run freshness checks (default: 300s = 5 min)
        """
        job_id = "data_freshness_monitor"
        if self.scheduler.get_job(job_id):
            self.scheduler.remove_job(job_id)
            logger.info("Removed existing data freshness monitor job")

        first_run = datetime.now() + timedelta(seconds=30)  # 30s warmup

        self.scheduler.add_job(
            func=self._run_data_freshness_monitor,
            trigger=IntervalTrigger(seconds=interval_seconds),
            id=job_id,
            name="Data Freshness Monitor (5m)",
            replace_existing=True,
            next_run_time=first_run,
            max_instances=1,
            coalesce=True,
        )
        logger.info(f"Added data freshness monitor job with {interval_seconds}s interval")

    def _run_data_freshness_monitor(self):
        """Sync wrapper for async data freshness monitoring."""
        try:
            if self._main_loop and self._main_loop.is_running():
                future = asyncio.run_coroutine_threadsafe(
                    self._run_data_freshness_monitor_async(),
                    self._main_loop,
                )
                future.result(timeout=60)
            else:
                asyncio.run(self._run_data_freshness_monitor_async())
        except Exception as e:
            logger.error(f"Failed to run data freshness monitor: {e}", exc_info=True)

    async def _run_data_freshness_monitor_async(self):
        """Run one data freshness check cycle."""
        from app.services.data_freshness_monitor import DataFreshnessMonitor

        monitor = DataFreshnessMonitor()
        await monitor.run_freshness_cycle()
        logger.debug("Data freshness monitor cycle completed")

    # -----------------------------------------------------------------
    # Uptime Aggregator (Tier 4 SLI)
    # -----------------------------------------------------------------

    def add_uptime_aggregator_jobs(self):
        """
        Register daily and monthly uptime aggregation jobs.

        Daily:  01:00 SAST every day       → aggregates prior day's checks
        Monthly: 02:00 SAST on 1st of month → aggregates prior complete month
        """
        from apscheduler.triggers.cron import CronTrigger

        from app.services.uptime_aggregator import UptimeAggregator

        uptime_agg = UptimeAggregator()

        # Daily aggregation: 01:00 SAST
        self.scheduler.add_job(
            func=uptime_agg.aggregate_daily_uptime,
            trigger=CronTrigger(hour=1, minute=0, timezone="Africa/Johannesburg"),
            id="uptime_daily_agg",
            name="Uptime Daily Aggregation (01:00 SAST)",
            max_instances=1,
            coalesce=True,
        )
        logger.info("Added uptime daily aggregation job (01:00 SAST)")

        # Monthly aggregation: 02:00 SAST on the 1st
        self.scheduler.add_job(
            func=uptime_agg.aggregate_monthly_uptime,
            trigger=CronTrigger(day=1, hour=2, minute=0, timezone="Africa/Johannesburg"),
            id="uptime_monthly_agg",
            name="Uptime Monthly Aggregation (1st 02:00 SAST)",
            max_instances=1,
            coalesce=True,
        )
        logger.info("Added uptime monthly aggregation job (1st 02:00 SAST)")

        # SLO report email: 02:10 SAST on the 1st (after monthly agg completes)
        self.scheduler.add_job(
            func=self._send_monthly_slo_report,
            trigger=CronTrigger(day=1, hour=2, minute=10, timezone="Africa/Johannesburg"),
            id="slo_monthly_report",
            name="Monthly SLO Report Email (1st 02:10 SAST)",
            max_instances=1,
            coalesce=True,
        )
        logger.info("Added monthly SLO report email job (1st 02:10 SAST)")

    def _send_monthly_slo_report(self):
        """Sync wrapper for monthly SLO report email."""
        try:
            if self._main_loop and self._main_loop.is_running():
                future = asyncio.run_coroutine_threadsafe(
                    self._send_monthly_slo_report_async(),
                    self._main_loop,
                )
                future.result(timeout=60)
            else:
                asyncio.run(self._send_monthly_slo_report_async())
        except Exception as e:
            logger.error(f"Failed to send monthly SLO report: {e}", exc_info=True)

    async def _send_monthly_slo_report_async(self):
        """Send monthly SLO report email to stakeholders."""
        from app.services.slo_report_service import SLOReportService

        service = SLOReportService()
        await service._send_monthly_slo_report_async(None)

    # -----------------------------------------------------------------
    # Critical Path Monitor (Tier 3 SLI)
    # -----------------------------------------------------------------

    def add_critical_path_monitor_job(self):
        """
        Register hourly aggregation job for PARASITE decision latencies.

        Runs at :00 SAST each hour. Collects all supervised_action_traces from
        the prior complete hour, computes p50/p99/p99.9/max/avg percentiles,
        and upserts into critical_path_hourly. SLO pass if p99 <= 7000ms.
        """
        from apscheduler.triggers.cron import CronTrigger

        from app.services.critical_path_monitor import CriticalPathMonitor

        critical_path = CriticalPathMonitor()
        self.scheduler.add_job(
            func=critical_path.run_hourly_aggregation,
            trigger=CronTrigger(minute=0, timezone="Africa/Johannesburg"),
            id="critical_path_hourly",
            name="Critical Path Hourly Aggregation (:00 SAST)",
            max_instances=1,
            coalesce=True,
        )
        logger.info("Added critical path hourly aggregation job (:00 SAST)")

    # -----------------------------------------------------------------
    # Event Intelligence evaluation
    # -----------------------------------------------------------------

    def add_event_intelligence_job(self, interval_seconds: int = 120):
        """Add a periodic job to evaluate all sites for operational events.

        The EventIntelligenceService converts raw telemetry into structured
        operational events (temperature deviations, energy spikes, sensor failures,
        comfort violations, etc.) and emits them via the event bus.

        This is read-only: it inspects telemetry and emits events. No control
        actions are taken.

        Args:
            interval_seconds: How often to evaluate (default: 120s = 2 minutes).
        """
        job_id = "event_intelligence_evaluation"
        if self.scheduler.get_job(job_id):
            self.scheduler.remove_job(job_id)

        first_run = datetime.now() + timedelta(seconds=90)  # 90s warmup

        self.scheduler.add_job(
            func=self._run_event_intelligence,
            trigger=IntervalTrigger(seconds=interval_seconds),
            id=job_id,
            name="Event Intelligence Evaluation",
            replace_existing=True,
            next_run_time=first_run,
            max_instances=1,
        )
        logger.info(
            "Added event intelligence job: %ds interval (first run at %s)",
            interval_seconds,
            first_run.strftime("%H:%M:%S"),
        )

    def _run_event_intelligence(self):
        """Sync wrapper for async event intelligence evaluation."""
        try:
            if self._main_loop and self._main_loop.is_running():
                future = asyncio.run_coroutine_threadsafe(
                    self._run_event_intelligence_async(),
                    self._main_loop,
                )
                future.result(timeout=60)
            else:
                asyncio.run(self._run_event_intelligence_async())
        except Exception as e:
            logger.error("Event intelligence evaluation failed: %s", e, exc_info=True)

    async def _run_event_intelligence_async(self):
        """Evaluate all registered sites for operational events."""
        from app.core.site_resolver import get_registered_site_ids
        from app.services.event_intelligence_service import get_event_intelligence_service

        site_ids = get_registered_site_ids()
        if not site_ids:
            return

        svc = get_event_intelligence_service()
        total_events = 0

        for site_id in site_ids:
            try:
                events = await svc.process_site(site_id)
                if events:
                    total_events += len(events)
                    logger.info(
                        "Event intelligence: %d events detected for %s",
                        len(events),
                        site_id,
                    )
            except Exception as e:
                logger.warning("Event intelligence failed for %s: %s", site_id, e)

        if total_events > 0:
            logger.info("Event intelligence cycle complete: %d events across %d sites", total_events, len(site_ids))

    # -----------------------------------------------------------------
    # Space Occupancy — Sensor health monitor
    # -----------------------------------------------------------------

    def add_space_sensor_health_job(self, interval_seconds: int = 60, site_id: str = "FLN02"):
        """Add a periodic job to check sensor health for the space occupancy POC.

        Detects sensors that have gone offline (no heartbeat within threshold).

        Args:
            interval_seconds: How often to check (default: 60s).
            site_id: The site to monitor.
        """
        job_id = f"space_sensor_health_{site_id}"
        if self.scheduler.get_job(job_id):
            self.scheduler.remove_job(job_id)

        self.scheduler.add_job(
            func=self._run_space_sensor_health,
            trigger=IntervalTrigger(seconds=interval_seconds),
            id=job_id,
            name=f"Space Sensor Health ({site_id})",
            replace_existing=True,
            kwargs={"site_id": site_id},
        )
        logger.info("Added space sensor health job for %s (%ds interval)", site_id, interval_seconds)

    def _run_space_sensor_health(self, site_id: str = "FLN02"):
        """Sync wrapper for async sensor health check."""
        try:
            if self._main_loop and self._main_loop.is_running():
                future = asyncio.run_coroutine_threadsafe(
                    self._run_space_sensor_health_async(site_id),
                    self._main_loop,
                )
                future.result(timeout=30)
            else:
                asyncio.run(self._run_space_sensor_health_async(site_id))
        except Exception as e:
            logger.error("Space sensor health check failed: %s", e, exc_info=True)

    async def _run_space_sensor_health_async(self, site_id: str = "FLN02"):
        """Run the async sensor health check."""
        from app.space.sensor_monitor import check_sensor_health

        await check_sensor_health(site_id=site_id)

    def add_ghost_room_monitor_job(self, interval_seconds: int = 60):
        """Periodically scan due meeting-room bookings for ghost-room alerts."""
        job_id = "space_ghost_room_monitor"
        if self.scheduler.get_job(job_id):
            self.scheduler.remove_job(job_id)

        self.scheduler.add_job(
            func=self._run_ghost_room_monitor,
            trigger=IntervalTrigger(seconds=interval_seconds),
            id=job_id,
            name="Space Ghost Room Monitor",
            replace_existing=True,
        )
        logger.info("Added ghost-room monitor job (%ds interval)", interval_seconds)

    def _run_ghost_room_monitor(self):
        """Sync wrapper for the async ghost-room booking scan."""
        try:
            if self._main_loop and self._main_loop.is_running():
                future = asyncio.run_coroutine_threadsafe(
                    self._run_ghost_room_monitor_async(),
                    self._main_loop,
                )
                future.result(timeout=30)
            else:
                asyncio.run(self._run_ghost_room_monitor_async())
        except Exception as e:
            logger.error("Ghost-room monitor failed: %s", e, exc_info=True)

    async def _run_ghost_room_monitor_async(self):
        """Run the async ghost-room scan and notification dispatch."""
        from app.services.ghost_room_monitor import scan_due_ghost_bookings

        await scan_due_ghost_bookings()

    def add_focus_relay_reconcile_job(self, interval_seconds: int = 30):
        """Periodically reconcile focus-room relay state for cooldown expiry."""
        job_id = "space_focus_relay_reconcile"
        if self.scheduler.get_job(job_id):
            self.scheduler.remove_job(job_id)

        self.scheduler.add_job(
            func=self._run_focus_relay_reconcile,
            trigger=IntervalTrigger(seconds=interval_seconds),
            id=job_id,
            name="Space Focus Relay Reconcile",
            replace_existing=True,
        )
        logger.info("Added focus relay reconcile job (%ds interval)", interval_seconds)

    def _run_focus_relay_reconcile(self):
        """Run focus-room relay cooldown reconciliation."""
        try:
            from app.services.focus_room_relay_service import scan_all_focus_relays

            result = scan_all_focus_relays()
            if result.get("changed", 0) > 0:
                logger.info(
                    "Focus relay reconcile: scanned=%d changed=%d",
                    result.get("scanned", 0),
                    result.get("changed", 0),
                )
        except Exception as e:
            logger.error("Focus relay reconcile failed: %s", e, exc_info=True)

    # ------------------------------------------------------------------
    # Database archival (Phase 4 — Supabase Performance Optimization)
    # ------------------------------------------------------------------

    def add_db_archival_job(self, interval_seconds: int = 86400):
        """Add daily job to archive resolved alerts/predictions older than 90 days."""
        job_id = "db_archival"
        if self.scheduler.get_job(job_id):
            self.scheduler.remove_job(job_id)
        self.scheduler.add_job(
            func=self._run_db_archival,
            trigger=IntervalTrigger(seconds=interval_seconds),
            id=job_id,
            name="Database Archival (resolved alerts/predictions >90d)",
            replace_existing=True,
        )
        logger.info("Added DB archival job (%ds interval)", interval_seconds)

    def _run_db_archival(self):
        """Run database archival for old resolved records."""
        try:
            from app.services.db_archival_service import archive_old_records

            result = archive_old_records(dry_run=False)
            total = result.get("alerts", 0) + result.get("predictions", 0)
            if total > 0:
                logger.info(
                    "DB archival: removed %d alerts + %d predictions (cutoff %s)",
                    result["alerts"],
                    result["predictions"],
                    result["cutoff"],
                )
        except Exception as e:
            logger.error("DB archival failed: %s", e, exc_info=True)

    def add_ai_cost_report_job(self):
        """Add daily AI cost report email job. Runs at 23:55 every day."""
        from apscheduler.triggers.cron import CronTrigger

        if self.scheduler.get_job("ai_cost_daily_report"):
            self.scheduler.remove_job("ai_cost_daily_report")

        self.scheduler.add_job(
            func=self._send_ai_cost_report,
            trigger=CronTrigger(hour=23, minute=55),
            id="ai_cost_daily_report",
            name="Daily AI Cost Report Email",
            replace_existing=True,
        )
        logger.info("Added daily AI cost report job (23:55)")

    def _send_ai_cost_report(self):
        """Send the daily AI cost report email."""
        try:
            from app.services.ai_usage_tracker import usage_tracker

            usage_tracker.flush()
            usage_tracker.send_daily_report_email("info@sentinel-ai.co.za")
        except Exception as e:
            logger.error("AI cost report email failed: %s", e, exc_info=True)

    # ------------------------------------------------------------------
    # Phase 189 — LLM Judge Loop (INTERIM)
    # ------------------------------------------------------------------

    def add_llm_judge_job(self):
        """Add LLM judge evaluation job. Runs every 60 minutes.

        INTERIM: Replace with iDNa AI Testing Framework call when endpoint is available.
        See docs/08-ai-ml/llm-judge-loop.md
        """
        from apscheduler.triggers.cron import CronTrigger

        if self.scheduler.get_job("llm_judge_evaluation"):
            self.scheduler.remove_job("llm_judge_evaluation")
            logger.info("Removed existing llm judge evaluation job")

        self.scheduler.add_job(
            func=self._run_llm_judge_evaluation,
            trigger=CronTrigger(minute=0),  # top of every hour
            id="llm_judge_evaluation",
            name="LLM Judge Evaluation",
            replace_existing=True,
        )
        logger.info("Added LLM judge evaluation job (top of every hour)")

    def _run_llm_judge_evaluation(self):
        """Run LLM judge evaluation and emit Prometheus gauge."""
        try:
            import asyncio

            from app.api.metrics import sentinel_llm_judge_score
            from ml.explanations.evaluation import LLMJudgeService

            service = LLMJudgeService(sample_size=10)
            result = asyncio.run(service.evaluate_recent())

            if result is not None:
                sentinel_llm_judge_score.labels(score_type="actionability").set(result.actionability_score or 0.0)
                sentinel_llm_judge_score.labels(score_type="factuality").set(result.factuality_score or 0.0)
                sentinel_llm_judge_score.labels(score_type="completeness").set(result.completeness_score or 0.0)
                sentinel_llm_judge_score.labels(score_type="conciseness").set(result.conciseness_score or 0.0)
                logger.info(
                    "[LLM JUDGE] actionability=%.3f factuality=%.3f completeness=%.3f conciseness=%.3f",
                    result.actionability_score or 0.0,
                    result.factuality_score or 0.0,
                    result.completeness_score or 0.0,
                    result.conciseness_score or 0.0,
                )
        except Exception as e:
            logger.error("[LLM JUDGE] Evaluation failed: %s", e, exc_info=True)

    # ------------------------------------------------------------------
    # Outlook calendar polling (Phase 176)
    # ------------------------------------------------------------------

    def add_outlook_polling_job(self, interval_minutes: int = 5):
        """
        Add a job to poll Outlook for external-attendee calendar events.

        Args:
            interval_minutes: How often to poll (default: 5 minutes)
        """
        job_id = "outlook_calendar_poll"
        if self.scheduler.get_job(job_id):
            self.scheduler.remove_job(job_id)
            logger.info("Removed existing Outlook polling job")

        self.scheduler.add_job(
            func=self._run_outlook_calendar_poll,
            trigger=IntervalTrigger(minutes=interval_minutes),
            id=job_id,
            name="Outlook Calendar Poll — External Attendees",
            replace_existing=True,
        )
        logger.info("Added Outlook calendar polling job (%d min interval)", interval_minutes)

    def _run_outlook_calendar_poll(self):
        """Run the Outlook calendar poll (sync wrapper for async service)."""
        try:
            import asyncio

            from app.services.outlook_calendar_service import OutlookCalendarService

            outlook_svc = OutlookCalendarService()

            # Run the async poll in a new event loop (APScheduler uses threads)
            loop = asyncio.new_event_loop()
            asyncio.set_event_loop(loop)
            try:
                visits = loop.run_until_complete(outlook_svc.poll_new_external_attendee_events())
                if visits:
                    logger.info(
                        "Outlook poll: created %d visit(s)",
                        len(visits),
                    )
            finally:
                loop.close()

        except Exception as e:
            logger.error("Outlook calendar poll failed: %s", e, exc_info=True)

    # ------------------------------------------------------------------
    # Google Calendar polling (Phase 176)
    # ------------------------------------------------------------------

    def add_google_calendar_poll_job(self, interval_minutes: int = 5):
        """Add a job to poll Google Calendar for external-attendee events.

        Used as fallback when Pub/Sub push is not configured.
        """
        job_id = "google_calendar_poll"
        if self.scheduler.get_job(job_id):
            self.scheduler.remove_job(job_id)
            logger.info("Removed existing Google Calendar polling job")

        self.scheduler.add_job(
            func=self._run_google_calendar_poll,
            trigger=IntervalTrigger(minutes=interval_minutes),
            id=job_id,
            name="Google Calendar Poll — External Attendees",
            replace_existing=True,
        )
        logger.info("Added Google Calendar polling job (%d min interval)", interval_minutes)

    def _run_google_calendar_poll(self):
        """Run the Google Calendar poll."""
        try:
            from app.services.google_calendar_service import GoogleCalendarService

            svc = GoogleCalendarService()
            if not svc.is_enabled():
                return
            visits = svc.poll_recent_events()
            if visits:
                logger.info("Google Calendar poll: created %d visit(s)", len(visits))
        except Exception as e:
            logger.error("Google Calendar poll failed: %s", e, exc_info=True)

    # ------------------------------------------------------------------
    # Graph subscription renewal (Phase 177)
    # ------------------------------------------------------------------

    def add_graph_subscription_renewal_job(self, interval_hours: int = 1):
        """
        Add a periodic job to renew the Graph webhook subscription before expiry.

        Graph subscriptions expire after 3 days. We renew at the 24-hour mark
        to stay well within the renewal window.

        Args:
            interval_hours: How often to check and renew (default: 1 hour)
        """
        job_id = "graph_subscription_renewal"
        if self.scheduler.get_job(job_id):
            self.scheduler.remove_job(job_id)

        self.scheduler.add_job(
            func=self._run_graph_subscription_renewal,
            trigger=IntervalTrigger(hours=interval_hours),
            id=job_id,
            name="Graph Subscription Renewal",
            replace_existing=True,
        )
        logger.info("Added Graph subscription renewal job (every %d hour(s))", interval_hours)

    def _run_graph_subscription_renewal(self):
        """Run the Graph subscription renewal (sync wrapper for async service)."""
        try:
            import asyncio

            from app.services.graph_subscription_service import graph_subscription_service

            async def _renew():
                renewed = await graph_subscription_service.renew_subscription_if_needed()
                if renewed:
                    logger.info("Graph subscription renewal: success")
                else:
                    logger.debug("Graph subscription renewal: skipped or failed")

            loop = asyncio.new_event_loop()
            asyncio.set_event_loop(loop)
            try:
                loop.run_until_complete(_renew())
            finally:
                loop.close()

        except Exception as e:
            logger.error("Graph subscription renewal failed: %s", e, exc_info=True)

    # ── Graph Credential Rotation Check ────────────────────────────────────────

    def add_graph_credential_rotation_check_job(self, interval_hours: int = 24):
        """
        Add a daily job to check Graph credential age and alert if rotation is overdue.

        Azure AD client secrets expire every 90 days. This job checks the last rotation
        timestamp and fires a CRITICAL alert if > 85 days have passed (5-day buffer
        before expiry).

        Phase 184-01-02, Section D.

        Args:
            interval_hours: How often to check (default: 24 hours)
        """
        job_id = "graph_credential_rotation_check"
        if self.scheduler.get_job(job_id):
            self.scheduler.remove_job(job_id)

        self.scheduler.add_job(
            func=self._run_graph_credential_rotation_check,
            trigger=IntervalTrigger(hours=interval_hours),
            id=job_id,
            name="Graph Credential Rotation Check",
            replace_existing=True,
        )
        logger.info("Added Graph credential rotation check job (every %d hour(s))", interval_hours)

    def _run_graph_credential_rotation_check(self):
        """Check credential age and alert if rotation is overdue."""
        try:
            import os

            from app.services.graph_oauth_service import _acquire_access_token

            # Check if credentials are configured
            if not os.getenv("OUTLOOK_CLIENT_ID") or not os.getenv("OUTLOOK_CLIENT_SECRET"):
                logger.debug("Graph credential rotation check: credentials not configured — skipping")
                return

            # Try to acquire a token — if it succeeds, credentials are valid
            import asyncio

            async def _check():
                token = await _acquire_access_token()
                return token is not None

            loop = asyncio.new_event_loop()
            asyncio.set_event_loop(loop)
            try:
                valid = loop.run_until_complete(_check())
                if valid:
                    logger.debug("Graph credential rotation check: credentials valid")
                else:
                    logger.critical(
                        "[GraphCredentialRotation] Azure AD credentials invalid — "
                        "rotate OUTLOOK_CLIENT_SECRET in Azure AD and update SENTINEL .env"
                    )
            finally:
                loop.close()

        except Exception as e:
            logger.error("Graph credential rotation check failed: %s", e, exc_info=True)

    # ── Shadow Mode Bridge Polling ─────────────────────────────────────────────

    def add_shadow_mode_polling_job(self, interval_seconds: int = 300, site_id: str = "site-002"):
        import logging as _shadow_log

        _shadow_log.warning("SHADOW_JOB: add_shadow_mode_polling_job ENTERED")
        """
        Add a periodic job to poll the site bridge and feed live data to ML pipeline.

        Fetches per-zone temperature/CO2 readings and aggregated power/water telemetry
        from the bridge, transforms them into equipment_states, and feeds
        SentinelDataSync (Supabase writes + ML feeder accumulation).

        This keeps ML models current during shadow mode operation when the simulation
        engine is disabled (ENABLE_SITE002_SOURCE=false) but the bridge is live.

        Args:
            interval_seconds: How often to poll the bridge (default: 300s = 5 minutes)
            site_id: Site to poll (default: site-002)
        """
        job_id = "shadow_mode_polling"
        import sys as _sys

        _sys.stderr.write("SHADOW_JOB_DEBUG: at job_id assignment\n")
        _sys.stderr.flush()
        if self.scheduler.get_job(job_id):
            self.scheduler.remove_job(job_id)
            logger.info("Removed existing shadow mode polling job")

        first_run = datetime.now() + timedelta(seconds=30)  # 30s warmup
        _sys.stderr.write(f"SHADOW_JOB_DEBUG: about to add job to scheduler, first_run={first_run}\n")
        _sys.stderr.flush()

        self.scheduler.add_job(
            func=self._run_shadow_mode_polling,
            trigger=IntervalTrigger(seconds=interval_seconds),
            id=job_id,
            name="Shadow Mode Bridge Polling",
            replace_existing=True,
            next_run_time=first_run,
            max_instances=1,
        )
        _sys.stderr.write("SHADOW_JOB_DEBUG: add_job completed\n")
        _sys.stderr.flush()
        logger.info(
            "Added shadow mode polling job: site=%s every %ds (first run at %s)",
            site_id,
            interval_seconds,
            first_run.strftime("%H:%M:%S"),
        )

    def _run_shadow_mode_polling(self):
        """Poll all enabled bridge sites and feed to ML pipeline.

        Uses MultiSitePollingCoordinator, which reads active sites from
        site_adapter_config and polls each via a ShadowModePollingService
        instance. S002 behaviour is unchanged; new sites are included
        automatically when their bridge adapter is enabled in the database.
        """
        import sys as _sys_shadow

        _sys_shadow.stderr.write("SHADOW_POLL_EXEC: _run_shadow_mode_polling ENTERED\n")
        _sys_shadow.stderr.flush()
        try:
            from app.services.multi_site_polling_coordinator import get_multi_site_polling_coordinator

            coordinator = get_multi_site_polling_coordinator()
            results = coordinator.poll_all()
            _sys_shadow.stderr.write(f"SHADOW_POLL_EXEC: sites_polled={list(results)}\n")
            _sys_shadow.stderr.flush()
        except Exception as e:
            _sys_shadow.stderr.write(f"SHADOW_POLL_EXEC: EXCEPTION={e}\n")
            _sys_shadow.stderr.flush()
            logger.error("Shadow mode polling failed: %s", e, exc_info=True)

    # ── Document MRI Sync ───────────────────────────────────────────────────────

    def add_document_mri_sync_job(self, interval_hours: int = 4, site_id: str = "site-002"):
        """
        Add a periodic job to sync documents from MRI Concept API.

        Fetches service reports and documents from the MRI Evolution documents
        endpoint, normalises them to DocumentRecord, and upserts to the documents table.

        Only runs when ENABLE_SITE002_SOURCE=false (shadow mode / bridge polling).

        Args:
            interval_hours: How often to sync (default: 4 hours)
            site_id: Site to associate synced documents with (default: site-002)
        """
        job_id = "document_mri_sync"
        if self.scheduler.get_job(job_id):
            self.scheduler.remove_job(job_id)
            logger.info("Removed existing document MRI sync job")

        first_run = datetime.now() + timedelta(seconds=30)  # 30s warmup

        self.scheduler.add_job(
            func=self._run_document_mri_sync,
            trigger=IntervalTrigger(hours=interval_hours),
            id=job_id,
            name="Document MRI Sync",
            replace_existing=True,
            next_run_time=first_run,
            max_instances=1,
        )
        logger.info(
            "Added document MRI sync job: site=%s every %dh (first run at %s)",
            site_id,
            interval_hours,
            first_run.strftime("%H:%M:%S"),
        )

    def _run_document_mri_sync(self):
        """Sync documents from MRI Concept API. Runs synchronously via APScheduler."""
        try:
            from app.config.settings import settings

            if not settings.mri_document_base_url:
                logger.warning("[DOC_MRI] MRI_DOCUMENT_BASE_URL not configured — skipping sync")
                return
        except Exception as e:
            logger.warning("[DOC_MRI] Could not load settings: %s — skipping sync", e)
            return

        try:
            import asyncio

            from app.services.document_adapter_mri import ConceptMRIAdapter

            adapter = ConceptMRIAdapter()
            result = asyncio.run(adapter.run_sync(site_id="site-002"))
            if result.get("errors"):
                logger.warning(
                    "[DOC_MRI] sync errors: %s",
                    result["errors"],
                )
            else:
                logger.info(
                    "[DOC_MRI] sync OK: ingested=%s updated=%s",
                    result.get("synced", 0),
                    result.get("failed", 0),
                )
        except Exception as e:
            logger.error("Document MRI sync failed: %s", e, exc_info=True)

    # ── Compiler Worker ─────────────────────────────────────────────────────────

    def add_compiler_worker_job(self, interval_minutes: int = 5):
        """
        Add periodic job to process compiler_queue entries.

        Runs the CompilerWorker.poll_and_process() method every N minutes.
        Each cycle processes up to 50 pending queue entries.

        Args:
            interval_minutes: How often to poll the queue (default: 5 minutes)
        """
        job_id = "compiler_worker"
        if self.scheduler.get_job(job_id):
            self.scheduler.remove_job(job_id)

        self.scheduler.add_job(
            _run_compiler_worker_sync,
            "interval",
            minutes=interval_minutes,
            id=job_id,
            replace_existing=True,
            max_instances=1,
        )
        logger.info("compiler_worker job registered — interval=%s min", interval_minutes)

    def add_financial_roi_job(self, interval_seconds: int = 86400) -> None:
        """Add daily financial ROI recommendation generation job.

        Runs AIRecommendationEngine for each site in advisory+ phase and persists
        financial_roi recommendations (lighting, water, HVAC, occupancy ROI).
        Deduplicates: skips if a financial_roi rec for the same site already exists
        within the last 24 hours.
        """
        job_id = "financial_roi_generation"
        if self.scheduler.get_job(job_id):
            self.scheduler.remove_job(job_id)
        self.scheduler.add_job(
            func=self._run_financial_roi,
            trigger=IntervalTrigger(seconds=interval_seconds),
            id=job_id,
            name="Financial ROI Recommendation Generation (daily)",
            replace_existing=True,
            max_instances=1,
        )
        logger.info("financial_roi_generation job registered — interval=%ds", interval_seconds)

    def _run_financial_roi(self):
        """Generate and persist financial ROI recommendations for all eligible sites."""
        import asyncio
        from datetime import timezone

        try:
            from app.core.site_resolver import get_registered_site_ids
            from app.database.repositories.recommendation_repository import get_recommendation_repository
            from app.models.onboarding_phase import effective_phase
            from app.models.recommendation import ActionRiskLevel, Recommendation, RecommendationStatus
            from app.services.ai_recommendation_engine import AIRecommendationEngine

            site_ids = get_registered_site_ids()
            if not site_ids:
                return

            repo = get_recommendation_repository()
            GENERATION_ALLOWED = {"shadow_live", "advisory", "supervised", "automatic"}

            for site_id in site_ids:
                try:
                    loop = asyncio.new_event_loop()
                    asyncio.set_event_loop(loop)
                    try:
                        current_stage = loop.run_until_complete(effective_phase(site_id))
                    finally:
                        loop.close()

                    if current_stage not in GENERATION_ALLOWED:
                        logger.info("[ROI] Skipping %s — phase=%s", site_id, current_stage)
                        continue

                    # Dedup: skip if a financial_roi rec was created in the last 24h
                    try:
                        from datetime import datetime, timedelta

                        cutoff = (datetime.now(timezone.utc) - timedelta(hours=24)).isoformat()
                        existing = repo.list_recommendations(
                            site_id=site_id,
                            status="pending",
                            limit=1,
                        )
                        roi_recent = any(
                            r.get("action_type") == "financial_roi" and r.get("timestamp", "") >= cutoff
                            for r in (existing or [])
                        )
                        if roi_recent:
                            logger.info("[ROI] Skipping %s — financial_roi rec already created today", site_id)
                            continue
                    except Exception as e:
                        logger.warning("[ROI] Dedup check failed for %s: %s — proceeding", site_id, e)

                    engine = AIRecommendationEngine(site_id)
                    loop = asyncio.new_event_loop()
                    asyncio.set_event_loop(loop)
                    try:
                        result = loop.run_until_complete(engine.generate_recommendations())
                    finally:
                        loop.close()

                    recs = result.get("recommendations", [])
                    if not recs:
                        logger.info("[ROI] %s: 0 financial recs generated", site_id)
                        continue

                    created = 0
                    for rec_dict in recs:
                        try:
                            rec = Recommendation(
                                site_id=site_id,
                                action_type="financial_roi",
                                risk_level=ActionRiskLevel.LOW,
                                target_equipment=site_id,
                                action={
                                    "category": rec_dict.get("category", ""),
                                    "roi_pct": rec_dict.get("roi_pct", 0),
                                    "payback_months": rec_dict.get("payback_months", 0),
                                },
                                reason=rec_dict.get("recommendation", rec_dict.get("reason", "")),
                                expected_impact={
                                    "annual_savings_r": rec_dict.get("annual_savings_r", 0),
                                    "investment_cost_r": rec_dict.get("investment_cost_r", 0),
                                    "roi_pct": rec_dict.get("roi_pct", 0),
                                    "payback_months": rec_dict.get("payback_months", 0),
                                    "messaging": rec_dict.get("messaging", ""),
                                },
                                confidence="medium",
                                confidence_score=0.7,
                                profile="cost_saving",
                                source="financial_roi",
                                source_type="rule_based",
                                status=RecommendationStatus.PENDING,
                                requires_approval=True,
                                metadata={
                                    "rank": rec_dict.get("rank", 0),
                                    "priority": rec_dict.get("priority", "medium"),
                                    "total_annual_savings_r": result.get("total_annual_savings_r", 0),
                                    "source_panel": "finance",
                                },
                            )
                            loop = asyncio.new_event_loop()
                            asyncio.set_event_loop(loop)
                            try:
                                loop.run_until_complete(repo.create(rec))
                            finally:
                                loop.close()
                            created += 1
                        except Exception as e:
                            logger.warning("[ROI] Failed to persist rec for %s: %s", site_id, e)

                    logger.info("[ROI] %s: created %d financial_roi recommendations", site_id, created)

                except Exception as e:
                    logger.error("[ROI] Site %s failed: %s", site_id, e, exc_info=True)

        except Exception as e:
            logger.error("[ROI] Job failed: %s", e, exc_info=True)

    def add_email_intake_poll_job(self, interval_minutes: int = 5) -> None:
        """
        Add periodic job to poll the intelligence intake IMAP mailbox.

        Args:
            interval_minutes: How often to poll (default: 5 minutes)
        """
        job_id = "email_intake_poll"
        if self.scheduler.get_job(job_id):
            self.scheduler.remove_job(job_id)

        self.scheduler.add_job(
            _run_email_intake_poll,
            "interval",
            minutes=interval_minutes,
            id=job_id,
            name="Email Intake IMAP Poller",
            replace_existing=True,
            max_instances=1,
        )
        logger.info("email_intake_poll job registered — interval=%s min", interval_minutes)


# Sync wrapper — APScheduler passes sync functions to job executors
def _run_compiler_worker_sync():
    """Sync wrapper — runs the CompilerWorker directly (it's a sync method)."""
    import logging

    from app.services.compiler_worker import CompilerWorker

    logger = logging.getLogger(__name__)
    try:
        worker = CompilerWorker()
        count = worker.poll_and_process()
        if count:
            logger.info("[CompilerWorker] Processed %d records", count)
    except Exception as exc:
        logger.critical("[CompilerWorker] sync runner failed: %s", exc, exc_info=True)
        raise


def _run_email_intake_poll():
    """Sync wrapper — runs the EmailIntakeService.poll() in a sync context."""
    import logging

    from app.services.email_intake_service import EmailIntakeService

    logger = logging.getLogger(__name__)
    try:
        service = EmailIntakeService()
        results = service.poll()
        if results:
            logger.info("[EmailIntake] Processed %d new email(s)", len(results))
        else:
            logger.debug("[EmailIntake] No new emails in this poll cycle")
    except Exception as exc:
        logger.error("[EmailIntake] poll runner failed: %s", exc, exc_info=True)


def _run_daily_health_sweep_sync():
    """Sync wrapper for daily health sweep — evaluates all sites for promotion gates.

    Iterates all sites in 'shadow_live' or 'advisory' phase and runs a full
    equipment sweep on each, then persists recommendations and notifies on Telegram.
    """
    import asyncio

    logger.info("[HEALTH-SWEEP] Daily sweep triggered")

    async def _sweep():
        from app.database.repositories.site_repository import SiteRepository
        from app.services.ai_optimizer import get_ai_optimizer

        repo = SiteRepository()
        optimizer = get_ai_optimizer()

        # Get sites in onboarding phases that need active monitoring
        active_phases = ["shadow_live", "advisory", "supervised"]
        all_sites = repo.get_all()
        target_sites = [s for s in all_sites if s.get("onboarding_phase", "").lower() in active_phases]

        if not target_sites:
            logger.info("[HEALTH-SWEEP] No sites in active onboarding phases")
            return

        total_recs = 0
        for site in target_sites:
            site_code = site.get("code", "")
            if not site_code:
                continue
            try:
                recs = await optimizer.run_full_equipment_sweep(site_code, bypass_occupancy_gate=True)
                # Persist recommendations
                for rec in recs:
                    try:
                        from app.models.recommendation import ActionRiskLevel, Recommendation, RecommendationStatus

                        recommendation = Recommendation(
                            site_id=site_code,
                            timestamp=datetime.utcnow(),
                            action_type=rec.get("action_type", "health_sweep"),
                            risk_level=ActionRiskLevel.LOW,
                            target_equipment=rec.get("equipment_id", ""),
                            action=rec.get("action", {}),
                            reason=rec.get("reason", ""),
                            expected_impact=rec.get("expected_impact", {}),
                            confidence=rec.get("confidence", 0.5),
                            confidence_score=rec.get("confidence", 0.5),
                            profile=rec.get("profile", ""),
                            source="health_sweep",
                            source_type="health_sweep",
                            status=RecommendationStatus.PENDING,
                        )
                        from app.database.repositories.recommendation_repository import RecommendationRepository

                        repo_rec = RecommendationRepository()
                        repo_rec.create(recommendation)
                    except Exception as rec_err:
                        logger.warning(f"[HEALTH-SWEEP] Failed to persist rec for {rec.get('equipment_id')}: {rec_err}")
                total_recs += len(recs)
                logger.info(f"[HEALTH-SWEEP] {site_code}: {len(recs)} recommendations generated")
            except Exception as site_err:
                logger.warning(f"[HEALTH-SWEEP] Sweep failed for {site_code}: {site_err}")

        logger.info(f"[HEALTH-SWEEP] Complete: {total_recs} total recommendations across {len(target_sites)} sites")

        # Telegram notification if any recommendations generated
        if total_recs > 0:
            try:
                from app.config.settings import settings

                chat_id = getattr(settings, "telegram_alert_chat_id", None) or getattr(
                    settings, "sentry_fm_chat_id", None
                )
                if chat_id:
                    from app.services.telegram_message_sender import get_telegram_sender

                    sender = get_telegram_sender()
                    body = (
                        f"\xf0\x9f\x9f\x8a *SENTINEL Health Sweep*\n"
                        f"{total_recs} recommendations generated across {len(target_sites)} active sites"
                    )
                    await sender.send_text(str(chat_id), body, parse_mode="HTML")
            except Exception as tf_err:
                logger.warning(f"[HEALTH-SWEEP] Telegram notification failed: {tf_err}")

    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)
    try:
        loop.run_until_complete(_sweep())
    finally:
        loop.close()


def _run_recommendation_digest_sync(site_id: str = "site-002"):
    """Sync wrapper for recommendation digest — sends Telegram morning digest."""
    import asyncio
    import logging

    from app.services.recommendation_service import get_recommendation_service

    logger = logging.getLogger(__name__)
    try:

        async def _send():
            svc = get_recommendation_service()
            pending = await svc.get_pending_recommendations(site_id, limit=20)
            if not pending:
                return

            from app.services.telegram_message_sender import get_telegram_sender

            sender = get_telegram_sender()
            from app.config.settings import settings

            chat_id = getattr(settings, "telegram_alert_chat_id", None) or getattr(settings, "sentry_fm_chat_id", None)
            if not chat_id:
                return

            header = (
                f"\xf0\x9f\x93\x9b *SENTINEL Morning Digest \u2014 {site_id.upper()}*\n"
                f"{len(pending)} recommendations pending approval:\n"
            )
            await sender.send_text(str(chat_id), header, parse_mode="HTML")

            from app.services.telegram_message_sender import InlineButton, InlineKeyboard

            for rec in pending[:5]:
                eq = rec.target_equipment or rec.action_type or "unknown"
                reason = rec.reason[:70] if rec.reason else ""
                sev = rec.risk_level.value if hasattr(rec.risk_level, "value") else rec.risk_level or "info"
                body = f"`{eq}` \u2014 {reason}\nSeverity: {sev}"
                rec_id = getattr(rec, "id", "") or ""
                keyboard = InlineKeyboard(
                    rows=[
                        [
                            InlineButton(label="Accept", callback_data=f"rec:accept:{rec_id}"),
                            InlineButton(label="Dismiss", callback_data=f"rec:dismiss:{rec_id}"),
                            InlineButton(label="Open", callback_data=f"rec:open:{rec_id}"),
                        ],
                    ]
                )
                await sender.send_text(str(chat_id), body, keyboard=keyboard, parse_mode="HTML")

        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        try:
            loop.run_until_complete(_send())
        finally:
            loop.close()
    except Exception as e:
        logger.warning(f"Recommendation digest failed: {e}")


# Global scheduler instance
scheduler_service = BackgroundSchedulerService()
