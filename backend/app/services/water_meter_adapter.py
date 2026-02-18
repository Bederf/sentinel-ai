"""Water meter device adapter for Modbus pulse counter communication.

Implements DeviceInterface for protocol-agnostic water meter operations.
Supports real Modbus RTU/TCP and simulated mode for demo.
"""

import logging
from typing import Dict, Any
from datetime import datetime

from app.services.device_abstraction import DeviceInterface

logger = logging.getLogger(__name__)


class WaterMeterAdapter(DeviceInterface):
    """Device adapter for water meters with Modbus pulse counters.

    Water meters use pulse counters to measure flow:
    - Each pulse represents a fixed volume (e.g., 10 liters per pulse)
    - Cumulative pulse count = total volume
    - Flow rate calculated from pulse delta over time
    """

    def __init__(self, device_id: str, config: Dict[str, Any]):
        """Initialize water meter adapter.

        Args:
            device_id: Equipment code (e.g., "S002-MTR-W-MAIN")
            config: Device configuration including pulse_weight, register_address
        """
        self.device_id = device_id
        self.config = config
        self.pulse_weight = config.get("pulse_weight", 10.0)  # Liters per pulse
        self.register_address = config.get("register_address", 30001)
        self.protocol = config.get("protocol", "modbus")
        self.site = config.get("site", "site-002")

        # Modbus client (mock for demo, real implementation in production)
        self._mock_pulse_count = 0
        self._mock_flow_rate = 0.0

    def connect(self) -> bool:
        """Establish connection to the meter.

        For demo mode, this always succeeds.
        In production, would establish Modbus TCP/RTU connection.
        """
        logger.info(f"Connected to water meter {self.device_id} via {self.protocol}")
        return True

    def disconnect(self) -> None:
        """Disconnect from the meter."""
        logger.info(f"Disconnected from water meter {self.device_id}")

    def read_point(self, point_name: str) -> Any:
        """Read a single point from the meter.

        Args:
            point_name: Name of point to read (pulse_count, flow_rate, volume_liters, etc.)

        Returns:
            Point value or None if read fails
        """
        if point_name == "pulse_count":
            return self._read_pulse_count()
        elif point_name == "flow_rate":
            return self._read_flow_rate()
        elif point_name == "volume_liters":
            return self._read_volume()
        elif point_name == "temperature":
            return 18.0 + hash(self.device_id) % 5  # Mock: 18-22°C
        elif point_name == "pressure":
            return 3.5 + (hash(self.device_id) % 10) / 10.0  # Mock: 3.5-4.5 bar
        else:
            logger.warning(f"Unknown point: {point_name}")
            return None

    def read_all_points(self) -> Dict[str, Any]:
        """Read all points from the meter.

        Returns:
            Dictionary of point_name -> value
        """
        return {
            "pulse_count": self._read_pulse_count(),
            "flow_rate": self._read_flow_rate(),
            "volume_liters": self._read_volume(),
            "temperature": 18.0 + hash(self.device_id) % 5,
            "pressure": 3.5 + (hash(self.device_id) % 10) / 10.0,
        }

    def write_point(self, point_name: str, value: Any) -> bool:
        """Write a point to the meter.

        Water meters are read-only, so this always fails.
        """
        logger.warning(f"Attempted write to read-only water meter {self.device_id}")
        return False

    def discover(self) -> Dict[str, Any]:
        """Auto-discover meter metadata.

        Returns:
            Dictionary with meter metadata (GTIN, serial, pulse_weight, etc.)
        """
        # Mock discovery - in production would read from Modbus registers
        return {
            "device_id": self.device_id,
            "manufacturer": "Elster",
            "model": "V100",
            "serial_number": f"EM-{self.site.upper().replace('SITE-', 'S')}-2023-001",
            "gtin": "4055449001234",
            "pulse_weight": self.pulse_weight,
            "diameter_mm": 80,
            "max_flow_rate_lpm": 100.0,
            "min_flow_rate_lpm": 0.5,
            "protocol": self.protocol,
            "register_address": self.register_address,
            "discovery_timestamp": datetime.now().isoformat(),
        }

    def _read_pulse_count(self) -> int:
        """Read cumulative pulse count from Modbus register."""
        # Mock implementation - in production read from Modbus
        self._mock_pulse_count += 1  # Simulate increment
        return self._mock_pulse_count

    def _read_flow_rate(self) -> float:
        """Read instantaneous flow rate in LPM.

        For demo, generates realistic flow pattern.
        """
        # Mock: time-based flow pattern
        hour = datetime.now().hour
        if 6 <= hour <= 9 or 17 <= hour <= 20:  # Peak times
            base_flow = 25.0
        elif 12 <= hour <= 14:  # Lunch
            base_flow = 30.0
        elif 22 <= hour or hour <= 4:  # Night
            base_flow = 1.5
        else:  # Normal daytime
            base_flow = 15.0

        # Add some variation
        import random
        self._mock_flow_rate = base_flow + random.uniform(-3, 3)
        return round(max(0, self._mock_flow_rate), 2)

    def _read_volume(self) -> float:
        """Read total volume in liters."""
        return self._read_pulse_count() * self.pulse_weight

    def get_device_info(self) -> Dict[str, Any]:
        """Get device information."""
        return {
            "device_id": self.device_id,
            "device_type": "METER",
            "protocol": self.protocol,
            "site": self.site,
            "pulse_weight": self.pulse_weight,
            "register_address": self.register_address,
            "status": "online",
        }


def create_water_meter_adapter(device_id: str, config: Dict[str, Any]) -> WaterMeterAdapter:
    """Factory function to create a water meter adapter.

    Args:
        device_id: Equipment code
        config: Device configuration

    Returns:
        WaterMeterAdapter instance
    """
    return WaterMeterAdapter(device_id, config)
