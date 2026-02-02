"""Background Scheduler Service.

Handles periodic background tasks such as:
- Generating demo audit data
- Running AI optimization analysis
- Cleaning up old logs
- Running scheduled maintenance tasks
"""

import logging
from datetime import datetime, timedelta
from pathlib import Path
from apscheduler.schedulers.background import BackgroundScheduler
from apscheduler.triggers.interval import IntervalTrigger

from app.services.audit_logger import AuditLogger
from app.services.ai_optimizer import ai_optimizer_service
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
        if hasattr(self, '_initialized'):
            return

        self._initialized = True
        self.scheduler = BackgroundScheduler()
        logger.info("Background scheduler initialized")

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
        if self.scheduler.get_job('generate_demo_audit_data'):
            self.scheduler.remove_job('generate_demo_audit_data')
            logger.info("Removed existing demo data job")

        # Add new job
        self.scheduler.add_job(
            func=self._generate_demo_audit_data,
            trigger=IntervalTrigger(seconds=interval_seconds),
            id='generate_demo_audit_data',
            name='Generate Demo Audit Data',
            replace_existing=True
        )
        logger.info(f"Added demo data job with {interval_seconds}s interval")

    def _generate_demo_audit_data(self):
        """Wrapper to generate demo audit data (runs in background)."""
        try:
            # Import here to avoid circular imports
            import random
            from app.models.audit_log import AuditActionType, AuditResultType, \
                AuditActionType as AAT, AuditResultType as ART

            logger.debug("Generating periodic demo audit data...")

            # Demo devices
            demo_devices = [
                "chiller-gateway-001",
                "ahu-level3-002",
                "lighting-lobby-003",
                "access-main-004",
                "fire-pump-005",
                "vav-office-006"
            ]

            demo_users = ["operator-1", "operator-2", "system", "scheduler", "admin"]
            demo_points = ["setpoint", "fan_speed", "brightness", "status", "mode"]

            audit_logger = AuditLogger()
            entries_created = 0

            # Generate 2-5 new entries per cycle to simulate real activity
            for _ in range(random.randint(2, 5)):
                device_id = random.choice(demo_devices)
                user = random.choice(demo_users)
                point_name = random.choice(demo_points)

                old_value = random.randint(20, 25) if "setpoint" in point_name else random.randint(50, 100)
                new_value = old_value + random.randint(-5, 5)

                result = random.choices(
                    [ART.SUCCESS, ART.WARNING, ART.BLOCKED, ART.FAILED],
                    weights=[70, 15, 10, 5]
                )[0]

                safety_validation = None
                error_message = None

                if result == ART.BLOCKED:
                    safety_validation = {
                        "rules_checked": ["temperature_range", "pressure_limits"],
                        "passed_rules": ["temperature_range"],
                        "failed_rules": ["pressure_limits"],
                        "details": "Pressure exceeds safe operating limits"
                    }
                    error_message = "Safety validation failed: Pressure limit exceeded"
                elif result == ART.WARNING:
                    safety_validation = {
                        "rules_checked": ["temperature_range", "minimum_runtime"],
                        "passed_rules": ["temperature_range"],
                        "warnings": ["minimum_runtime"],
                        "details": "Minimum runtime requirement not met (warning only)"
                    }
                elif result == ART.SUCCESS:
                    safety_validation = {
                        "rules_checked": ["temperature_range", "pressure_limits"],
                        "passed_rules": ["temperature_range", "pressure_limits"],
                        "details": "All safety checks passed"
                    }

                audit_logger.log_control_action(
                    device_id=device_id,
                    point_name=point_name,
                    user=user,
                    old_value=old_value,
                    new_value=new_value,
                    result=result,
                    safety_validation=safety_validation,
                    error_message=error_message,
                    metadata={
                        "demo_data": True,
                        "generated_at": datetime.now().isoformat(),
                        "priority": random.randint(8, 16)
                    }
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
        if self.scheduler.get_job('run_optimization_analysis'):
            self.scheduler.remove_job('run_optimization_analysis')
            logger.info("Removed existing optimization analysis job")

        # Add new job
        self.scheduler.add_job(
            func=self._run_optimization_analysis,
            trigger=IntervalTrigger(seconds=interval_seconds),
            id='run_optimization_analysis',
            name='Run Optimization Analysis',
            replace_existing=True
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

                    recommendation = loop.run_until_complete(
                        ai_optimizer_service.analyze_building(site_id)
                    )

                    loop.close()

                    # Validate recommendation
                    loop = asyncio.new_event_loop()
                    asyncio.set_event_loop(loop)

                    validation = loop.run_until_complete(
                        ai_optimizer_service.validate_recommendation(site_id, recommendation)
                    )

                    loop.close()

                    # Update site status
                    # Only mark as pending if there are actual recommendations to show
                    if validation["allowed"] and len(recommendation.recommendations) > 0:
                        site["optimization_status"] = OptimizationStatus.RECOMMENDATION_PENDING.value
                        site["last_recommendation"] = recommendation.to_dict()
                        results.append({
                            "site_id": site_id,
                            "site_name": site_name,
                            "status": "success",
                            "confidence": recommendation.confidence,
                            "recommendations_count": len(recommendation.recommendations),
                        })
                    elif validation["allowed"] and len(recommendation.recommendations) == 0:
                        # No actionable recommendations - don't show notification
                        site["optimization_status"] = OptimizationStatus.OPTIMIZED.value
                        site["last_recommendation"] = None  # Clear any old recommendation
                        results.append({
                            "site_id": site_id,
                            "site_name": site_name,
                            "status": "skipped",
                            "reason": "No actionable adjustments available (building has no controllable HVAC assets or conditions don't warrant changes)",
                        })
                    else:
                        site["optimization_status"] = OptimizationStatus.WARNING.value
                        site["last_recommendation"] = recommendation.to_dict()
                        results.append({
                            "site_id": site_id,
                            "site_name": site_name,
                            "status": "warning",
                            "reason": "Safety validation failed",
                        })

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
                        }
                    )
                    site["optimization_history"].append(history_entry.to_dict())

                    # Keep only last 50 history entries
                    if len(site["optimization_history"]) > 50:
                        site["optimization_history"] = site["optimization_history"][-50:]

                except Exception as e:
                    logger.error(f"Error analyzing site {site_id}: {e}")
                    site["optimization_status"] = OptimizationStatus.ERROR.value
                    site["error_message"] = str(e)
                    results.append({
                        "site_id": site_id,
                        "site_name": site_name,
                        "status": "error",
                        "error": str(e),
                    })

            # Save updated sites back to file
            with open(sites_file, 'w') as f:
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
        if self.scheduler.get_job('generate_predictions'):
            self.scheduler.remove_job('generate_predictions')
            logger.info("Removed existing prediction generation job")

        # Add new job
        self.scheduler.add_job(
            func=self._run_prediction_generation,
            trigger=IntervalTrigger(seconds=interval_seconds),
            id='generate_predictions',
            name='Generate Predictions for At-Risk Equipment',
            replace_existing=True
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
                result = loop.run_until_complete(
                    generator.generate_predictions_for_all_sites()
                )
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
        if self.scheduler.get_job('generate_recommendations'):
            self.scheduler.remove_job('generate_recommendations')
            logger.info("Removed existing recommendation generation job")

        # Add new job
        self.scheduler.add_job(
            func=self._run_recommendation_generation,
            trigger=IntervalTrigger(seconds=interval_seconds),
            id='generate_recommendations',
            name='Generate AI Recommendations for At-Risk Equipment',
            replace_existing=True
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
                AIRecommendation, ModuleType, RecommendationType, RecommendationPriority
            )
            import uuid
            from datetime import datetime, timedelta

            logger.info("Running scheduled AI recommendation generation...")

            client = get_supabase_client()
            recommender = get_maintenance_recommender(client)
            module_registry = ModuleRegistryService()

            # Get all equipment with health below 90% - include real data fields
            response = client.table("equipment").select(
                "id, code, name, type, health_score, building_id, status, "
                "install_date, last_service, manufacturer, model"
            ).lt("health_score", 90).execute()

            at_risk_equipment = response.data if response.data else []
            logger.info(f"Found {len(at_risk_equipment)} equipment below 90% health")

            generated = 0
            for eq in at_risk_equipment:
                try:
                    health = eq.get("health_score", 100)
                    equipment_id = eq.get("id")

                    # Get building/site code
                    building_response = client.table("buildings").select("code, name").eq("id", eq.get("building_id")).execute()
                    site_code = building_response.data[0]["code"] if building_response.data else "unknown"
                    building_name = building_response.data[0]["name"] if building_response.data else "Unknown Building"

                    # Get recent alerts for this equipment (last 30 days)
                    alerts_response = client.table("alerts").select(
                        "type, severity, created_at, message"
                    ).eq("equipment_id", equipment_id).gte(
                        "created_at", (datetime.now() - timedelta(days=30)).isoformat()
                    ).order("created_at", desc=True).limit(5).execute()
                    recent_alerts = alerts_response.data if alerts_response.data else []

                    # Get existing prediction for this equipment
                    prediction_response = client.table("predictions").select(
                        "probability_percent, contributing_factors, evidence, recommended_action"
                    ).eq("equipment_id", equipment_id).eq("status", "active").limit(1).execute()
                    prediction = prediction_response.data[0] if prediction_response.data else None

                    # Calculate days since last service
                    days_since_service = None
                    if eq.get("last_service"):
                        try:
                            last_service_date = datetime.fromisoformat(eq["last_service"].replace("Z", "+00:00"))
                            days_since_service = (datetime.now(last_service_date.tzinfo) - last_service_date).days
                        except:
                            pass

                    # Calculate equipment age in years
                    equipment_age_years = None
                    if eq.get("install_date"):
                        try:
                            install_date = datetime.fromisoformat(eq["install_date"].replace("Z", "+00:00"))
                            equipment_age_years = (datetime.now(install_date.tzinfo) - install_date).days / 365
                        except:
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

                    # Generate recommendation using real context
                    risk_level = "critical" if health < 50 else ("high" if health < 70 else "medium")
                    recommendation = recommender._generate_fallback_recommendation(
                        equipment_id=eq.get("code", eq["id"]),
                        equipment_type=eq.get("type", "unknown"),
                        risk_level=risk_level,
                        predicted_failure="health_degradation"
                    )

                    # Enhance actions based on real data
                    enhanced_actions = list(recommendation.immediate_actions)
                    if days_since_service and days_since_service > 180:
                        enhanced_actions.insert(0, "Schedule overdue preventive maintenance")
                    if recent_alerts and len(recent_alerts) >= 3:
                        enhanced_actions.insert(0, "Review recurring alert pattern")
                    if prediction and prediction.get("probability_percent", 0) > 70:
                        enhanced_actions.insert(0, prediction.get("recommended_action", "Address predicted failure"))

                    # Determine priority based on multiple factors
                    priority = RecommendationPriority.MEDIUM
                    if health < 50 or (prediction and prediction.get("probability_percent", 0) > 80):
                        priority = RecommendationPriority.CRITICAL
                    elif health < 70 or (days_since_service and days_since_service > 365):
                        priority = RecommendationPriority.HIGH

                    description = ". ".join(context_parts)
                    if enhanced_actions:
                        description += f". Recommended: {enhanced_actions[0]}"

                    ai_rec = AIRecommendation(
                        recommendation_id=str(uuid.uuid4()),
                        timestamp=datetime.now().isoformat(),
                        source_module=ModuleType.HVAC,
                        recommendation_type=RecommendationType.MAINTENANCE,
                        priority=priority,
                        title=f"Maintenance Required: {eq['name']}",
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
                            "type": "schedule_maintenance",
                            "priority": recommendation.priority,
                            "immediate_actions": enhanced_actions[:5],
                            "evidence": [
                                f"Health at {health}%",
                                f"{len(recent_alerts)} alerts in 30 days" if recent_alerts else "No recent alerts",
                                f"Service overdue by {days_since_service - 180} days" if days_since_service and days_since_service > 180 else None,
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


# Global scheduler instance
scheduler_service = BackgroundSchedulerService()
