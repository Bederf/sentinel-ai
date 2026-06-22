"""KNX-backed BMS adapter for SIMBIOT.

Wraps the existing KNXClient (app.services.knx.knx_client) behind the
canonical SIMBIOT ``BmsAdapter`` contract so discovery, reads, and writes
can flow through one building-level boundary regardless of source type.

Group addresses are configured via ETS export (loaded into
BmsConnectionConfig.metadata["group_addresses"]). The adapter reuses
the existing KNXClient read/write path and preserves the emergency/fire
group write-block safety check from knx_adapter.py.
"""

from __future__ import annotations

import logging
from typing import Any

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

logger = logging.getLogger(__name__)

_EMERGENCY_PATTERNS = ("emergency", "fire", "evacuation", "alarm", "panic")


def _is_emergency_group(point_metadata: dict) -> bool:
    """Check if a group address description matches emergency/fire patterns."""
    desc = point_metadata.get("description", "").lower()
    return any(p in desc for p in _EMERGENCY_PATTERNS)


class KnxBmsAdapter(BmsAdapter):
    """Concrete BMS adapter that wraps the shared KNXClient."""

    def __init__(self) -> None:
        self._config: BmsConnectionConfig | None = None
        self._connected = False
        self._client: Any | None = None
        self._group_addresses: dict[str, dict[str, Any]] = {}

    @property
    def adapter_id(self) -> str:
        return "knx"

    @property
    def capabilities(self) -> BmsAdapterCapabilities:
        return BmsAdapterCapabilities(
            supports_device_discovery=False,  # KNX topology comes from ETS export
            supports_point_discovery=True,
            supports_reads=True,
            supports_writes=True,
            supports_subscriptions=False,
            supports_history=False,
        )

    async def connect(self, config: BmsConnectionConfig) -> BmsConnectionStatus:
        self._config = config
        host = config.host or "localhost"
        port = config.port or 3671

        self._group_addresses = config.metadata.get("group_addresses", {})

        try:
            from app.services.knx.knx_client import get_knx_client

            self._client = get_knx_client(host, port)
            connected = await self._client.connect()

            if connected:
                self._connected = True
                return BmsConnectionStatus(
                    connected=True,
                    site_id=config.site_id,
                    source_type=self.adapter_id,
                    status="connected",
                    message=f"KNX gateway connected at {host}:{port}",
                )
            return BmsConnectionStatus(
                connected=False,
                site_id=config.site_id,
                source_type=self.adapter_id,
                status="disconnected",
                message=f"KNX gateway connection refused: {host}:{port}",
            )
        except Exception as e:
            self._connected = False
            logger.error("KNX connect failed (%s): %s", host, e)
            return BmsConnectionStatus(
                connected=False,
                site_id=config.site_id,
                source_type=self.adapter_id,
                status="error",
                message=f"KNX connection failed: {e}",
            )

    async def disconnect(self) -> None:
        if self._client:
            await self._client.disconnect()
        self._connected = False
        self._client = None

    async def get_status(self) -> BmsConnectionStatus:
        site_id = self._config.site_id if self._config else "unknown"
        source_type = self._config.source_type if self._config else self.adapter_id

        if self._client is not None and self._connected:
            try:
                health = await self._client.gateway_health_check()
                status_str = health.get("status", "unknown")
                connected = status_str == "healthy"
                return BmsConnectionStatus(
                    connected=connected,
                    site_id=site_id,
                    source_type=source_type,
                    status="connected" if connected else "disconnected",
                    message=health.get("status", "KNX gateway ready") if connected else f"Gateway {status_str}",
                )
            except Exception as e:
                return BmsConnectionStatus(
                    connected=False,
                    site_id=site_id,
                    source_type=source_type,
                    status="error",
                    message=f"KNX status check failed: {e}",
                )

        return BmsConnectionStatus(
            connected=False,
            site_id=site_id,
            source_type=source_type,
            status="disconnected",
            message="KNX client not initialized",
        )

    async def discover_devices(self) -> list[BmsDeviceDescriptor]:
        # KNX has no bus-level device discovery — return single logical gateway
        return [
            BmsDeviceDescriptor(
                device_id=f"knx-gateway-{self._config.site_id if self._config else 'unknown'}",
                display_name="KNXnet/IP Gateway",
                protocol="knx",
                address=self._config.host if self._config else None,
            )
        ]

    async def discover_points(self, device_id: str) -> list[BmsPointDescriptor]:
        if not self._group_addresses:
            return []

        points = []
        for point_name, ga_meta in self._group_addresses.items():
            dpt = ga_meta.get("dpt", "9.001")
            write_addr = ga_meta.get("write_address")
            read_addr = ga_meta.get("read_address")
            writable = bool(write_addr) and not _is_emergency_group(ga_meta)

            points.append(
                BmsPointDescriptor(
                    point_id=point_name,
                    point_name=point_name,
                    point_type=dpt,
                    unit=ga_meta.get("unit"),
                    writable=writable,
                    metadata={
                        "read_address": read_addr,
                        "write_address": write_addr or read_addr,
                        "dpt": dpt,
                        "description": ga_meta.get("description", ""),
                    },
                )
            )
        return points

    async def read_point(self, device_id: str, point_id: str) -> BmsPointValue:
        self._ensure_connected()
        assert self._client is not None

        ga_meta = self._group_addresses.get(point_id)
        if not ga_meta:
            raise ValueError(f"Point not found: {device_id}.{point_id}")

        read_addr = ga_meta.get("read_address")
        if not read_addr:
            raise ValueError(f"Point {point_id} has no read_address in group_addresses metadata")

        dpt = ga_meta.get("dpt", "9.001")
        value = await self._client.read_group_address(read_addr, dpt)

        return BmsPointValue(
            device_id=device_id,
            point_id=point_id,
            value=value,
            unit=ga_meta.get("unit"),
            metadata={
                "read_address": read_addr,
                "dpt": dpt,
                "description": ga_meta.get("description", ""),
            },
        )

    async def write_point(self, request: BmsWriteRequest) -> bool:
        self._ensure_connected()
        assert self._client is not None

        ga_meta = self._group_addresses.get(request.point_id)
        if not ga_meta:
            logger.error("KNX write failed: point not found %s.%s", request.device_id, request.point_id)
            return False

        write_addr = ga_meta.get("write_address") or ga_meta.get("read_address")
        if not write_addr:
            logger.error("KNX write failed: no write_address for %s", request.point_id)
            return False

        # Safety: block writes to emergency/fire group addresses
        if _is_emergency_group(ga_meta):
            logger.error(
                "KNX write BLOCKED: emergency/fire group address (%s) is read-only",
                write_addr,
            )
            return False

        dpt = ga_meta.get("dpt", "9.001")
        return await self._client.write_group_address(write_addr, request.value, dpt, request.priority)

    def _ensure_connected(self) -> None:
        if not self._connected or not self._client:
            raise ConnectionError("KNX BMS adapter is not connected")
