"""Generator Service for DeepSea DSE Controller Integration.

SCADA-style monitoring for generator sets with:
- Modbus polling (mock for demo)
- N+1 redundancy management
- Diesel fuel tracking
- Predictive maintenance analysis
"""

from typing import Dict, List, Optional
from datetime import datetime
import json
import logging
import random
from pathlib import Path

from app.models.generator import Generator, GeneratorGroup, DieselTank, GeneratorHealth, PredictiveIndicator

logger = logging.getLogger(__name__)


class GeneratorService:
    """Service for generator system monitoring and control."""

    def __init__(self):
        self._generators: Dict[str, Generator] = {}
        self._groups: Dict[str, GeneratorGroup] = {}
        self._tanks: Dict[str, DieselTank] = {}
        self._health_cache: Dict[str, GeneratorHealth] = {}
        self._load_mock_data()

    def _load_mock_data(self):
        """Load mock generator data from JSON."""
        # Try building-specific data first (Sandton)
        data_paths = [
            Path(__file__).parent.parent / "data" / "sites" / "sandton" / "generators.json",
            Path(__file__).parent.parent / "data" / "generators.json",
        ]

        for data_path in data_paths:
            if data_path.exists():
                with open(data_path) as f:
                    data = json.load(f)

                # Parse generators
                for g in data.get("generators", []):
                    gen = Generator.from_dict(g)
                    self._generators[gen.generator_id] = gen

                # Parse groups
                for grp in data.get("groups", []):
                    group = GeneratorGroup.from_dict(grp)
                    self._groups[group.group_id] = group

                # Parse diesel tanks
                for t in data.get("diesel_tanks", []):
                    tank = DieselTank(**t)
                    self._tanks[tank.tank_id] = tank

                logger.info(
                    f"Loaded generator data from {data_path}: "
                    f"{len(self._generators)} generators, "
                    f"{len(self._groups)} groups, "
                    f"{len(self._tanks)} tanks"
                )
                break
        else:
            logger.warning("Generator mock data not found")

    # === Generator Operations ===

    def get_generators(self, site_id: Optional[str] = None, group_id: Optional[str] = None) -> List[Generator]:
        """Get all generators with optional filters."""
        generators = list(self._generators.values())
        if site_id:
            generators = [g for g in generators if g.site_id == site_id]
        if group_id:
            generators = [g for g in generators if g.group_id == group_id]
        return generators

    def get_generator(self, generator_id: str) -> Optional[Generator]:
        """Get single generator by ID."""
        return self._generators.get(generator_id)

    def get_generator_telemetry(self, generator_id: str) -> Optional[Dict]:
        """Get current telemetry for a generator (simulated Modbus poll)."""
        gen = self._generators.get(generator_id)
        if not gen:
            return None

        # Build telemetry response based on current state
        telemetry = {
            "generator_id": generator_id,
            "timestamp": datetime.now().isoformat(),
            "status": gen.status,
            "mains_available": gen.mains_available,
            "engine_running": gen.engine_running,
            "on_load": gen.on_load,
            "battery_voltage": gen.battery_voltage,
            "charger_current": gen.charger_current,
            "fuel_level_pct": gen.fuel_level_pct,
            "start_attempts": gen.start_attempts,
        }

        # Add engine data if running
        if gen.engine_running and gen.engine:
            telemetry["engine"] = gen.engine

        # Add electrical data if on load
        if gen.on_load and gen.electrical:
            telemetry["electrical"] = gen.electrical

        # Add any active alarms
        if gen.alarms:
            telemetry["alarms"] = gen.alarms

        return telemetry

    # === Group Operations ===

    def get_groups(self, site_id: Optional[str] = None) -> List[GeneratorGroup]:
        """Get all generator groups with optional site filter."""
        groups = list(self._groups.values())
        if site_id:
            groups = [g for g in groups if g.site_id == site_id]
        return groups

    def get_group(self, group_id: str) -> Optional[GeneratorGroup]:
        """Get single group by ID."""
        return self._groups.get(group_id)

    def get_group_status(self, group_id: str) -> Optional[Dict]:
        """Get comprehensive status for a generator group."""
        group = self._groups.get(group_id)
        if not group:
            return None

        # Get all generators in group
        generators = [self._generators.get(gid) for gid in group.generator_ids]
        generators = [g for g in generators if g is not None]

        # Calculate group metrics
        running = [g for g in generators if g.engine_running]
        on_load = [g for g in generators if g.on_load]
        faulted = [g for g in generators if g.status == "fault"]

        total_load = sum(g.electrical.get("power_kw", 0) if g.electrical else 0 for g in on_load)
        total_capacity = sum(g.rated_power_kw for g in generators)

        # Get fuel tank status
        tank = self._tanks.get(group.diesel_tank_id) if group.diesel_tank_id else None

        return {
            "group_id": group_id,
            "name": group.name,
            "timestamp": datetime.now().isoformat(),
            "generators": {
                "total": len(generators),
                "running": len(running),
                "on_load": len(on_load),
                "faulted": len(faulted),
                "required": group.required_running,
            },
            "load": {
                "current_kw": total_load,
                "capacity_kw": total_capacity,
                "percent": round(total_load / total_capacity * 100, 1) if total_capacity else 0,
            },
            "ats": {
                "position": group.ats_position,
                "mains_healthy": group.mains_healthy,
                "transfer_mode": group.transfer_mode,
            },
            "fuel": tank.to_dict() if tank else None,
            "generator_details": [
                {
                    "generator_id": g.generator_id,
                    "name": g.name,
                    "status": g.status,
                    "priority": g.priority,
                    "engine_running": g.engine_running,
                    "on_load": g.on_load,
                    "load_kw": g.electrical.get("power_kw", 0) if g.electrical else 0,
                    "battery_voltage": g.battery_voltage,
                    "fuel_level_pct": g.fuel_level_pct,
                }
                for g in sorted(generators, key=lambda x: x.priority)
            ],
        }

    # === Diesel Tank Operations ===

    def get_tanks(self, site_id: Optional[str] = None) -> List[DieselTank]:
        """Get all diesel tanks."""
        return list(self._tanks.values())

    def get_tank(self, tank_id: str) -> Optional[DieselTank]:
        """Get single tank by ID."""
        return self._tanks.get(tank_id)

    def get_fuel_status(self, group_id: str) -> Optional[Dict]:
        """Get fuel status for a generator group."""
        group = self._groups.get(group_id)
        if not group or not group.diesel_tank_id:
            return None

        tank = self._tanks.get(group.diesel_tank_id)
        if not tank:
            return None

        # Calculate burn rate based on running generators
        generators = [self._generators.get(gid) for gid in group.generator_ids]
        generators = [g for g in generators if g is not None and g.on_load]

        current_burn_rate = sum(g.engine.get("fuel_rate_lph", 0) if g.engine else 0 for g in generators)

        # Estimate runtime remaining
        if current_burn_rate > 0:
            hours_remaining = tank.current_level_liters / current_burn_rate
        else:
            hours_remaining = None

        return {
            "tank_id": tank.tank_id,
            "name": tank.name,
            "capacity_liters": tank.capacity_liters,
            "current_liters": tank.current_level_liters,
            "current_pct": tank.current_level_pct,
            "low_alarm_pct": tank.low_level_alarm_pct,
            "reorder_pct": tank.reorder_level_pct,
            "current_burn_rate_lph": current_burn_rate,
            "hours_remaining": round(hours_remaining, 1) if hours_remaining else None,
            "days_remaining": tank.days_remaining,
            "last_fill_date": tank.last_fill_date,
            "alerts": self._get_fuel_alerts(tank),
        }

    def _get_fuel_alerts(self, tank: DieselTank) -> List[Dict]:
        """Generate fuel-related alerts."""
        alerts = []

        if tank.current_level_pct <= tank.low_level_alarm_pct:
            alerts.append(
                {
                    "severity": "alarm",
                    "message": f"Low fuel level: {tank.current_level_pct}%",
                    "action": "Urgent refuel required",
                }
            )
        elif tank.current_level_pct <= tank.reorder_level_pct:
            alerts.append(
                {
                    "severity": "warning",
                    "message": f"Fuel below reorder level: {tank.current_level_pct}%",
                    "action": "Schedule fuel delivery",
                }
            )

        return alerts

    # === Predictive Maintenance ===

    def get_generator_health(self, generator_id: str) -> Optional[GeneratorHealth]:
        """Get health assessment with predictive indicators."""
        gen = self._generators.get(generator_id)
        if not gen:
            return None

        indicators = []
        score = 100.0

        # Battery health (from telemetry patterns)
        battery_indicator = self._assess_battery(gen)
        indicators.append(battery_indicator)
        if battery_indicator.trend == "degrading":
            score -= 15
        elif battery_indicator.trend == "critical":
            score -= 35

        # Oil pressure trend
        if gen.engine:
            oil_indicator = self._assess_oil_pressure(gen)
            indicators.append(oil_indicator)
            if oil_indicator.trend == "degrading":
                score -= 10

        # Service interval
        service_indicator = self._assess_service_interval(gen)
        indicators.append(service_indicator)
        if service_indicator.trend == "degrading":
            score -= 10
        elif service_indicator.trend == "critical":
            score -= 25

        # Fuel system
        fuel_indicator = self._assess_fuel(gen)
        indicators.append(fuel_indicator)
        if fuel_indicator.trend == "degrading":
            score -= 5

        # Determine overall status
        if score >= 85:
            status = "healthy"
        elif score >= 70:
            status = "attention"
        elif score >= 50:
            status = "warning"
        else:
            status = "critical"

        health = GeneratorHealth(
            generator_id=generator_id,
            overall_score=max(0, score),
            status=status,
            indicators=indicators,
            last_assessment=datetime.now().isoformat(),
        )

        self._health_cache[generator_id] = health
        return health

    def _assess_battery(self, gen: Generator) -> PredictiveIndicator:
        """Assess battery health from voltage trend."""
        voltage = gen.battery_voltage

        if voltage >= 26.5:
            trend = "stable"
            recommendation = None
        elif voltage >= 25.5:
            trend = "degrading"
            recommendation = "Schedule battery inspection within 30 days"
        elif voltage >= 25.0:
            trend = "degrading"
            recommendation = "Battery replacement recommended within 14 days"
        else:
            trend = "critical"
            recommendation = "URGENT: Battery replacement required - start failure risk"

        return PredictiveIndicator(
            parameter="battery_voltage",
            current_value=voltage,
            threshold_low=25.0,
            threshold_high=30.0,
            trend=trend,
            recommendation=recommendation,
        )

    def _assess_oil_pressure(self, gen: Generator) -> PredictiveIndicator:
        """Assess oil pressure trend (only relevant when engine running)."""
        if not gen.engine or not gen.engine_running:
            # Oil pressure only relevant when running
            return PredictiveIndicator(
                parameter="oil_pressure_kpa",
                current_value=0,
                trend="stable",
                recommendation=None,
            )

        pressure = gen.engine.get("oil_pressure_kpa", 400)

        if pressure >= 380:
            trend = "stable"
            recommendation = None
        elif pressure >= 350:
            trend = "degrading"
            recommendation = "Monitor oil pressure - schedule inspection"
        else:
            trend = "critical"
            recommendation = "Low oil pressure - check oil level and pump"

        return PredictiveIndicator(
            parameter="oil_pressure_kpa",
            current_value=pressure,
            threshold_low=350,
            trend=trend,
            recommendation=recommendation,
        )

    def _assess_service_interval(self, gen: Generator) -> PredictiveIndicator:
        """Assess service interval status."""
        run_hours = gen.engine.get("run_hours", 0) if gen.engine else 0
        next_service = gen.next_service_hours
        hours_until_service = next_service - (run_hours % 500)  # Assuming 500hr service

        if hours_until_service > 100:
            trend = "stable"
            recommendation = None
        elif hours_until_service > 25:
            trend = "degrading"
            recommendation = f"Service due in {int(hours_until_service)} run hours"
        else:
            trend = "critical"
            recommendation = "Service overdue - schedule immediately"

        return PredictiveIndicator(
            parameter="service_interval_hours",
            current_value=hours_until_service,
            threshold_low=25,
            trend=trend,
            recommendation=recommendation,
        )

    def _assess_fuel(self, gen: Generator) -> PredictiveIndicator:
        """Assess fuel level."""
        fuel_pct = gen.fuel_level_pct

        if fuel_pct >= 30:
            trend = "stable"
            recommendation = None
        elif fuel_pct >= 20:
            trend = "degrading"
            recommendation = "Schedule fuel delivery"
        else:
            trend = "critical"
            recommendation = "Low fuel - urgent delivery required"

        return PredictiveIndicator(
            parameter="fuel_level_pct",
            current_value=fuel_pct,
            threshold_low=20,
            trend=trend,
            recommendation=recommendation,
        )

    def get_site_health_summary(self, site_id: str) -> Dict:
        """Get health summary for all generators at a site."""
        generators = self.get_generators(site_id=site_id)
        health_data = []

        for gen in generators:
            health = self.get_generator_health(gen.generator_id)
            if health:
                health_data.append(
                    {
                        "generator_id": gen.generator_id,
                        "name": gen.name,
                        "score": health.overall_score,
                        "status": health.status,
                        "critical_issues": [i.parameter for i in health.indicators if i.trend == "critical"],
                    }
                )

        avg_score = sum(h["score"] for h in health_data) / len(health_data) if health_data else 0

        return {
            "site_id": site_id,
            "timestamp": datetime.now().isoformat(),
            "average_health_score": round(avg_score, 1),
            "generators": health_data,
            "critical_count": sum(1 for h in health_data if h["status"] == "critical"),
            "warning_count": sum(1 for h in health_data if h["status"] == "warning"),
        }

    # === SCADA Overview ===

    def get_scada_overview(self, site_id: str) -> Dict:
        """Get SCADA-style overview for control room display."""
        groups = self.get_groups(site_id=site_id)

        overview = {
            "site_id": site_id,
            "timestamp": datetime.now().isoformat(),
            "groups": [],
        }

        for group in groups:
            group_status = self.get_group_status(group.group_id)
            if group_status:
                overview["groups"].append(group_status)

        # Calculate site totals
        all_gens = self.get_generators(site_id=site_id)
        overview["site_totals"] = {
            "total_generators": len(all_gens),
            "running": sum(1 for g in all_gens if g.engine_running),
            "on_load": sum(1 for g in all_gens if g.on_load),
            "faulted": sum(1 for g in all_gens if g.status == "fault"),
            "total_load_kw": sum(g.electrical.get("power_kw", 0) if g.electrical else 0 for g in all_gens if g.on_load),
            "total_capacity_kw": sum(g.rated_power_kw for g in all_gens),
            "mains_healthy": all(g.mains_available for g in all_gens),
        }

        return overview

    # === Simulation (for demo) ===

    def simulate_state_change(self, event: str = "normal"):
        """Simulate state changes for demo purposes."""
        for gen in self._generators.values():
            if event == "load_shedding":
                # Simulate load shedding - start generators
                gen.mains_available = False
                gen.engine_running = True
                gen.on_load = True
                gen.status = "on_load"
                gen.engine = {
                    "rpm": 1500,
                    "oil_pressure_kpa": 380 + random.uniform(-20, 20),
                    "coolant_temp_c": 65 + random.uniform(-5, 15),
                    "run_hours": 4500 + random.uniform(0, 100),
                    "fuel_rate_lph": 45 + random.uniform(-5, 5),
                }
                gen.electrical = {
                    "voltage_l1": 400 + random.uniform(-2, 2),
                    "voltage_l2": 400 + random.uniform(-2, 2),
                    "voltage_l3": 400 + random.uniform(-2, 2),
                    "frequency_hz": 50.0 + random.uniform(-0.2, 0.2),
                    "power_kw": gen.rated_power_kw * 0.7,
                    "power_kva": gen.rated_power_kva * 0.7,
                    "power_factor": 0.88,
                }

            elif event == "mains_restored":
                # Simulate mains restoration
                gen.mains_available = True
                gen.engine_running = False
                gen.on_load = False
                gen.status = "standby"
                gen.engine = None
                gen.electrical = None

            elif event == "normal":
                # Normal standby state with slight variations
                gen.battery_voltage = 27.0 + random.uniform(-0.3, 0.3)
                gen.charger_current = 2.0 + random.uniform(-0.2, 0.2)

            gen.last_poll = datetime.now().isoformat()


# Singleton instance
_generator_service: Optional[GeneratorService] = None


def get_generator_service() -> GeneratorService:
    """Get the singleton generator service instance."""
    global _generator_service
    if _generator_service is None:
        _generator_service = GeneratorService()
    return _generator_service
