"""KNX/IP DeviceAdapter for SENTINEL.

Implements the DeviceAdapter abstract interface using KNXnet/IP tunnelling.
Group addresses are mapped to DevicePoints via device.metadata["group_addresses"].

Point metadata schema:
    {
        "read_address": "1/1/1",      # required: group address to read
        "write_address": "1/1/1",     # optional: separate write address
        "status_address": "1/1/2",    # optional: feedback/status address
        "dpt": "9.001",              # required: KNX data point type
        "description": "Zone 1 temperature",
        "unit": "°C"
    }
"""

from __future__ import annotations

import logging
from datetime import datetime
from typing import Any

from app.models.device import Device, DevicePoint, DeviceStatus, DeviceValue, PointType
from app.services.device_abstraction import DeviceAdapter
from app.services.knx.knx_client import KNXClient, get_knx_client

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Emergency / fire group address detection
# ---------------------------------------------------------------------------

_EMERGENCY_PATTERNS = ("emergency", "fire", "evacuation", "alarm", "panic")


def _is_emergency_group(point_metadata: dict) -> bool:
    desc = point_metadata.get("description", "").lower()
    return any(p in desc for p in _EMERGENCY_PATTERNS)


# ---------------------------------------------------------------------------
# KNX-specific safety rules
# ---------------------------------------------------------------------------

# Binary brightness: no restriction (KNX dimming has its own safety)
# Temperature: delegated to safety_engine (via validate_control)
# Emergency/fire addresses: READ ONLY, block all writes


class KNXAdapter(DeviceAdapter):
    """DeviceAdapter for KNX/IP devices.

    Each point maps a KNX group address to a SENTINEL DevicePoint.
    Communication uses KNXnet/IP UDP (port 3671) via xknx.
    """

    def __init__(self, device: Device):
        super().__init__(device)
        self._client: KNXClient | None = None
        self._gateway_host: str | None = None

    def _resolve_gateway(self) -> str:
        """Get gateway host from device metadata or raise."""
        host = self.device.metadata.get("gateway_host")
        if not host:
            raise ValueError(
                f"Device {self.device.id} has no gateway_host in metadata. "
                "KNX integration requires a KNXnet/IP gateway."
            )
        return host

    @property
    def client(self) -> KNXClient:
        if self._client is None or self._client.gateway_host != self._resolve_gateway():
            self._client = get_knx_client(self._resolve_gateway())
        return self._client

    # ------------------------------------------------------------------8
    # Protocol-specific implementations
    # ------------------------------------------------------------------

    async def _protocol_connect(self) -> bool:
        """Connect to the KNXnet/IP gateway."""
        try:
            gateway = self._resolve_gateway()
            self._client = get_knx_client(gateway)
            connected = await self._client.connect()

            if connected:
                self.device.status = DeviceStatus.ONLINE
                self.device.last_seen = datetime.utcnow().isoformat()
                logger.info("KNX adapter connected: device=%s gateway=%s", self.device.id, gateway)
            else:
                self.device.status = DeviceStatus.OFFLINE

            return connected

        except Exception as e:
            logger.error("KNX connect failed (device=%s): %s", self.device.id, e)
            self.device.status = DeviceStatus.OFFLINE
            return False

    async def _protocol_disconnect(self) -> None:
        """Disconnect from the KNX gateway."""
        if self._client:
            await self._client.disconnect()
        self._connected = False

    async def _protocol_read(self, point_name: str) -> DeviceValue:
        """Read a KNX group address value and return as DeviceValue."""
        point = self.device.get_point(point_name)
        if not point:
            raise ValueError(f"Point {point_name} not found on device {self.device.id}")

        ga_meta = point.metadata.get("group_addresses", {}).get(point_name, {})
        read_addr = ga_meta.get("read_address")
        if not read_addr:
            raise ValueError(
                f"Point {point_name} has no read_address in group_addresses metadata"
            )

        dpt = ga_meta.get("dpt", "9.001")
        value = await self.client.read_group_address(read_addr, dpt)

        return DeviceValue(
            point_name=point_name,
            value=value,
            unit=point.unit or ga_meta.get("unit", ""),
            quality="good",
            timestamp=datetime.utcnow().isoformat(),
        )

    async def _protocol_write(self, point_name: str, value: Any, priority: int) -> bool:
        """Write a value to a KNX group address with safety checks."""
        point = self.device.get_point(point_name)
        if not point:
            raise ValueError(f"Point {point_name} not found on device {self.device.id}")

        ga_meta = point.metadata.get("group_addresses", {}).get(point_name, {})
        write_addr = ga_meta.get("write_address") or ga_meta.get("read_address")
        if not write_addr:
            raise ValueError(
                f"Point {point_name} has no write_address or read_address in metadata"
            )

        # Safety: block writes to emergency/fire group addresses
        if _is_emergency_group(ga_meta):
            raise ValueError(
                f"Emergency/fire group address ({write_addr}) is read-only — write blocked"
            )

        dpt = ga_meta.get("dpt", "9.001")
        return await self.client.write_group_address(write_addr, value, dpt, priority)

    # ------------------------------------------------------------------
    # Point discovery (KNX topology is in ETS, not auto-discovered)
    # ------------------------------------------------------------------

    async def get_points(self) -> dict[str, DevicePoint]:
        """Return all KNX group addresses as DevicePoints."""
        return self.device.points

    async def scan_points(self) -> dict[str, DevicePoint]:
        """Return points from device metadata.

        KNX group addresses are configured in ETS, not auto-discovered
        from the bus (topology lives in the ETS project export).
        """
        return await self.get_points()

    # ------------------------------------------------------------------
    # Extended: gateway health
    # ------------------------------------------------------------------

    async def get_status(self) -> DeviceStatus:
        """Return device status: online if gateway responds."""
        if not self._connected:
            return DeviceStatus.OFFLINE

        health = await self.client.gateway_health_check()
        if health.get("status") == "healthy":
            self.device.status = DeviceStatus.ONLINE
        elif health.get("status") == "unreachable":
            self.device.status = DeviceStatus.OFFLINE
        else:
            self.device.status = DeviceStatus.FAULT

        return self.device.status
