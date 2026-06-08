"""Background Scheduler Service.

Handles periodic background tasks such as:
- Generating demo audit data
- Running AI optimization analysis
- Cleaning up old logs
- Running scheduled maintenance tasks
"""

import asyncio
import logging
import os
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any

from apscheduler.schedulers.background import BackgroundScheduler
from apscheduler.triggers.cron import CronTrigger
from apscheduler.triggers.interval import IntervalTrigger

from app.services.ai_optimizer import get_ai_optimizer
from app.services.audit_logger import AuditLogger
from app.services.phase_promotion_evaluator import get_phase_promotion_evaluator

EXPIRY_HOURS = 24  # Expire pending recommendations older than 24 hours

logger = logging.getLogger(__name__)


def _normalize_value_for_dedup(value: Any) -> str:
    """Normalize numeric values for consistent string comparison in dedup.

    Python's str() distinguishes int from float: str(50)='50', str(50.0)='50.0'.
    JSON stores both as text. This causes '50' != '50.0' in the dedup set,
    allowing duplicate recommendations for the same setpoint.

    Fix: normalize by stripping trailing .0 for integer-valued floats,
    then compare as lowercase strings.
    """
    if value is None:
        return ""
    try:
        # Try to parse as float, normalize, then convert to string
        f = float(value)
        # If it's an integer value (1.0, 50.0, 7.0), drop the decimal
        if f == int(f):
            return str(int(f)).strip().lower()
        return str(f).strip().lower()
    except (ValueError, TypeError):
        return str(value).strip().lower()


def _log_rec_dedup_status(equipment_id: str, point_name: str, action_value: Any, recent_keys: set) -> None:
    """Log dedup decision per recommendation for traceability."""
    if not equipment_id or not point_name:
        return
    rec_key = (equipment_id, point_name, _normalize_value_for_dedup(action_value))
    # Log at most 1 message per equipment per cycle (first rec that hits this path)
    logger.info(
        f"[DEDUP-B] Checking rec: {equipment_id} {point_name}={action_value} "
        f"→ normalized={rec_key[2]} "
        f"in recent_keys={rec_key in recent_keys}"
    )


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
    # Previous conditions for change detection gate
    _last_conditions: dict[str, Any] = {}

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

        # Poll every 30 minutes for live sites (real-time). The sim-time gate inside
        # _run_optimization_analysis_gated handles simulator runs separately.
        # Real-time sites run every 30 minutes regardless of simulator state.
        poll_minutes = 30
        first_run = datetime.now() + timedelta(seconds=60)  # 60s warmup

        self.scheduler.add_job(
            func=self._run_optimization_analysis_gated,
            trigger=IntervalTrigger(minutes=poll_minutes),
            id="run_optimization_analysis",
            name="Run Optimization Analysis (sim-aware)",
            replace_existing=True,
            next_run_time=first_run,
            max_instances=1,
        )
        logger.info(
            f"Added optimization analysis job: poll every {poll_minutes}min, "
            f"sim-gate={self.OPTIMIZATION_SIM_HOURS}h, "
            f"real-fallback={interval_seconds}s "
            f"(first run at {first_run.strftime('%H:%M:%S')})"
        )

    def _run_optimization_analysis_gated(self):
        """Real-time gate — runs every 30 minutes for live sites.

        No simulator, no simulated time. Uses wall-clock datetime.now().
        """
        if self._last_optimization_sim_time is not None:
            elapsed = (datetime.now() - self._last_optimization_sim_time).total_seconds()
            if elapsed < self._optimization_real_interval:
                return
        self._last_optimization_sim_time = datetime.now()
        logger.warning("[AI-OPT] Live site site-002 — running real-time optimization (30min interval)")

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

            # Live site — HVAC comfort recs are allowed 24/7 per user mandate
            logger.warning("[AI-OPT] Live site site-002 — HVAC comfort recs ACTIVE 24/7")

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
            self._pending_advisories: dict[str, list] = {}

            for site_id in site_ids:
                try:
                    # Mode gate: Supabase onboarding_phase is authoritative.
                    # Use effective_phase() which reads sites.onboarding_phase and
                    # normalises legacy names (shadow→shadow_live, auto→automatic).
                    try:
                        from app.models.onboarding_phase import effective_phase

                        current_stage = asyncio.run_coroutine_threadsafe(
                            effective_phase(site_id), self._main_loop
                        ).result(timeout=30)
                    except Exception:
                        current_stage = "commissioning"

                    GENERATION_ALLOWED = {"advisory", "supervised", "automatic"}
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

                    # Condition-change gate: skip if nothing material changed since last cycle
                    try:
                        import httpx

                        token = os.getenv("BRIDGE_API_TOKEN_SITE002") or os.getenv("BRIDGE_API_TOKEN", "")
                        resp = httpx.get(
                            f"http://10.99.0.1:8080/api/sites/{site_id}/telemetry",
                            headers={"Authorization": f"Bearer {token}"},
                            timeout=10,
                        )
                        if resp.is_success:
                            data = resp.json()
                            power = data.get("power", {})
                            current_kw = power.get("total_kw") or 0
                            current_temp = (
                                data.get("chiller", {}).get("supply_temp_c")
                                or data.get("ahu", {}).get("ahu1_supply_temp_c")
                                or 0
                            )
                            current_occ = (
                                100
                                if data.get("security", {}).get("entries", 0) > 500
                                else 50
                                if data.get("security", {}).get("entries", 0) > 100
                                else 10
                            )
                            current_tariff = "peak" if 7 <= datetime.now().hour < 10 else "off_peak"
                            is_occupied = datetime.now().weekday() < 5 and 7 <= datetime.now().hour < 18

                            prev = self._last_conditions.get(site_id, {})
                            prev_kw = prev.get("total_kw")
                            prev_temp = prev.get("outdoor_temp")
                            prev_occ = prev.get("occupancy")
                            prev_tariff = prev.get("tariff_band")
                            prev_occupied = prev.get("is_occupied")

                            changed = False

                            # 1. Power change >5%
                            if prev_kw is not None:
                                if abs(current_kw - prev_kw) / max(prev_kw, 1) * 100 > 5.0:
                                    logger.info("[AI-OPT] Power changed — triggering cycle")
                                    changed = True

                            # 2. Tariff band changed
                            if not changed and prev_tariff is not None and prev_tariff != current_tariff:
                                logger.info("[AI-OPT] Tariff band changed — triggering cycle")
                                changed = True

                            # 3. Occupancy crossed a threshold
                            if not changed and prev_occ is not None:
                                for t in [10, 50, 80]:
                                    if (prev_occ < t) != (current_occ < t):
                                        logger.info(f"[AI-OPT] Occupancy crossed {t}% threshold — triggering cycle")
                                        changed = True
                                        break

                            # 4. Outdoor temp changed >3°C
                            if not changed and prev_temp is not None and current_temp:
                                if abs(current_temp - prev_temp) > 3.0:
                                    logger.info("[AI-OPT] Outdoor temp changed >3°C — triggering cycle")
                                    changed = True

                            # 5. First cycle after occupied hours start
                            if not changed and is_occupied and not prev_occupied:
                                logger.info("[AI-OPT] Building entered occupied hours — triggering cycle")
                                changed = True

                            # Store current conditions
                            self._last_conditions[site_id] = {
                                "total_kw": current_kw,
                                "outdoor_temp": current_temp,
                                "occupancy": current_occ,
                                "tariff_band": current_tariff,
                                "is_occupied": is_occupied,
                            }

                            if not changed and prev_kw is not None:
                                logger.info("[AI-OPT] No condition changed — skipping cycle")
                                continue
                    except Exception:
                        pass

                    try:
                        optimization_result = asyncio.run(get_ai_optimizer().analyze_building(site_id))
                    except Exception:
                        logger.exception(f"[AI-OPT] analyze_building failed for {site_id}")
                        continue

                    # Holistic optimizer — creates recommendations for all active modules
                    # Goes through recommendation_repo.create() to trigger Telegram notifications
                    from app.services.optimization.evaluator import evaluate as holistic_evaluate

                    try:
                        holistic_recs = holistic_evaluate(site_id)
                        for hrec in holistic_recs:
                            hrec_equipment = hrec.get("target_equipment", "")
                            hrec_action = hrec.get("action", {})
                            try:
                                hrec_model = Recommendation(
                                    site_id=site_id,
                                    timestamp=datetime.utcnow(),
                                    action_type="ai_optimization",
                                    risk_level=ActionRiskLevel.MEDIUM,
                                    target_equipment=hrec_equipment,
                                    action=hrec_action,
                                    reason=hrec.get("reason", ""),
                                    expected_impact=hrec.get("expected_impact", {}),
                                    confidence=str(hrec.get("confidence_score", 0.7)),
                                    confidence_score=hrec.get("confidence_score", 0.7),
                                    profile="holistic_optimizer",
                                    source="ai_optimizer",
                                    source_type="rule_based",
                                    status=RecommendationStatus.PENDING,
                                    requires_approval=True,
                                )
                                asyncio.run_coroutine_threadsafe(
                                    recommendation_repo.create(hrec_model), self._main_loop
                                ).result(timeout=30)
                                created_count += 1
                            except Exception as e:
                                logger.warning(
                                    "[HOLISTIC] Failed to persist rec for %s: %s",
                                    hrec_equipment,
                                    e,
                                )
                        if holistic_recs:
                            logger.info("[HOLISTIC] %d recommendations created for %s", len(holistic_recs), site_id)
                    except Exception as e:
                        logger.warning("[HOLISTIC] evaluation failed for %s: %s", site_id, e)

                    # Gate: load active urgent/critical work orders before persisting any recs
                    # Prevents SENTINEL from recommending on equipment with active faults
                    urgent_equipment: set[str] = set()
                    try:
                        from app.database.repositories.work_order_repository import WorkOrderRepository

                        wo_repo = WorkOrderRepository()
                        urgent_wos = asyncio.run_coroutine_threadsafe(
                            wo_repo.get_open_urgent_work_orders(site_id), self._main_loop
                        ).result(timeout=30)
                        urgent_equipment = {wo.get("equipment_code") for wo in urgent_wos if wo.get("equipment_code")}
                        if urgent_equipment:
                            logger.warning(
                                f"[GATE] Active urgent/critical work orders for {site_id}: "
                                f"{len(urgent_equipment)} equipment — {urgent_equipment}"
                            )
                    except Exception as _wo_err:
                        logger.warning(f"[GATE] Could not load urgent work orders: {_wo_err}")

                    recs_len = len(optimization_result.recommendations)
                    logger.warning(
                        "[AI-OPT DEBUG] recs count=%d, recs=%s", recs_len, optimization_result.recommendations
                    )

                    if not optimization_result.recommendations:
                        logger.warning(f"[AI-OPT] {site_id}: 0 recommendations (building at optimal)")
                        continue

                    # Validate recommendations
                    try:
                        validation = asyncio.run_coroutine_threadsafe(
                            get_ai_optimizer().validate_recommendation(site_id, optimization_result),
                            self._main_loop,
                        ).result(timeout=60)
                    except Exception:
                        logger.exception(f"[AI-OPT] validate_recommendation failed for {site_id}")
                        continue

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
                    # Build existing-key set for dedup: (target_equipment, action_type) within 48h
                    existing_maint_keys: set[tuple[str, str]] = set()
                    try:
                        existing_pending = asyncio.run_coroutine_threadsafe(
                            recommendation_repo.get_by_status(site_id, RecommendationStatus.PENDING, limit=500),
                            self._main_loop,
                        ).result(timeout=30)
                        maint_cutoff = datetime.now().replace(tzinfo=None) - timedelta(hours=48)
                        for existing in existing_pending:
                            ts = existing.timestamp
                            if isinstance(ts, str):
                                try:
                                    ts = datetime.fromisoformat(ts)
                                except (ValueError, TypeError):
                                    continue
                            if hasattr(ts, "tzinfo") and ts.tzinfo is not None:
                                ts = ts.replace(tzinfo=None)
                            if ts >= maint_cutoff:
                                existing_maint_keys.add((existing.target_equipment, existing.action_type))
                    except Exception:
                        pass

                    for rec_dict in maintenance_recs:
                        equipment_id = rec_dict.get("target_equipment", "")
                        if not equipment_id:
                            equipment_id = rec_dict.get("equipment_id", "")

                        # Dedup: skip if pending maintenance rec exists for this equipment within 48h
                        dedup_key = (equipment_id, rec_dict.get("action_type", "maintenance"))
                        if dedup_key in existing_maint_keys:
                            logger.debug(
                                "[AI-OPT] Dedup: skipping maintenance rec for %s — already pending",
                                equipment_id,
                            )
                            skipped_count += 1
                            continue

                        # Gate: skip recommendations for equipment with active urgent/critical WO
                        if urgent_equipment and equipment_id in urgent_equipment:
                            logger.warning(
                                f"[GATE] Skipping maintenance recommendation for {equipment_id} — "
                                f"active urgent/critical work order exists"
                            )
                            continue

                        rec_action_type = rec_dict.get("action_type", "")
                        if not rec_action_type:
                            rec_action_type = "health_maintenance"
                        logger.info(
                            "[AI-OPT] Persisting %s rec for %s — maintenance (no validation)",
                            rec_action_type,
                            equipment_id,
                        )
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
                                "cost_zar": optimization_result.projected_savings.get("cost_zar_per_hour"),
                            },
                            confidence="0.7",
                            confidence_score=0.7,
                            profile=optimization_result.profile or "",
                            source="health_engine",
                            source_type="rule_based",
                            status=RecommendationStatus.PENDING,
                            requires_approval=False,
                        )
                        asyncio.run_coroutine_threadsafe(recommendation_repo.create(rec), self._main_loop).result(
                            timeout=30
                        )
                        created_count += 1

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
                    try:
                        validation = asyncio.run_coroutine_threadsafe(
                            get_ai_optimizer().validate_recommendation(site_id, filtered_recommendation),
                            self._main_loop,
                        ).result(timeout=60)
                    except Exception:
                        logger.exception(f"[AI-OPT] control validate_recommendation failed for {site_id}")
                        continue

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
                    try:
                        existing_pending = asyncio.run_coroutine_threadsafe(
                            recommendation_repo.get_by_status(site_id, RecommendationStatus.PENDING, limit=500),
                            self._main_loop,
                        ).result(timeout=30)
                    except Exception:
                        logger.exception(f"[AI-OPT] Failed to fetch existing PENDING recs for {site_id}")
                        continue

                    # Build value-aware dedup set: (equipment, point, value) for recs < 48 sim-hours old
                    # Use effective time so dedup window matches simulated day boundaries
                    dedup_cutoff = datetime.now().replace(tzinfo=None) - timedelta(hours=48)
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
                                action_value = _normalize_value_for_dedup(existing.action.get("value", ""))
                            recent_keys.add((existing.target_equipment, action_point, action_value))

                    # Persist each recommendation
                    for rec_dict in control_recs:
                        # FIX: Use correct field name from ai_optimizer response
                        equipment_id = rec_dict.get("target_equipment", "")
                        if not equipment_id:
                            equipment_id = rec_dict.get("equipment_id", "")

                        # Handle both flat format (point_name) and grouped format (action.point)
                        raw_point = rec_dict.get("point_name", "")
                        if not raw_point:
                            raw_point = rec_dict.get("action", {}).get("point", "")
                        point_name = raw_point

                        # FIX: Force ai_optimization action type if not set
                        rec_action_type = rec_dict.get("action_type", "")
                        if not rec_action_type:
                            rec_action_type = "ai_optimization"

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

                        # Value-aware dedup check: same equipment + point + value within 48h
                        # Handle both flat format (recommended_value) and grouped format (action.value)
                        raw_value = rec_dict.get("recommended_value", "")
                        if raw_value == "":
                            raw_value = rec_dict.get("action", {}).get("value", "")
                        rec_value = _normalize_value_for_dedup(raw_value)
                        if (equipment_id, point_name, rec_value) in recent_keys:
                            skipped_count += 1
                            logger.info(
                                f"[DEDUP-B] Skipped duplicate: {equipment_id} {point_name}={raw_value} "
                                f"(matches existing pending with same normalized value)"
                            )
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

                        # Skip DALI equipment — Tridonic handles autonomously
                        eq_upper = (equipment_id or "").upper()
                        if eq_upper.startswith("S002-DALI") or eq_upper.startswith("DALI"):
                            logger.info(f"[AI-OPT] Skipped DALI equipment {equipment_id}")
                            continue

                        # Real-time — no simulator
                        datetime.now()

                        # FIX: Handle both flat format (recommended_value) and nested format (action.value)
                        action_value = rec_dict.get("recommended_value")
                        if action_value is None:
                            action_value = rec_dict.get("action", {}).get("value")
                        # Log dedup info for first rec of each equipment so we can trace decisions
                        _log_rec_dedup_status(equipment_id, point_name, action_value, recent_keys)
                        current_value = rec_dict.get("current_value")
                        if current_value is None:
                            current_value = rec_dict.get("action", {}).get("current_value")
                        unit_value = rec_dict.get("unit", "")
                        if not unit_value:
                            unit_value = rec_dict.get("action", {}).get("unit", "")

                        # Gate: skip recommendations for equipment with active urgent/critical WO
                        if urgent_equipment and equipment_id in urgent_equipment:
                            logger.warning(
                                f"[GATE] Skipping recommendation for {equipment_id} — "
                                f"active urgent/critical work order exists"
                            )
                            continue

                        rec = Recommendation(
                            site_id=site_id,
                            timestamp=datetime.utcnow(),
                            action_type=rec_action_type or "ai_optimization",
                            risk_level=ActionRiskLevel.LOW,
                            target_equipment=equipment_id,
                            action={
                                "point": point_name,
                                "value": action_value,
                            },
                            reason=rec_dict.get("reason", ""),
                            expected_impact={
                                "current_value": current_value,
                                "recommended_value": action_value,
                                "unit": unit_value,
                                "energy_savings_percent": rec_dict.get("savings_kwh", 5),
                                "cost_zar": optimization_result.projected_savings.get("cost_zar_per_hour"),
                            },
                            confidence=str(confidence_num),
                            confidence_score=confidence_num,
                            profile=optimization_result.profile or "",
                            source="ai_optimizer",
                            source_type="ml_model",
                            status=RecommendationStatus.PENDING,
                            requires_approval=True,
                            shadow_mode=(current_stage == "shadow_live"),
                            metadata={
                                "group_recommendation": is_grouped,
                                "affected_equipment": affected,
                                # Best-effort name for grouped recommendations; pick first affected item with a name
                                "equipment_name": (
                                    affected[0].get("name")
                                    if (
                                        is_grouped
                                        and isinstance(affected, list)
                                        and affected
                                        and isinstance(affected[0], dict)
                                    )
                                    else None
                                )
                                if is_grouped
                                else rec_dict.get("metadata", {}).get("equipment_name"),
                            }
                            if is_grouped
                            else {"equipment_name": rec_dict.get("metadata", {}).get("equipment_name")},
                        )
                        asyncio.run_coroutine_threadsafe(recommendation_repo.create(rec), self._main_loop).result(
                            timeout=30
                        )
                        created_count += 1
                        if current_stage == "shadow_live":
                            logger.info(
                                "[AI-OPT] Stored shadow recommendation evidence for %s; "
                                "no UI event or Telegram notification emitted",
                                rec.target_equipment,
                            )
                            continue
                            # Emit SSE toast event for new AI recommendation
                        try:
                            from app.services.event_emitter import get_event_emitter

                            emitter = get_event_emitter()
                            asyncio.run_coroutine_threadsafe(
                                emitter.emit_recommendation_created(
                                    recommendation_id=rec.id,
                                    site_id=rec.site_id,
                                    action_type=rec.action_type,
                                    reason=rec.reason or "",
                                    confidence=rec.confidence or "medium",
                                    risk_level=rec.risk_level.value if rec.risk_level else "medium",
                                    target_equipment=rec.target_equipment,
                                ),
                                self._main_loop,
                            ).result(timeout=10)
                        except Exception as emit_err:
                            logger.warning(f"Failed to emit recommendation_created SSE event: {emit_err}")

                        # Batch Telegram notifications — collect sendable recs for combined summary
                        try:
                            if self._is_sendable_ai_recommendation(rec):
                                self._pending_advisories.setdefault(site_id, []).append(rec)
                        except Exception:
                            pass

                except Exception as e:
                    logger.error(f"Error analyzing site {site_id}: {e}")
                    error_count += 1

            # ── Combined Telegram summary per site ──────────────────────────
            for _site_id, _recs in self._pending_advisories.items():
                if not _recs:
                    continue
                try:
                    from app.config.settings import settings as _app_settings
                    from app.services.telegram_message_sender import InlineButton, InlineKeyboard, get_telegram_sender

                    _chat_id = getattr(_app_settings, "telegram_alert_chat_id", None) or getattr(
                        _app_settings, "sentry_fm_chat_id", None
                    )
                    if not _chat_id:
                        continue
                    _lines = []
                    for _r in _recs[:8]:
                        _target = _r.target_equipment or ""
                        _point = _r.action.get("point", "") if isinstance(_r.action, dict) else ""
                        _val = _r.action.get("value", "") if isinstance(_r.action, dict) else ""
                        _reason = (_r.reason or "")[:120]
                        _lines.append(f"• {_target}: {_point} → {_val}")
                        _lines.append(f"  {_reason}")
                    if len(_recs) > 8:
                        _lines.append(f"… and {len(_recs) - 8} more")
                    _lines.append("")
                    _lines.append("Open dashboard to create work orders or approve:")
                    _base_url = getattr(_app_settings, "app_base_url", "https://bms.sentinel-ai.co.za")
                    _lines.append(f"{_base_url}/buildings/{_site_id}")
                    _combined = "\n".join(_lines)

                    _keyboard = InlineKeyboard(
                        rows=[
                            [InlineButton(label="✅ Acknowledged", callback_data=f"ack:combined:{_site_id}")],
                        ]
                    )
                    _sender = get_telegram_sender()
                    _send_result = _sender.send_text(
                        chat_id=str(_chat_id),
                        text=f"<b>SENTINEL Advisory — {_site_id}</b>\n\n{_combined}",
                        keyboard=_keyboard,
                    )
                    asyncio.run_coroutine_threadsafe(_send_result, self._main_loop).result(timeout=30)
                    logger.info("[NOTIFY] Combined advisory sent for %s (%d recs)", _site_id, len(_recs))
                except Exception as _notify_err:
                    logger.warning("Failed to send combined Telegram advisory: %s", _notify_err)

            # Health engine disabled — data exists in equipment (health scores) and predictions tables.
            # Maintenance panel reads directly from those tables. No duplication needed.

            logger.warning(
                f"[AI-OPT] Cycle complete: {created_count} created, {skipped_count} deduped, {error_count} errors"
            )

        except Exception as e:
            logger.error(f"Failed to run optimization analysis: {e}")

    def _generate_health_recommendations(self, site_ids, prediction_repo) -> tuple[int, int]:
        """Generate maintenance predictions for degraded equipment using configured thresholds.

        Rule-based — no LLM call. Writes to predictions table instead of recommendations
        (which is reserved for ai_optimization records that count toward the Trust Ladder gate).

        Reads health thresholds from settings page (Supabase system_settings → JSON → defaults).

        Also creates dashboard alerts and sends Sentry/Telegram notifications
        for critical and warning equipment.

        Returns:
            (created_count, deduped_count)
        """
        from app.database.supabase_client import get_supabase_client
        from app.models.onboarding_phase import phase_allows
        from app.services.equipment_alert_service import get_equipment_alert_service
        from app.services.health_threshold_service import get_health_thresholds

        thresholds = get_health_thresholds()
        t_healthy = thresholds.get("healthy", 90)
        t_warning = thresholds.get("warning", 70)
        t_critical = thresholds.get("critical", 50)

        sb = get_supabase_client()
        created = 0
        deduped = 0

        # Maintenance actions by severity — maps to prediction severity field
        ACTIONS = {
            "critical": {
                "action": "urgent_inspection",
                "reason": "Health score below {t_critical}% — schedule urgent inspection and diagnostic. "
                "Equipment may be at risk of failure. Check sensor readings, vibration, "
                "and operating parameters.",
                "probability": 75,
                "timeframe_days": 7,
            },
            "warning": {
                "action": "scheduled_maintenance",
                "reason": "Health score below {t_warning}% — schedule preventive maintenance. "
                "Inspect filters, bearings, connections, and calibration.",
                "probability": 55,
                "timeframe_days": 30,
            },
        }

        for site_id in site_ids:
            try:
                # Get site UUID
                site_resp = sb.table("sites").select("id, onboarding_phase").eq("code", site_id).execute()
                if not site_resp.data:
                    continue
                site_uuid = site_resp.data[0]["id"]
                site_phase = site_resp.data[0].get("onboarding_phase") or "commissioning"
                recommendations_visible = phase_allows(site_phase, "recommendations_ui")

                # Get degraded equipment (below healthy threshold)
                eq_resp = (
                    sb.table("equipment")
                    .select("id,code,type,health_score,status")
                    .eq("site_id", site_uuid)
                    .lt("health_score", t_healthy)
                    .execute()
                )
                if not eq_resp.data:
                    continue

                # Fetch existing active predictions for dedup
                existing_active = (
                    sb.table("predictions")
                    .select("equipment_id")
                    .eq("site_id", site_uuid)
                    .eq("status", "active")
                    .execute()
                )
                existing_eq_ids: set[str] = {r["equipment_id"] for r in existing_active.data}

                # Fetch previous health from last resolved prediction for transition detection
                last_resolved = (
                    sb.table("predictions")
                    .select("equipment_id, evidence")
                    .eq("site_id", site_uuid)
                    .in_("status", ["resolved", "acknowledged", "work_order_raised"])
                    .execute()
                )
                prev_health: dict[str, float | None] = {}
                for r in last_resolved.data:
                    ev = r.get("evidence") or {}
                    if isinstance(ev, dict):
                        prev_health[r["equipment_id"]] = ev.get("current_health")

                for eq in eq_resp.data:
                    eq_uuid = eq["id"]
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

                    # Transition detection — only notify on H→W or W→C changes
                    prev = prev_health.get(eq_uuid)
                    is_transition = False
                    if prev is not None:
                        # healthy→warning: crossed below healthy threshold
                        is_H_to_W = prev >= t_healthy and health < t_healthy
                        # warning→critical: was in warning zone (50-89), now below critical
                        is_W_to_C = prev >= t_critical and prev < t_healthy and health < t_critical
                        is_transition = is_H_to_W or is_W_to_C
                        if not is_transition:
                            logger.info(
                                f"[HEALTH-PRED] {code}: health={health}% — no transition (prev={prev}%), "
                                "skipping notification, still creating prediction"
                            )
                        else:
                            transition_label = "H→W" if is_H_to_W else "W→C"
                            logger.warning(f"[HEALTH-PRED] {code}: {transition_label} transition ({prev}%→{health}%)")
                    else:
                        # No history — treat as first detection, don't notify (can't confirm transition)
                        logger.info(
                            f"[HEALTH-PRED] {code}: first detection health={health}%, no transition notification"
                        )

                    action_info = ACTIONS[severity]

                    # Dedup check — one active prediction per equipment
                    if eq_uuid in existing_eq_ids:
                        deduped += 1
                        continue

                    reason = action_info["reason"].format(t_critical=t_critical, t_warning=t_warning)
                    recommended_action = f"{code} ({eq_type}): health={health}% — {reason}"
                    timeframe_days = action_info["timeframe_days"]
                    probability = action_info["probability"]

                    prediction_data = {
                        "site_id": site_uuid,
                        "equipment_id": eq_uuid,
                        "prediction_type": "health_maintenance",
                        "probability_percent": probability,
                        "confidence": "high",
                        "predicted_failure_date": (datetime.now() + timedelta(days=timeframe_days)).isoformat(),
                        "timeframe_days": timeframe_days,
                        "severity": severity,
                        "status": "active",
                        "recommended_action": recommended_action,
                        "evidence": {
                            "current_health": health,
                            "threshold": t_critical if severity == "critical" else t_warning,
                            "severity": severity,
                        },
                        "repair_cost_zar": None,
                        "replacement_cost_zar": None,
                        "downtime_cost_per_hour_zar": None,
                        "potential_loss_zar": None,
                    }

                    try:
                        prediction_repo.create(prediction_data)
                        created += 1
                        logger.warning(
                            f"[HEALTH-PRED] {code}: health={health}% [{severity.upper()}] — prediction created"
                        )
                        if not recommendations_visible:
                            logger.info(
                                "[HEALTH-PRED] Stored shadow prediction for %s in phase=%s; "
                                "no UI event or Telegram notification emitted",
                                code,
                                site_phase,
                            )
                            continue
                        # Emit SSE event for maintenance panel (reads from predictions)
                        try:
                            from app.services.event_emitter import get_event_emitter

                            emitter = get_event_emitter()
                            asyncio.run_coroutine_threadsafe(
                                emitter.emit_recommendation_created(
                                    recommendation_id="",
                                    site_id=site_id,
                                    action_type="health_maintenance",
                                    reason=recommended_action,
                                    confidence="high",
                                    risk_level=severity,
                                    target_equipment=code,
                                ),
                                self._main_loop,
                            ).result(timeout=10)
                        except Exception as emit_err:
                            logger.warning(f"Failed to emit SSE event: {emit_err}")
                    except Exception as e:
                        logger.warning(f"[HEALTH-PRED] Failed to persist for {code}: {e}")

                    # === DASHBOARD ALERT + SENTRY/TELEGRAM NOTIFICATION — transition only ===
                    if is_transition:
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
                                notify_telegram=True,
                            )
                            if result.get("error"):
                                logger.warning(f"[HEALTH-PRED] Alert creation failed for {code}: {result['error']}")
                            else:
                                tg_status = "sent" if result.get("telegram_sent") else "skipped"
                                logger.warning(
                                    f"[HEALTH-PRED] Alert created for {code} [{severity.upper()}], telegram={tg_status}"
                                )
                        except Exception as e:
                            logger.warning(f"[HEALTH-PRED] Notification failed for {code}: {e}")

            except Exception as e:
                logger.warning(f"[HEALTH-PRED] Error for {site_id}: {e}")

        if created > 0:
            logger.warning(f"[HEALTH-PRED] {created} predictions created, {deduped} deduped")

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

            result = asyncio.run_coroutine_threadsafe(
                generator.generate_predictions_for_all_sites(), self._main_loop
            ).result(timeout=120)
            logger.info(
                f"Prediction generation complete: {result['generated']} generated, "
                f"{result['skipped_duplicate']} skipped (duplicate), "
                f"{result['resolved']} resolved"
            )

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

        poll_seconds = interval_seconds
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

            results = asyncio.run_coroutine_threadsafe(process_pending_verifications(), self._main_loop).result(
                timeout=60
            )
            if results:
                logger.info(
                    "[OUTCOME] Verified %d recommendation outcomes",
                    len(results),
                )
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
            processed = asyncio.run_coroutine_threadsafe(
                self._run_recommendation_processing_async(), self._main_loop
            ).result(timeout=300)
            if processed:
                logger.warning("[REC-PROC] Processed %d recommendation batches", processed)
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
                    logger.warning(f"[REC-PROC] Completed processing for {site_id}")
                elif result and result.get("needs_input"):
                    # Tier 2 — send approval request via Telegram
                    response_text = result.get("response", "")
                    if response_text:
                        await self._send_tier2_telegram_notification(site_id, response_text)
                    processed += 1
                    logger.warning(f"[REC-PROC] Tier 2 approval requested for {site_id}")
                else:
                    logger.debug(f"[REC-PROC] No recommendations to process for {site_id}")
            except Exception as e:
                logger.warning(f"[REC-PROC] Failed to process {site_id}: {e}")

        return processed

    async def _send_tier2_telegram_notification(self, site_id: str, message: str) -> None:
        """Send a Tier 2 approval request as a Telegram notification."""
        try:
            from app.config.settings import settings

            chat_id = getattr(settings, "telegram_alert_chat_id", None) or getattr(settings, "sentry_fm_chat_id", None)
            if not chat_id:
                logger.debug(f"[REC-PROC] No Telegram chat ID configured for {site_id}")
                return

            from app.services.telegram_message_sender import get_telegram_sender

            sender = get_telegram_sender()
            await sender.send_text(str(chat_id), message, parse_mode="Markdown")
            logger.warning(f"[REC-PROC] Tier 2 approval request sent via Telegram for {site_id}")
        except Exception as e:
            logger.warning(f"[REC-PROC] Failed to send Tier 2 Telegram notification: {e}")

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
                asyncio.run_coroutine_threadsafe(svc.escalate_breach(rec.id, breach), self._main_loop).result(
                    timeout=30
                )
        except Exception as e:
            logger.error("Milestone deadline check failed: %s", e)

    def add_recommendation_expiry_job(self, interval_seconds: int = 3600):
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
            expired_count, dedup_count = asyncio.run_coroutine_threadsafe(
                self._run_recommendation_expiry_async(), self._main_loop
            ).result(timeout=120)
            if expired_count or dedup_count:
                logger.info(
                    "[REC-EXPIRY] expired=%d, dedup=%d",
                    expired_count,
                    dedup_count,
                )
        except Exception as e:
            logger.error("Recommendation expiry job failed: %s", e)

    def _run_orphan_alert_cleanup_sync(self):
        """Sync wrapper for orphan alert cleanup."""
        try:
            deleted = asyncio.run_coroutine_threadsafe(self._run_orphan_alert_cleanup_async(), self._main_loop).result(
                timeout=60
            )
            if deleted:
                logger.info("[ALERT-CLEANUP] Deleted %d orphan/stale alerts", deleted)
        except Exception as e:
            logger.error("Orphan alert cleanup job failed: %s", e)

    async def _run_orphan_alert_cleanup_async() -> int:
        """Delete orphaned fault alerts and stale active alerts with no equipment FK.

        Removes:
          1. fault alerts with null equipment_id older than 1 hour (COV monitoring artifacts)
          2. Any alert (any type) with null site_id AND null equipment_id older than 7 days

        Returns:
            Total number of alerts deleted
        """
        from app.database.supabase_client import get_supabase_client

        sb = get_supabase_client()
        deleted = 0

        try:
            # 1. Orphaned fault alerts (null equipment_id, >1h old)
            cutoff_1h = datetime.now(UTC) - timedelta(hours=1)
            result1 = await asyncio.to_thread(
                lambda: (
                    sb.table("alerts")
                    .delete()
                    .not_.eq("equipment_id", "00000000-0000-0000-0000-000000000000")  # not null in Postgres needs this
                    .is_("equipment_id", None)
                    .eq("type", "fault")
                    .eq("status", "active")
                    .lt("created_at", cutoff_1h.isoformat())
                    .execute()
                )
            )
            if result1.data:
                deleted += len(result1.data)
                logger.info("[ALERT-CLEANUP] Removed %d orphan fault alerts", len(result1.data))
        except Exception as e:
            logger.warning("[ALERT-CLEANUP] Orphan fault cleanup failed: %s", e)

        try:
            # 2. Very old alerts with no equipment and no site linkage (>7 days)
            cutoff_7d = datetime.now(UTC) - timedelta(days=7)
            result2 = await asyncio.to_thread(
                lambda: (
                    sb.table("alerts")
                    .delete()
                    .is_("equipment_id", None)
                    .is_("site_id", None)
                    .lt("created_at", cutoff_7d.isoformat())
                    .execute()
                )
            )
            if result2.data:
                deleted += len(result2.data)
                logger.info("[ALERT-CLEANUP] Removed %d ancient orphaned alerts", len(result2.data))
        except Exception as e:
            logger.warning("[ALERT-CLEANUP] Ancient orphan cleanup failed: %s", e)

        return deleted

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
                # Expire ALL pending records older than cutoff regardless of type
                # Uses timestamp comparison directly — no limit, no pagination needed
                result = await asyncio.to_thread(
                    lambda sid=site_id, c=cutoff.isoformat(): (
                        sb.table("recommendations")
                        .select("id, timestamp, action_type")
                        .eq("site_id", sid)
                        .eq("status", "pending")
                        .lt("timestamp", c)
                        .order("timestamp", desc=True)
                        .execute()
                    )
                )

                records = result.data or []
                if not records:
                    continue

                # Partition by action_type — keep the 10 most recent per type
                by_type: dict[str, list[dict]] = {}
                for r in records:
                    by_type.setdefault(r["action_type"], []).append(r)

                ids_to_expire: set[str] = set()

                for _action_type, typed_records in by_type.items():
                    for r in typed_records[3:]:
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
        """Real-time gate — runs every 30 minutes for live sites.

        No simulator, no simulated time. Uses wall-clock datetime.now().
        """
        if self._last_recommendation_sim_time is not None:
            elapsed = (datetime.now() - self._last_recommendation_sim_time).total_seconds()
            if elapsed < self._optimization_real_interval:
                return
        self._last_recommendation_sim_time = datetime.now()
        logger.warning("[REC] Live site site-002 — running real-time recommendation generation (30min interval)")

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

            logger.warning("Running scheduled AI recommendation generation...")

            # Mode gate: build sets for generation + visibility control
            # Generation runs for advisory/supervised/automatic only
            # Shadow mode collects data and trains ML models only — no recommendations
            GENERATION_ALLOWED = {"advisory", "supervised", "automatic"}
            generation_site_ids: set[str] = set()
            shadow_site_ids: set[str] = set()
            try:
                from app.core.site_resolver import get_registered_site_ids
                from app.models.onboarding_phase import effective_phase

                for sid in get_registered_site_ids():
                    try:
                        current_stage = asyncio.run_coroutine_threadsafe(effective_phase(sid), self._main_loop).result(
                            timeout=30
                        )
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

            # Phase 227 — maintenance gap detection (runs once per eligible site)
            from app.services.maintenance_gap_detector import build_gap_recommendation_id, detect_maintenance_gaps

            gap_member_codes: set[str] = set()
            for gap_site in generation_site_ids or []:
                try:
                    gaps = detect_maintenance_gaps(gap_site)
                except Exception as e:
                    logger.warning("Maintenance gap detection failed for %s: %s", gap_site, e)
                    continue
                for gap in gaps:
                    gap_member_codes.update(gap.get("member_codes", []))
                    try:
                        rec_id = build_gap_recommendation_id(gap["site_id"], gap["equipment_type"])
                        client.table("recommendations").upsert(
                            {
                                "id": rec_id,
                                "site_id": gap["site_id"],
                                "timestamp": datetime.utcnow().isoformat(),
                                "action_type": "maintenance_gap",
                                "risk_level": "medium",
                                "target_equipment": f"{gap['equipment_type'].upper()}",
                                "action": {"inspection": "priority"},
                                "reason": (
                                    f"{gap['member_count']} {gap['equipment_type']} units at "
                                    f"health_score <= 65 with no recorded maintenance history."
                                ),
                                "expected_impact": {},
                                "confidence": "medium",
                                "confidence_score": 0.7,
                                "profile": "maintenance_gap",
                                "multi_objective_score": 0.0,
                                "status": "pending",
                                "requires_approval": True,
                                "shadow_mode": False,
                                "metadata": {
                                    "equipment_type": gap["equipment_type"],
                                    "member_count": gap["member_count"],
                                    "member_ids": gap["member_ids"],
                                    "member_codes": gap["member_codes"],
                                    "avg_health_score": gap["avg_health_score"],
                                    "detection": gap["detection"],
                                },
                            },
                            on_conflict="id",
                        ).execute()
                        logger.info(
                            "Maintenance gap: %d %s units at health %s (rec_id=%s)",
                            gap["member_count"],
                            gap["equipment_type"],
                            gap["avg_health_score"],
                            rec_id,
                        )
                    except Exception as e:
                        logger.warning("Failed to persist gap recommendation: %s", e)

            generated = 0
            for eq in all_equipment:
                # Skip equipment already covered by a maintenance gap recommendation
                if eq.get("code") in gap_member_codes:
                    continue
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
                    else:
                        resolver_id = site_code
                        if site_code.startswith("S") and site_code[1:].isdigit():
                            resolver_id = f"site-{site_code[1:]}"

                    is_shadow_site = resolver_id in shadow_site_ids

                    # Licensing gate — skip recommendation generation for equipment
                    # types whose module is not licensed for this site
                    eq_type = eq.get("type", "").lower()
                    if eq_type:
                        from app.services.module_registry_service import module_registry as _module_registry
                        from app.services.simbiot.connection_policy import (
                            infer_module_from_equipment_type as _infer_module,
                        )

                        mt = _infer_module(eq_type)
                        if (
                            mt
                            and mt not in (ModuleType.KPI, ModuleType.ML, ModuleType.ASSETS)
                            and not _module_registry.is_module_active(resolver_id, mt)
                        ):
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
                        title=f"{title_prefix}: {eq.get('code', eq['name'])}",
                        description=description,
                        confidence=0.90 if prediction else 0.75,
                        related_modules=[],
                        telemetry_context={
                            "equipment_id": eq.get("code", eq["id"]),
                            "equipment_name": eq.get("name"),
                            "equipment_type": eq.get("type", "unknown"),
                            "health_score": health,
                            "site_id": f"site-{site_code[1:]}"
                            if site_code.startswith("S") and site_code[1:].isdigit()
                            else site_code,
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

                    if not is_shadow_site:
                        module_registry.add_recommendation(site_code, ai_rec)

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
                                "site_id": f"site-{site_code[1:]}"
                                if site_code.startswith("S") and site_code[1:].isdigit()
                                else site_code,
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
                                "shadow_mode": is_shadow_site,
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

    def _is_sendable_ai_recommendation(self, rec) -> bool:
        """Gate: only send notifications that meet the advisory standard."""
        if rec.action_type != "ai_optimization":
            logger.warning(f"[NOTIFY] Suppressed — not ai_optimization: {rec.action_type}")
            return False
        if rec.target_equipment and "DALI" in rec.target_equipment.upper():
            logger.warning(f"[NOTIFY] Suppressed — DALI equipment: {rec.target_equipment}")
            return False
        action = rec.action or {}
        if not action.get("point") or action.get("value") is None:
            logger.warning(f"[NOTIFY] Suppressed — no specific action: {rec.target_equipment}")
            return False
        reason = rec.reason or ""
        GENERIC_PHRASES = [
            "health score",
            "failure probability",
            "maintenance schedule",
            "no service history",
            "add to maintenance queue",
            "establish maintenance",
        ]
        if any(phrase in reason.lower() for phrase in GENERIC_PHRASES):
            logger.warning(f"[NOTIFY] Suppressed — maintenance content: {reason[:60]}")
            return False
        return True

    def _format_advisory_notification(self, rec, can_create_work_order: bool = False) -> str:
        """Format AI optimization notification with holistic building view."""
        metadata = rec.metadata or {}
        adjustments = metadata.get("all_adjustments", [])
        building_assessment = metadata.get("building_assessment", "")
        title = metadata.get("title") or (
            f"Adjustment for {rec.target_equipment}" if rec.target_equipment else "SENTINEL Advisory"
        )
        saving = metadata.get("saving", "")
        confidence = rec.confidence_score or 0.0
        confidence_basis = metadata.get("confidence_basis", "")
        profile = (rec.profile or "cost_saving").replace("_", " ").title()
        reason = rec.reason or ""

        # Fallback: construct adjustments from flat action format when array is empty
        # (happens when LLM returns point/value at top level instead of nested)
        if not adjustments and rec.action:
            point = rec.action.get("point", "")
            value = rec.action.get("value", "")
            current = rec.action.get("current_value", "")
            unit = rec.action.get("unit", "")
            if point and value is not None:
                adjustments = [
                    {
                        "equipment_id": rec.target_equipment,
                        "point": point,
                        "current_value": current,
                        "recommended_value": value,
                        "unit": unit,
                    }
                ]

        adj_lines = []

        for adj in adjustments[:5]:
            equip_code = adj.get("equipment_id", "")
            point = adj.get("point", "").replace("_", " ").title()
            curr = adj.get("current_value", "")
            recd = adj.get("recommended_value", "")
            unit = adj.get("unit", "")
            display_name = equip_code
            if curr:
                adj_lines.append(f"\u2022 {display_name}: {point} {curr}{unit} -> {recd}{unit}")
            else:
                adj_lines.append(f"\u2022 {display_name}: Set {point} to {recd}{unit}")
        if len(adjustments) > 5:
            adj_lines.append(f"\u2022 ...and {len(adjustments) - 5} more zones")

        lines = [
            "*SENTINEL Advisory — Sandton City Office Tower*",
            "",
            f"<b>{title}</b>",
            "",
        ]
        if building_assessment:
            lines.extend(["<b>Building state:</b>", f"{building_assessment}", ""])
        # Truncate reason at sentence boundary, not mid-word
        _MAX_REASON = 350
        if len(reason) > _MAX_REASON:
            truncated = reason[:_MAX_REASON]
            last_period = truncated.rfind(". ")
            last_newline = truncated.rfind("\n")
            cutoff = max(last_period, last_newline)
            reason = truncated[: cutoff + 1] if cutoff > 150 else truncated.rstrip() + "…"
        lines.extend(
            ["<b>Adjustments needed:</b>", *adj_lines, "", "<b>Why:</b>", reason, "", f"<b>Goal:</b> {profile}"]
        )
        if saving:
            lines.append(f"<b>Saving:</b> {saving}")
        if confidence > 0:
            basis = f" ({confidence_basis})" if confidence_basis else ""
            lines.append(f"<b>Confidence:</b> {round(confidence * 100)}%{basis}")
        if can_create_work_order:
            lines.extend(["", "-> Create a work order if this adjustment needs technician action"])
        else:
            lines.extend(["", "-> Acknowledge once reviewed"])
        return "\n".join(lines)

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

    def add_orphan_alert_cleanup_job(self, interval_minutes: int = 30):
        """Purge orphaned fault alerts (equipment_id=null) and stale active alerts.

        Runs every 30 min to prevent alert-table pollution from COV monitoring spikes
        and equipment with null FK that was present during the uniform-72 scorer era.

        Deletes:
          - fault alerts with null equipment_id and age > 1 hour (orphaned COV artifacts)
          - any alert with no equipment FK and no site FK that is > 7 days old

        Args:
            interval_minutes: How often to run (default 30 min)
        """
        if self.scheduler.get_job("orphan_alert_cleanup"):
            self.scheduler.remove_job("orphan_alert_cleanup")

        first_run = datetime.now() + timedelta(minutes=5)
        self.scheduler.add_job(
            func=self._run_orphan_alert_cleanup_sync,
            trigger=IntervalTrigger(minutes=interval_minutes),
            id="orphan_alert_cleanup",
            name="Orphan Alert Cleanup (30min)",
            replace_existing=True,
            next_run_time=first_run,
            max_instances=1,
            coalesce=True,
        )
        logger.info("orphan_alert_cleanup job registered — every %d min", interval_minutes)

    def add_rag_doc_sync_job(self, interval_hours: int = 12):
        """
        Add a job to incrementally sync changed system docs to the RAG vector store.

        Phase 209: Keeps RAG docs up-to-date by detecting content changes and
        re-embedding only modified documents. Runs every 12 hours (configurable).
        Uses the same incremental logic as ingest_system_docs.py -- watches for
        content changes, updates existing records and re-embeds, skips unchanged.

        Args:
            interval_hours: How often to run the sync (default: 12 hours)
        """
        if self.scheduler.get_job("rag_doc_sync"):
            self.scheduler.remove_job("rag_doc_sync")

        self.scheduler.add_job(
            func=_run_rag_doc_sync,
            trigger=IntervalTrigger(hours=interval_hours),
            id="rag_doc_sync",
            name="RAG Documentation Sync",
            replace_existing=True,
            misfire_grace_time=3600,
            max_instances=1,
        )
        logger.info(f"rag_doc_sync job registered — every {interval_hours}h")

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
                    recommendation = asyncio.run_coroutine_threadsafe(
                        coordinator.evaluate_current_state(site_id), self._main_loop
                    ).result(timeout=120)

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
            from ml.monitoring.drift import EQUIPMENT_TYPES, get_drift_detector
            from ml.monitoring.triggers import RetrainingTrigger

            logger.debug("Running drift detection check...")

            detector = get_drift_detector()

            # Run feature drift detection and record scores to Prometheus
            try:
                from app.api.metrics import sentinel_model_drift_alerts, sentinel_model_drift_score
                from app.services.governance_metrics_collector import governance_metrics

                for eq_type in EQUIPMENT_TYPES:
                    result = detector.detect_feature_drift(eq_type)
                    features_checked = result.get("features_checked", 0)
                    features_drifted = result.get("features_drifted", 0)
                    score = features_drifted / features_checked if features_checked > 0 else 0.0
                    sentinel_model_drift_alerts.labels(site_id="site-002", model_type=eq_type.upper()).set(
                        1 if result.get("drift_detected") else 0
                    )
                    sentinel_model_drift_score.labels(model_id=eq_type, model_type=eq_type.upper()).set(score)
                    governance_metrics.record_drift_score(eq_type, eq_type.upper(), score)
            except Exception as metrics_err:
                logger.debug(f"Drift metrics update skipped: {metrics_err}")

            # Trigger retraining based on drift (uses same detector state)
            trigger = RetrainingTrigger()
            result = trigger.evaluate_and_trigger()

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

            verified = asyncio.run_coroutine_threadsafe(mv_service.run_pending_verifications(), self._main_loop).result(
                timeout=60
            )

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
                logger.warning("Main event loop not available, skipping pending service check")
                pending = []

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
                logger.warning("Main event loop not available, skipping fire pump compliance check")

        except Exception as e:
            logger.error(f"Failed to check fire pump compliance: {e}")

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

    def add_supabase_retention_job(self, interval_seconds: int = 86400):
        """Add periodic Supabase SQL table retention enforcement (POPIA S14)."""
        job_id = "supabase_retention_enforcement"
        if self.scheduler.get_job(job_id):
            self.scheduler.remove_job(job_id)
            logger.info("Removed existing Supabase retention enforcement job")

        self.scheduler.add_job(
            func=self._run_supabase_retention_enforcement,
            trigger=IntervalTrigger(seconds=interval_seconds),
            id=job_id,
            name="Supabase SQL Retention Enforcement",
            replace_existing=True,
        )
        logger.info(
            "Added Supabase retention enforcement job with %ss interval (ML: 7d, Snapshots: 30d, Audit: 5y)",
            interval_seconds,
        )

    def _run_supabase_retention_enforcement(self):
        """Execute Supabase table retention enforcement and log summary."""
        # Direct SQL fallback — reliable even when REST API auth fails
        try:
            import psycopg2

            conn = psycopg2.connect(
                host="127.0.0.1",
                port=55322,
                dbname="postgres",
                user="postgres",
                password="postgres",
            )
            cursor = conn.cursor()
            for table, col, days in [
                ("equipment_fault_events", "recorded_at", 7),
                ("recommendations", "created_at", 7),
                ("predictions", "created_at", 14),
                ("adapter_health", "timestamp", 7),
                ("adapter_health_current", "updated_at", 7),
                ("adapter_health_alerts", "created_at", 7),
                ("space_occupancy_events", "timestamp", 7),
                ("equipment_sensor_readings", "recorded_at", 90),
                ("asset_health_snapshots", "created_at", 30),
                ("system_health_snapshots", "created_at", 30),
            ]:
                cursor.execute(f"DELETE FROM {table} WHERE {col} < now() - interval '{days} days'")
            conn.commit()
            cursor.close()
            conn.close()
        except Exception as e:
            logger.warning(f"SQL retention fallback failed: {e}")

        try:
            from app.services.supabase_retention_service import get_supabase_retention_service

            service = get_supabase_retention_service()

            # TIER 2: ML training data — 7-day rolling delete
            ml_result = service.run_ml_training_deletion(dry_run=False)

            # TIER 4: Operational snapshots — 30-day rolling delete
            snapshot_result = service.run_snapshot_deletion(dry_run=False)

            # TIER 5: Audit trail — 5-year retention (weekly, low urgency)
            audit_result = service.run_audit_trail_deletion(dry_run=False)

            total_deleted = ml_result.total_deleted + snapshot_result.total_deleted + audit_result.total_deleted
            total_reviewed = ml_result.total_reviewed + snapshot_result.total_reviewed + audit_result.total_reviewed
            error_count = len(ml_result.errors) + len(snapshot_result.errors) + len(audit_result.errors)

            logger.info(
                "Supabase retention enforcement completed: deleted=%s reviewed=%s errors=%s",
                total_deleted,
                total_reviewed,
                error_count,
            )

            try:
                from app.services.audit_logger import AuditLogger

                audit_logger = AuditLogger()
                audit_logger.log_system_event(
                    event_type="supabase_retention_enforcement",
                    metadata={
                        "total_deleted": total_deleted,
                        "total_reviewed": total_reviewed,
                        "error_count": error_count,
                        "ml_deleted": ml_result.total_deleted,
                        "snapshot_deleted": snapshot_result.total_deleted,
                        "audit_deleted": audit_result.total_deleted,
                        "dry_run": False,
                    },
                )
            except Exception as exc:
                logger.warning("Failed to write retention enforcement audit event: %s", exc)
        except Exception as e:
            logger.error(f"Failed to run Supabase retention enforcement: {e}", exc_info=True)

    def add_tier1_tier2_aggregation_job(self) -> None:
        """Add nightly tier1->tier2 telemetry aggregation job (00:00 UTC)."""
        job_id = "tier1_to_tier2_aggregation"
        if self.scheduler.get_job(job_id):
            self.scheduler.remove_job(job_id)
            logger.info("Removed existing tier1->tier2 aggregation job")

        self.scheduler.add_job(
            func=self._run_tier1_to_tier2_aggregation,
            trigger=CronTrigger(hour=0, minute=0),
            id=job_id,
            name="Tier1->Tier2 Telemetry Aggregation",
            replace_existing=True,
        )
        logger.info("Added tier1->tier2 aggregation job (daily 00:00 UTC)")

    def _run_tier1_to_tier2_aggregation(self) -> None:
        """Execute tier1->tier2 raw-to-hourly telemetry aggregation."""
        try:
            from app.services.telemetry_aggregation_service import get_telemetry_aggregation_service

            service = get_telemetry_aggregation_service()
            result = service.aggregate_tier1_to_tier2()
            logger.info(
                "[AGGREGATION] Tier1->Tier2: processed=%s written=%s errors=%s",
                result["rows_processed"],
                result["rows_written"],
                len(result["errors"]),
            )
        except Exception as e:
            logger.error(f"[AGGREGATION] Tier1->Tier2 failed: {e}", exc_info=True)

    def add_tier2_tier3_aggregation_job(self) -> None:
        """Add weekly tier2->tier3 telemetry aggregation job (Sunday 01:00 UTC)."""
        job_id = "tier2_to_tier3_aggregation"
        if self.scheduler.get_job(job_id):
            self.scheduler.remove_job(job_id)
            logger.info("Removed existing tier2->tier3 aggregation job")

        self.scheduler.add_job(
            func=self._run_tier2_to_tier3_aggregation,
            trigger=CronTrigger(day_of_week="sun", hour=1, minute=0),
            id=job_id,
            name="Tier2->Tier3 Telemetry Aggregation",
            replace_existing=True,
        )
        logger.info("Added tier2->tier3 aggregation job (weekly Sun 01:00 UTC)")

    def _run_tier2_to_tier3_aggregation(self) -> None:
        """Execute tier2->tier3 hourly-to-daily telemetry aggregation."""
        try:
            from app.services.telemetry_aggregation_service import get_telemetry_aggregation_service

            service = get_telemetry_aggregation_service()
            result = service.aggregate_tier2_to_tier3()
            logger.info(
                "[AGGREGATION] Tier2->Tier3: processed=%s written=%s errors=%s",
                result["rows_processed"],
                result["rows_written"],
                len(result["errors"]),
            )
        except Exception as e:
            logger.error(f"[AGGREGATION] Tier2->Tier3 failed: {e}", exc_info=True)

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
                if write_status in ("succeeded", "failed"):
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

    def add_equipment_health_snapshot_job(self, interval_minutes: int = 15):
        """
        Add a job to compute and store equipment health snapshots periodically.

        Args:
            interval_minutes: How often to recompute snapshots (default: 15 minutes)
        """
        job_id = "equipment_health_snapshot"
        if self.scheduler.get_job(job_id):
            self.scheduler.remove_job(job_id)
            logger.info("Removed existing equipment health snapshot job")

        first_run = datetime.now(UTC) + timedelta(seconds=30)  # 30s warmup
        self.scheduler.add_job(
            func=self._run_equipment_health_snapshot,
            trigger=IntervalTrigger(minutes=interval_minutes),
            id=job_id,
            name="Equipment Health Snapshot",
            replace_existing=True,
            next_run_time=first_run,
            max_instances=1,
        )
        logger.info(
            "Added equipment health snapshot job (%dm interval, first run at %s)",
            interval_minutes,
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

    def add_baseline_capture_job(self, interval_minutes: int = 5):
        """
        Add a job to capture baselines for unscored equipment.

        Runs every 5 minutes to find equipment with NULL health_score
        (newly discovered or recently replaced) and calculates age-only baselines.
        """
        job_id = "baseline_capture"
        if self.scheduler.get_job(job_id):
            self.scheduler.remove_job(job_id)
            logger.info("Removed existing baseline capture job")

        self.scheduler.add_job(
            func=self._run_baseline_capture,
            trigger=IntervalTrigger(minutes=interval_minutes),
            id=job_id,
            name="Baseline Capture",
            replace_existing=True,
            max_instances=1,
        )
        logger.info(f"Added baseline capture job ({interval_minutes}min interval)")

    def _run_baseline_capture(self):
        """Sync wrapper for async baseline capture."""
        try:
            if self._main_loop and self._main_loop.is_running():
                future = asyncio.run_coroutine_threadsafe(
                    self._run_baseline_capture_async(),
                    self._main_loop,
                )
                future.result(timeout=60)
            else:
                asyncio.run(self._run_baseline_capture_async())
        except Exception as e:
            logger.error(f"Baseline capture failed: {e}", exc_info=True)

    async def _run_baseline_capture_async(self):
        """Run baseline capture for unscored equipment."""
        from app.tasks.baseline_capture_task import capture_baselines_for_unscored_equipment

        await capture_baselines_for_unscored_equipment()

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

    def add_focus_overstay_check_job(self, interval_seconds: int = 120):
        """Periodic check for focus room overstays — fires alerts for sessions past the limit."""
        job_id = "focus_overstay_check"
        self.scheduler.add_job(
            func=self._run_focus_overstay_check,
            trigger="interval",
            seconds=interval_seconds,
            id=job_id,
            replace_existing=True,
            name="Focus room overstay check",
        )
        logger.info(f"Focus overstay check scheduled every {interval_seconds}s")

    def _run_focus_overstay_check(self):
        try:
            import asyncio

            loop = asyncio.new_event_loop()
            asyncio.set_event_loop(loop)
            try:
                loop.run_until_complete(self._check_focus_overstays())
            finally:
                loop.close()
        except Exception as e:
            logger.warning(f"Focus overstay check failed: {e}")

    async def _check_focus_overstays(self):
        from app.database.supabase_client import get_supabase_client

        sb = get_supabase_client()
        if not sb:
            return
        try:
            active = sb.table("space_focus_room_sessions").select("*").is_("end_time", None).execute()
        except Exception:
            return
        from app.config.settings import settings
        from app.services.focus_room_notifier import send_focus_overstay_alert
        from app.services.focus_room_session_service import describe_focus_session_state
        from app.services.space_event_service import _overstay_alert_sent

        for session in active.data or []:
            session_id = session.get("session_id") or session.get("id", "")
            if not session_id or session_id in _overstay_alert_sent:
                continue
            room_code = session.get("room_code", "")
            site_id = session.get("site_id", "site-002")
            from datetime import datetime, timedelta, timezone

            from app.services import occupancy_store

            active_sesh = occupancy_store.get_active_session(room_code)
            if not active_sesh or active_sesh.session_id != session_id:
                continue
            # SAST is UTC+2 - use local time to match session timestamps
            SAST = timezone(timedelta(hours=2))
            state = describe_focus_session_state(active_sesh, now=datetime.now(SAST).replace(tzinfo=None))
            if state.get("red_light_on"):
                _overstay_alert_sent.add(session_id)
                cooldown = max(1, int((settings.focus_red_light_cooldown_seconds or 300) / 60))
                loop = asyncio.get_event_loop()
                loop.create_task(
                    send_focus_overstay_alert(
                        site_id=site_id,
                        room_code=room_code,
                        max_allowed_minutes=max(1, int((settings.focus_extended_use_seconds or 7200) / 60)),
                        cooldown_minutes=cooldown,
                    )
                )
                logger.info("Focus overstay alert triggered via periodic check: %s", room_code)

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

        This keeps ML models current during shadow mode operation when the bridge is live.
        Note: ENABLE_SITE002_SOURCE was deprecated 2026-06 — simulation engine removed.

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

        Always runs; site-002 bridge polling is independent of the deprecated ENABLE_SITE002_SOURCE flag.

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

    # ── IPMVP Data Sync ─────────────────────────────────────────────────────────

    def add_ipmvp_sync_job(self, interval_hours: int = 1):
        """Add periodic job to fetch IPMVP data from bridge and persist to Supabase.

        Consumes /ipmvp/energy, /oat, /events, /occupancy, /tariff endpoints
        and stores in dedicated ipmvp_* tables for engineering M&V analysis.
        """
        job_id = "ipmvp_data_sync"
        if self.scheduler.get_job(job_id):
            self.scheduler.remove_job(job_id)

        self.scheduler.add_job(
            func=self._run_ipmvp_sync,
            trigger=IntervalTrigger(hours=interval_hours),
            id=job_id,
            name="IPMVP Data Sync — Bridge → Supabase",
            replace_existing=True,
            max_instances=1,
        )
        logger.info("IPMVP data sync job registered — interval=%s hours", interval_hours)

    def _run_ipmvp_sync(self):
        """Run IPMVP data sync in a new event loop."""
        import asyncio

        try:
            from app.services.ipmvp.site002_fetcher import Site002DataFetcher

            fetcher = Site002DataFetcher()
            loop = asyncio.new_event_loop()
            asyncio.set_event_loop(loop)
            try:
                result = loop.run_until_complete(fetcher.run_full_sync(days_back=7))
                logger.info("[IPMVP] Sync result: %s", result)
            finally:
                loop.close()
        except Exception as e:
            logger.error("[IPMVP] Sync failed: %s", e, exc_info=True)

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
            GENERATION_ALLOWED = {"advisory", "supervised", "automatic"}

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

                        cutoff = (datetime.now(UTC) - timedelta(hours=24)).isoformat()
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

    def add_rooms_email_intake_poll_job(self, interval_minutes: int = 5) -> None:
        """Add periodic job to poll the rooms@ IMAP mailbox."""
        job_id = "rooms_email_intake_poll"
        if self.scheduler.get_job(job_id):
            self.scheduler.remove_job(job_id)

        self.scheduler.add_job(
            _run_rooms_email_intake_poll,
            "interval",
            minutes=interval_minutes,
            id=job_id,
            name="Rooms Email Intake IMAP Poller",
            replace_existing=True,
            max_instances=1,
        )
        logger.info("rooms_email_intake_poll job registered — interval=%s min", interval_minutes)

    # -----------------------------------------------------------------
    # BACnet Discovery Polling — detect equipment changes on site-002
    # -----------------------------------------------------------------

    def add_bacnet_discovery_polling_job(self, interval_seconds: int = 21600, site_id: str = "site-002"):
        """Add a job to periodically discover BACnet devices and detect equipment changes.

        Polls the bridge at 10.99.0.1:8080 for the BACnet object catalog, then
        compares discovered equipment against known records in the database.
        New devices, missing devices, and metadata changes are logged and tracked.

        Args:
            interval_seconds: How often to scan (default: 21600 = 6 hours)
            site_id: Site to scan (default: site-002)
        """
        job_id = "bacnet_discovery_polling"
        if self.scheduler.get_job(job_id):
            self.scheduler.remove_job(job_id)
            logger.info("Removed existing BACnet discovery polling job")

        first_run = datetime.now() + timedelta(minutes=15)  # give system time to settle

        self.scheduler.add_job(
            func=self._run_bacnet_discovery,
            trigger=IntervalTrigger(seconds=interval_seconds),
            id=job_id,
            name=f"BACnet Discovery Polling ({site_id})",
            args=[site_id],
            replace_existing=True,
            next_run_time=first_run,
            max_instances=1,
            coalesce=True,
        )
        logger.info(
            "Added BACnet discovery polling job for %s: every %ds (first run at %s)",
            site_id,
            interval_seconds,
            first_run.strftime("%H:%M:%S"),
        )

    def _run_bacnet_discovery(self, site_id: str = "site-002"):
        """Query the bridge for BACnet objects and detect equipment changes.

        Fetches the full BACnet object catalog from the bridge at 10.99.0.1:8080,
        extracts equipment IDs, and compares against known equipment in the DB.
        Logs new, missing, or changed equipment.
        """
        try:
            import asyncio
            import os

            import httpx

            token = os.getenv("BRIDGE_API_TOKEN_SITE002") or os.getenv("BRIDGE_API_TOKEN", "")
            if not token:
                logger.warning("[BACNET-DISCOVERY] No bridge token configured — skipping")
                return

            base_url = "http://10.99.0.1:8080"
            headers = {"Authorization": f"Bearer {token}"}

            async def _fetch_objects() -> list[dict]:
                async with httpx.AsyncClient(timeout=30.0) as client:
                    resp = await client.get(
                        f"{base_url}/api/sites/{site_id}/objects",
                        headers=headers,
                        params={"limit": 2000},
                    )
                    resp.raise_for_status()
                    data = resp.json()
                    return data.get("objects", [])

            loop = asyncio.new_event_loop()
            asyncio.set_event_loop(loop)
            try:
                objects = loop.run_until_complete(_fetch_objects())
            finally:
                loop.close()

            if not objects:
                logger.info("[BACNET-DISCOVERY] No BACnet objects returned from bridge for %s", site_id)
                return

            bridge_equipment_ids: set[str] = set()
            object_by_equipment: dict[str, list[dict]] = {}
            for obj in objects:
                eq_id = (obj.get("equipment_id") or "").strip()
                if eq_id:
                    bridge_equipment_ids.add(eq_id)
                    object_by_equipment.setdefault(eq_id, []).append(obj)

            logger.info(
                "[BACNET-DISCOVERY] Bridge reports %d BACnet objects across %d equipment for %s",
                len(objects),
                len(bridge_equipment_ids),
                site_id,
            )

            known_codes: set[str] = set()
            try:
                from app.database.supabase_client import get_supabase_client

                sb = get_supabase_client()
                site_resp = sb.table("sites").select("id").eq("code", site_id).limit(1).execute()
                if not site_resp.data:
                    logger.warning("[BACNET-DISCOVERY] Site %s not found in database", site_id)
                    return
                site_uuid = site_resp.data[0]["id"]
                resp = sb.table("equipment").select("code").eq("site_id", site_uuid).execute()
                known_codes = {row["code"] for row in (resp.data or [])}
            except Exception as db_err:
                logger.warning("[BACNET-DISCOVERY] DB query failed: %s", db_err)

            new_equipment = bridge_equipment_ids - known_codes
            missing_equipment = known_codes - bridge_equipment_ids

            if new_equipment:
                logger.warning(
                    "[BACNET-DISCOVERY] NEW equipment detected on %s (%d): %s",
                    site_id,
                    len(new_equipment),
                    sorted(new_equipment)[:20],
                )
            if missing_equipment:
                logger.warning(
                    "[BACNET-DISCOVERY] MISSING equipment on %s (%d): %s",
                    site_id,
                    len(missing_equipment),
                    sorted(missing_equipment)[:20],
                )

            if not new_equipment and not missing_equipment:
                logger.info(
                    "[BACNET-DISCOVERY] No equipment changes detected for %s",
                    site_id,
                )

            logger.info(
                "[BACNET-DISCOVERY] Summary for %s: %d total, %d new, %d missing",
                site_id,
                len(bridge_equipment_ids),
                len(new_equipment),
                len(missing_equipment),
            )

        except httpx.ConnectError:
            logger.warning("[BACNET-DISCOVERY] Bridge unreachable for %s — will retry next cycle", site_id)
        except httpx.TimeoutException:
            logger.warning("[BACNET-DISCOVERY] Bridge timed out for %s — will retry next cycle", site_id)
        except Exception as e:
            logger.error("[BACNET-DISCOVERY] Failed for %s: %s", site_id, e, exc_info=True)


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


def _run_rooms_email_intake_poll():
    """Sync wrapper — runs the RoomsEmailIntakeService.poll()."""
    import logging

    from app.services.rooms_email_intake_service import RoomsEmailIntakeService

    logger = logging.getLogger(__name__)
    try:
        service = RoomsEmailIntakeService()
        results = service.poll()
        if results:
            logger.info("[RoomsEmail] Processed %d new email(s)", len(results))
        else:
            logger.debug("[RoomsEmail] No new emails in this poll cycle")
    except Exception as exc:
        logger.error("[RoomsEmail] poll runner failed: %s", exc, exc_info=True)


def _run_daily_health_sweep_sync():
    """Sync wrapper for daily health sweep — evaluates sites for promotion gates.

    Iterates all sites in 'advisory' or above and runs a full equipment sweep
    on each, then persists recommendations and notifies on Telegram.
    """
    import asyncio

    logger.info("[HEALTH-SWEEP] Daily sweep triggered")

    async def _sweep():
        from app.database.repositories.site_repository import SiteRepository
        from app.services.ai_optimizer import get_ai_optimizer

        repo = SiteRepository()
        optimizer = get_ai_optimizer()

        # Get sites in onboarding phases that need active monitoring
        active_phases = ["advisory", "supervised"]
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
                        f"*SENTINEL Health Sweep*\n"
                        f"{total_recs} recommendations generated across {len(target_sites)} active sites"
                    )
                    await sender.send_text(str(chat_id), body, parse_mode="Markdown")
            except Exception as tf_err:
                logger.warning(f"[HEALTH-SWEEP] Telegram notification failed: {tf_err}")

    asyncio.run_coroutine_threadsafe(_sweep(), scheduler_service._main_loop).result(timeout=300)


def _run_rag_doc_sync():
    """Incrementally sync changed system docs to the RAG vector store.

    Compares each doc's current content against the stored full_text in Supabase.
    Only re-embeds documents where content has actually changed. Skips the rest.

    Runs as a background APScheduler job every 12 hours (or as configured).
    """
    import subprocess
    import sys

    logger.info("[RAG-SYNC] Documentation sync job triggered")

    try:
        # Run the ingest script in incremental mode (no --force, no --file)
        # The script itself handles change detection via full_text comparison
        result = subprocess.run(
            [
                sys.executable,
                "/opt/bms-intelligence/backend/scripts/ingest_system_docs.py",
            ],
            capture_output=True,
            text=True,
            timeout=600,  # 10 minute max
        )
        if result.returncode == 0:
            logger.info("[RAG-SYNC] Documentation sync completed successfully")
        else:
            logger.warning("[RAG-SYNC] Documentation sync completed with errors: %s", result.stderr)
    except Exception as e:
        logger.error("[RAG-SYNC] Documentation sync failed: %s", e)


def _run_recommendation_digest_sync(site_id: str = "site-002"):
    """Send morning building digest to FM Telegram — health, alerts, work orders, AI recommendations."""
    import asyncio
    import logging

    from app.services.recommendation_service import get_recommendation_service

    logger = logging.getLogger(__name__)

    BUILDING_NAMES = {
        "site-001": "Rosebank Towers",
        "site-002": "Sandton City Office Tower",
        "site-003": "Centurion Mall",
        "site-004": "V&A Waterfront Retail",
        "site-005": "Gateway Theatre of Shopping",
        "site-006": "Mediclinic Sandton",
        "site-007": "Mediclinic Constantiaberg",
        "site-008": "Standard Bank Centre",
        "site-009": "Standard Bank Rosebank",
        "site-010": "Standard Bank Durban Regional",
    }

    try:

        async def _send():
            from app.config.settings import settings
            from app.services.telegram_message_sender import get_telegram_sender

            sender = get_telegram_sender()
            chat_id = getattr(settings, "telegram_alert_chat_id", None) or getattr(settings, "sentry_fm_chat_id", None)
            if not chat_id:
                return

            # --- 1. Equipment health from Supabase ---
            critical_assets = []
            warning_assets = []
            healthy_count = 0
            total_assets = 0
            site_uuid = None
            try:
                from app.database.supabase_client import get_supabase_client

                sb = get_supabase_client()
                # Resolve site UUID from resolver ID (site-002 format matches DB)
                site_code = site_id.lower()  # site-002, site-005, etc.
                site_resp = sb.table("sites").select("id").eq("code", site_code).limit(1).execute()
                site_uuid = site_resp.data[0]["id"] if site_resp.data else None
                if not site_uuid:
                    logger.warning(f"[DIGEST] Site not found: {site_id}")
                else:
                    resp = (
                        sb.table("equipment")
                        .select("code,name,type,health_score,location,status,manufacturer")
                        .eq("site_id", site_uuid)
                        .execute()
                    )
                    if resp.data:
                        total_assets = len(resp.data)
                        for eq in resp.data:
                            hs = eq.get("health_score") or 100
                            if hs < 70:
                                critical_assets.append(eq)
                            elif hs < 90:
                                warning_assets.append(eq)
                            else:
                                healthy_count += 1
            except Exception as e:
                logger.warning(f"[DIGEST] Could not fetch equipment health: {e}")

            # --- 2. Active alerts ---
            alert_count = 0
            critical_alerts = []
            try:
                from app.database.repositories.alert_repository import AlertRepository

                alert_repo = AlertRepository()
                all_alerts = await alert_repo.get_all(status="active", site_id=site_uuid)
                if all_alerts:
                    alert_count = len(all_alerts)
                    critical_alerts = [
                        a for a in all_alerts if str(a.get("severity", "") or "").lower() in ("critical", "high")
                    ][:5]
            except Exception as e:
                logger.warning(f"[DIGEST] Could not fetch active alerts: {e}")

            # --- 3. Open work orders ---
            open_wo_count = 0
            try:
                from app.services.csv_loader import WorkOrderData

                site_wos = WorkOrderData.get_by_site(site_id) if site_id else WorkOrderData.load()
                open_wo_count = sum(
                    1 for wo in site_wos if str(wo.get("status", "")).lower() in ("open", "scheduled", "in_progress")
                )
            except Exception as e:
                logger.warning(f"[DIGEST] Could not fetch work orders: {e}")

            # --- 4. Pending AI recommendations ---
            ai_recs = []
            try:
                svc = get_recommendation_service()
                # Use site-002 format directly (matches DB column)
                pending = await svc.get_pending_recommendations(site_id, limit=20)
                ADVISORY_TYPES = {"ai_optimization"}
                ai_recs = [r for r in pending if (getattr(r, "action_type", "") or "") in ADVISORY_TYPES]
            except Exception as e:
                logger.warning(f"[DIGEST] Could not fetch recommendations: {e}")

            # --- 5. ROI savings (verified vs estimated) ---
            verified_savings = 0
            estimated_savings = 0
            verified_count = 0
            try:
                from app.mcp.openai_connector_server import get_openai_connector_server

                server = get_openai_connector_server()
                roi = await server.get_roi_summary(site_id, "all")
                verified_savings = roi.get("verified_savings_zar") or 0
                estimated_savings = roi.get("estimated_savings_zar") or 0
                verified_count = roi.get("verified_count") or 0
            except Exception as e:
                logger.warning(f"[DIGEST] Could not fetch ROI summary: {e}")

            # --- Build digest ---
            site_name = BUILDING_NAMES.get(site_id, site_id.upper())
            lines = []

            lines.append(f"*SENTINEL Morning Digest — {site_name}*")
            lines.append(f"Generated: {datetime.now().strftime('%Y-%m-%d %H:%M SAST')}")
            lines.append("")

            # Health section
            if critical_assets:
                health_status = "CRITICAL"
            elif warning_assets:
                health_status = "NEEDS ATTENTION"
            else:
                health_status = "HEALTHY"

            lines.append(f"*Building Health:* {health_status}")
            lines.append(
                f"Total: {total_assets} │ "
                f"Critical: {len(critical_assets)} │ "
                f"Warning: {len(warning_assets)} │ "
                f"Healthy: {healthy_count}"
            )

            if critical_assets:
                lines.append("\n*Critical equipment:*")
                for eq in critical_assets[:5]:
                    hs = eq.get("health_score", 0)
                    name = eq.get("name", eq.get("code", "?"))
                    loc = eq.get("location", "")
                    loc_str = f" @ {loc}" if loc else ""
                    lines.append(f"  ● {name} ({hs}%){loc_str}")
            if warning_assets:
                lines.append("\n*Warning:*")
                for eq in warning_assets[:3]:
                    hs = eq.get("health_score", 0)
                    name = eq.get("name", eq.get("code", "?"))
                    lines.append(f"  ○ {name} ({hs}%)")

            # Alerts section
            lines.append("")
            if alert_count > 0:
                lines.append(f"*Active Alerts:* {alert_count} ({len(critical_alerts)} critical)")
                for a in critical_alerts[:3]:
                    msg = getattr(a, "message", "Alert")[:60]
                    lines.append(f"  [{getattr(a, 'severity', '?').upper()}] {msg}")
            else:
                lines.append("*Active Alerts:* 0")

            # Work orders section
            lines.append(f"*Open Work Orders:* {open_wo_count}")

            # Savings section
            if verified_savings > 0 or estimated_savings > 0:
                lines.append(f"*Savings this month:* R{verified_savings:,.0f} verified")
                if estimated_savings > 0:
                    lines.append(
                        f"   + R{estimated_savings:,.0f} estimated ({verified_count} recommendation{'s' if verified_count != 1 else ''} confirmed)"
                    )
            else:
                lines.append("*Savings this month:* No verified savings yet")

            # AI recommendations section
            lines.append("")
            if ai_recs:
                lines.append(f"*AI Recommendations:* {len(ai_recs)} pending approval")
                from app.services.telegram_message_sender import InlineButton, InlineKeyboard

                for rec in ai_recs[:5]:
                    eq = getattr(rec, "target_equipment", "?") or "?"
                    reason = (getattr(rec, "reason", "") or "")[:65]
                    sev = getattr(rec.risk_level, "value", None) if hasattr(rec, "risk_level") else None
                    sev = sev or getattr(rec, "risk_level", "info") or "info"
                    body = f"`{eq}` — {reason}\nSeverity: {sev}"
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
                    await sender.send_text(str(chat_id), body, keyboard=keyboard, parse_mode="Markdown")
            else:
                lines.append("*AI Recommendations:* None pending")

            digest = "\n".join(lines)
            await sender.send_text(str(chat_id), digest, parse_mode="Markdown")

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
