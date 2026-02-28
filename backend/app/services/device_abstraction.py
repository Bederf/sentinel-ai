"""Device Abstraction Service.

Protocol-agnostic interface for building automation devices.
Provides a clean abstraction layer over different protocols (BACnet, Modbus, site002, etc.)
with consistent API for device discovery, reading, and writing.

The simulator adapter (SimulatedDeviceAdapter) is loaded lazily so that the
bms_simulator package can be removed without breaking SENTINEL core.
"""

import logging
from abc import ABC, abstractmethod
from typing import Dict, Any, Optional, List
from datetime import datetime

from app.models.device import Device, DeviceValue, DeviceStatus, DevicePoint, create_device_from_dict
from app.services.safety_interlocks import safety_engine
from app.services.audit_logger import AuditLogger
from app.models.audit_log import AuditResultType

logger = logging.getLogger(__name__)


class DeviceInterface(ABC):
    """Protocol-agnostic device interface.

    All device implementations (BACnet, Modbus, simulated, etc.) must implement
    this interface to ensure consistent behavior across protocols.
    """

    @abstractmethod
    async def connect(self) -> bool:
        """Connect to the device."""
        pass

    @abstractmethod
    async def disconnect(self) -> None:
        """Disconnect from the device."""
        pass

    @abstractmethod
    async def read_value(self, point_name: str) -> DeviceValue:
        """Read a value from a device point."""
        pass

    @abstractmethod
    async def write_value(self, point_name: str, value: Any, priority: int = 8) -> bool:
        """Write a value to a device point."""
        pass

    async def validate_control(self, point_name: str, value: Any) -> Dict[str, Any]:
        """
        Validate a control action against safety rules.

        Default implementation uses the safety engine.
        Can be overridden by specific adapters if needed.
        """
        # Initialize safety engine if not already done
        if not safety_engine._initialized:
            await safety_engine.initialize()

        # Get device for validation - subclasses should provide this
        device = getattr(self, "device", None)
        if device:
            return await safety_engine.validate_control(device, point_name, value)

        # Fallback if no device available
        return {
            "allowed": True,
            "reasons": [],
            "warnings": [],
            "validation_details": {"status": "no_device", "message": "Safety validation skipped - no device context"},
        }

    @abstractmethod
    async def get_status(self) -> DeviceStatus:
        """Get device operational status."""
        pass

    @abstractmethod
    async def get_points(self) -> Dict[str, DevicePoint]:
        """Get all available points on the device."""
        pass

    @abstractmethod
    async def scan_points(self) -> Dict[str, DevicePoint]:
        """Scan device for available points (dynamic discovery)."""
        pass


class DeviceAdapter(ABC):
    """Base class for protocol-specific device adapters.

    Adapters handle the protocol-specific communication while
    presenting a consistent DeviceInterface.
    """

    def __init__(self, device: Device):
        self.device = device
        self._connected = False
        self.audit_logger = AuditLogger()

    @abstractmethod
    async def _protocol_connect(self) -> bool:
        """Protocol-specific connection implementation."""
        pass

    @abstractmethod
    async def _protocol_disconnect(self) -> None:
        """Protocol-specific disconnection implementation."""
        pass

    @abstractmethod
    async def _protocol_read(self, point_name: str) -> DeviceValue:
        """Protocol-specific read implementation."""
        pass

    @abstractmethod
    async def _protocol_write(self, point_name: str, value: Any, priority: int) -> bool:
        """Protocol-specific write implementation."""
        pass

    async def connect(self) -> bool:
        """Connect to device with error handling."""
        try:
            self._connected = await self._protocol_connect()
            if self._connected:
                logger.info(f"Connected to device {self.device.id}")
                self.device.status = DeviceStatus.ONLINE
                self.device.last_seen = datetime.now().isoformat()
            return self._connected
        except Exception as e:
            logger.error(f"Failed to connect to device {self.device.id}: {e}")
            self.device.status = DeviceStatus.OFFLINE
            return False

    async def disconnect(self) -> None:
        """Disconnect from device with error handling."""
        try:
            await self._protocol_disconnect()
            self._connected = False
            logger.info(f"Disconnected from device {self.device.id}")
        except Exception as e:
            logger.error(f"Error disconnecting from device {self.device.id}: {e}")
        finally:
            self._connected = False

    async def validate_control(self, point_name: str, value: Any) -> Dict[str, Any]:
        """
        Validate a control action against safety rules.

        Uses the safety engine for validation.
        """
        # Initialize safety engine if not already done
        if not safety_engine._initialized:
            await safety_engine.initialize()

        # Use device from adapter
        return await safety_engine.validate_control(self.device, point_name, value)

    async def read_value(self, point_name: str) -> DeviceValue:
        """Read value with validation and error handling."""
        if not self._connected:
            raise ConnectionError(f"Device {self.device.id} is not connected")

        point = self.device.get_point(point_name)
        if not point:
            raise ValueError(f"Point {point_name} not found on device {self.device.id}")

        try:
            value = await self._protocol_read(point_name)
            logger.debug(f"Read {point_name} from device {self.device.id}: {value.value}")
            return value
        except Exception as e:
            logger.error(f"Failed to read {point_name} from device {self.device.id}: {e}")
            raise

    async def write_value(self, point_name: str, value: Any, priority: int = 8, user: str = "system") -> bool:
        """Write value with validation, safety checks, and audit logging."""
        if not self._connected:
            raise ConnectionError(f"Device {self.device.id} is not connected")

        point = self.device.get_point(point_name)
        if not point:
            raise ValueError(f"Point {point_name} not found on device {self.device.id}")

        if not point.writable:
            raise ValueError(f"Point {point_name} is not writable")

        if not point.validate_value(value):
            raise ValueError(f"Value {value} is invalid for point {point_name}")

        # Get current value for audit logging
        old_value = None
        try:
            current_value = await self.read_value(point_name)
            old_value = current_value.value
        except Exception as e:
            logger.warning(f"Could not read current value for audit logging: {e}")

        # Check safety rules before writing
        safety_result = await self.validate_control(point_name, value)
        if not safety_result["allowed"]:
            reasons = safety_result.get("reasons", [])
            if reasons:
                error_msg = f"Safety violation: {', '.join(reasons)}"
            else:
                error_msg = "Safety validation failed"

            # Log blocked action to audit
            self.audit_logger.log_control_action(
                device_id=self.device.id,
                point_name=point_name,
                user=user,
                old_value=old_value,
                new_value=value,
                result=AuditResultType.BLOCKED,
                safety_validation=safety_result,
                error_message=error_msg,
                metadata={"priority": priority},
            )

            raise ValueError(error_msg)

        # Log safety warnings if any
        warnings = safety_result.get("warnings", [])
        if warnings:
            logger.warning(
                f"Safety warnings for {point_name} = {value} on device {self.device.id}: {', '.join(warnings)}"
            )

        try:
            success = await self._protocol_write(point_name, value, priority)

            # Log to audit system
            if success:
                self.audit_logger.log_control_action(
                    device_id=self.device.id,
                    point_name=point_name,
                    user=user,
                    old_value=old_value,
                    new_value=value,
                    result=AuditResultType.SUCCESS,
                    safety_validation=safety_result,
                    metadata={"priority": priority},
                )
                logger.info(f"Wrote {point_name} = {value} to device {self.device.id} (priority: {priority})")
            else:
                self.audit_logger.log_control_action(
                    device_id=self.device.id,
                    point_name=point_name,
                    user=user,
                    old_value=old_value,
                    new_value=value,
                    result=AuditResultType.FAILED,
                    safety_validation=safety_result,
                    error_message="Protocol write failed",
                    metadata={"priority": priority},
                )
                logger.warning(f"Failed to write {point_name} = {value} to device {self.device.id}")

            return success
        except Exception as e:
            # Log exception to audit
            self.audit_logger.log_control_action(
                device_id=self.device.id,
                point_name=point_name,
                user=user,
                old_value=old_value,
                new_value=value,
                result=AuditResultType.FAILED,
                safety_validation=safety_result,
                error_message=str(e),
                metadata={"priority": priority},
            )
            logger.error(f"Error writing {point_name} = {value} to device {self.device.id}: {e}")
            raise

    async def get_status(self) -> DeviceStatus:
        """Get device status."""
        return self.device.status

    async def get_points(self) -> Dict[str, DevicePoint]:
        """Get device points."""
        return self.device.points

    async def scan_points(self) -> Dict[str, DevicePoint]:
        """Scan for points (default implementation returns existing points)."""
        return await self.get_points()


class DeviceManager:
    """Singleton manager for device discovery and lifecycle management."""

    _instance = None
    _devices: Dict[str, Device] = {}
    _adapters: Dict[str, DeviceAdapter] = {}
    _initialized = False

    def __new__(cls):
        if cls._instance is None:
            cls._instance = super(DeviceManager, cls).__new__(cls)
        return cls._instance

    async def initialize(self, devices_data: Optional[List[Dict[str, Any]]] = None) -> None:
        """Initialize device manager with optional initial devices."""
        if self._initialized:
            return

        logger.info("Initializing DeviceManager")

        if devices_data:
            for device_data in devices_data:
                await self.add_device(device_data)

        self._initialized = True
        logger.info(f"DeviceManager initialized with {len(self._devices)} devices")

    async def add_device(self, device_data: Dict[str, Any]) -> Device:
        """Add a device to the manager."""
        device = create_device_from_dict(device_data)

        if device.id in self._devices:
            logger.warning(f"Device {device.id} already exists, updating")
            # Update existing device
            self._devices[device.id] = device
        else:
            self._devices[device.id] = device
            logger.info(f"Added device {device.id} ({device.name})")

        # Create appropriate adapter based on protocol
        await self._create_adapter(device)

        return device

    async def _create_adapter(self, device: Device) -> None:
        """Create appropriate adapter for device protocol.

        SimulatedDeviceAdapter is imported lazily so the bms_simulator package
        can be removed without impacting SENTINEL core.
        """
        from app.services.niagara.bacnet_adapter import NiagaraBACnetAdapter
        from app.config.settings import settings

        # Lazy-load SimulatedDeviceAdapter (removable with bms_simulator/)
        SimulatedDeviceAdapter = None
        try:
            from app.services.bms_simulator.adapters.simulated_adapter import (
                SimulatedDeviceAdapter as _SimAdapter,
            )

            SimulatedDeviceAdapter = _SimAdapter
        except ImportError:
            pass

        # Map protocol to adapter class
        adapter_map: dict = {
            "bacnet": NiagaraBACnetAdapter,
            # Future: "modbus": ModbusDeviceAdapter,
        }
        if SimulatedDeviceAdapter is not None:
            adapter_map["mock"] = SimulatedDeviceAdapter
            adapter_map["site002"] = SimulatedDeviceAdapter

        adapter_class = adapter_map.get(device.protocol.value)
        if not adapter_class:
            if SimulatedDeviceAdapter is not None:
                logger.warning(f"No adapter for protocol {device.protocol.value}, using simulated adapter")
                adapter_class = SimulatedDeviceAdapter
            else:
                logger.warning(
                    "No adapter for protocol %s and simulator unavailable — skipping device %s",
                    device.protocol.value,
                    device.id,
                )
                return
        elif adapter_class is NiagaraBACnetAdapter and settings.site002_source_enabled:
            if SimulatedDeviceAdapter is not None:
                logger.info(
                    "Site-002 source enabled: using simulated adapter for BACnet device %s",
                    device.id,
                )
                adapter_class = SimulatedDeviceAdapter
            else:
                logger.warning(
                    "Site-002 source enabled but simulator unavailable — skipping BACnet device %s",
                    device.id,
                )
                return

        adapter = adapter_class(device)
        self._adapters[device.id] = adapter

        # Try to connect
        try:
            await adapter.connect()
        except Exception as e:
            logger.error(f"Failed to connect device {device.id}: {e}")

    async def get_device(self, device_id: str) -> Optional[Device]:
        """Get device by ID."""
        return self._devices.get(device_id)

    async def get_adapter(self, device_id: str) -> Optional[DeviceAdapter]:
        """Get device adapter by ID."""
        return self._adapters.get(device_id)

    async def list_devices(self) -> List[Device]:
        """List all devices."""
        return list(self._devices.values())

    async def list_devices_by_site(self, site_id: str) -> List[Device]:
        """List devices at a specific site."""
        return [device for device in self._devices.values() if device.site_id == site_id]

    async def list_devices_by_type(self, device_type: str) -> List[Device]:
        """List devices of a specific type."""
        return [device for device in self._devices.values() if device.device_type.value == device_type]

    async def read_device_value(self, device_id: str, point_name: str) -> DeviceValue:
        """Read value from a device point."""
        adapter = await self.get_adapter(device_id)
        if not adapter:
            raise ValueError(f"Device {device_id} not found or not connected")

        return await adapter.read_value(point_name)

    async def write_device_value(
        self, device_id: str, point_name: str, value: Any, priority: int = 8, user: str = "system"
    ) -> bool:
        """Write value to a device point."""
        adapter = await self.get_adapter(device_id)
        if not adapter:
            raise ValueError(f"Device {device_id} not found or not connected")

        return await adapter.write_value(point_name, value, priority, user)

    async def get_device_status(self, device_id: str) -> DeviceStatus:
        """Get device status."""
        adapter = await self.get_adapter(device_id)
        if not adapter:
            raise ValueError(f"Device {device_id} not found")

        return await adapter.get_status()

    async def get_device_safety_status(self, device_id: str) -> Dict[str, Any]:
        """Get device safety status using safety engine."""
        device = await self.get_device(device_id)
        if not device:
            raise ValueError(f"Device {device_id} not found")

        # Initialize safety engine if not already done
        if not safety_engine._initialized:
            await safety_engine.initialize()

        # Get safety status from engine
        return await safety_engine.get_device_safety_status(device)

    async def scan_device_points(self, device_id: str) -> Dict[str, DevicePoint]:
        """Scan device for available points."""
        adapter = await self.get_adapter(device_id)
        if not adapter:
            raise ValueError(f"Device {device_id} not found or not connected")

        points = await adapter.scan_points()

        # Update device points if scan found new ones
        device = await self.get_device(device_id)
        if device:
            device.points.update(points)
            device.updated_at = datetime.now().isoformat()

        return points

    async def connect_device(self, device_id: str) -> bool:
        """Connect to a device."""
        adapter = await self.get_adapter(device_id)
        if not adapter:
            raise ValueError(f"Device {device_id} not found")

        return await adapter.connect()

    async def disconnect_device(self, device_id: str) -> None:
        """Disconnect from a device."""
        adapter = await self.get_adapter(device_id)
        if not adapter:
            raise ValueError(f"Device {device_id} not found")

        await adapter.disconnect()

    async def shutdown(self) -> None:
        """Shutdown all device connections."""
        logger.info("Shutting down DeviceManager")
        for device_id, adapter in self._adapters.items():
            try:
                await adapter.disconnect()
                logger.debug(f"Disconnected device {device_id}")
            except Exception as e:
                logger.error(f"Error disconnecting device {device_id}: {e}")

        self._adapters.clear()
        self._initialized = False
        logger.info("DeviceManager shutdown complete")


# Global instance for easy access
device_manager = DeviceManager()
