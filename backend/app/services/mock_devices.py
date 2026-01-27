"""Mock Device Adapter.

Mock implementation of DeviceInterface for demo purposes.
Simulates realistic device behavior without requiring real hardware
or network connections.
"""

import asyncio
import random
import logging
from datetime import datetime
from typing import Dict, Any, Optional

from app.models.device import (
    Device, DeviceValue, DeviceStatus, DevicePoint,
    PointType
)
from app.services.device_abstraction import DeviceAdapter

logger = logging.getLogger(__name__)


class MockDeviceAdapter(DeviceAdapter):
    """Mock device adapter for demo and testing.

    Simulates realistic device behavior including:
    - Network latency (50-200ms)
    - Occasional errors
    - State persistence (in-memory)
    - Realistic value ranges and validation
    """

    def __init__(self, device: Device):
        super().__init__(device)
        self._state: Dict[str, Any] = {}
        self._error_rate = 0.05  # 5% chance of error
        self._initialize_state()

    def _initialize_state(self) -> None:
        """Initialize device state from points configuration."""
        for point_name, point in self.device.points.items():
            if point.default_value is not None:
                self._state[point_name] = point.default_value
            else:
                # Set reasonable defaults based on point type
                if point.point_type in [PointType.ANALOG_INPUT, PointType.ANALOG_OUTPUT, PointType.ANALOG_VALUE]:
                    if point.min_value is not None and point.max_value is not None:
                        self._state[point_name] = (point.min_value + point.max_value) / 2
                    else:
                        self._state[point_name] = 0.0
                elif point.point_type in [PointType.BINARY_INPUT, PointType.BINARY_OUTPUT, PointType.BINARY_VALUE]:
                    self._state[point_name] = False
                elif point.point_type in [PointType.MULTISTATE_INPUT, PointType.MULTISTATE_OUTPUT, PointType.MULTISTATE_VALUE]:
                    self._state[point_name] = 0

        logger.debug(f"Initialized mock state for device {self.device.id}: {self._state}")

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
        """Mock connection always succeeds."""
        await self._simulate_network_delay(100, 300)
        logger.info(f"Mock connected to device {self.device.id}")
        return True

    async def _protocol_disconnect(self) -> None:
        """Mock disconnection."""
        await self._simulate_network_delay(50, 150)
        logger.info(f"Mock disconnected from device {self.device.id}")

    async def _protocol_read(self, point_name: str) -> DeviceValue:
        """Mock read implementation with simulated latency and errors."""
        await self._simulate_network_delay()

        if await self._simulate_error():
            raise IOError(f"Mock read error on point {point_name}")

        if point_name not in self._state:
            raise ValueError(f"Point {point_name} not found in mock state")

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

        return DeviceValue(
            point_name=point_name,
            value=value,
            unit=point.unit,
            quality="good"
        )

    async def _protocol_write(self, point_name: str, value: Any, priority: int) -> bool:
        """Mock write implementation with validation and simulation."""
        await self._simulate_network_delay(100, 300)

        if await self._simulate_error():
            logger.warning(f"Mock write error on point {point_name}")
            return False

        point = self.device.get_point(point_name)
        if not point:
            raise ValueError(f"Point {point_name} not configured on device")

        if not point.writable:
            raise ValueError(f"Point {point_name} is not writable")

        if not point.validate_value(value):
            raise ValueError(f"Value {value} invalid for point {point_name}")

        # Special safety checks for critical devices
        if self.device.metadata.get("life_safety") and point_name == "test_mode":
            # Fire safety devices have special restrictions
            if value and not self._validate_safety_test_conditions():
                logger.error(f"Safety test conditions not met for {self.device.id}")
                return False

        # Apply the write
        old_value = self._state.get(point_name)
        self._state[point_name] = value

        # Log the change
        logger.info(
            f"Mock wrote {point_name}: {old_value} -> {value} "
            f"(priority: {priority}, device: {self.device.id})"
        )

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
        # For mock, simulate 80% success rate
        return random.random() < 0.8

    async def scan_points(self) -> Dict[str, DevicePoint]:
        """Mock point scanning - returns configured points."""
        await self._simulate_network_delay(200, 500)
        return self.device.points

    def get_state(self) -> Dict[str, Any]:
        """Get current mock device state (for testing)."""
        return self._state.copy()

    def set_state(self, point_name: str, value: Any) -> None:
        """Set mock device state (for testing)."""
        self._state[point_name] = value


class MockDeviceManager:
    """Helper for managing mock devices in demo scenarios."""

    @staticmethod
    async def create_demo_scenario(device_manager) -> None:
        """Create interesting demo scenarios with mock devices."""
        logger.info("Setting up mock device demo scenarios")

        # Get the Gateway Chiller (hero device)
        chiller = await device_manager.get_device("chiller-gateway-01")
        if chiller:
            # Simulate some interesting state for demo
            adapter = await device_manager.get_adapter("chiller-gateway-01")
            if adapter and isinstance(adapter, MockDeviceAdapter):
                # Set compressor pressure near alarm threshold
                adapter.set_state("compressor_pressure", 22.8)  # Near 25 bar max
                logger.info("Set chiller compressor pressure near alarm threshold for demo")

        # Set AHU filter pressure high for maintenance demo
        ahu = await device_manager.get_device("ahu-level3-01")
        if ahu:
            adapter = await device_manager.get_adapter("ahu-level3-01")
            if adapter and isinstance(adapter, MockDeviceAdapter):
                adapter.set_state("filter_pressure", 210)  # Above 200 Pa alarm threshold
                logger.info("Set AHU filter pressure above alarm threshold for demo")

        # Set office temperature outside comfort range
        vav = await device_manager.get_device("vav-office-301")
        if vav:
            adapter = await device_manager.get_adapter("vav-office-301")
            if adapter and isinstance(adapter, MockDeviceAdapter):
                adapter.set_state("room_temp", 29.5)  # Above 28°C max
                logger.info("Set office temperature above comfort range for demo")

    @staticmethod
    async def simulate_device_events(device_manager) -> None:
        """Simulate changing device values over time (for demo)."""
        devices = await device_manager.list_devices()

        for device in devices:
            adapter = await device_manager.get_adapter(device.id)
            if not adapter or not isinstance(adapter, MockDeviceAdapter):
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

        logger.debug("Simulated device value changes for demo")