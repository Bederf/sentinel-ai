"""Bridge BMS Adapter — REST API proxy for lifecycle simulators.

The Shadow Bridge at http://10.99.0.1:8080 speaks HTTP REST and translates
requests into underlying BMS protocol (BACnet/DESIGO CC). This adapter
provides the SIMBIOT BmsAdapter contract over that REST interface.

Connection config (from site_adapter_config.connection_config):
    {
        "base_url": "http://10.99.0.1:8080",
        "token": "...",
        "poll_interval_seconds": 300
    }

The actual telemetry ETL (zones, trends, alarms) is performed by
ShadowModePollingService — not this class. This adapter handles:
  - Connection health checks
  - Device/point discovery (BACnet catalog)
  - Single-point reads (for health monitors and SIMBIOT wizards)

Bulk telemetry ingestion goes through MultiSitePollingCoordinator →
ShadowModePollingService.poll(), bypassing this adapter's read_point path.
"""

from __future__ import annotations

import logging
from typing import Any

import httpx

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

logger = logging.getLogger("sentinel.simbiot.bridge")


class BridgeBmsAdapter(BmsAdapter):
    """SIMBIOT adapter for the Shadow Bridge REST proxy."""

    def __init__(self, base_url: str, token: str, timeout_seconds: float = 10.0) -> None:
        self._base_url = base_url.rstrip("/")
        self._token = token
        self._timeout = timeout_seconds
        self._site_id: str = ""
        self._connected: bool = False

    @property
    def adapter_id(self) -> str:
        return "bridge"

    @property
    def capabilities(self) -> BmsAdapterCapabilities:
        return BmsAdapterCapabilities(
            supports_device_discovery=True,
            supports_point_discovery=True,
            supports_reads=True,
            supports_writes=False,
            supports_subscriptions=False,
            supports_history=False,
        )

    @property
    def _headers(self) -> dict[str, str]:
        return {"Authorization": f"Bearer {self._token}"}

    async def connect(self, config: BmsConnectionConfig) -> BmsConnectionStatus:
        self._site_id = config.site_id
        try:
            async with httpx.AsyncClient(timeout=self._timeout) as client:
                resp = await client.get(
                    f"{self._base_url}/api/sites/{self._site_id}/telemetry",
                    headers=self._headers,
                )
            self._connected = resp.status_code in (200, 204)
            status = "connected" if self._connected else "error"
            message = "" if self._connected else f"HTTP {resp.status_code}"
        except Exception as exc:
            self._connected = False
            status = "error"
            message = str(exc)
            logger.warning("[BRIDGE] connect failed for %s: %s", self._site_id, exc)

        return BmsConnectionStatus(
            connected=self._connected,
            site_id=config.site_id,
            source_type="bridge",
            status=status,
            message=message,
        )

    async def disconnect(self) -> None:
        self._connected = False

    async def get_status(self) -> BmsConnectionStatus:
        return BmsConnectionStatus(
            connected=self._connected,
            site_id=self._site_id,
            source_type="bridge",
            status="connected" if self._connected else "disconnected",
        )

    async def discover_devices(self) -> list[BmsDeviceDescriptor]:
        """Return the bridge itself as a single logical device."""
        return [
            BmsDeviceDescriptor(
                device_id=f"bridge-{self._site_id}",
                display_name=f"Shadow Bridge ({self._site_id})",
                protocol="bridge",
                address=self._base_url,
            )
        ]

    async def discover_points(self, device_id: str) -> list[BmsPointDescriptor]:
        """Fetch BACnet object catalog from bridge and convert to point descriptors."""
        try:
            async with httpx.AsyncClient(timeout=30.0) as client:
                resp = await client.get(
                    f"{self._base_url}/api/sites/{self._site_id}/objects",
                    headers=self._headers,
                    params={"limit": 500},
                )
                resp.raise_for_status()
                data = resp.json()
        except Exception as exc:
            logger.warning("[BRIDGE] discover_points failed: %s", exc)
            return []

        points: list[BmsPointDescriptor] = []
        for obj in data.get("objects", []):
            points.append(
                BmsPointDescriptor(
                    point_id=obj.get("object_id", ""),
                    point_name=obj.get("object_name", obj.get("object_id", "")),
                    point_type=obj.get("point_type", "unknown"),
                    unit=obj.get("unit"),
                    writable=obj.get("point_type", "") in {"setpoint", "analog_value", "command"},
                    metadata={"equipment_id": obj.get("equipment_id", "")},
                )
            )
        return points

    async def read_point(self, device_id: str, point_id: str) -> BmsPointValue:
        """Read one point from the bridge (single-point health monitor path).

        Bulk telemetry uses ShadowModePollingService.poll() instead.
        """
        try:
            async with httpx.AsyncClient(timeout=self._timeout) as client:
                resp = await client.get(
                    f"{self._base_url}/api/sites/{self._site_id}/points/{point_id}",
                    headers=self._headers,
                )
                resp.raise_for_status()
                data = resp.json()
        except Exception as exc:
            logger.warning("[BRIDGE] read_point %s failed: %s", point_id, exc)
            return BmsPointValue(
                device_id=device_id,
                point_id=point_id,
                value=None,
                quality="bad",
            )

        return BmsPointValue(
            device_id=device_id,
            point_id=point_id,
            value=data.get("value"),
            quality="good",
            timestamp=data.get("timestamp"),
            unit=data.get("unit"),
        )

    async def write_point(self, request: BmsWriteRequest) -> bool:
        """Bridge is read-only from SENTINEL's perspective."""
        logger.warning(
            "[BRIDGE] write_point called on read-only bridge adapter (site=%s, point=%s)",
            self._site_id,
            request.point_id,
        )
        return False


def bridge_adapter_from_connection_config(
    site_id: str,
    connection_config: dict[str, Any],
) -> BridgeBmsAdapter | None:
    """Instantiate a BridgeBmsAdapter from a site_adapter_config.connection_config dict.

    Returns None if required fields are missing.
    """
    base_url = connection_config.get("base_url", "")
    token = connection_config.get("token", "")
    if not base_url or not token:
        logger.error(
            "[BRIDGE] Cannot create adapter for %s — missing base_url or token in connection_config",
            site_id,
        )
        return None
    return BridgeBmsAdapter(
        base_url=base_url,
        token=token,
        timeout_seconds=connection_config.get("timeout_seconds", 10.0),
    )
