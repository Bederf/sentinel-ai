"""
Simulation Bridge - Integrates BMS simulation with existing equipment API
Converts simulation data to match existing equipment format
"""

import json
import asyncio
from datetime import datetime, timedelta
from typing import List, Dict, Any, Optional
from pathlib import Path

from app.services.bms_simulation_service import create_simulation_service

class SimulationBridge:
    """Bridge between simulation data and existing equipment API format"""

    def __init__(self):
        self.simulation_service = create_simulation_service()
        self.data_dir = Path(__file__).parent.parent / "data"

    async def initialize(self):
        """Initialize the simulation bridge"""
        if not self.simulation_service.is_running:
            await self.simulation_service.start_simulation()

    def convert_simulation_to_equipment_format(self, sim_equipment: Dict[str, Any]) -> Dict[str, Any]:
        """Convert simulation equipment to existing equipment format"""
        return {
            "id": sim_equipment["id"],
            "name": sim_equipment["name"],
            "type": sim_equipment["type"],
            "manufacturer": sim_equipment["manufacturer"],
            "model": self._get_model_for_equipment(sim_equipment),
            "serial_number": f"SIM-{sim_equipment['id']}",
            "location": sim_equipment["location"],
            "building": "Main Building",
            "floor": self._extract_floor_from_location(sim_equipment["location"]),
            "zone": self._extract_zone_from_location(sim_equipment["location"]),
            "room": self._extract_room_from_location(sim_equipment["location"]),
            "health_score": sim_equipment["health_score"],
            "status": sim_equipment["status"],
            "installation_date": "2023-01-01",  # Simulated
            "last_maintenance": sim_equipment["last_maintenance"].isoformat() if isinstance(sim_equipment["last_maintenance"], datetime) else sim_equipment["last_maintenance"],
            "next_maintenance": (datetime.now() + timedelta(days=30)).isoformat(),
            "warranty_expiry": "2025-01-01",  # Simulated
            "specifications": self._generate_specifications(sim_equipment),
            "images": [],  # No images for simulated equipment
            "documents": [],  # No documents for simulated equipment
            "tags": [sim_equipment["type"], "simulated"],
            "created_at": datetime.now().isoformat(),
            "updated_at": sim_equipment["timestamp"].isoformat() if isinstance(sim_equipment["timestamp"], datetime) else sim_equipment["timestamp"]
        }

    def convert_simulation_to_sensor_format(self, sim_equipment: Dict[str, Any]) -> List[Dict[str, Any]]:
        """Convert simulation sensor readings to sensor format"""
        sensors = []

        # Convert each sensor reading to sensor format
        for sensor_name, value in sim_equipment["sensor_readings"].items():
            # Skip non-numeric sensor values (like dates)
            if not isinstance(value, (int, float)):
                continue

            sensor = {
                "id": f"{sim_equipment['id']}_{sensor_name.upper()}",
                "equipment_id": sim_equipment["id"],
                "name": f"{sim_equipment['name']} {sensor_name.replace('_', ' ').title()}",
                "type": self._get_sensor_type(sensor_name),
                "unit": self._get_sensor_unit(sensor_name),
                "current_value": value,
                "timestamp": sim_equipment["timestamp"].isoformat() if isinstance(sim_equipment["timestamp"], datetime) else sim_equipment["timestamp"],
                "quality": "good",
                "min_value": value * 0.8,  # Simulated range
                "max_value": value * 1.2,
                "threshold_low": value * 0.9,
                "threshold_high": value * 1.1,
                "description": f"{sensor_name.replace('_', ' ')} for {sim_equipment['name']}"
            }
            sensors.append(sensor)

        return sensors

    def convert_simulation_to_alert_format(self, sim_equipment: Dict[str, Any]) -> List[Dict[str, Any]]:
        """Convert simulation fault codes to alert format"""
        alerts = []

        for fault_code in sim_equipment["fault_codes"]:
            # Parse fault code (format: "Manufacturer:Code")
            if ":" in fault_code:
                manufacturer, code = fault_code.split(":", 1)
                description = self._get_fault_description(manufacturer, code)
            else:
                description = f"Fault detected: {fault_code}"

            alert = {
                "id": f"ALERT_{sim_equipment['id']}_{fault_code}",
                "equipment_id": sim_equipment["id"],
                "type": "fault",
                "severity": self._get_severity_for_fault(fault_code),
                "title": f"{sim_equipment['name']} - Fault {fault_code}",
                "description": description,
                "status": "active",
                "created_at": datetime.now().isoformat(),
                "acknowledged": False,
                "assigned_to": None,
                "priority": self._get_priority_for_fault(fault_code),
                "tags": ["fault", "simulated"]
            }
            alerts.append(alert)

        return alerts

    def get_equipment_with_sensors_and_alerts(self) -> tuple:
        """Get complete equipment data with sensors and alerts"""
        if not self.simulation_service.is_running:
            return [], [], []

        equipment_data = self.simulation_service.get_real_time_data()
        equipment_list = equipment_data.get("equipment", [])

        # Convert equipment
        converted_equipment = []
        all_sensors = []
        all_alerts = []

        for sim_eq in equipment_list:
            # Convert equipment
            converted_eq = self.convert_simulation_to_equipment_format(sim_eq)
            converted_equipment.append(converted_eq)

            # Convert sensors
            sensors = self.convert_simulation_to_sensor_format(sim_eq)
            all_sensors.extend(sensors)

            # Convert alerts
            alerts = self.convert_simulation_to_alert_format(sim_eq)
            all_alerts.extend(alerts)

        return converted_equipment, all_sensors, all_alerts

    def _get_model_for_equipment(self, sim_equipment: Dict[str, Any]) -> str:
        """Generate a model name based on equipment type and manufacturer"""
        manufacturer = sim_equipment["manufacturer"]
        equipment_type = sim_equipment["type"]

        models = {
            "Carrier": {
                "ahu": "39AQA",
                "chiller": "30XA",
                "fcu": "42QH",
                "ups": "APC Smart-UPS"
            },
            "York": {
                "ahu": "YAHU",
                "chiller": "YMC2",
                "fcu": "YFCU",
                "ups": "APC Smart-UPS"
            },
            "Trane": {
                "ahu": "Tracer",
                "chiller": "CGAM",
                "fcu": "FCU",
                "ups": "APC Smart-UPS"
            },
            "Daikin": {
                "ahu": "VAM",
                "chiller": "EWQ",
                "fcu": "FCU",
                "ups": "APC Smart-UPS"
            }
        }

        return models.get(manufacturer, {}).get(equipment_type, f"{manufacturer}-{equipment_type.upper()}")

    def _extract_floor_from_location(self, location: str) -> str:
        """Extract floor number from location string"""
        if "Level" in location or "Floor" in location:
            # Extract number from "Level 1" or "Floor 2"
            import re
            match = re.search(r'(\d+)', location)
            return match.group(1) if match else "1"
        return "1"

    def _extract_zone_from_location(self, location: str) -> str:
        """Extract zone from location string"""
        if "Zone" in location:
            import re
            match = re.search(r'Zone\s+(\d+)', location)
            return match.group(1) if match else "1"
        return "1"

    def _extract_room_from_location(self, location: str) -> str:
        """Extract room from location string"""
        if "Room" in location:
            import re
            match = re.search(r'Room\s+(\d+)', location)
            return match.group(1) if match else "01"
        return "01"

    def _get_sensor_type(self, sensor_name: str) -> str:
        """Map sensor name to type"""
        sensor_type_map = {
            "temperature": "temperature",
            "temp": "temperature",
            "pressure": "pressure",
            "press": "pressure",
            "flow": "flow_rate",
            "humidity": "humidity",
            "speed": "speed",
            "level": "level"
        }

        for key, value in sensor_type_map.items():
            if key in sensor_name.lower():
                return value

        return "generic"

    def _get_sensor_unit(self, sensor_name: str) -> str:
        """Map sensor name to unit"""
        unit_map = {
            "temperature": "°C",
            "temp": "°C",
            "pressure": "bar",
            "press": "bar",
            "flow": "L/min",
            "humidity": "%RH",
            "speed": "rpm",
            "level": "%"
        }

        for key, value in unit_map.items():
            if key in sensor_name.lower():
                return value

        return "-"

    def _get_fault_description(self, manufacturer: str, code: str) -> str:
        """Get description for fault code"""
        fault_descriptions = {
            "Carrier": {
                "E1": "High pressure switch open - Check condenser coil",
                "E2": "Low pressure switch open - Check for refrigerant leak",
                "E14": "Outdoor fan motor fault - Motor may need replacement",
                "E21": "Compressor overload - Check electrical connections"
            },
            "York": {
                "F1": "High pressure fault - Clean condenser coils",
                "F2": "Low pressure fault - Check refrigerant levels",
                "F14": "Indoor fan fault - Inspect fan motor",
                "F21": "Temperature sensor fault - Replace sensor"
            }
        }

        return fault_descriptions.get(manufacturer, {}).get(code, f"{manufacturer} fault code {code}")

    def _get_severity_for_fault(self, fault_code: str) -> str:
        """Determine severity based on fault code"""
        # Higher numbers generally mean more severe faults
        if any(code in fault_code for code in ["E21", "F21", "U21"]):
            return "critical"
        elif any(code in fault_code for code in ["E14", "F14", "U14"]):
            return "major"
        else:
            return "minor"

    def _get_priority_for_fault(self, fault_code: str) -> int:
        """Determine priority (1-5) based on fault code"""
        severity = self._get_severity_for_fault(fault_code)
        severity_map = {
            "critical": 5,
            "major": 4,
            "minor": 2
        }
        return severity_map.get(severity, 3)

    def _generate_specifications(self, sim_equipment: Dict[str, Any]) -> Dict[str, Any]:
        """Generate realistic specifications for equipment"""
        specs = {
            "capacity": "Standard",
            "efficiency": "High",
            "power_supply": "380V/3P/50Hz",
            "operating_range": "-10°C to 50°C",
            "noise_level": "<65dB",
            "weight": "Standard",
            "dimensions": "Standard",
            "certifications": ["ISO 9001", "CE", "RoHS"]
        }

        # Add type-specific specs
        if sim_equipment["type"] == "chiller":
            specs.update({
                "refrigerant": "R410A",
                "compressor_type": "Scroll",
                "condenser_type": "Air-cooled"
            })
        elif sim_equipment["type"] == "ahu":
            specs.update({
                "fan_type": "Centrifugal",
                "filter_type": "Bag filter",
                "coil_type": "Copper tube, aluminum fin"
            })

        return specs


# Global bridge instance
simulation_bridge = SimulationBridge()

# Export for use
__all__ = ['simulation_bridge', 'SimulationBridge']
