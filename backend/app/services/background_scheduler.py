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
                    if validation["allowed"]:
                        site["optimization_status"] = OptimizationStatus.RECOMMENDATION_PENDING.value
                        site["last_recommendation"] = recommendation.to_dict()
                        results.append({
                            "site_id": site_id,
                            "site_name": site_name,
                            "status": "success",
                            "confidence": recommendation.confidence,
                            "recommendations_count": len(recommendation.recommendations),
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


# Global scheduler instance
scheduler_service = BackgroundSchedulerService()
