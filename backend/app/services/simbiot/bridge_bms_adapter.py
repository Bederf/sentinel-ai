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

    def __init__(
        self,
        base_url: str = "",
        token: str = "",
        timeout_seconds: float = 10.0,
        write_enabled: bool = False,
    ) -> None:
        self._base_url = base_url.rstrip("/") if base_url else ""
        self._token = token
        self._timeout = timeout_seconds
        self._write_enabled = write_enabled
        self._site_id: str = ""
        self._connected: bool = False
        self.last_write_response: dict[str, Any] | None = None

    @staticmethod
    def _resolve_base_url(config: BmsConnectionConfig) -> str:
        host = config.host or ""
        port = config.port or 8080
        return f"http://{host}:{port}"

    @property
    def adapter_id(self) -> str:
        return "bridge"

    @property
    def capabilities(self) -> BmsAdapterCapabilities:
        return BmsAdapterCapabilities(
            supports_device_discovery=True,
            supports_point_discovery=True,
            supports_reads=True,
            supports_writes=self._write_enabled,
            supports_subscriptions=False,
            supports_history=False,
        )

    @property
    def _headers(self) -> dict[str, str]:
        if self._token:
            return {"Authorization": f"Bearer {self._token}"}
        return {}

    async def connect(self, config: BmsConnectionConfig) -> BmsConnectionStatus:
        self._site_id = config.site_id
        if not self._base_url:
            self._base_url = self._resolve_base_url(config)
        if not self._token:
            self._token = str(config.metadata.get("token", "")) if config.metadata else ""
        if not self._token:
            return BmsConnectionStatus(
                connected=False,
                site_id=config.site_id,
                source_type="bridge",
                status="error",
                message="Bridge API token is required — enter it in the Password/Token field",
            )
        try:
            async with httpx.AsyncClient(timeout=self._timeout) as client:
                resp = await client.get(
                    f"{self._base_url}/api/sites/{self._site_id}/telemetry",
                    headers=self._headers,
                )
            # 200/204 = data available. 404 = bridge is up, site exists but no telemetry yet.
            # Either way the bridge is reachable and authenticated.
            self._connected = resp.status_code in (200, 204, 404)
            status = "connected" if self._connected else "error"
            if self._connected:
                message = ""
            elif resp.status_code == 401:
                message = (
                    f"Bridge authentication failed for site {self._site_id} — check that your API token is correct"
                )
            else:
                message = f"Bridge returned HTTP {resp.status_code} — check the bridge URL and port"
        except httpx.ConnectTimeout:
            self._connected = False
            status = "error"
            message = (
                f"Cannot reach bridge at {self._base_url} — connection timed out. "
                f"Make sure port 8080 is the correct bridge HTTP API port "
                f"(not the BACnet UDP port 47808)"
            )
            logger.warning("[BRIDGE] connect timeout for %s at %s", self._site_id, self._base_url)
        except httpx.ConnectError:
            self._connected = False
            status = "error"
            message = (
                f"Cannot reach bridge at {self._base_url} — connection refused. "
                f"Verify the bridge IP and port (expected HTTP API on port 8080)"
            )
            logger.warning("[BRIDGE] connect refused for %s at %s", self._site_id, self._base_url)
        except Exception as exc:
            self._connected = False
            status = "error"
            message = f"Bridge connection error: {exc}"
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
        data: dict[str, Any] = {}
        try:
            async with httpx.AsyncClient(timeout=30.0) as client:
                last_error: Exception | None = None
                for endpoint in ("objects", "points"):
                    try:
                        resp = await client.get(
                            f"{self._base_url}/api/sites/{self._site_id}/{endpoint}",
                            headers=self._headers,
                            params={"limit": 500},
                        )
                        resp.raise_for_status()
                        data = resp.json()
                        break
                    except Exception as exc:
                        last_error = exc
                else:
                    raise last_error or RuntimeError("Bridge point discovery failed")
        except Exception as exc:
            logger.warning("[BRIDGE] discover_points failed: %s", exc)
            return []

        points: list[BmsPointDescriptor] = []
        raw_points = data.get("objects") or data.get("points") or []
        for obj in raw_points:
            point_id = obj.get("object_id") or obj.get("point_id") or obj.get("id") or ""
            point_name = obj.get("object_name") or obj.get("point_name") or obj.get("name") or point_id
            points.append(
                BmsPointDescriptor(
                    point_id=point_id,
                    point_name=point_name,
                    point_type=obj.get("point_type", "unknown"),
                    unit=obj.get("unit"),
                    writable=obj.get("point_type", "") in {"setpoint", "analog_value", "command"},
                    metadata={
                        "equipment_id": obj.get("equipment_id", ""),
                        "bacnet_object_type": obj.get("object_type"),
                        "bacnet_instance": obj.get("instance"),
                        "source_endpoint": "objects" if data.get("objects") else "points",
                    },
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
        """Write one point through the bridge when supervised/automatic mode enables writes."""
        self.last_write_response = None
        if not self._write_enabled:
            logger.warning(
                "[BRIDGE] write_point blocked because bridge writes are disabled (site=%s, point=%s)",
                self._site_id,
                request.point_id,
            )
            return False

        metadata = request.metadata or {}
        payload = {
            "object_id": str(request.point_id),
            "value": request.value,
            "priority": request.priority,
            "requested_by": request.user or "sentinel",
            "approval_id": str(metadata.get("correlation_id") or ""),
        }
        try:
            async with httpx.AsyncClient(timeout=self._timeout) as client:
                resp = await client.post(
                    f"{self._base_url}/api/sites/{self._site_id}/write",
                    headers=self._headers,
                    json=payload,
                )
                if resp.status_code >= 400:
                    logger.warning(
                        "[BRIDGE] write_point rejected for %s.%s: HTTP %s %s",
                        self._site_id,
                        request.point_id,
                        resp.status_code,
                        resp.text[:300],
                    )
                resp.raise_for_status()
                data = resp.json() if resp.content else {}
                self.last_write_response = data
        except Exception as exc:
            logger.warning("[BRIDGE] write_point failed for %s.%s: %s", self._site_id, request.point_id, exc)
            return False

        return bool(
            data.get("success", True) is not False
            and data.get("ok", True) is not False
            and data.get("accepted", True) is not False
        )


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
        write_enabled=(
            connection_config.get("supports_writes") is True and connection_config.get("write_enabled") is True
        ),
    )
