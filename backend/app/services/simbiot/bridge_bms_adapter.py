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
            supports_hierarchy_discovery=True,
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

    async def discover_hierarchy(self) -> dict[str, Any]:
        """Fetch native BMS hierarchy proxied by the bridge, when available.

        Expected bridge endpoint:
            GET /api/sites/{site_id}/hierarchy

        The bridge may expose Desigo plant/location trees, Niagara station
        trees, or BACnet Structured Views behind this normalized endpoint.
        Older flat-point bridges do not have it; that is reported as
        unavailable so onboarding can fall back to naming inference/manual
        review without failing activation.
        """
        if not self._site_id:
            return {
                "available": False,
                "source": "bridge",
                "nodes": [],
                "relationships": [],
                "message": "Bridge adapter is not connected to a site",
            }

        try:
            async with httpx.AsyncClient(timeout=30.0) as client:
                resp = await client.get(
                    f"{self._base_url}/api/sites/{self._site_id}/hierarchy",
                    headers=self._headers,
                )
                if resp.status_code == 404:
                    return {
                        "available": False,
                        "source": "bridge",
                        "nodes": [],
                        "relationships": [],
                        "message": "Bridge hierarchy endpoint is not available",
                    }
                resp.raise_for_status()
                data = resp.json() if resp.content else {}
        except Exception as exc:
            logger.warning("[BRIDGE] discover_hierarchy failed for %s: %s", self._site_id, exc)
            return {
                "available": False,
                "source": "bridge",
                "nodes": [],
                "relationships": [],
                "message": str(exc),
            }

        nodes = data.get("nodes") or data.get("hierarchy", {}).get("nodes") or []
        relationships = data.get("relationships") or data.get("hierarchy", {}).get("relationships") or []
        if not nodes and not relationships:
            flattened = _flatten_bridge_hierarchy(data)
            nodes = flattened["nodes"]
            relationships = flattened["relationships"]

        return {
            "available": bool(nodes or relationships),
            "source": _bridge_hierarchy_source(data),
            "adapter": "bridge",
            "nodes": nodes,
            "relationships": relationships,
            "raw": data,
        }

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
    from app.services.shadow_mode_polling import resolve_site_bridge_token

    token = resolve_site_bridge_token(site_id, connection_config)
    if not base_url or not token:
        logger.error(
            "[BRIDGE] Cannot create adapter for %s — missing base_url or bridge token",
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


def _bridge_hierarchy_source(data: dict[str, Any]) -> str:
    raw = str(data.get("source") or data.get("source_type") or data.get("hierarchy_source") or "").lower()
    system = str(data.get("bms_system") or data.get("bms_vendor") or "").lower()
    if "desigo" in raw or "desigo" in system:
        return "desigo_plant_tree"
    if "niagara" in raw or "jace" in raw or "niagara" in system or "jace" in system:
        return "niagara_station_tree"
    if "bacnet" in raw and "structured" in raw:
        return "bacnet_structured_view"
    return "bridge_hierarchy"


def _flatten_bridge_hierarchy(data: dict[str, Any]) -> dict[str, list[dict[str, Any]]]:
    nodes_by_id: dict[str, dict[str, Any]] = {}
    relationships: dict[tuple[str, str, str], dict[str, Any]] = {}
    roots = [
        ("plant_tree", data.get("plant_tree")),
        ("station_tree", data.get("station_tree")),
        ("location_tree", data.get("location_tree")),
    ]
    for root_name, root in roots:
        if isinstance(root, dict):
            source = _source_for_tree(root_name, data)
            _walk_bridge_node(
                root,
                tree_name=root_name,
                source=source,
                path=[],
                nodes_by_id=nodes_by_id,
                relationships=relationships,
                nearest_equipment_id=None,
            )
    return {"nodes": list(nodes_by_id.values()), "relationships": list(relationships.values())}


def _source_for_tree(tree_name: str, data: dict[str, Any]) -> str:
    if tree_name == "station_tree":
        return "niagara_station_tree"
    if tree_name == "location_tree":
        return "desigo_location_tree" if "desigo" in _bridge_hierarchy_source(data) else _bridge_hierarchy_source(data)
    if tree_name == "plant_tree":
        return "desigo_plant_tree" if "desigo" in _bridge_hierarchy_source(data) else _bridge_hierarchy_source(data)
    return _bridge_hierarchy_source(data)


def _walk_bridge_node(
    node: dict[str, Any],
    *,
    tree_name: str,
    source: str,
    path: list[str],
    nodes_by_id: dict[str, dict[str, Any]],
    relationships: dict[tuple[str, str, str], dict[str, Any]],
    nearest_equipment_id: str | None,
) -> None:
    name = str(node.get("name") or node.get("equipment_id") or node.get("zone_id") or node.get("id") or "node")
    current_path = [*path, name]
    node_id = _bridge_node_id(node, tree_name, current_path)
    node_type = str(
        node.get("node_type") or node.get("type") or ("equipment" if node.get("equipment_id") else "folder")
    )
    current_source = str(node.get("source") or source)
    confidence = _coerce_confidence(node.get("confidence"))
    review_status = _normalize_review_status(node.get("review_status"), confidence)
    evidence_basis = node.get("evidence_basis") or " > ".join(current_path)

    normalized_node = {
        "id": node_id,
        "node_id": node_id,
        "name": name,
        "type": node_type,
        "node_type": node_type,
        "path": " > ".join(current_path),
        "source": current_source,
        "confidence": confidence,
        "review_status": review_status,
        "evidence_basis": evidence_basis,
    }
    for key in ("equipment_id", "canonical_code", "zone_id", "zone_key", "equipment_type"):
        if node.get(key):
            normalized_node[key] = node[key]
    nodes_by_id[node_id] = normalized_node

    current_equipment_id = node.get("canonical_code") or node.get("equipment_id")
    if nearest_equipment_id and current_equipment_id and nearest_equipment_id != current_equipment_id:
        rel_type = str(node.get("relationship_type") or ("manages" if source == "niagara_station_tree" else "contains"))
        _add_bridge_relationship(
            relationships,
            parent=str(nearest_equipment_id),
            child=str(current_equipment_id),
            relationship_type=rel_type,
            source=current_source,
            confidence=confidence,
            review_status=review_status,
            evidence_basis=evidence_basis,
        )

    zone_id = node.get("zone_id") or node.get("zone_key")
    if nearest_equipment_id and zone_id:
        _add_bridge_relationship(
            relationships,
            parent=str(nearest_equipment_id),
            child=str(zone_id),
            relationship_type=str(node.get("relationship_type") or "serves"),
            source=current_source,
            confidence=confidence,
            review_status=review_status,
            evidence_basis=evidence_basis,
        )

    next_nearest_equipment = str(current_equipment_id) if current_equipment_id else nearest_equipment_id
    for child in node.get("children") or []:
        if isinstance(child, dict):
            _walk_bridge_node(
                child,
                tree_name=tree_name,
                source=source,
                path=current_path,
                nodes_by_id=nodes_by_id,
                relationships=relationships,
                nearest_equipment_id=next_nearest_equipment,
            )


def _bridge_node_id(node: dict[str, Any], tree_name: str, path: list[str]) -> str:
    for key in ("id", "node_id", "canonical_code", "equipment_id", "zone_id", "zone_key"):
        if node.get(key):
            return str(node[key])
    return f"{tree_name}:{'/'.join(path)}"


def _add_bridge_relationship(
    relationships: dict[tuple[str, str, str], dict[str, Any]],
    *,
    parent: str,
    child: str,
    relationship_type: str,
    source: str,
    confidence: float,
    review_status: str,
    evidence_basis: Any,
) -> None:
    key = (parent, child, relationship_type)
    relationships[key] = {
        "parent": parent,
        "child": child,
        "relationship_type": relationship_type,
        "source": source,
        "confidence": confidence,
        "review_status": review_status,
        "evidence_basis": evidence_basis,
    }


def _coerce_confidence(value: Any) -> float:
    try:
        return max(0.0, min(1.0, float(value)))
    except (TypeError, ValueError):
        return 0.85


def _normalize_review_status(value: Any, confidence: float) -> str:
    raw = str(value or "").strip().lower()
    if raw in {"approved", "suggested", "rejected"}:
        return raw
    if confidence >= 0.90 and raw in {"auto_approved", "high_confidence_approved"}:
        return "approved"
    return "suggested"
