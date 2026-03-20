"""BACnet-backed BMS adapter for SIMBIOT.

This adapter wraps the existing Niagara BACnet client behind the canonical
SIMBIOT ``BmsAdapter`` contract so discovery, reads, and writes can flow
through one building-level boundary regardless of source type.
"""

from __future__ import annotations

from app.services.niagara.bacnet_client import BACnetException, DiscoveredPoint, get_bacnet_client
from app.services.simbiot.bms_adapter import (
    BmsAdapter,
    BmsAdapterCapabilities,
    BmsConnectionConfig,
    BmsConnectionStatus,
    BmsDeviceDescriptor,
    BmsPointDescriptor,
    BmsPointValue,
    BmsWriteRequest,
)

DISCOVERABLE_OBJECT_TYPES = [
    "analogInput",
    "analogOutput",
    "analogValue",
    "binaryInput",
    "binaryOutput",
    "binaryValue",
]


class BacnetBmsAdapter(BmsAdapter):
    """Concrete BMS adapter that wraps the shared BACnet client."""

    def __init__(self) -> None:
        self._config: BmsConnectionConfig | None = None
        self._connected = False
        self._client = get_bacnet_client()

    @property
    def adapter_id(self) -> str:
        return "bacnet"

    @property
    def capabilities(self) -> BmsAdapterCapabilities:
        return BmsAdapterCapabilities(
            supports_device_discovery=True,
            supports_point_discovery=True,
            supports_reads=True,
            supports_writes=True,
            supports_subscriptions=False,
            supports_history=False,
        )

    async def connect(self, config: BmsConnectionConfig) -> BmsConnectionStatus:
        self._config = config
        if not self._client.is_running:
            await self._client.start()
        self._connected = self._client.is_running
        return await self.get_status()

    async def disconnect(self) -> None:
        self._connected = False

    async def get_status(self) -> BmsConnectionStatus:
        site_id = self._config.site_id if self._config else "unknown"
        source_type = self._config.source_type if self._config else self.adapter_id
        host = self._config.host if self._config else None
        status = "connected" if self._connected and self._client.is_running else "disconnected"
        message = "BACnet client ready"
        if status != "connected":
            if self._client._bac0_unavailable:
                message = "BAC0 library not installed"
            else:
                message = "BACnet client not connected"
        return BmsConnectionStatus(
            connected=status == "connected",
            site_id=site_id,
            source_type=source_type,
            status=status,
            message=message,
            metadata={"host": host} if host else {},
        )

    async def discover_devices(self) -> list[BmsDeviceDescriptor]:
        self._ensure_connected()
        devices = await self._client.discover_devices()
        return [
            BmsDeviceDescriptor(
                device_id=str(device.device_id),
                display_name=device.object_name or f"BACnet Device {device.device_id}",
                protocol="bacnet",
                address=device.ip_address,
                metadata={
                    "vendor_name": device.vendor_name,
                    "model_name": device.model_name,
                    "firmware_version": device.firmware_version,
                },
            )
            for device in devices
        ]

    async def discover_points(self, device_id: str) -> list[BmsPointDescriptor]:
        self._ensure_connected()
        bacnet_device_id = int(device_id)
        points = await self._client.read_point_list(
            bacnet_device_id,
            object_types=DISCOVERABLE_OBJECT_TYPES,
            use_cache=False,
        )
        return [await self._descriptor_from_point(bacnet_device_id, point) for point in points]

    async def read_point(self, device_id: str, point_id: str) -> BmsPointValue:
        self._ensure_connected()
        object_type, instance = self._parse_point_id(point_id)
        bacnet_device_id = int(device_id)
        value = await self._client.read_point(
            bacnet_device_id,
            object_type,
            instance,
            property_name="presentValue",
        )
        unit = await self._safe_read_property(bacnet_device_id, object_type, instance, "units")
        return BmsPointValue(
            device_id=device_id,
            point_id=point_id,
            value=value,
            unit=str(unit) if unit else None,
            metadata={
                "object_type": object_type,
                "instance": instance,
            },
        )

    async def write_point(self, request: BmsWriteRequest) -> bool:
        self._ensure_connected()
        object_type, instance = self._parse_point_id(request.point_id)
        return await self._client.write_point(
            device_id=int(request.device_id),
            object_type=object_type,
            instance=instance,
            value=request.value,
            priority=request.priority,
        )

    def _ensure_connected(self) -> None:
        if not self._connected or not self._client.is_running:
            raise ConnectionError("BACnet BMS adapter is not connected")

    def _parse_point_id(self, point_id: str) -> tuple[str, int]:
        try:
            object_type, instance = point_id.split(":", 1)
            return object_type, int(instance)
        except ValueError as exc:
            raise ValueError(f"Invalid BACnet point id '{point_id}'") from exc

    async def _descriptor_from_point(self, device_id: int, point: DiscoveredPoint) -> BmsPointDescriptor:
        point_name = await self._safe_read_property(device_id, point.object_type, point.instance, "objectName")
        description = await self._safe_read_property(device_id, point.object_type, point.instance, "description")
        units = await self._safe_read_property(device_id, point.object_type, point.instance, "units")
        return BmsPointDescriptor(
            point_id=f"{point.object_type}:{point.instance}",
            point_name=str(point_name) if point_name else f"{point.object_type}_{point.instance}",
            point_type=point.object_type,
            unit=str(units) if units else None,
            writable=point.writable,
            metadata={
                "object_type": point.object_type,
                "instance": point.instance,
                "description": str(description) if description else "",
            },
        )

    async def _safe_read_property(
        self,
        device_id: int,
        object_type: str,
        instance: int,
        property_name: str,
    ) -> str | int | float | bool | None:
        try:
            return await self._client.read_point(device_id, object_type, instance, property_name=property_name)
        except BACnetException:
            return None
