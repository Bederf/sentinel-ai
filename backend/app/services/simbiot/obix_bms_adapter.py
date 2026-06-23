"""oBIX-backed BMS adapter for SIMBIOT.

Wraps the existing OBIXClient behind the canonical BmsAdapter contract
so discovery, reads, and writes flow through one building-level boundary.
"""

from __future__ import annotations

import asyncio
import logging
from typing import Any

from app.services.niagara.obix_client import (
    OBIXAuthenticationError,
    OBIXConnectionError,
    OBIXParseError,
    OBIXPointNotFoundError,
)

logger = logging.getLogger(__name__)
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

# Unit conversion constants (oBIX → SI)
# Format: {unit: (si_unit, multiplier)} — value * multiplier + offset
UNIT_CONVERSIONS: dict[str, tuple[str, float]] = {
    "°F": ("°C", 0.5556),  # (°F - 32) * 5/9 = °F * 0.5556 - 17.778
    "cfm": ("l/s", 0.4719),
    "psi": ("kPa", 6.8948),
    "inWC": ("Pa", 249.09),
    "kVA": ("kW", 0.9),
    "kBtu": ("kWh", 0.2931),
    "gpm": ("l/s", 0.06309),
    "fpm": ("m/s", 0.00508),
}
# Offset corrections — precomputed to avoid formula errors
# Formula: result = value * multiplier + offset
# For °F: (°F - 32) * 5/9 = °F * 0.5556 - 17.778 => offset = -17.778
UNIT_OFFSET_CORRECTIONS: dict[str, float] = {
    "°F": -17.778,
}


def _normalize_unit(value: float, unit: str) -> tuple[float, str]:
    """Normalize oBIX unit to SI unit. Returns (normalized_value, si_unit)."""
    if unit in UNIT_CONVERSIONS:
        si_unit, multiplier = UNIT_CONVERSIONS[unit]
        offset = UNIT_OFFSET_CORRECTIONS.get(unit, 0.0)
        return value * multiplier + offset, si_unit
    return value, unit  # pass-through for unknown/unsupported units


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


class ObixBmsAdapter(BmsAdapter):
    """Concrete BMS adapter wrapping OBIXClient."""

    def __init__(self) -> None:
        self._config: BmsConnectionConfig | None = None
        self._connected = False
        self._obix_client: Any | None = None

    @property
    def adapter_id(self) -> str:
        return "obix"

    @property
    def capabilities(self) -> BmsAdapterCapabilities:
        return BmsAdapterCapabilities(
            supports_device_discovery=False,  # oBIX has no device discovery
            supports_point_discovery=True,
            supports_hierarchy_discovery=True,
            supports_reads=True,
            supports_writes=True,
            supports_subscriptions=False,
            supports_history=True,
        )

    async def connect(self, config: BmsConnectionConfig) -> BmsConnectionStatus:
        self._config = config
        host = config.host or "localhost"
        port = config.port or 8080
        username = config.username or ""
        password = config.password or ""
        use_tls = getattr(config, "use_tls", False)
        timeout = getattr(config, "timeout_seconds", 30)

        protocol = "https" if use_tls else "http"
        base_url = f"{protocol}://{host}:{port}"

        # Create a dedicated OBIXClient for this adapter instance
        from app.services.niagara.obix_client import OBIXClient

        self._obix_client = OBIXClient(
            base_url=base_url,
            username=username,
            password=password,
            timeout=timeout,
            use_https=use_tls,
        )

        try:
            # Run sync authenticate in thread pool to avoid blocking event loop
            await asyncio.wait_for(asyncio.to_thread(self._obix_client.authenticate), timeout=timeout)
            self._connected = self._obix_client.is_authenticated
        except OBIXAuthenticationError as e:
            self._connected = False
            return BmsConnectionStatus(
                connected=False,
                site_id=config.site_id,
                source_type=self.adapter_id,
                status="error",
                message=f"oBIX authentication failed: {e}",
            )
        except OBIXConnectionError as e:
            self._connected = False
            return BmsConnectionStatus(
                connected=False,
                site_id=config.site_id,
                source_type=self.adapter_id,
                status="error",
                message=f"oBIX connection failed: {e}",
            )
        except Exception as e:
            self._connected = False
            return BmsConnectionStatus(
                connected=False,
                site_id=config.site_id,
                source_type=self.adapter_id,
                status="error",
                message=f"oBIX connection failed: {e}",
            )

        return await self.get_status()

    async def disconnect(self) -> None:
        self._connected = False
        self._obix_client = None

    async def get_status(self) -> BmsConnectionStatus:
        site_id = self._config.site_id if self._config else "unknown"
        source_type = self._config.source_type if self._config else self.adapter_id

        if self._obix_client is not None:
            check = await asyncio.to_thread(self._obix_client.check_connection)
            connected = bool(check.get("connected", False))
            status = "connected" if connected else "disconnected"
            message = check.get("message", "oBIX client ready" if connected else "oBIX client not connected")
            return BmsConnectionStatus(
                connected=connected,
                site_id=site_id,
                source_type=source_type,
                status=status,
                message=message,
            )

        return BmsConnectionStatus(
            connected=False,
            site_id=site_id,
            source_type=source_type,
            status="disconnected",
            message="oBIX client not initialized",
        )

    async def discover_devices(self) -> list[BmsDeviceDescriptor]:
        # oBIX has no device discovery — return single logical device
        return [
            BmsDeviceDescriptor(
                device_id="obix-broker",
                display_name="oBIX Broker",
                protocol="obix",
                address=self._config.host if self._config else None,
            )
        ]

    async def discover_points(self, device_id: str) -> list[BmsPointDescriptor]:
        # oBIX requires manual point path configuration
        # Return empty — points must be discovered via configuration
        return []

    async def discover_hierarchy(self) -> dict[str, Any]:
        """Return oBIX hierarchy supplied by adapter configuration.

        Niagara/oBIX is hierarchical, but this adapter currently reads explicit
        point paths rather than browsing the whole station tree. During
        onboarding, the bridge/config layer can pass normalized hierarchy in
        ``metadata.hierarchy`` or ``metadata.relationships``.
        """
        metadata = self._config.metadata if self._config else {}
        configured = _hierarchy_from_metadata(metadata, default_source="obix_config_hierarchy")
        if configured:
            return configured
        return {
            "available": False,
            "source": "obix_config_hierarchy",
            "nodes": [],
            "relationships": [],
            "message": "No oBIX hierarchy metadata configured; station-tree browsing is not implemented in the direct oBIX adapter yet.",
        }

    async def read_point(self, device_id: str, point_id: str) -> BmsPointValue:
        self._ensure_connected()
        assert self._obix_client is not None

        try:
            result = await asyncio.to_thread(self._obix_client.read_point, point_id)
        except OBIXPointNotFoundError:
            raise
        except OBIXConnectionError:
            raise
        except OBIXParseError:
            raise
        except Exception as e:
            raise OBIXConnectionError(f"read_point failed for {point_id}: {e}") from e

        if not result:
            raise OBIXPointNotFoundError(f"Point not found: {point_id}")

        raw_value = result.get("value")
        unit = result.get("type", "")  # OBIXClient uses "type" for the value type, unit comes from attrs

        is_numeric = raw_value is not None and isinstance(raw_value, (int, float)) and not isinstance(raw_value, bool)
        normalized_value = raw_value
        si_unit = unit
        if is_numeric and unit:
            # Try to get unit from the point metadata if available
            normalized_value, si_unit = _normalize_unit(float(raw_value), unit)

        return BmsPointValue(
            device_id=device_id,
            point_id=point_id,
            value=normalized_value,
            unit=si_unit,
            metadata={"raw_value": raw_value, "obix_type": unit},
        )

    async def read_points(self, device_id: str, point_ids: list[str]) -> list[BmsPointValue]:
        self._ensure_connected()
        assert self._obix_client is not None

        values = []
        for point_id in point_ids:
            try:
                result = await asyncio.to_thread(self._obix_client.read_point, point_id)
            except OBIXPointNotFoundError:
                raise
            except OBIXConnectionError:
                raise
            except OBIXParseError:
                raise
            except Exception as e:
                raise OBIXConnectionError(f"read_point failed for {point_id}: {e}") from e

            raw_value = result.get("value")
            unit = result.get("type", "")

            is_numeric = (
                raw_value is not None and isinstance(raw_value, (int, float)) and not isinstance(raw_value, bool)
            )
            normalized_value = raw_value
            si_unit = unit
            if is_numeric and unit:
                normalized_value, si_unit = _normalize_unit(float(raw_value), unit)

            values.append(
                BmsPointValue(
                    device_id=device_id,
                    point_id=point_id,
                    value=normalized_value,
                    unit=si_unit,
                    metadata={"raw_value": raw_value, "obix_type": unit},
                )
            )
        return values

    async def write_point(self, request: BmsWriteRequest) -> bool:
        self._ensure_connected()
        assert self._obix_client is not None

        try:
            # Run sync write_point in thread pool to avoid blocking event loop
            # verify=True reads back the point after writing to catch silent
            # no-ops (Niagara priority-array override, manual-override state)
            result = await asyncio.to_thread(self._obix_client.write_point, request.point_id, request.value, True)
            if result:
                logger.info(f"oBIX write verified: {request.device_id}:{request.point_id} = {request.value}")
            else:
                logger.warning(
                    f"oBIX write verification failed: {request.device_id}:{request.point_id} "
                    f"(wrote {request.value}, read-back mismatch — possible priority-array override)"
                )
            return result
        except OBIXPointNotFoundError:
            logger.error(f"oBIX write failed: point not found {request.point_id}")
            return False
        except OBIXConnectionError as e:
            logger.error(f"oBIX write connection error for {request.point_id}: {e}")
            return False
        except Exception as e:
            logger.error(f"oBIX write failed for {request.point_id}: {e}")
            return False

    def _ensure_connected(self) -> None:
        if not self._connected or not self._obix_client:
            raise ConnectionError("oBIX BMS adapter is not connected")
