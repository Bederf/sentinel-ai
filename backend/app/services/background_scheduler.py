"""Background Scheduler Service.

Handles periodic background tasks such as:
- Generating demo audit data
- Running AI optimization analysis
- Cleaning up old logs
- Running scheduled maintenance tasks
"""

import asyncio
import logging
from datetime import datetime
from pathlib import Path
from apscheduler.schedulers.background import BackgroundScheduler
from apscheduler.triggers.interval import IntervalTrigger

from app.config.settings import settings
from app.services.audit_logger import AuditLogger
from app.services.ai_optimizer import get_ai_optimizer
from app.models.optimization import OptimizationStatus

logger = logging.getLogger(__name__)

# Data directory
DATA_DIR = Path(__file__).parent.parent / "data"


class BackgroundSchedulerService:
    """Singleton background scheduler service."""

    _instance = None
    _scheduler = None

    def __new__(cls):
        """Ensure singleton pattern."""
        if cls._instance is None:
            cls._instance = super(BackgroundSchedulerService, cls).__new__(cls)
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
            from app.models.audit_log import AuditResultType as ART
            from app.database.repositories.equipment_repository import EquipmentRepository

            logger.debug("Generating periodic demo audit data...")

            # Get real equipment IDs from site-002
            demo_devices = []
            try:
                equipment_repo = EquipmentRepository()
                equipment_list = equipment_repo.get_by_building_code("site-002")
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
                    demo_devices = [
                        eq.get("code") or eq.get("equipment_id") or eq.get("id")
                        for eq in equipment_list
                        if any(t in (eq.get("type", "") or "").lower() for t in controllable_types)
                    ][:20]  # Limit to 20 devices
            except Exception as e:
                logger.warning(f"Could not fetch site-002 equipment: {e}")

            # Fallback to real Sandton City equipment codes if Supabase unavailable
            if not demo_devices:
                demo_devices = [
                    "S002-CHILLER-B1-001",
                    "S002-CHILLER-B1-002",
                    "S002-CHILLER-B1-003",
                    "S002-AHU-L0-01",
                    "S002-AHU-L1-01",
                    "S002-AHU-L2-01",
                    "S002-FCU-L0-A",
                    "S002-FCU-L1-A",
                    "S002-FCU-L1-C",
                    "S002-FCU-L2-A",
                    "S002-FCU-L2-C",
                    "S002-VAV-L0-C",
                    "S002-VAV-L1-A",
                    "S002-VAV-L1-E",
                    "S002-VAV-L2-A",
                    "S002-VAV-L2-E",
                    "S002-DALI-L0-01",
                    "S002-DALI-L1-01",
                    "S002-DALI-L2-05",
                    "S002-LUM-L0-A",
                    "S002-LUM-L1-A",
                    "S002-LUM-L2-E",
                    "S002-GEN-B1-001",
                    "S002-GEN-B1-002",
                    "S002-UPS-B1-001",
                    "S002-ATS-B1-001",
                    "S002-TX-B1-001",
                    "S002-MTR-B1-MAIN",
                    "S002-CO2-L1-E",
                ]

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

    def add_optimization_analysis_job(self, interval_seconds: int = 900):
        """
        Add a job to run optimization analysis periodically.

        Args:
            interval_seconds: How often to run analysis (default: 900 seconds = 15 minutes)
        """
        # Remove existing job if it exists
        if self.scheduler.get_job("run_optimization_analysis"):
            self.scheduler.remove_job("run_optimization_analysis")
            logger.info("Removed existing optimization analysis job")

        # Add new job
        self.scheduler.add_job(
            func=self._run_optimization_analysis,
            trigger=IntervalTrigger(seconds=interval_seconds),
            id="run_optimization_analysis",
            name="Run Optimization Analysis",
            replace_existing=True,
        )
        logger.info(f"Added optimization analysis job with {interval_seconds}s interval")

    def _run_optimization_analysis(self):
        """
        Wrapper to run optimization analysis for all enabled sites (runs in background).
        """
        try:
            logger.debug("Running periodic optimization analysis...")

            # Load sites
            import json

            sites_file = DATA_DIR / "sites.json"
            if not sites_file.exists():
                logger.warning("sites.json not found, skipping optimization analysis")
                return

            with open(sites_file) as f:
                sites = json.load(f)

            # Find sites with optimization enabled
            enabled_sites = [s for s in sites if s.get("optimization_enabled", False)]

            if not enabled_sites:
                logger.debug("No sites with optimization enabled found")
                return

            logger.info(f"Running optimization analysis for {len(enabled_sites)} enabled sites")

            import asyncio

            results = []

            # Run analysis for each enabled site
            for site in enabled_sites:
                site_id = site.get("id")
                site_name = site.get("name", site_id)

                try:
                    # Run async analysis in new event loop
                    loop = asyncio.new_event_loop()
                    asyncio.set_event_loop(loop)

                    recommendation = loop.run_until_complete(get_ai_optimizer().analyze_building(site_id))

                    loop.close()

                    # Validate recommendation
                    loop = asyncio.new_event_loop()
                    asyncio.set_event_loop(loop)

                    validation = loop.run_until_complete(
                        get_ai_optimizer().validate_recommendation(site_id, recommendation)
                    )

                    loop.close()

                    # Update site status
                    # Only mark as pending if there are actual recommendations to show
                    if validation["allowed"] and len(recommendation.recommendations) > 0:
                        site["optimization_status"] = OptimizationStatus.RECOMMENDATION_PENDING.value
                        site["last_recommendation"] = recommendation.to_dict()
                        results.append(
                            {
                                "site_id": site_id,
                                "site_name": site_name,
                                "status": "success",
                                "confidence": recommendation.confidence,
                                "recommendations_count": len(recommendation.recommendations),
                            }
                        )
                    elif validation["allowed"] and len(recommendation.recommendations) == 0:
                        # No actionable recommendations - don't show notification
                        site["optimization_status"] = OptimizationStatus.OPTIMIZED.value
                        site["last_recommendation"] = None  # Clear any old recommendation
                        results.append(
                            {
                                "site_id": site_id,
                                "site_name": site_name,
                                "status": "skipped",
                                "reason": (
                                    "No actionable adjustments available"
                                    " (building has no controllable HVAC"
                                    " assets or conditions don't warrant"
                                    " changes)"
                                ),
                            }
                        )
                    else:
                        site["optimization_status"] = OptimizationStatus.WARNING.value
                        site["last_recommendation"] = recommendation.to_dict()
                        results.append(
                            {
                                "site_id": site_id,
                                "site_name": site_name,
                                "status": "warning",
                                "reason": "Safety validation failed",
                            }
                        )

                    # Update last_analysis timestamp
                    if "optimization_settings" not in site:
                        site["optimization_settings"] = {}

                    site["optimization_settings"]["last_analysis"] = datetime.now().isoformat()

                    # Add to history
                    if "optimization_history" not in site:
                        site["optimization_history"] = []

                    from app.models.optimization import OptimizationHistoryEntry

                    history_entry = OptimizationHistoryEntry(
                        timestamp=datetime.now().isoformat(),
                        action="analyzed",
                        result="success" if validation["allowed"] else "warning",
                        user="scheduler",
                        details={
                            "confidence": recommendation.confidence,
                            "validation_passed": validation["allowed"],
                            "recommendations_count": len(recommendation.recommendations),
                        },
                    )
                    site["optimization_history"].append(history_entry.to_dict())

                    # Keep only last 50 history entries
                    if len(site["optimization_history"]) > 50:
                        site["optimization_history"] = site["optimization_history"][-50:]

                except Exception as e:
                    logger.error(f"Error analyzing site {site_id}: {e}")
                    site["optimization_status"] = OptimizationStatus.ERROR.value
                    site["error_message"] = str(e)
                    results.append(
                        {
                            "site_id": site_id,
                            "site_name": site_name,
                            "status": "error",
                            "error": str(e),
                        }
                    )

            # Save updated sites back to file
            with open(sites_file, "w") as f:
                json.dump(sites, f, indent=2)

            # Log summary
            success_count = len([r for r in results if r["status"] == "success"])
            warning_count = len([r for r in results if r["status"] == "warning"])
            error_count = len([r for r in results if r["status"] == "error"])

            logger.info(
                f"Optimization analysis complete: {success_count} success, "
                f"{warning_count} warnings, {error_count} errors"
            )

        except Exception as e:
            logger.error(f"Failed to run optimization analysis: {e}")

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

        # Add new job
        self.scheduler.add_job(
            func=self._run_prediction_generation,
            trigger=IntervalTrigger(seconds=interval_seconds),
            id="generate_predictions",
            name="Generate Predictions for At-Risk Equipment",
            replace_existing=True,
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

        Scans all equipment and generates maintenance recommendations for at-risk equipment.

        Args:
            interval_seconds: How often to run (default: 600 seconds = 10 minutes)
        """
        # Remove existing job if it exists
        if self.scheduler.get_job("generate_recommendations"):
            self.scheduler.remove_job("generate_recommendations")
            logger.info("Removed existing recommendation generation job")

        # Add new job
        self.scheduler.add_job(
            func=self._run_recommendation_generation,
            trigger=IntervalTrigger(seconds=interval_seconds),
            id="generate_recommendations",
            name="Generate AI Recommendations for At-Risk Equipment",
            replace_existing=True,
        )
        logger.info(f"Added recommendation generation job with {interval_seconds}s interval")

    def _run_recommendation_generation(self):
        """
        Generate AI recommendations for all equipment below health threshold.
        Uses real data: health scores, install dates, service history, alerts, predictions.
        """
        try:
            from app.database.supabase_client import get_supabase_client
            from app.services.maintenance_recommender import get_maintenance_recommender
            from app.services.module_registry_service import ModuleRegistryService
            from app.models.module_registry import (
                AIRecommendation,
                ModuleType,
                RecommendationType,
                RecommendationPriority,
            )
            import uuid
            from datetime import datetime, timedelta

            logger.info("Running scheduled AI recommendation generation...")

            client = get_supabase_client()
            recommender = get_maintenance_recommender(client)
            module_registry = ModuleRegistryService()

            # Get ALL equipment - generate recommendations for all, not just degraded
            response = (
                client.table("equipment")
                .select(
                    "id, code, name, type, health_score, building_id, status, "
                    "install_date, last_service, manufacturer, model"
                )
                .execute()
            )

            all_equipment = response.data if response.data else []
            at_risk = len([eq for eq in all_equipment if eq.get("health_score", 100) < 90])
            logger.info(f"Generating recommendations for {len(all_equipment)} equipment ({at_risk} at-risk)")

            generated = 0
            for eq in all_equipment:
                try:
                    health = eq.get("health_score", 100)
                    equipment_id = eq.get("id")

                    # Get building/site code
                    building_response = (
                        client.table("buildings").select("code, name").eq("id", eq.get("building_id")).execute()
                    )
                    site_code = building_response.data[0]["code"] if building_response.data else "unknown"
                    building_name = building_response.data[0]["name"] if building_response.data else "Unknown Building"

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
                            "building_id": site_code,
                            "building_name": building_name,
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
                    generated += 1

                except Exception as e:
                    logger.warning(f"Failed to generate recommendation for {eq.get('name', 'unknown')}: {e}")

            logger.info(f"AI recommendation generation complete: {generated} generated")

        except Exception as e:
            logger.error(f"Failed to run recommendation generation: {e}")

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
                    # Run async evaluation
                    loop = asyncio.new_event_loop()
                    asyncio.set_event_loop(loop)

                    try:
                        recommendation = loop.run_until_complete(coordinator.evaluate_current_state(site_id))

                        if recommendation:
                            logger.info(
                                f"Site {site_id}: Generated {recommendation['type']} recommendation - "
                                f"Modules: {recommendation.get('modules_involved')}, "
                                f"Reduction: {recommendation.get('estimated_reduction_kw'):.0f}kW"
                            )
                    finally:
                        loop.close()

                except Exception as e:
                    logger.warning(f"Demand coordination failed for site {site_id}: {e}")

        except Exception as e:
            logger.error(f"Failed to run demand-aware coordination: {e}")

    def _get_all_sites(self):
        """Get all configured sites for demand coordination."""
        try:
            import json

            sites_file = DATA_DIR / "sites.json"
            if sites_file.exists():
                with open(sites_file) as f:
                    return json.load(f)
        except Exception as e:
            logger.debug(f"Could not load sites.json: {e}")
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

                # Count triggers per model_type
                drift_counts: dict[str, int] = {}
                for t in result.get("triggered", []):
                    mt = t.get("model_type", "unknown").upper()
                    drift_counts[mt] = drift_counts.get(mt, 0) + 1

                # Set gauge for each model type (0 = no drift, N = active alerts)
                for model_type in ["LSTM", "AUTOENCODER", "CLASSIFIER"]:
                    sentinel_model_drift_alerts.labels(site_id="site-002", model_type=model_type).set(
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
        """Wrapper to process pending Sentry notifications (runs in background)."""
        try:
            import asyncio
            import httpx

            logger.debug("Processing pending Sentry notifications...")
            sentry_secret = (settings.sentry_webhook_secret or "").strip()
            if settings.is_live_mode and not sentry_secret:
                logger.error("SENTRY_WEBHOOK_SECRET is required in live mode; skipping Sentry notification job cycle")
                return

            # Call the endpoint to process pending notifications
            loop = asyncio.new_event_loop()
            asyncio.set_event_loop(loop)
            base_url = (settings.backend_url or "http://localhost:9095").rstrip("/")
            headers = {"X-Sentry-Secret": sentry_secret} if sentry_secret else {}
            if settings.sentry_bot_api_key:
                headers["X-Sentry-API-Key"] = settings.sentry_bot_api_key

            async def process():
                async with httpx.AsyncClient(timeout=10) as client:
                    response = await client.post(
                        f"{base_url}/api/sentry/process-pending-notifications",
                        headers=headers,
                    )
                    return response.json()

            result = loop.run_until_complete(process())
            loop.close()

            if result.get("success"):
                processed = result.get("processed", 0)
                if processed > 0:
                    logger.info(f"📲 Sent {processed} Telegram notifications to technicians")
            else:
                logger.warning(f"Failed to process notifications: {result.get('error')}")

        except Exception as e:
            logger.error(f"Failed to process Sentry notifications: {e}", exc_info=True)

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
        Poll database for queued simulations and start one.
        Prevents multiple concurrent simulations (max 1 at a time).

        Uses the main event loop so that background asyncio tasks
        (like the simulation loop) survive after this function returns.
        """
        logger.warning(">>> _process_simulation_queue() called by APScheduler")
        try:
            # Use the main event loop (uvicorn's loop) so background asyncio tasks survive
            if self._main_loop and self._main_loop.is_running():
                future = asyncio.run_coroutine_threadsafe(self._process_simulation_queue_async(), self._main_loop)
                # Wait for the queue check to complete (not the simulation itself)
                future.result(timeout=300)
                logger.warning(">>> Queue processor completed on main event loop")
            else:
                # Fallback: no main loop available
                logger.warning(">>> No main loop available, using asyncio.run() fallback")
                asyncio.run(self._process_simulation_queue_async())
                logger.warning(">>> asyncio.run() fallback completed")

        except Exception as e:
            logger.error(f"❌ Error processing simulation queue: {e}", exc_info=True)

    async def _process_simulation_queue_async(self) -> None:
        """Async implementation of queue processor."""
        logger.warning(">>> _process_simulation_queue_async() started")
        try:
            from app.database.supabase_client import Supabase
            from app.services.simulation_orchestrator import (
                create_orchestrator,
                register_simulation,
                get_simulation_by_task_id,
            )

            logger.warning(">>> Imports successful, getting Supabase client...")
            supabase = Supabase.instance()
            logger.warning(">>> Supabase client obtained")

            # Test basic query first
            logger.warning(">>> TEST: Trying simple count query on lifecycle_simulation_tasks...")
            try:
                test_response = supabase.table("lifecycle_simulation_tasks").select("count", count="exact").execute()
                logger.warning(f">>> TEST: Count query succeeded, response: {test_response}")
                if hasattr(test_response, "count"):
                    logger.warning(f">>> TEST: Total tasks in table: {test_response.count}")
            except Exception as test_err:
                logger.error(f">>> TEST: Count query failed: {test_err}", exc_info=True)

            # Test: Get ALL tasks to see what's in the database
            logger.warning(">>> TEST: Querying ALL tasks (no filters) to see what's in database...")
            try:
                all_tasks_response = (
                    supabase.table("lifecycle_simulation_tasks")
                    .select("task_id,status,simulation_type,scenario")
                    .limit(5)
                    .execute()
                )
                logger.warning(
                    ">>> TEST: All tasks query returned"
                    f" {len(all_tasks_response.data) if all_tasks_response.data else 0} rows"
                )
                if all_tasks_response.data:
                    for task in all_tasks_response.data:
                        logger.warning(f">>>   Task: {task}")
            except Exception as test_err:
                logger.error(f">>> TEST: All tasks query failed: {test_err}", exc_info=True)

            # Query next queued simulation (FIFO: oldest first)
            logger.warning(">>> Querying for queued simulations with status='queued', simulation_type='lifecycle'")
            logger.warning(">>> Building query...")
            try:
                query_builder = (
                    supabase.table("lifecycle_simulation_tasks")
                    .select("*")
                    .eq("status", "queued")
                    .eq("simulation_type", "lifecycle")
                    .order("created_at", desc=False)
                    .limit(1)
                )
                logger.warning(f">>> Query builder created: {type(query_builder)}")

                logger.warning(">>> Executing query...")
                response = query_builder.execute()
                logger.warning(f">>> Query returned, response type: {type(response)}")
                logger.warning(f">>> Response object: {response}")
                logger.warning(f">>> Response has data attr: {hasattr(response, 'data')}")
                if hasattr(response, "data"):
                    logger.warning(f">>> Response.data type: {type(response.data)}")
                    logger.warning(f">>> Response.data value: {response.data}")
                if hasattr(response, "error"):
                    logger.warning(f">>> Response.error: {response.error}")
            except Exception as query_err:
                logger.error(f">>> Query FAILED: {query_err}", exc_info=True)
                raise

            logger.warning(f">>> After query - response is: {response is not None}")
            if response and hasattr(response, "data"):
                logger.warning(f">>> Response.data length: {len(response.data) if response.data else 0}")

            if not response.data:
                logger.warning(">>> No queued tasks found, returning")
                return  # No queued tasks

            task = response.data[0]
            task_id = str(task["task_id"])
            logger.warning(f">>> Found queued task: {task_id}, scenario: {task.get('scenario')}")

            # Check if already running (prevent double-start)
            if get_simulation_by_task_id(task_id):
                logger.warning(f">>> Task {task_id} already running, skipping")
                return

            # Mark as running
            logger.warning(f">>> Marking task {task_id} as running in database...")
            supabase.table("lifecycle_simulation_tasks").update({"status": "running"}).eq("task_id", task_id).execute()
            logger.warning(">>> Task marked as running")

            logger.warning(f">>> ✅ Starting lifecycle simulation task {task_id}")

            # Create orchestrator and register
            site_id = task.get("site_id", "site-002")
            logger.warning(f">>> Creating orchestrator for task {task_id} (site: {site_id})...")
            orchestrator = create_orchestrator(task_id, site_id=site_id)
            register_simulation(task_id, orchestrator)
            logger.warning(">>> Orchestrator registered")

            # Start simulation and wait for completion
            logger.warning(f">>> Starting simulation for task {task_id}...")
            await self._run_simulation_task(
                task_id,
                orchestrator,
                scenario=task["scenario"],
                duration_minutes=float(task.get("duration_minutes", 3650.0)),
            )
            logger.warning(">>> Simulation task completed")

        except Exception as e:
            logger.error(f"❌ Error in simulation queue processor: {e}", exc_info=True)

    async def _run_simulation_task(self, task_id: str, orchestrator, scenario: str, duration_minutes: float) -> None:
        """
        Run a lifecycle simulation task and update database on completion.
        Supports crash recovery by loading state from checkpoint if available.

        Args:
            task_id: Task identifier
            orchestrator: LifecycleOrchestrator instance
            scenario: Scenario name (fault_day, sentinel_annual, etc)
            duration_minutes: Simulation duration in real minutes
        """
        from app.database.supabase_client import Supabase
        from app.services.simulation_orchestrator import unregister_simulation
        from app.services.lifecycle_orchestrator import ALL_SCENARIOS
        from datetime import datetime

        supabase = Supabase.instance()
        is_recovery = False

        try:
            # Check if this is a crash recovery (has state_snapshot)
            response = (
                supabase.table("lifecycle_simulation_tasks").select("state_snapshot").eq("task_id", task_id).execute()
            )

            state_snapshot = None
            if response.data and response.data[0].get("state_snapshot"):
                state_snapshot = response.data[0]["state_snapshot"]
                is_recovery = True
                logger.info(f"🔄 Recovering simulation from checkpoint: task {task_id}")

            if is_recovery and state_snapshot:
                # CRASH RECOVERY PATH: Restore full orchestrator state from checkpoint
                # Get scenario config
                orchestrator.current_scenario = ALL_SCENARIOS.get(scenario, ALL_SCENARIOS["sentinel_annual"])

                # Set max_days, max_cycles, and speed_multiplier BEFORE restoring state
                # Without this, the orchestrator uses __init__ defaults (max_days=1)
                # which causes 365-day sims to stop after 1 day on recovery
                is_annual_scenario = "annual" in scenario.lower()
                orchestrator.max_days = 365 if is_annual_scenario else 1
                orchestrator.max_cycles = 1
                orchestrator.speed_multiplier = max(
                    0.1, min(10000, float(state_snapshot.get("speed_multiplier", 10.0)))
                )

                # Restore all state from checkpoint
                restored = orchestrator.deserialize_state(state_snapshot)
                orchestrator.simulated_time = restored.simulated_time
                orchestrator.days_simulated = restored.days_simulated
                orchestrator.time_multiplier = restored.time_multiplier
                orchestrator._occupancy_seed = restored._occupancy_seed
                orchestrator.active_faults = restored.active_faults
                orchestrator.pending_repairs = restored.pending_repairs
                orchestrator.events = restored.events  # Restore event history
                if orchestrator._occupancy_seed:
                    orchestrator._scenario_rng.seed(orchestrator._occupancy_seed)

                # For annual simulations, restore seasonal modeler
                if orchestrator.seasonal_modeler is None and orchestrator.days_simulated > 0:
                    from app.services.seasonal_modeler import SeasonalModeler

                    orchestrator.seasonal_modeler = SeasonalModeler(seed=orchestrator._occupancy_seed)

                # Set up for simulation restart
                orchestrator.real_start_time = datetime.now()
                orchestrator.running = True
                orchestrator.paused = False

                logger.info(
                    f"✅ Restored checkpoint: day {orchestrator.days_simulated}/365, "
                    f"time {orchestrator.simulated_time.isoformat()}"
                )

                # Start the simulation loop directly (bypasses fresh initialization)
                orchestrator._task = asyncio.create_task(orchestrator._run_simulation())

            else:
                # FRESH START PATH: Initialize new simulation
                await orchestrator.start(scenario=scenario, duration_minutes=duration_minutes)

            # For persistent simulations, start task and attach a completion watcher
            if orchestrator._task:
                logger.info(f"🔄 Simulation task {task_id} started - running in background")
                # Mark as running in database
                try:
                    supabase.table("lifecycle_simulation_tasks").update(
                        {
                            "status": "running",
                            "progress_pct": 0,
                            "days_completed": 0,
                        }
                    ).eq("task_id", task_id).execute()
                    logger.info(f"📊 Task {task_id} marked as running")
                except Exception as db_error:
                    logger.error(f"Failed to update task status to running: {db_error}")

                # Fire-and-forget completion watcher: awaits the simulation task,
                # then unregisters on success or writes failure status on error.
                # This replaces the old finally-block unregister which fired too early.
                async def _watch_completion(sim_task_id: str, sim_async_task: asyncio.Task):
                    try:
                        await sim_async_task
                        logger.info(f"✅ Simulation task {sim_task_id} finished normally")
                    except asyncio.CancelledError:
                        logger.info(f"Simulation task {sim_task_id} was cancelled")
                    except Exception as sim_err:
                        logger.error(f"❌ Simulation task {sim_task_id} failed: {sim_err}")
                        try:
                            from app.database.supabase_client import Supabase
                            from datetime import datetime as dt

                            client = Supabase.instance()
                            client.table("lifecycle_simulation_tasks").update(
                                {
                                    "status": "failed",
                                    "error_message": str(sim_err)[:500],
                                    "completed_at": dt.now().isoformat(),
                                }
                            ).eq("task_id", sim_task_id).execute()
                        except Exception as db_err:
                            logger.error(f"Failed to write failure status: {db_err}")
                    finally:
                        unregister_simulation(sim_task_id)

                asyncio.create_task(_watch_completion(task_id, orchestrator._task))

                # Return immediately — watcher handles cleanup
                return

        except Exception as e:
            logger.error(f"❌ Simulation task {task_id} failed during setup: {e}")

            # Mark as failed with error message
            try:
                supabase.table("lifecycle_simulation_tasks").update(
                    {
                        "status": "failed",
                        "error_message": str(e)[:500],
                        "completed_at": datetime.now().isoformat(),
                    }
                ).eq("task_id", task_id).execute()
            except Exception as db_error:
                logger.error(f"Failed to update task status in DB: {db_error}")

            # Only unregister on setup failure (not on normal return —
            # the completion watcher handles that)
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
        """Run MIP dispatch optimization for site-002."""
        try:
            from app.services.mip_dispatch_optimizer import get_mip_dispatch_optimizer
            from app.services.load_forecast_service import get_load_forecast_service

            optimizer = get_mip_dispatch_optimizer()
            load_svc = get_load_forecast_service()

            # Get current load forecast
            load_forecast = load_svc.get_forecast("site-002", intervals_ahead=96)
            load_values = [i.demand_kw for i in load_forecast.intervals]

            # Get solar forecast (optional)
            solar_values = None
            try:
                from app.services.solar_forecast_service import get_solar_forecast_service

                solar_svc = get_solar_forecast_service()
                solar_obj = solar_svc.get_forecast("site-002", hours_ahead=24)
                solar_values = []
                for h in solar_obj.hourly:
                    solar_values.extend([h.generation_kw] * 4)
                solar_values = solar_values[:96]
            except Exception:
                pass

            schedule = optimizer.optimize(
                "site-002",
                load_forecast=load_values,
                solar_forecast=solar_values,
            )

            logger.info(
                "MIP dispatch optimized: status=%s cost=R%.2f peak=%.0f kW cycles=%.2f solve=%.0f ms",
                schedule.solver_status,
                schedule.total_cost_zar,
                schedule.peak_grid_import_kw,
                schedule.cycles,
                schedule.solve_time_ms,
            )
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
        """Refresh 15-min load forecast for all solar sites."""
        try:
            from app.services.load_forecast_service import get_load_forecast_service

            service = get_load_forecast_service()
            forecast = service.get_forecast("site-002")
            logger.info(
                "Load forecast refreshed: site=site-002 intervals=%d peak=%.0f kW avg=%.0f kW",
                len(forecast.intervals),
                forecast.peak_demand_kw,
                forecast.avg_demand_kw,
            )
        except Exception as e:
            logger.error(f"Failed to refresh load forecast: {e}", exc_info=True)

    def add_site_mode_policy_dry_run_job(self, interval_seconds: int = 300, site_id: str = "site-002"):
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


# Global scheduler instance
scheduler_service = BackgroundSchedulerService()
