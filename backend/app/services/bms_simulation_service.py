"""
BMS Simulation Service - Generates realistic, changing equipment data
for testing AI responses and fallback scenarios
"""

import asyncio
import json
import random
import time
import math
from datetime import datetime, timedelta
from typing import Dict, List, Optional, Any
from dataclasses import dataclass, asdict
import logging

logger = logging.getLogger(__name__)

@dataclass
class EquipmentState:
    """Current state of simulated equipment"""
    id: str
    name: str
    type: str
    manufacturer: str
    location: str
    health_score: float
    status: str
    temperature: float
    pressure: float
    power_consumption: float
    runtime_hours: float
    last_maintenance: datetime
    fault_codes: List[str]
    sensor_readings: Dict[str, float]
    timestamp: datetime

class BMSimulationService:
    """Service to simulate realistic BMS equipment behavior"""

    def __init__(self):
        self.is_running = False
        self.simulation_speed = 1.0  # 1.0 = real time, 2.0 = 2x speed
        self.equipment = {}
        self.fault_simulator = FaultSimulator()
        self.sensor_simulator = SensorSimulator()
        self.data_generator = DataGenerator()

        # Alert queue for SENTINEL integration
        self.alert_queue: List[Dict[str, Any]] = []
        self.alert_history: List[Dict[str, Any]] = []
        self._alert_id_counter = 1000

        # Health thresholds for status changes
        self.health_thresholds = {
            "normal": 70,      # Above 70% = normal operation
            "warning": 50,     # 50-70% = warning state
            "critical": 20,    # 20-50% = critical, needs immediate attention
            "down": 20         # Below 20% = equipment fails/goes down
        }

        # Simulation configuration
        self.config = {
            "enable_faults": True,
            "enable_sensor_drift": True,
            "enable_load_variation": True,
            "enable_cascading_failures": True,  # Chiller down affects FCUs
            "fault_probability": 0.005,  # 0.5% chance of fault per update (more aggressive)
            "degradation_rate": 0.02,  # Health degrades 0.02% per update naturally
            "fault_degradation": 2.0,  # Each fault accelerates degradation by 2%
            "sensor_drift_rate": 0.0001,
            "update_interval": 3,  # Faster updates for demo (3 seconds)
            "equipment_count": {
                "ahu": 3,
                "chiller": 2,
                "fcu": 8,
                "ups": 1,
                "temperature_sensor": 15,
                "pressure_sensor": 10,
                "flow_sensor": 8
            }
        }

    async def start_simulation(self):
        """Start the BMS simulation"""
        if self.is_running:
            logger.warning("Simulation already running")
            return

        logger.info("Starting BMS simulation...")
        self.is_running = True

        # Initialize equipment
        await self._initialize_equipment()

        # Start simulation loop
        asyncio.create_task(self._simulation_loop())

        logger.info("BMS simulation started successfully")

    async def stop_simulation(self):
        """Stop the BMS simulation"""
        logger.info("Stopping BMS simulation...")
        self.is_running = False

    async def _initialize_equipment(self):
        """Initialize simulated equipment"""
        self.equipment = {}

        # Generate AHUs (Air Handling Units)
        for i in range(self.config["equipment_count"]["ahu"]):
            ahu = self._create_ahu(i)
            self.equipment[ahu.id] = ahu

        # Generate Chillers
        for i in range(self.config["equipment_count"]["chiller"]):
            chiller = self._create_chiller(i)
            self.equipment[chiller.id] = chiller

        # Generate FCUs (Fan Coil Units)
        for i in range(self.config["equipment_count"]["fcu"]):
            fcu = self._create_fcu(i)
            self.equipment[fcu.id] = fcu

        # Generate UPS
        for i in range(self.config["equipment_count"]["ups"]):
            ups = self._create_ups(i)
            self.equipment[ups.id] = ups

        # Generate sensors
        for sensor_type in ["temperature_sensor", "pressure_sensor", "flow_sensor"]:
            for i in range(self.config["equipment_count"][sensor_type]):
                sensor = self._create_sensor(sensor_type, i)
                self.equipment[sensor.id] = sensor

    def _create_ahu(self, index: int) -> EquipmentState:
        """Create an AHU (Air Handling Unit)"""
        return EquipmentState(
            id=f"AHU-L{index+1:02d}-01",
            name=f"Air Handling Unit L{index+1}",
            type="ahu",
            manufacturer=random.choice(["Carrier", "York", "Trane", "Daikin"]),
            location=f"Level {index+1}",
            health_score=random.uniform(85, 95),
            status="running",
            temperature=random.uniform(20, 24),
            pressure=random.uniform(1.0, 1.2),
            power_consumption=random.uniform(15, 25),
            runtime_hours=random.uniform(1000, 5000),
            last_maintenance=datetime.now() - timedelta(days=random.randint(30, 90)),
            fault_codes=[],
            sensor_readings={
                "supply_temp": random.uniform(18, 22),
                "return_temp": random.uniform(22, 26),
                "fan_speed": random.uniform(0.7, 0.9),
                "filter_pressure": random.uniform(0.1, 0.3)
            },
            timestamp=datetime.now()
        )

    def _create_chiller(self, index: int) -> EquipmentState:
        """Create a chiller unit"""
        return EquipmentState(
            id=f"CH-{index+1:02d}",
            name=f"Chiller {index+1}",
            type="chiller",
            manufacturer=random.choice(["Carrier", "York", "Trane", "Daikin"]),
            location="Basement",
            health_score=random.uniform(80, 90),
            status="running",
            temperature=random.uniform(6, 10),
            pressure=random.uniform(2.0, 2.5),
            power_consumption=random.uniform(100, 200),
            runtime_hours=random.uniform(2000, 8000),
            last_maintenance=datetime.now() - timedelta(days=random.randint(60, 120)),
            fault_codes=[],
            sensor_readings={
                "evap_temp": random.uniform(5, 8),
                "cond_temp": random.uniform(30, 35),
                "oil_pressure": random.uniform(2.0, 2.5),
                "refrigerant_pressure": random.uniform(1.5, 2.0)
            },
            timestamp=datetime.now()
        )

    def _create_fcu(self, index: int) -> EquipmentState:
        """Create a Fan Coil Unit"""
        zone = (index // 4) + 1
        unit = (index % 4) + 1

        return EquipmentState(
            id=f"FCU-Z{zone:02d}-{unit:02d}",
            name=f"Fan Coil Unit Zone {zone} Unit {unit}",
            type="fcu",
            manufacturer=random.choice(["Carrier", "York", "Trane", "Daikin"]),
            location=f"Zone {zone}, Unit {unit}",
            health_score=random.uniform(75, 95),
            status=random.choice(["running", "standby"]),
            temperature=random.uniform(20, 24),
            pressure=random.uniform(0.8, 1.2),
            power_consumption=random.uniform(0.5, 2.0),
            runtime_hours=random.uniform(500, 3000),
            last_maintenance=datetime.now() - timedelta(days=random.randint(15, 60)),
            fault_codes=[],
            sensor_readings={
                "room_temp": random.uniform(20, 24),
                "setpoint": random.uniform(20, 22),
                "valve_position": random.uniform(0.3, 0.8),
                "fan_speed": random.uniform(0.4, 0.9) if random.choice(["running", "standby"]) == "running" else 0.0
            },
            timestamp=datetime.now()
        )

    def _create_ups(self, index: int) -> EquipmentState:
        """Create a UPS unit"""
        return EquipmentState(
            id=f"UPS-{index+1:02d}",
            name=f"UPS {index+1}",
            type="ups",
            manufacturer=random.choice(["APC", "Eaton", "Vertiv"]),
            location="Server Room",
            health_score=random.uniform(90, 98),
            status="normal",
            temperature=random.uniform(18, 22),
            pressure=1.0,
            power_consumption=random.uniform(5, 15),
            runtime_hours=random.uniform(8760, 17520),  # 1-2 years
            last_maintenance=datetime.now() - timedelta(days=random.randint(90, 180)),
            fault_codes=[],
            sensor_readings={
                "battery_level": random.uniform(95, 100),
                "load_percentage": random.uniform(20, 60),
                "input_voltage": random.uniform(220, 240),
                "output_voltage": random.uniform(220, 240)
            },
            timestamp=datetime.now()
        )

    def _create_sensor(self, sensor_type: str, index: int) -> EquipmentState:
        """Create a sensor device"""
        sensor_configs = {
            "temperature_sensor": {
                "prefix": "TEMP",
                "type": "temperature_sensor",
                "manufacturers": ["Honeywell", "Siemens", "Johnson Controls"],
                "base_temp": 22.0,
                "variance": 2.0
            },
            "pressure_sensor": {
                "prefix": "PRESS",
                "type": "pressure_sensor",
                "manufacturers": ["Rosemount", "Endress+Hauser", "Yokogawa"],
                "base_pressure": 1.0,
                "variance": 0.1
            },
            "flow_sensor": {
                "prefix": "FLOW",
                "type": "flow_sensor",
                "manufacturers": ["Emerson", "Krohne", "ABB"],
                "base_flow": 100.0,
                "variance": 20.0
            }
        }

        config = sensor_configs[sensor_type]
        base_value = config.get("base_value", config.get(f"base_{sensor_type.split('_')[0]}", 0))

        return EquipmentState(
            id=f"{config['prefix']}-{index+1:03d}",
            name=f"{sensor_type.replace('_', ' ').title()} {index+1}",
            type=config["type"],
            manufacturer=random.choice(config["manufacturers"]),
            location=f"Zone {(index % 5) + 1}",
            health_score=random.uniform(95, 100),
            status="active",
            temperature=22.0,
            pressure=1.0,
            power_consumption=0.1,
            runtime_hours=random.uniform(8760, 17520),
            last_maintenance=datetime.now() - timedelta(days=random.randint(180, 365)),
            fault_codes=[],
            sensor_readings={
                "value": base_value + random.uniform(-config["variance"], config["variance"]),
                "accuracy": random.uniform(0.95, 0.99),
                "calibration_date": datetime.now() - timedelta(days=random.randint(30, 180))
            },
            timestamp=datetime.now()
        )

    async def _simulation_loop(self):
        """Main simulation loop"""
        while self.is_running:
            try:
                # Update all equipment
                await self._update_equipment()

                # Apply faults if enabled
                if self.config["enable_faults"]:
                    await self._apply_faults()

                # Wait for next update
                await asyncio.sleep(self.config["update_interval"] / self.simulation_speed)

            except Exception as e:
                logger.error(f"Error in simulation loop: {e}")
                await asyncio.sleep(1)  # Prevent tight error loops

    async def _update_equipment(self):
        """Update equipment states with realistic changes"""
        current_time = datetime.now()

        for equipment in self.equipment.values():
            # Skip updates for down equipment (except health continues to degrade)
            if equipment.status == "down":
                old_health = equipment.health_score
                equipment.health_score = max(0, equipment.health_score - 0.01)  # Slow degradation while down
                equipment.timestamp = current_time
                continue

            # Update runtime
            equipment.runtime_hours += self.config["update_interval"] / 3600

            # Apply sensor drift
            if self.config["enable_sensor_drift"]:
                self.sensor_simulator.apply_drift(equipment)

            # Update based on equipment type
            if equipment.type == "ahu":
                self._update_ahu(equipment, current_time)
            elif equipment.type == "chiller":
                self._update_chiller(equipment, current_time)
            elif equipment.type == "fcu":
                self._update_fcu(equipment, current_time)
            elif equipment.type == "ups":
                self._update_ups(equipment, current_time)
            elif "sensor" in equipment.type:
                self._update_sensor(equipment, current_time)

            # Store old health for comparison
            old_health = equipment.health_score

            # Update health score based on various factors
            equipment.health_score = self._calculate_health_score(equipment)

            # Update status and generate alerts based on health changes
            self._update_equipment_status(equipment, old_health)

            # Check for comfort/operational alerts (actionable remotely)
            self._check_comfort_alerts(equipment, current_time)

            # Update timestamp
            equipment.timestamp = current_time

    def _update_ahu(self, ahu: EquipmentState, current_time: datetime):
        """Update AHU specific parameters"""
        # Simulate load variation based on time of day
        hour = current_time.hour
        base_load = 0.6 + 0.3 * math.sin((hour - 6) * math.pi / 12)  # Peak at noon

        # Update fan speed based on load
        ahu.sensor_readings["fan_speed"] = base_load + random.uniform(-0.1, 0.1)
        ahu.sensor_readings["fan_speed"] = max(0.3, min(1.0, ahu.sensor_readings["fan_speed"]))

        # Update temperatures
        ahu.sensor_readings["supply_temp"] = 20 + (ahu.sensor_readings["fan_speed"] - 0.6) * 5
        ahu.sensor_readings["return_temp"] = ahu.sensor_readings["supply_temp"] + random.uniform(2, 4)

        # Update filter pressure (increases over time)
        ahu.sensor_readings["filter_pressure"] += random.uniform(0.0001, 0.0005)

        # Update power consumption
        ahu.power_consumption = 15 + (ahu.sensor_readings["fan_speed"] * 10)

    def _update_chiller(self, chiller: EquipmentState, current_time: datetime):
        """Update chiller specific parameters"""
        # Ambient temperature affects chiller performance
        hour = current_time.hour
        ambient_temp = 20 + 8 * math.sin((hour - 6) * math.pi / 12)  # Simulates daily temp cycle

        # Update chiller temperatures
        chiller.temperature = 6 + (ambient_temp - 20) * 0.2  # Higher ambient = higher evap temp
        chiller.sensor_readings["evap_temp"] = chiller.temperature
        chiller.sensor_readings["cond_temp"] = ambient_temp + 10 + random.uniform(-2, 2)

        # Update pressures
        chiller.sensor_readings["refrigerant_pressure"] = 1.5 + (chiller.sensor_readings["cond_temp"] - 30) * 0.05

        # Power consumption varies with load
        load_factor = 0.6 + 0.3 * math.sin((hour - 8) * math.pi / 12)
        chiller.power_consumption = 100 + (load_factor * 100)

    def _update_fcu(self, fcu: EquipmentState, current_time: datetime):
        """Update FCU specific parameters"""
        # Simulate occupancy-based control
        hour = current_time.hour
        if 8 <= hour <= 18:  # Business hours
            target_temp = 22
            occupancy_factor = 0.8
        else:
            target_temp = 24
            occupancy_factor = 0.3

        # Update setpoint
        fcu.sensor_readings["setpoint"] = target_temp

        # Update room temperature (gradually approaches setpoint)
        current_temp = fcu.sensor_readings["room_temp"]
        temp_diff = target_temp - current_temp
        fcu.sensor_readings["room_temp"] += temp_diff * 0.1 + random.uniform(-0.2, 0.2)

        # Update valve position based on temperature difference
        temp_error = abs(fcu.sensor_readings["room_temp"] - target_temp)
        fcu.sensor_readings["valve_position"] = min(1.0, temp_error * 0.5)

        # Update fan speed based on occupancy
        if fcu.status == "running":
            fcu.sensor_readings["fan_speed"] = occupancy_factor + random.uniform(-0.1, 0.1)
            fcu.power_consumption = 0.5 + (fcu.sensor_readings["fan_speed"] * 1.5)

    def _update_sensor(self, sensor: EquipmentState, current_time: datetime):
        """Update sensor specific parameters"""
        # Apply sensor drift
        if self.config["enable_sensor_drift"]:
            # Very slow drift over time
            drift = random.uniform(-self.config["sensor_drift_rate"], self.config["sensor_drift_rate"])
            sensor.sensor_readings["value"] += drift

        # Add some noise
        noise = random.uniform(-0.1, 0.1)
        sensor.sensor_readings["value"] += noise

        # Update accuracy (degrades slightly over time)
        sensor.sensor_readings["accuracy"] *= 0.9999
        sensor.sensor_readings["accuracy"] = max(0.9, sensor.sensor_readings["accuracy"])

    def _update_ups(self, ups: EquipmentState, current_time: datetime):
        """Update UPS specific parameters"""
        # Battery slowly discharges over time
        discharge_rate = 0.001  # 0.1% per update
        ups.sensor_readings["battery_level"] -= discharge_rate

        # Recharge if above threshold
        if ups.sensor_readings["battery_level"] < 95:
            ups.sensor_readings["battery_level"] += discharge_rate * 1.1  # Slight overcharge

        # Keep within bounds
        ups.sensor_readings["battery_level"] = max(90, min(100, ups.sensor_readings["battery_level"]))

        # Vary load based on building activity
        hour = current_time.hour
        if 9 <= hour <= 17:  # Business hours
            ups.sensor_readings["load_percentage"] = random.uniform(40, 70)
        else:
            ups.sensor_readings["load_percentage"] = random.uniform(20, 40)

    def _calculate_health_score(self, equipment: EquipmentState) -> float:
        """Calculate equipment health score (0-100) with realistic degradation"""
        # Start from current health (persistent degradation)
        current_health = equipment.health_score

        # Natural degradation over time
        natural_degradation = self.config["degradation_rate"]

        # Fault-based degradation (accelerated)
        fault_degradation = len(equipment.fault_codes) * self.config["fault_degradation"]

        # Runtime penalty (equipment wears out)
        runtime_penalty = min(equipment.runtime_hours / 5000 * 0.01, 0.05)

        # Maintenance boost - if recently maintained, health improves
        days_since_maintenance = (datetime.now() - equipment.last_maintenance).days
        if days_since_maintenance < 7:
            maintenance_boost = 0.1  # Recent maintenance helps
        elif days_since_maintenance > 90:
            maintenance_boost = -0.05  # Overdue maintenance hurts
        else:
            maintenance_boost = 0

        # Operating condition penalties
        condition_penalty = 0
        if equipment.type == "chiller":
            if equipment.temperature > 12:
                condition_penalty = 0.1
            if equipment.sensor_readings.get("refrigerant_pressure", 0) > 2.5:
                condition_penalty += 0.2
        elif equipment.type == "ahu":
            if equipment.sensor_readings.get("filter_pressure", 0) > 0.5:
                condition_penalty = 0.15  # Clogged filter
            if equipment.temperature > 28:
                condition_penalty += 0.1
        elif equipment.type == "fcu":
            # FCUs affected by chiller status (cascading)
            if self.config["enable_cascading_failures"]:
                for eq in self.equipment.values():
                    if eq.type == "chiller" and eq.status == "down":
                        condition_penalty = 0.3  # Chiller down = FCUs struggle
                        break

        # Random fluctuation (small)
        random_factor = random.uniform(-0.05, 0.02)

        # Calculate new health
        total_degradation = natural_degradation + fault_degradation + runtime_penalty + condition_penalty + random_factor - maintenance_boost
        new_health = current_health - total_degradation

        # Clamp to valid range
        return max(0, min(100, new_health))

    def _update_equipment_status(self, equipment: EquipmentState, old_health: float):
        """Update equipment status based on health and generate alerts"""
        new_health = equipment.health_score
        old_status = equipment.status

        # Determine new status based on health thresholds
        if new_health >= self.health_thresholds["normal"]:
            new_status = "running" if equipment.type in ["ahu", "chiller", "fcu"] else "normal" if equipment.type == "ups" else "active"
        elif new_health >= self.health_thresholds["warning"]:
            new_status = "warning"
        elif new_health >= self.health_thresholds["critical"]:
            new_status = "critical"
        else:
            new_status = "down"

        # Handle equipment going DOWN
        if new_status == "down" and old_status != "down":
            equipment.status = "down"
            # Stop all operations when down
            if equipment.type in ["ahu", "fcu"]:
                equipment.sensor_readings["fan_speed"] = 0
                equipment.power_consumption = 0
            elif equipment.type == "chiller":
                equipment.power_consumption = 0
            self._generate_alert(equipment, "failure", f"{equipment.name} has FAILED and is now OFFLINE")
            logger.warning(f"EQUIPMENT DOWN: {equipment.id} - {equipment.name}")

        # Status transitions that generate alerts
        elif new_status != old_status:
            equipment.status = new_status
            if new_status == "critical" and old_status != "critical":
                self._generate_alert(equipment, "critical", f"{equipment.name} is in CRITICAL state - immediate attention required")
            elif new_status == "warning" and old_status in ["running", "normal", "active"]:
                self._generate_alert(equipment, "warning", f"{equipment.name} health degrading - maintenance recommended")

        # Health threshold crossing alerts
        if old_health >= 50 and new_health < 50:
            self._generate_alert(equipment, "health_critical", f"{equipment.name} health dropped below 50% - risk of failure")
        elif old_health >= 30 and new_health < 30:
            self._generate_alert(equipment, "health_danger", f"{equipment.name} health at {new_health:.0f}% - FAILURE IMMINENT")

    def _check_comfort_alerts(self, equipment: EquipmentState, current_time: datetime):
        """Check for comfort/operational issues that can be fixed remotely"""
        # Only check HVAC equipment for comfort
        if equipment.type not in ["ahu", "fcu", "chiller"]:
            return

        # Throttle comfort alerts - only once per 15 minutes per equipment
        alert_key = f"comfort_{equipment.id}"
        if not hasattr(self, '_comfort_alert_times'):
            self._comfort_alert_times = {}

        last_alert = self._comfort_alert_times.get(alert_key)
        if last_alert and (current_time - last_alert).total_seconds() < 900:  # 15 min
            return

        # Get temperature readings
        supply_temp = equipment.sensor_readings.get("supply_temp", 22)
        return_temp = equipment.sensor_readings.get("return_temp", 24)
        zone_temp = equipment.temperature

        # Comfort thresholds
        COMFORT_MIN = 20.0  # Too cold below this
        COMFORT_MAX = 26.0  # Too hot above this
        IDEAL_MIN = 21.0
        IDEAL_MAX = 24.0

        # Check for too hot (actionable: lower setpoint)
        if zone_temp > COMFORT_MAX and equipment.status != "down":
            self._generate_alert(
                equipment, "too_hot",
                f"Zone temperature {zone_temp:.1f}°C exceeds comfort limit ({COMFORT_MAX}°C). "
                f"Lower setpoint or increase cooling."
            )
            self._comfort_alert_times[alert_key] = current_time
            return

        # Check for too cold (actionable: raise setpoint)
        if zone_temp < COMFORT_MIN and equipment.status != "down":
            self._generate_alert(
                equipment, "too_cold",
                f"Zone temperature {zone_temp:.1f}°C below comfort limit ({COMFORT_MIN}°C). "
                f"Raise setpoint or switch to heating."
            )
            self._comfort_alert_times[alert_key] = current_time
            return

        # Check for high energy use (equipment running hard but zone not at setpoint)
        power = equipment.power_consumption
        if equipment.type == "chiller" and power > 180:  # High power
            self._generate_alert(
                equipment, "high_energy",
                f"{equipment.name} consuming {power:.0f}kW (high). Check if all zones need cooling."
            )
            self._comfort_alert_times[alert_key] = current_time
            return

        # Check for after-hours running (between 22:00 and 06:00)
        hour = current_time.hour
        if (hour >= 22 or hour < 6) and equipment.status == "running":
            # Only alert occasionally for after-hours
            if random.random() < 0.01:  # 1% chance per check
                self._generate_alert(
                    equipment, "after_hours",
                    f"{equipment.name} running after hours ({current_time.strftime('%H:%M')}). "
                    f"Turn off if building is unoccupied."
                )
                self._comfort_alert_times[alert_key] = current_time

    def _generate_alert(self, equipment: EquipmentState, alert_type: str, message: str):
        """Generate a SENTINEL alert"""
        self._alert_id_counter += 1

        severity_map = {
            "failure": "critical",
            "critical": "critical",
            "health_critical": "warning",
            "health_danger": "critical",
            "warning": "warning",
            "fault": "warning",
            "info": "info",
            # Comfort/operational alerts (actionable remotely)
            "too_hot": "warning",
            "too_cold": "warning",
            "high_energy": "warning",
            "after_hours": "info",
            "equipment_idle": "info"
        }

        priority_map = {
            "critical": 1,
            "warning": 2,
            "info": 3
        }

        severity = severity_map.get(alert_type, "warning")

        # Suggested actions for actionable alerts
        action_map = {
            "too_hot": f"Lower setpoint or increase fan speed: 'set {equipment.id} temp to 21'",
            "too_cold": f"Raise setpoint or switch to heating: 'set {equipment.id} temp to 24'",
            "high_energy": f"Check if equipment needed, turn off if not: 'turn off {equipment.id}'",
            "after_hours": f"Turn off or check schedule: 'turn off {equipment.id}'",
            "equipment_idle": f"Turn on if needed: 'turn on {equipment.id}'",
            "failure": "Dispatch technician - cannot fix remotely",
            "critical": "Run maintenance or dispatch technician",
            "warning": "Schedule maintenance soon"
        }

        alert = {
            "id": f"SIM-ALERT-{self._alert_id_counter}",
            "equipment_id": equipment.id,
            "equipment_name": equipment.name,
            "site_id": "site-001",
            "site_name": "SENTINEL Demo Site",
            "type": alert_type,
            "severity": severity,
            "priority": priority_map.get(severity, 2),
            "status": "active",
            "title": f"{severity.upper()}: {equipment.name} - {alert_type.replace('_', ' ').title()}",
            "message": message,
            "health_score": equipment.health_score,
            "fault_codes": equipment.fault_codes.copy(),
            "created_at": datetime.now().isoformat(),
            "acknowledged": False,
            "acknowledged_by": None,
            "category": "hvac" if equipment.type in ["ahu", "chiller", "fcu"] else "electrical" if equipment.type == "ups" else "sensor",
            "suggested_action": action_map.get(alert_type, None),
            "actionable_remotely": alert_type in ["too_hot", "too_cold", "high_energy", "after_hours", "equipment_idle"]
        }

        self.alert_queue.append(alert)
        self.alert_history.append(alert)

        # Keep history manageable
        if len(self.alert_history) > 500:
            self.alert_history = self.alert_history[-500:]

        logger.info(f"SENTINEL ALERT: [{severity.upper()}] {message}")

    def get_active_alerts(self) -> List[Dict[str, Any]]:
        """Get all active alerts from simulation"""
        return [a for a in self.alert_queue if a["status"] == "active"]

    def get_alert_history(self) -> List[Dict[str, Any]]:
        """Get alert history"""
        return self.alert_history.copy()

    def acknowledge_alert(self, alert_id: str, acknowledged_by: str = "Facilities Manager") -> bool:
        """Acknowledge an alert"""
        for alert in self.alert_queue:
            if alert["id"] == alert_id:
                alert["acknowledged"] = True
                alert["acknowledged_by"] = acknowledged_by
                alert["acknowledged_at"] = datetime.now().isoformat()
                return True
        return False

    def clear_alert(self, alert_id: str) -> bool:
        """Clear/resolve an alert"""
        for alert in self.alert_queue:
            if alert["id"] == alert_id:
                alert["status"] = "resolved"
                alert["resolved_at"] = datetime.now().isoformat()
                return True
        return False

    def perform_maintenance(self, equipment_id: str) -> Dict[str, Any]:
        """Simulate maintenance on equipment - restores health"""
        if equipment_id not in self.equipment:
            return {"success": False, "message": f"Equipment {equipment_id} not found"}

        equipment = self.equipment[equipment_id]
        old_health = equipment.health_score

        # Maintenance restores health significantly
        equipment.health_score = min(95, equipment.health_score + 30)
        equipment.last_maintenance = datetime.now()
        equipment.fault_codes = []  # Clear faults

        # If equipment was down, bring it back up
        if equipment.status == "down":
            equipment.status = "running" if equipment.type in ["ahu", "chiller", "fcu"] else "normal"
            self._generate_alert(equipment, "info", f"{equipment.name} restored to service after maintenance")

        logger.info(f"MAINTENANCE: {equipment_id} health restored from {old_health:.0f}% to {equipment.health_score:.0f}%")

        return {
            "success": True,
            "message": f"Maintenance completed on {equipment.name}",
            "old_health": old_health,
            "new_health": equipment.health_score
        }

    async def _apply_faults(self):
        """Apply random faults to equipment"""
        fault_probability = self.config["fault_probability"]

        for equipment in self.equipment.values():
            # Skip if down or already has max faults
            if equipment.status == "down" or len(equipment.fault_codes) >= 3:
                continue

            # Check if fault should occur
            if random.random() < fault_probability:
                fault_code = self.fault_simulator.generate_fault(equipment)
                if fault_code and fault_code not in equipment.fault_codes:
                    equipment.fault_codes.append(fault_code)
                    logger.warning(f"FAULT DETECTED: {fault_code} on {equipment.id} - {equipment.name}")

                    # Generate fault alert
                    fault_descriptions = {
                        "E14": "High pressure cutout - compressor protection activated",
                        "E21": "Low refrigerant detected - possible leak",
                        "F07": "Fan motor overload - check bearings",
                        "F21": "Airflow restriction - check filters",
                        "P01": "Pressure sensor fault",
                        "T03": "Temperature sensor drift detected",
                        "C05": "Communication fault with controller"
                    }
                    description = fault_descriptions.get(fault_code, f"Fault code {fault_code} detected")
                    self._generate_alert(equipment, "fault", f"{equipment.name}: {description}")

    def get_equipment_summary(self) -> Dict[str, Any]:
        """Get summary of all equipment"""
        summary = {
            "total_equipment": len(self.equipment),
            "by_type": {},
            "health_stats": {
                "avg_health": sum(eq.health_score for eq in self.equipment.values()) / len(self.equipment),
                "min_health": min(eq.health_score for eq in self.equipment.values()),
                "max_health": max(eq.health_score for eq in self.equipment.values())
            },
            "fault_summary": {
                "total_faults": sum(len(eq.fault_codes) for eq in self.equipment.values()),
                "equipment_with_faults": sum(1 for eq in self.equipment.values() if eq.fault_codes)
            },
            "timestamp": datetime.now()
        }

        # Count by type
        for equipment in self.equipment.values():
            if equipment.type not in summary["by_type"]:
                summary["by_type"][equipment.type] = 0
            summary["by_type"][equipment.type] += 1

        return summary

    def inject_fault(self, equipment_id: str, fault_code: str):
        """Manually inject a fault for testing"""
        if equipment_id in self.equipment:
            self.equipment[equipment_id].fault_codes.append(fault_code)
            logger.info(f"Injected fault {fault_code} into {equipment_id}")
        else:
            logger.error(f"Equipment {equipment_id} not found")

    def clear_faults(self, equipment_id: str):
        """Clear faults from equipment"""
        if equipment_id in self.equipment:
            self.equipment[equipment_id].fault_codes.clear()
            logger.info(f"Cleared faults from {equipment_id}")

    def get_real_time_data(self, equipment_id: Optional[str] = None) -> Dict[str, Any]:
        """Get current real-time data for equipment"""
        if equipment_id:
            if equipment_id in self.equipment:
                return asdict(self.equipment[equipment_id])
            else:
                return {"error": "Equipment not found"}
        else:
            return {
                "equipment": [asdict(eq) for eq in self.equipment.values()],
                "summary": self.get_equipment_summary()
            }


class FaultSimulator:
    """Generates realistic fault codes and conditions"""

    def __init__(self):
        self.fault_codes = {
            "Carrier": {
                "E1": "High pressure switch open",
                "E2": "Low pressure switch open",
                "E3": "Condenser coil sensor fault",
                "E4": "Evaporator coil sensor fault",
                "E5": "Communication error",
                "E14": "Outdoor fan motor fault",
                "E21": "Compressor overload",
                "E23": "Outdoor coil temperature sensor fault"
            },
            "York": {
                "F1": "High pressure fault",
                "F2": "Low pressure fault",
                "F3": "Phase loss",
                "F4": "Compressor overload",
                "F5": "Outdoor fan fault",
                "F14": "Indoor fan fault",
                "F21": "Temperature sensor fault",
                "F23": "Communication fault"
            },
            "Trane": {
                "E01": "High pressure cutout",
                "E02": "Low pressure cutout",
                "E03": "Outdoor coil sensor fault",
                "E04": "Indoor coil sensor fault",
                "E05": "Communication error",
                "E14": "Fan motor fault",
                "E21": "Compressor fault",
                "E23": "Sensor communication fault"
            },
            "Daikin": {
                "U1": "High pressure switch",
                "U2": "Low pressure switch",
                "U3": "Outdoor coil sensor",
                "U4": "Indoor coil sensor",
                "U5": "Communication error",
                "U14": "Fan motor error",
                "U21": "Compressor error",
                "U23": "Sensor error"
            },
            "Generic": {
                "E001": "System communication fault",
                "E002": "Sensor calibration required",
                "E003": "Filter replacement needed",
                "E004": "Maintenance due",
                "E005": "Power supply issue",
                "E006": "Temperature out of range",
                "E007": "Pressure out of range",
                "E008": "Flow rate too low"
            }
        }

    def generate_fault(self, equipment: EquipmentState) -> Optional[str]:
        """Generate a realistic fault code for equipment"""
        # Higher chance of fault for older equipment or equipment with lower health
        health_factor = (100 - equipment.health_score) / 100
        age_factor = min(equipment.runtime_hours / 10000, 1.0)

        fault_probability = (health_factor + age_factor) / 2

        if random.random() < fault_probability * 0.1:  # 10% base chance
            manufacturer = equipment.manufacturer
            if manufacturer in self.fault_codes:
                fault_codes = list(self.fault_codes[manufacturer].keys())
                fault_code = random.choice(fault_codes)
                return f"{manufacturer}:{fault_code}"
            else:
                # Use generic fault codes
                generic_codes = list(self.fault_codes["Generic"].keys())
                fault_code = random.choice(generic_codes)
                return f"Generic:{fault_code}"

        return None


class SensorSimulator:
    """Simulates sensor behavior including drift and noise"""

    def apply_drift(self, equipment: EquipmentState):
        """Apply realistic sensor drift over time"""
        # Different drift rates for different sensor types
        drift_rates = {
            "temperature": 0.01,
            "pressure": 0.005,
            "flow": 0.02
        }

        for key, value in equipment.sensor_readings.items():
            if isinstance(value, (int, float)):
                # Apply small drift
                if "temp" in key.lower():
                    drift = random.uniform(-drift_rates["temperature"], drift_rates["temperature"])
                elif "press" in key.lower():
                    drift = random.uniform(-drift_rates["pressure"], drift_rates["pressure"])
                elif "flow" in key.lower():
                    drift = random.uniform(-drift_rates["flow"], drift_rates["flow"])
                else:
                    drift = random.uniform(-0.01, 0.01)

                equipment.sensor_readings[key] += drift


class DataGenerator:
    """Generates realistic time-series data patterns"""

    def generate_time_pattern(self, base_value: float, time_of_day: int, pattern_type: str = "daily") -> float:
        """Generate time-based patterns (daily, weekly, etc.)"""
        if pattern_type == "daily":
            # Sinusoidal pattern peaking during business hours
            amplitude = 0.2 * base_value
            phase = (time_of_day - 6) * 2 * math.pi / 24
            return base_value + amplitude * math.sin(phase)
        elif pattern_type == "weekly":
            # Lower values on weekends
            day_of_week = datetime.now().weekday()
            if day_of_week >= 5:  # Weekend
                return base_value * 0.7
            else:
                return base_value
        else:
            return base_value

    def generate_noise(self, base_value: float, noise_level: float = 0.05) -> float:
        """Add realistic noise to sensor readings"""
        return base_value + random.uniform(-noise_level * base_value, noise_level * base_value)


def create_simulation_service() -> BMSimulationService:
    """Factory function to create simulation service"""
    return BMSimulationService()


# Export for use in other modules
__all__ = ['BMSimulationService', 'create_simulation_service', 'EquipmentState']