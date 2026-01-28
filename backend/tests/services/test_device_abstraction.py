"""
Unit tests for device abstraction service.
"""

import pytest
from app.services.device_abstraction import DeviceManager
from tests.factories import DeviceFactory


@pytest.mark.unit
class TestDeviceManager:
    """Test DeviceManager service."""

    @pytest.mark.asyncio
    async def test_initialize_with_devices(self, mock_devices_data):
        """Test initializing DeviceManager with device data."""
        manager = DeviceManager()
        await manager.initialize(mock_devices_data)
        
        assert manager._initialized is True
        assert len(manager.devices) > 0

    @pytest.mark.asyncio
    async def test_discover_devices(self, device_manager):
        """Test device discovery."""
        devices = await device_manager.discover_devices()
        
        assert isinstance(devices, list)
        assert len(devices) > 0

    @pytest.mark.asyncio
    async def test_get_device_by_id(self, device_manager):
        """Test getting a device by ID."""
        devices = await device_manager.discover_devices()
        if devices:
            device_id = devices[0]["id"]
            device = await device_manager.get_device(device_id)
            
            assert device is not None
            assert device["id"] == device_id

    @pytest.mark.asyncio
    async def test_read_device_point(self, device_manager):
        """Test reading a value from a device point."""
        devices = await device_manager.discover_devices()
        if devices:
            device_id = devices[0]["id"]
            device = await device_manager.get_device(device_id)
            
            if device and "points" in device:
                point_name = list(device["points"].keys())[0]
                value = await device_manager.read_point(device_id, point_name)
                
                assert value is not None

    @pytest.mark.asyncio
    async def test_write_device_point(self, device_manager):
        """Test writing a value to a device point."""
        devices = await device_manager.discover_devices()
        if devices:
            device_id = devices[0]["id"]
            device = await device_manager.get_device(device_id)
            
            if device and "points" in device:
                # Find a writable point
                writable_point = None
                for point_name, point_data in device["points"].items():
                    if point_data.get("writable", False):
                        writable_point = point_name
                        break
                
                if writable_point:
                    new_value = 22.0
                    result = await device_manager.write_point(
                        device_id, writable_point, new_value
                    )
                    
                    assert result is True

    @pytest.mark.asyncio
    async def test_get_device_status(self, device_manager):
        """Test getting device operational status."""
        devices = await device_manager.discover_devices()
        if devices:
            device_id = devices[0]["id"]
            status = await device_manager.get_device_status(device_id)
            
            assert status is not None
            assert "status" in status or "online" in str(status).lower()

    @pytest.mark.asyncio
    async def test_get_nonexistent_device(self, device_manager):
        """Test getting a device that doesn't exist."""
        device = await device_manager.get_device("nonexistent-device-id")
        
        assert device is None

    @pytest.mark.asyncio
    async def test_read_nonexistent_point(self, device_manager):
        """Test reading from a point that doesn't exist."""
        devices = await device_manager.discover_devices()
        if devices:
            device_id = devices[0]["id"]
            value = await device_manager.read_point(device_id, "nonexistent_point")
            
            assert value is None
