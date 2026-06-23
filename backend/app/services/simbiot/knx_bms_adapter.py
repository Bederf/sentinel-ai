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


def _hierarchy_from_metadata(metadata: dict[str, Any], *, default_source: str) -> dict[str, Any] | None:
    hierarchy = metadata.get("hierarchy")
    if isinstance(hierarchy, dict):
        return {
            "available": bool(hierarchy.get("nodes") or hierarchy.get("relationships")),
            "source": hierarchy.get("source") or default_source,
            "nodes": hierarchy.get("nodes") or [],
            "relationships": hierarchy.get("relationships") or [],
            "raw": hierarchy,
        }

    nodes = metadata.get("hierarchy_nodes") or metadata.get("nodes")
    relationships = metadata.get("hierarchy_relationships") or metadata.get("relationships")
    if nodes or relationships:
        return {
            "available": True,
            "source": metadata.get("hierarchy_source") or default_source,
            "nodes": nodes or [],
            "relationships": relationships or [],
            "raw": {"nodes": nodes or [], "relationships": relationships or []},
        }
    return None


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
            supports_hierarchy_discovery=True,
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

    async def discover_hierarchy(self) -> dict[str, Any]:
        """Return KNX hierarchy from ETS/group-address metadata.

        KNX group-address traffic does not describe building engineering
        relationships by itself. ETS exports or configured group metadata may
        include floor, zone, and equipment bindings; those are imported here.
        """
        metadata = self._config.metadata if self._config else {}
        configured = _hierarchy_from_metadata(metadata, default_source="knx_ets_export")
        if configured:
            return configured

        nodes: dict[str, dict[str, Any]] = {}
        relationships: list[dict[str, Any]] = []
        for point_name, ga_meta in self._group_addresses.items():
            equipment_id = ga_meta.get("equipment_id") or ga_meta.get("canonical_code")
            zone_id = ga_meta.get("zone_id") or ga_meta.get("zone_key")
            if equipment_id:
                nodes[str(equipment_id)] = {
                    "id": str(equipment_id),
                    "equipment_id": str(equipment_id),
                    "type": "equipment",
                    "name": str(equipment_id),
                }
            if zone_id:
                nodes[str(zone_id)] = {
                    "id": str(zone_id),
                    "zone_id": str(zone_id),
                    "type": "zone",
                    "name": ga_meta.get("zone_name") or str(zone_id),
                }
            if equipment_id and zone_id:
                relationships.append(
                    {
                        "parent": str(equipment_id),
                        "child": str(zone_id),
                        "relationship_type": ga_meta.get("relationship_type") or "controls",
                        "evidence_basis": f"KNX group address {point_name}",
                        "source": "knx_ets_export",
                    }
                )

        return {
            "available": bool(relationships),
            "source": "knx_ets_export",
            "nodes": list(nodes.values()),
            "relationships": relationships,
            "message": ""
            if relationships
            else "KNX hierarchy requires ETS metadata with equipment_id and zone_id bindings.",
        }

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
