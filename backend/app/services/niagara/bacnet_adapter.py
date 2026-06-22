"""Niagara BACnet/IP Device Adapter.

Integrates the NiagaraBACnetClient with SENTINEL's device abstraction layer.
Provides a protocol-specific DeviceAdapter implementation for BACnet/IP
devices controlled via Tridium Niagara JACE/Supervisor.
"""

import logging
from datetime import datetime
from typing import Any

from app.models.device import (
    Device,
    DevicePoint,
    DeviceStatus,
    DeviceValue,
    PointType,
)
from app.services.device_abstraction import DeviceAdapter
from app.services.niagara.bacnet_client import (
    BACnetException,
    BACnetReadError,
    BACnetTimeoutError,
    DiscoveredPoint,
    get_bacnet_client,
)

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# BACnet object type <-> SENTINEL PointType mapping
# ---------------------------------------------------------------------------

BACNET_TO_POINT_TYPE = {
    "analogInput": PointType.ANALOG_INPUT,
    "analogOutput": PointType.ANALOG_OUTPUT,
    "analogValue": PointType.ANALOG_VALUE,
    "binaryInput": PointType.BINARY_INPUT,
    "binaryOutput": PointType.BINARY_OUTPUT,
    "binaryValue": PointType.BINARY_VALUE,
    "multiStateInput": PointType.MULTISTATE_INPUT,
    "multiStateOutput": PointType.MULTISTATE_OUTPUT,
    "multiStateValue": PointType.MULTISTATE_VALUE,
}

POINT_TYPE_TO_BACNET = {v: k for k, v in BACNET_TO_POINT_TYPE.items()}


def _bacnet_type_writable(bacnet_type: str) -> bool:
    """Determine if a BACnet object type is writable."""
    return bacnet_type in (
        "analogOutput",
        "analogValue",
        "binaryOutput",
        "binaryValue",
        "multiStateOutput",
        "multiStateValue",
    )


def _discovered_point_to_device_point(dp: DiscoveredPoint) -> DevicePoint:
    """Convert a DiscoveredPoint from the BACnet client to a DevicePoint."""
    point_type = BACNET_TO_POINT_TYPE.get(dp.object_type, PointType.ANALOG_VALUE)

    return DevicePoint(
        name=dp.name or f"{dp.object_type}_{dp.instance}",
        point_type=point_type,
        description=dp.description,
        unit=dp.units,
        writable=dp.writable,
        default_value=dp.present_value,
        metadata={
            "bacnet_object_type": dp.object_type,
            "bacnet_instance": dp.instance,
        },
    )


class NiagaraBACnetAdapter(DeviceAdapter):
    """DeviceAdapter for Niagara BACnet/IP devices.

    Wraps the NiagaraBACnetClient to provide SENTINEL's standard
    device interface (connect, disconnect, read, write, scan).

    The adapter extracts the BACnet device_id from the Device's metadata:
        device.metadata["bacnet_device_id"] = 1234

    Each point must include bacnet_object_type and bacnet_instance
    in its metadata for read/write to resolve the correct BACnet address.

    Usage:
        device = create_device_from_dict({
            "id": "S002-AHU-L1-001",
            "protocol": "bacnet",
            "metadata": {"bacnet_device_id": 1234},
            ...
        })
        adapter = NiagaraBACnetAdapter(device)
        await adapter.connect()
        value = await adapter.read_value("chw_supply_temp")
    """

    def __init__(self, device: Device):
        super().__init__(device)
        self._bacnet_device_id: int | None = None
        self._client = get_bacnet_client()
        self._last_status_message: str | None = None

    @property
    def bacnet_device_id(self) -> int:
        """Get the BACnet device instance number for this device."""
        if self._bacnet_device_id is not None:
            return self._bacnet_device_id

        # Extract from device metadata
        device_id = self.device.metadata.get("bacnet_device_id")
        if device_id is None:
            raise BACnetException(f"Device {self.device.id} has no bacnet_device_id in metadata")
        self._bacnet_device_id = int(device_id)
        return self._bacnet_device_id

    # ------------------------------------------------------------------
    # Protocol-specific implementations
    # ------------------------------------------------------------------

    async def _protocol_connect(self) -> bool:
        """Start the BACnet client and verify device is reachable.

        Uses the shared singleton BACnet client. If the client
        is not yet started, it is started here.
        """
        try:
            if self.device.metadata.get("bacnet_device_id") is None:
                self._last_status_message = "skipped: missing bacnet_device_id"
                logger.info(
                    "BACnet device %s has no bacnet_device_id metadata; leaving adapter disconnected",
                    self.device.id,
                )
                return False

            if not self._client.is_running:
                if self._client._bac0_unavailable:
                    return False
                await self._client.start()

            # Verify device is reachable by reading its objectName
            try:
                await self._client.read_point(
                    self.bacnet_device_id,
                    "device",
                    self.bacnet_device_id,
                    property_name="objectName",
                )
                logger.info(
                    "Connected to BACnet device %s (instance %d)",
                    self.device.id,
                    self.bacnet_device_id,
                )
                self._last_status_message = None
                return True
            except BACnetTimeoutError:
                self._last_status_message = "BACnet timeout while reading device objectName"
                logger.warning(
                    "BACnet device %s (instance %d) not responding",
                    self.device.id,
                    self.bacnet_device_id,
                )
                return False
            except BACnetException as e:
                self._last_status_message = str(e)
                logger.warning(
                    "Could not verify BACnet device %s: %s",
                    self.device.id,
                    e,
                )
                # Still consider connected - device may just not support objectName read
                return True

        except BACnetException as e:
            self._last_status_message = str(e)
            # Only log if this is NOT the expected missing-library case
            # (the client itself logs the missing-library message once)
            if not self._client._bac0_unavailable:
                logger.error("Failed to start BACnet client: %s", e)
            return False

    async def _protocol_disconnect(self) -> None:
        """Disconnect from this BACnet device.

        The shared BACnet client is NOT stopped here because other
        adapters may be using it. It is stopped at DeviceManager shutdown.
        """
        if self.device.metadata.get("bacnet_device_id") is None:
            self._last_status_message = "skipped: missing bacnet_device_id"
            logger.debug(
                "BACnet device %s has no bacnet_device_id metadata; no protocol disconnect needed", self.device.id
            )
            return

        # Cancel any COV subscriptions for this device
        for sub in list(self._client.list_subscriptions()):
            if sub.device_id == self.bacnet_device_id:
                await self._client.cancel_subscription(sub.subscription_id)

        logger.info(
            "Disconnected adapter for BACnet device %s (instance %d)",
            self.device.id,
            self.bacnet_device_id,
        )

    async def _protocol_read(self, point_name: str) -> DeviceValue:
        """Read a point value via BACnet/IP."""
        point = self.device.get_point(point_name)
        if not point:
            raise ValueError(f"Point {point_name} not found on device {self.device.id}")

        # Get BACnet addressing from point metadata
        bacnet_type = point.metadata.get("bacnet_object_type")
        bacnet_instance = point.metadata.get("bacnet_instance")

        if bacnet_type is None or bacnet_instance is None:
            raise ValueError(f"Point {point_name} missing BACnet metadata (bacnet_object_type, bacnet_instance)")

        try:
            value = await self._client.read_point(
                device_id=self.bacnet_device_id,
                object_type=bacnet_type,
                instance=int(bacnet_instance),
            )

            return DeviceValue(
                point_name=point_name,
                value=value,
                unit=point.unit,
                quality="good",
                timestamp=datetime.utcnow().isoformat(),
            )

        except BACnetTimeoutError:
            return DeviceValue(
                point_name=point_name,
                value=None,
                unit=point.unit,
                quality="uncertain",
                timestamp=datetime.utcnow().isoformat(),
                metadata={"error": "timeout"},
            )
        except BACnetReadError as e:
            return DeviceValue(
                point_name=point_name,
                value=None,
                unit=point.unit,
                quality="bad",
                timestamp=datetime.utcnow().isoformat(),
                metadata={"error": str(e)},
            )

    async def _protocol_write(self, point_name: str, value: Any, priority: int) -> bool:
        """Write a value to a BACnet point with priority array support."""
        point = self.device.get_point(point_name)
        if not point:
            raise ValueError(f"Point {point_name} not found on device {self.device.id}")

        bacnet_type = point.metadata.get("bacnet_object_type")
        bacnet_instance = point.metadata.get("bacnet_instance")

        if bacnet_type is None or bacnet_instance is None:
            raise ValueError(f"Point {point_name} missing BACnet metadata (bacnet_object_type, bacnet_instance)")

        return await self._client.write_point(
            device_id=self.bacnet_device_id,
            object_type=bacnet_type,
            instance=int(bacnet_instance),
            value=value,
            priority=priority,
        )

    # ------------------------------------------------------------------
    # Extended operations
    # ------------------------------------------------------------------

    async def scan_points(self) -> dict[str, DevicePoint]:
        """Discover BACnet points on this device and return as DevicePoints.

        Reads the device's objectList to enumerate all available
        BACnet objects and converts them to SENTINEL DevicePoints.
        """
        try:
            discovered = await self._client.read_point_list(
                device_id=self.bacnet_device_id,
                use_cache=False,  # Force fresh scan
            )

            points: dict[str, DevicePoint] = {}
            for dp in discovered:
                device_point = _discovered_point_to_device_point(dp)
                points[device_point.name] = device_point

            logger.info(
                "Scanned %d points on BACnet device %s (instance %d)",
                len(points),
                self.device.id,
                self.bacnet_device_id,
            )
            return points

        except BACnetException as e:
            logger.error("Point scan failed for device %s: %s", self.device.id, e)
            # Return existing points on failure
            return self.device.points

    async def get_status(self) -> DeviceStatus:
        """Get device status by attempting a read.

        Tries to read the device's objectName property. If successful,
        the device is ONLINE. If it times out, it is OFFLINE.
        """
        try:
            if self.device.metadata.get("bacnet_device_id") is None:
                self._last_status_message = "skipped: missing bacnet_device_id"
                self.device.status = DeviceStatus.OFFLINE
                return self.device.status

            await self._client.read_point(
                self.bacnet_device_id,
                "device",
                self.bacnet_device_id,
                property_name="objectName",
            )
            self.device.status = DeviceStatus.ONLINE
            self._last_status_message = None
        except BACnetTimeoutError:
            self.device.status = DeviceStatus.OFFLINE
            self._last_status_message = "BACnet timeout while reading device objectName"
        except BACnetException as e:
            self.device.status = DeviceStatus.FAULT
            self._last_status_message = str(e)

        return self.device.status
