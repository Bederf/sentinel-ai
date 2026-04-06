"""Simulated Device Adapter.

BMS simulator implementation of DeviceInterface for the Site 002 lifecycle simulator.
Produces realistic device telemetry without requiring physical hardware
or network connections.
"""

import asyncio
import json
import logging
import random
from datetime import datetime
from pathlib import Path
from typing import Any

from app.models.device import Device, DevicePoint, DeviceValue, PointType
from app.services.device_abstraction import DeviceAdapter

logger = logging.getLogger(__name__)

# State persistence file
STATE_FILE = Path(__file__).parent.parent.parent.parent / "data" / "bms_simulator" / "device_state.json"

# Global state cache for all simulated devices
_global_state_cache: dict[str, dict[str, Any]] = {}
_state_loaded = False


def _load_global_state() -> None:
    """Load persisted state from file."""
    global _global_state_cache, _state_loaded
    if _state_loaded:
        return

    if STATE_FILE.exists():
        try:
            with open(STATE_FILE) as f:
                _global_state_cache = json.load(f)
            logger.info(f"Loaded device state for {len(_global_state_cache)} devices")
        except Exception as e:
            logger.warning(f"Failed to load device state: {e}")
            _global_state_cache = {}
    _state_loaded = True


def _save_global_state() -> None:
    """Save state to file."""
    global _global_state_cache
    try:
        STATE_FILE.parent.mkdir(parents=True, exist_ok=True)
        with open(STATE_FILE, "w") as f:
            json.dump(_global_state_cache, f, indent=2)
        logger.debug(f"Saved device state for {len(_global_state_cache)} devices")
    except Exception as e:
        logger.error(f"Failed to save device state: {e}")


class SimulatedDeviceAdapter(DeviceAdapter):
    """Simulated device adapter for the BMS simulator.

    Produces realistic device telemetry including:
    - Network latency (50-200ms)
    - Occasional errors
    - State persistence (file-backed)
    - Realistic value ranges and validation
    """

    def __init__(self, device: Device):
        super().__init__(device)
        self._error_rate = 0.05  # 5% chance of error
        self._initialize_state()

    @property
    def _state(self) -> dict[str, Any]:
        """Get device state from global cache."""
        _load_global_state()
        if self.device.id not in _global_state_cache:
            _global_state_cache[self.device.id] = {}
        return _global_state_cache[self.device.id]

    def _initialize_state(self) -> None:
        """Initialize device state from points configuration or persisted state."""
        _load_global_state()

        # Check if we have persisted state
        if _global_state_cache.get(self.device.id):
            logger.debug(f"Using persisted state for device {self.device.id}")
            # Ensure all points have values (for new points added after state was saved)
            for point_name, point in self.device.points.items():
                if point_name not in _global_state_cache[self.device.id]:
                    _global_state_cache[self.device.id][point_name] = self._get_default_value(point)
            return

        # Initialize from defaults
        _global_state_cache[self.device.id] = {}
        for point_name, point in self.device.points.items():
            _global_state_cache[self.device.id][point_name] = self._get_default_value(point)

        logger.debug(f"Initialized state for device {self.device.id}: {_global_state_cache[self.device.id]}")

    def _get_default_value(self, point: DevicePoint) -> Any:
        """Get default value for a point based on its type."""
        if point.default_value is not None:
            return point.default_value

        # Set reasonable defaults based on point type
        if point.point_type in [PointType.ANALOG_INPUT, PointType.ANALOG_OUTPUT, PointType.ANALOG_VALUE]:
            if point.min_value is not None and point.max_value is not None:
                return (point.min_value + point.max_value) / 2
            return 0.0
        elif point.point_type in [PointType.BINARY_INPUT, PointType.BINARY_OUTPUT, PointType.BINARY_VALUE]:
            return False
        elif point.point_type in [PointType.MULTISTATE_INPUT, PointType.MULTISTATE_OUTPUT, PointType.MULTISTATE_VALUE]:
            return 0
        return None

    async def _simulate_network_delay(self, min_ms: float = 50, max_ms: float = 200) -> None:
        """Simulate network latency."""
        delay = random.uniform(min_ms / 1000, max_ms / 1000)
        await asyncio.sleep(delay)

    async def _simulate_error(self) -> bool:
        """Simulate occasional device errors."""
        if random.random() < self._error_rate:
            logger.warning(f"Simulating error on device {self.device.id}")
            return True
        return False

    async def _protocol_connect(self) -> bool:
        """Simulated connection always succeeds."""
        await self._simulate_network_delay(100, 300)
        logger.info(f"Connected to simulated device {self.device.id}")
        return True

    async def _protocol_disconnect(self) -> None:
        """Simulated disconnection."""
        await self._simulate_network_delay(50, 150)
        logger.info(f"Disconnected from simulated device {self.device.id}")

    async def _protocol_read(self, point_name: str) -> DeviceValue:
        """Simulated read implementation with network latency and errors."""
        await self._simulate_network_delay()

        if await self._simulate_error():
            raise OSError(f"Read error on point {point_name}")

        if point_name not in self._state:
            raise ValueError(f"Point {point_name} not found in device state")

        point = self.device.get_point(point_name)
        if not point:
            raise ValueError(f"Point {point_name} not configured on device")

        # Add small random variation to analog values for realism
        value = self._state[point_name]
        if point.point_type in [PointType.ANALOG_INPUT, PointType.ANALOG_OUTPUT, PointType.ANALOG_VALUE]:
            if isinstance(value, (int, float)):
                # Add ±2% variation
                variation = random.uniform(-0.02, 0.02) * value
                value = value + variation
                # Round to reasonable precision
                if point.unit == "°C":
                    value = round(value, 1)
                elif point.unit == "%":
                    value = round(value, 0)
                else:
                    value = round(value, 2)

        return DeviceValue(point_name=point_name, value=value, unit=point.unit, quality="good")

    async def _protocol_write(self, point_name: str, value: Any, priority: int) -> bool:
        """Simulated write implementation with validation."""
        await self._simulate_network_delay(100, 300)

        point = self.device.get_point(point_name)
        if not point:
            raise ValueError(f"Point {point_name} not configured on device")

        if not point.writable:
            raise ValueError(f"Point {point_name} is not writable")

        if not point.validate_value(value):
            raise ValueError(f"Value {value} invalid for point {point_name}")

        # Log test_mode changes for fire safety devices
        if self.device.metadata.get("life_safety") and point_name == "test_mode":
            if value:
                logger.info(f"Fire safety test mode enabled for {self.device.id}")

        # Apply the write
        old_value = self._state.get(point_name)
        _global_state_cache[self.device.id][point_name] = value

        # Persist state to file
        _save_global_state()

        # Log the change
        logger.info(f"Wrote {point_name}: {old_value} -> {value} (priority: {priority}, device: {self.device.id})")

        # Update device timestamp
        self.device.updated_at = datetime.now().isoformat()

        return True

    def _validate_safety_test_conditions(self) -> bool:
        """Validate conditions for safety device testing."""
        # In real implementation, would check:
        # - Building evacuation status
        # - Fire alarm system status
        # - Authorized personnel present
        # - Time of day restrictions
        # For simulated adapter, simulate 80% success rate
        return random.random() < 0.8

    async def scan_points(self) -> dict[str, DevicePoint]:
        """Scan for device points — returns configured points."""
        await self._simulate_network_delay(200, 500)
        return self.device.points

    def get_state(self) -> dict[str, Any]:
        """Get current device state (for testing)."""
        return self._state.copy()

    def set_state(self, point_name: str, value: Any, persist: bool = False) -> None:
        """Set device state (for testing).

        Args:
            point_name: The point to set
            value: The value to set
            persist: If True, save state to file (default False for test scenarios)
        """
        _global_state_cache[self.device.id][point_name] = value
        if persist:
            _save_global_state()


class SimulatedDeviceManager:
    """Helper for managing simulated devices in scenario setups."""

    @staticmethod
    async def create_demo_scenario(device_manager) -> None:
        """Create interesting scenarios with simulated devices."""
        logger.info("Setting up simulated device scenarios")

        # Get the Gateway Chiller (hero device)
        chiller = await device_manager.get_device("chiller-gateway-01")
        if chiller:
            # Set up interesting state for scenario
            adapter = await device_manager.get_adapter("chiller-gateway-01")
            if adapter and isinstance(adapter, SimulatedDeviceAdapter):
                # Set compressor pressure near alarm threshold
                adapter.set_state("compressor_pressure", 22.8)  # Near 25 bar max
                logger.info("Set chiller compressor pressure near alarm threshold")

        # Set AHU filter pressure high for maintenance scenario
        ahu = await device_manager.get_device("ahu-level3-01")
        if ahu:
            adapter = await device_manager.get_adapter("ahu-level3-01")
            if adapter and isinstance(adapter, SimulatedDeviceAdapter):
                adapter.set_state("filter_pressure", 210)  # Above 200 Pa alarm threshold
                logger.info("Set AHU filter pressure above alarm threshold")

        # Set office temperature outside comfort range
        vav = await device_manager.get_device("vav-office-301")
        if vav:
            adapter = await device_manager.get_adapter("vav-office-301")
            if adapter and isinstance(adapter, SimulatedDeviceAdapter):
                adapter.set_state("room_temp", 29.5)  # Above 28°C max
                logger.info("Set office temperature above comfort range")

    @staticmethod
    async def simulate_device_events(device_manager) -> None:
        """Simulate changing device values over time."""
        devices = await device_manager.list_devices()

        for device in devices:
            adapter = await device_manager.get_adapter(device.id)
            if not adapter or not isinstance(adapter, SimulatedDeviceAdapter):
                continue

            state = adapter.get_state()

            # Simulate small changes in analog values
            for point_name, value in state.items():
                point = device.get_point(point_name)
                if not point:
                    continue

                if point.point_type in [PointType.ANALOG_INPUT, PointType.ANALOG_OUTPUT, PointType.ANALOG_VALUE]:
                    if isinstance(value, (int, float)):
                        # Small random walk
                        change = random.uniform(-0.5, 0.5)
                        new_value = value + change

                        # Keep within bounds
                        if point.min_value is not None:
                            new_value = max(new_value, point.min_value)
                        if point.max_value is not None:
                            new_value = min(new_value, point.max_value)

                        adapter.set_state(point_name, new_value)

            # Occasionally change binary/multistate values
            if random.random() < 0.1:  # 10% chance per device
                for point_name, point in device.points.items():
                    if point.point_type in [PointType.BINARY_INPUT, PointType.BINARY_VALUE]:
                        if random.random() < 0.3:  # 30% chance to toggle
                            current = state.get(point_name, False)
                            adapter.set_state(point_name, not current)
                            logger.debug(f"Toggled {point_name} on device {device.id}")

        logger.debug("Simulated device value changes complete")
