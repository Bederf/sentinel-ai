"""
Health Simulation Service - Simulates equipment health degradation in Supabase.

This service periodically degrades equipment health scores in the database,
triggering Sentry health alerts when equipment drops below thresholds.

Configuration:
- SIMULATION_ENABLED: Enable/disable simulation (default: True)
- SIMULATION_INTERVAL: Seconds between updates (default: 300 = 5 minutes)
- DEGRADATION_RATE: Max health drop per cycle (default: 5%)
- FAULT_PROBABILITY: Chance of sudden fault (default: 0.02 = 2%)
"""

import asyncio
import logging
import random
from datetime import datetime
from typing import Any

from app.core.site_resolver import get_primary_site_code
from app.database.supabase_client import get_supabase_client

logger = logging.getLogger(__name__)


class HealthSimulationService:
    """Service to simulate realistic equipment health degradation."""

    def __init__(self):
        self.client = get_supabase_client()
        self.is_running = False
        self._task: asyncio.Task | None = None
        self._deferred = False  # True when lifecycle orchestrator is managing health
        self._deferred_by: str | None = None  # task_id of deferring simulation

        # Configuration
        self.config = {
            "enabled": True,
            "interval_seconds": 3600,  # 1 hour
            "degradation_rate": 5.0,  # Max % drop per cycle
            "fault_probability": 0.02,  # 2% chance of sudden fault
            "recovery_probability": 0.05,  # 5% chance of recovery (maintenance)
            "min_health": 10,  # Don't go below 10%
            "max_health": 98,  # Don't go above 98%
            "target_equipment_per_cycle": 10,  # How many to update per cycle
            "site_id": get_primary_site_code() or "unknown",  # Target building for simulation
            "business_hours_only": True,  # Only run during business hours
            "business_hours_start": 8,  # 08:00
            "business_hours_end": 17,  # 17:00
        }

        # Health thresholds (matches Sentry alerts)
        self.thresholds = {
            "critical": 50,
            "warning": 70,
            "healthy": 90,
        }

        # Track simulation state
        self.last_run = None
        self.total_updates = 0
        self.alerts_triggered = 0

    async def start(self):
        """Start the health simulation loop."""
        if self.is_running:
            logger.warning("Health simulation already running")
            return

        if not self.config["enabled"]:
            logger.info("Health simulation is disabled")
            return

        logger.info(f"Starting health simulation (interval: {self.config['interval_seconds']}s)")
        self.is_running = True
        self._task = asyncio.create_task(self._simulation_loop())

    async def stop(self):
        """Stop the health simulation."""
        logger.info("Stopping health simulation")
        self.is_running = False
        if self._task:
            self._task.cancel()
            try:
                await self._task
            except asyncio.CancelledError:
                pass

    def defer_to_orchestrator(self, task_id: str) -> bool:
        """
        Pause independent health simulation while a lifecycle orchestrator runs.
        The orchestrator manages health scores directly during simulation.

        Args:
            task_id: ID of the lifecycle simulation taking over health management

        Returns:
            True if deferred successfully, False if already deferred by another task
        """
        if self._deferred and self._deferred_by != task_id:
            logger.warning(f"Health sim already deferred by {self._deferred_by}, cannot defer for {task_id}")
            return False

        self._deferred = True
        self._deferred_by = task_id
        logger.info(f"Health simulation deferred to orchestrator (task: {task_id})")
        return True

    def resume_independent(self, task_id: str) -> bool:
        """
        Resume independent health simulation after orchestrator completes.

        Args:
            task_id: ID of the lifecycle simulation releasing health management

        Returns:
            True if resumed, False if task_id doesn't match deferring task
        """
        if self._deferred_by and self._deferred_by != task_id:
            logger.warning(f"Health sim deferred by {self._deferred_by}, cannot resume for {task_id}")
            return False

        self._deferred = False
        self._deferred_by = None
        logger.info(f"Health simulation resumed independent mode (task: {task_id})")
        return True

    @property
    def is_deferred(self) -> bool:
        """Check if health simulation is deferred to an orchestrator."""
        return self._deferred

    async def _simulation_loop(self):
        """Main simulation loop."""
        while self.is_running:
            try:
                # Skip cycle if deferred to lifecycle orchestrator
                if self._deferred:
                    logger.debug(
                        f"Health simulation deferred to orchestrator (task: {self._deferred_by}), skipping cycle"
                    )
                    await asyncio.sleep(self.config["interval_seconds"])
                    continue

                # Check if we're within business hours
                if self._is_business_hours():
                    await self._run_simulation_cycle()
                else:
                    logger.debug(
                        f"Outside business hours ({self.config['business_hours_start']}:00-"
                        f"{self.config['business_hours_end']}:00), skipping simulation cycle"
                    )

                await asyncio.sleep(self.config["interval_seconds"])
            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.error(f"Error in simulation cycle: {e}")
                await asyncio.sleep(60)  # Wait before retry

    def _is_business_hours(self) -> bool:
        """Check if current time is within business hours."""
        if not self.config.get("business_hours_only", False):
            return True

        current_hour = datetime.now().hour
        start = self.config.get("business_hours_start", 8)
        end = self.config.get("business_hours_end", 17)

        return start <= current_hour < end

    async def _run_simulation_cycle(self):
        """Run one simulation cycle - degrade some equipment health."""
        self.last_run = datetime.now()

        # Get equipment from target building
        equipment = self._get_equipment()
        if not equipment:
            logger.warning("No equipment found for simulation")
            return

        # Select random subset to update
        sample_size = min(self.config["target_equipment_per_cycle"], len(equipment))
        selected = random.sample(equipment, sample_size)

        updates = []
        for eq in selected:
            old_health = eq.get("health_score", 85)
            new_health = self._calculate_new_health(eq)

            if new_health != old_health:
                updates.append(
                    {
                        "id": eq["id"],
                        "name": eq.get("name", eq["id"]),
                        "old_health": old_health,
                        "new_health": new_health,
                        "crossed_threshold": self._check_threshold_crossing(old_health, new_health),
                    }
                )

                # Update in Supabase
                self._update_equipment_health(eq["id"], new_health)

        # Log summary
        if updates:
            self.total_updates += len(updates)
            threshold_crossings = [u for u in updates if u["crossed_threshold"]]
            self.alerts_triggered += len(threshold_crossings)

            logger.info(
                f"Simulation cycle: {len(updates)} equipment updated, {len(threshold_crossings)} threshold crossings"
            )

            # Log threshold crossings (will trigger Sentry alerts)
            for u in threshold_crossings:
                logger.warning(
                    f"THRESHOLD CROSSED: {u['name']} dropped from {u['old_health']:.0f}% to {u['new_health']:.0f}%"
                )

    def _get_equipment(self) -> list[dict[str, Any]]:
        """Get equipment from Supabase."""
        try:
            # First get the building UUID from the code
            site_response = self.client.table("sites").select("id").eq("code", self.config["site_id"]).execute()

            if not site_response.data:
                logger.warning(f"Building {self.config['site_id']} not found")
                return []

            site_uuid = site_response.data[0]["id"]

            # Get equipment for that building
            response = (
                self.client.table("equipment")
                .select("id, code, name, type, health_score, site_id")
                .eq("site_id", site_uuid)
                .execute()
            )
            return response.data or []
        except Exception as e:
            logger.error(f"Failed to get equipment: {e}")
            return []

    def _calculate_new_health(self, equipment: dict[str, Any]) -> float:
        """Calculate new health score with realistic degradation."""
        current_health = equipment.get("health_score", 85)
        equipment_type = equipment.get("type", "unknown")

        # Check for sudden fault (equipment failure event)
        if random.random() < self.config["fault_probability"]:
            # Sudden drop of 20-40%
            drop = random.uniform(20, 40)
            new_health = max(self.config["min_health"], current_health - drop)
            logger.warning(f"FAULT EVENT: {equipment.get('name', equipment['id'])} dropped {drop:.0f}%")
            return round(new_health, 1)

        # Check for recovery (simulates maintenance)
        if current_health < 70 and random.random() < self.config["recovery_probability"]:
            # Recovery brings health up by 30-50%
            boost = random.uniform(30, 50)
            new_health = min(self.config["max_health"], current_health + boost)
            logger.info(f"MAINTENANCE: {equipment.get('name', equipment['id'])} recovered to {new_health:.0f}%")
            return round(new_health, 1)

        # Normal degradation based on equipment type
        degradation_rates = {
            "hvac_zone": 0.5,  # HVAC zones degrade slowly
            "ahu": 1.0,  # AHUs moderate
            "chiller": 1.5,  # Chillers degrade faster
            "generator": 0.3,  # Generators very slow (rarely used)
            "ups": 0.2,  # UPS very slow
            "transformer": 0.1,  # Transformers almost static
            "switchboard": 0.2,  # Switchboards slow
            "distribution": 0.3,  # Distribution boards slow
            "luminaire": 0.8,  # Lights moderate
            "default": 0.5,
        }

        base_rate = degradation_rates.get(equipment_type, degradation_rates["default"])

        # Add randomness (-50% to +100% of base rate)
        actual_rate = base_rate * random.uniform(0.5, 2.0)

        # Cap at max degradation rate
        actual_rate = min(actual_rate, self.config["degradation_rate"])

        # Apply degradation
        new_health = current_health - actual_rate

        # Ensure within bounds
        new_health = max(self.config["min_health"], min(self.config["max_health"], new_health))

        return round(new_health, 1)

    def _check_threshold_crossing(self, old_health: float, new_health: float) -> bool:
        """Check if health crossed a threshold that would trigger an alert."""
        for threshold in [self.thresholds["critical"], self.thresholds["warning"]]:
            if old_health >= threshold and new_health < threshold:
                return True
        return False

    def _update_equipment_health(self, equipment_id: str, new_health: float):
        """Update equipment health in Supabase."""
        try:
            # Round to integer since health_score is INTEGER in database
            health_int = int(round(new_health))
            self.client.table("equipment").update(
                {
                    "health_score": health_int,
                    "updated_at": datetime.now().isoformat(),
                }
            ).eq("id", equipment_id).execute()
        except Exception as e:
            logger.error(f"Failed to update equipment {equipment_id}: {e}")

    def get_status(self) -> dict[str, Any]:
        """Get simulation status."""
        return {
            "running": self.is_running,
            "enabled": self.config["enabled"],
            "deferred": self._deferred,
            "deferred_by": self._deferred_by,
            "interval_seconds": self.config["interval_seconds"],
            "last_run": self.last_run.isoformat() if self.last_run else None,
            "total_updates": self.total_updates,
            "alerts_triggered": self.alerts_triggered,
            "site_id": self.config["site_id"],
        }

    def set_config(self, **kwargs):
        """Update simulation configuration."""
        for key, value in kwargs.items():
            if key in self.config:
                self.config[key] = value
                logger.info(f"Simulation config updated: {key}={value}")

    async def trigger_fault(self, equipment_id: str, severity: str = "moderate"):
        """Manually trigger a fault on specific equipment."""
        severity_drops = {
            "minor": (10, 20),
            "moderate": (20, 35),
            "major": (35, 50),
            "critical": (50, 70),
        }
        drop_range = severity_drops.get(severity, (20, 35))

        # Get current health - try by code first, then by UUID
        response = (
            self.client.table("equipment").select("id, code, name, health_score").eq("code", equipment_id).execute()
        )

        if not response.data:
            # Try by UUID
            response = (
                self.client.table("equipment").select("id, code, name, health_score").eq("id", equipment_id).execute()
            )

        if not response.data:
            return {"error": f"Equipment {equipment_id} not found"}

        eq = response.data[0]
        old_health = eq.get("health_score", 85)
        drop = random.uniform(*drop_range)
        new_health = max(self.config["min_health"], old_health - drop)

        self._update_equipment_health(eq["id"], new_health)

        logger.warning(f"MANUAL FAULT: {eq['name']} dropped from {old_health:.0f}% to {new_health:.0f}%")

        return {
            "equipment_id": eq.get("code", equipment_id),
            "equipment_name": eq["name"],
            "old_health": old_health,
            "new_health": new_health,
            "severity": severity,
        }

    async def trigger_maintenance(self, equipment_id: str):
        """Manually trigger maintenance on specific equipment."""
        # Get current health - try by code first, then by UUID
        response = (
            self.client.table("equipment").select("id, code, name, health_score").eq("code", equipment_id).execute()
        )

        if not response.data:
            # Try by UUID
            response = (
                self.client.table("equipment").select("id, code, name, health_score").eq("id", equipment_id).execute()
            )

        if not response.data:
            return {"error": f"Equipment {equipment_id} not found"}

        eq = response.data[0]
        old_health = eq.get("health_score", 85)

        # Maintenance brings health to 85-95%
        new_health = random.uniform(85, 95)

        self._update_equipment_health(eq["id"], new_health)

        logger.info(f"MAINTENANCE: {eq['name']} restored from {old_health:.0f}% to {new_health:.0f}%")

        return {
            "equipment_id": eq.get("code", equipment_id),
            "equipment_name": eq["name"],
            "old_health": old_health,
            "new_health": new_health,
        }


# Global service instance
health_simulation_service = HealthSimulationService()

# Singleton accessor
_health_sim_instance: HealthSimulationService | None = None


def get_health_simulation_service() -> HealthSimulationService:
    """Get or create the singleton HealthSimulationService instance."""
    global _health_sim_instance
    if _health_sim_instance is None:
        _health_sim_instance = HealthSimulationService()
    return _health_sim_instance


__all__ = ["HealthSimulationService", "get_health_simulation_service", "health_simulation_service"]
