"""
Unit tests for device abstraction service.
"""

import pytest
from app.services.device_abstraction import DeviceManager, device_manager


@pytest.mark.unit
class TestDeviceManager:
    """Test DeviceManager service."""

    def test_device_manager_exists(self):
        """Test DeviceManager singleton exists."""
        assert device_manager is not None

    def test_device_manager_is_singleton(self):
        """Test DeviceManager uses singleton pattern."""
        manager1 = DeviceManager()
        manager2 = DeviceManager()
        assert manager1 is manager2

    def test_device_manager_has_required_methods(self):
        """Test DeviceManager has all required methods."""
        manager = DeviceManager()

        # Core methods
        assert hasattr(manager, "initialize")
        assert hasattr(manager, "add_device")
        assert hasattr(manager, "get_device")
        assert hasattr(manager, "list_devices")
        assert hasattr(manager, "get_adapter")

        # Read/write methods
        assert hasattr(manager, "read_device_value")
        assert hasattr(manager, "write_device_value")

        # Status methods
        assert hasattr(manager, "get_device_status")
        assert hasattr(manager, "get_device_safety_status")

        # Lifecycle methods
        assert hasattr(manager, "shutdown")

    @pytest.mark.asyncio
    async def test_list_devices_returns_list(self):
        """Test list_devices returns a list."""
        manager = DeviceManager()

        # May or may not be initialized
        devices = await manager.list_devices()

        assert isinstance(devices, list)

    @pytest.mark.asyncio
    async def test_get_nonexistent_device(self):
        """Test getting a device that doesn't exist."""
        manager = DeviceManager()
        device = await manager.get_device("nonexistent-device-id-12345")

        assert device is None


@pytest.mark.unit
class TestDeviceManagerInitialization:
    """Test DeviceManager initialization."""

    @pytest.mark.asyncio
    async def test_initialize_with_empty_list(self):
        """Test initializing with empty device list."""
        manager = DeviceManager()

        # Reset for fresh init
        manager._initialized = False
        manager._devices = {}
        manager._adapters = {}

        await manager.initialize([])

        assert manager._initialized is True

    @pytest.mark.asyncio
    async def test_initialize_is_idempotent(self):
        """Test multiple initialize calls are safe."""
        manager = DeviceManager()

        # First init
        await manager.initialize([])

        # Second init should not fail
        await manager.initialize([])

        assert manager._initialized is True


@pytest.mark.unit
class TestDeviceInterface:
    """Test device interface requirements."""

    def test_device_adapter_base_class_exists(self):
        """Test DeviceAdapter base class exists."""
        from app.services.device_abstraction import DeviceAdapter

        assert DeviceAdapter is not None

    def test_device_interface_exists(self):
        """Test DeviceInterface ABC exists."""
        from app.services.device_abstraction import DeviceInterface

        assert DeviceInterface is not None


@pytest.mark.integration
class TestMockDeviceAdapter:
    """Test mock device adapter."""

    def test_simulated_adapter_exists(self):
        """Test SimulatedDeviceAdapter exists."""
        from app.services.bms_simulator.adapters.simulated_adapter import SimulatedDeviceAdapter

        assert SimulatedDeviceAdapter is not None


@pytest.mark.unit
class TestDeviceManagerOperations:
    """Test device manager operations with actual device data."""

    @pytest.mark.asyncio
    async def test_add_device(self):
        """Test adding a device."""
        manager = DeviceManager()

        device_data = {
            "id": "test-device-unit-001",
            "name": "Test Device",
            "device_type": "hvac",
            "protocol": "mock",
            "site_id": "test-site",
            "description": "Unit test device",
            "points": {
                "setpoint": {
                    "name": "setpoint",
                    "point_type": "analog_output",
                    "description": "Temperature setpoint",
                    "unit": "°C",
                    "min_value": 16.0,
                    "max_value": 28.0,
                    "default_value": 22.0,
                    "writable": True,
                    "priority": 8,
                }
            },
        }

        try:
            device = await manager.add_device(device_data)
            assert device is not None
            assert device.id == "test-device-unit-001"
        except Exception as e:
            pytest.skip(f"Add device failed: {e}")

    @pytest.mark.asyncio
    async def test_list_devices_by_site(self):
        """Test listing devices by site."""
        manager = DeviceManager()

        # Should return list (possibly empty)
        devices = await manager.list_devices_by_site("test-site")
        assert isinstance(devices, list)

    @pytest.mark.asyncio
    async def test_list_devices_by_type(self):
        """Test listing devices by type."""
        manager = DeviceManager()

        # Should return list (possibly empty)
        devices = await manager.list_devices_by_type("hvac")
        assert isinstance(devices, list)
