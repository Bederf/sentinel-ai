"""Policy-enforced BMS adapter wrapper for SIMBIOT."""

from __future__ import annotations

from typing import Sequence

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
from app.services.simbiot.connection_policy import (
    is_point_allowed_for_site,
    is_runtime_processing_enabled,
)


class PolicyEnforcedBmsAdapter(BmsAdapter):
    """Decorator that enforces runtime processing and module policy."""

    def __init__(self, inner: BmsAdapter):
        self._inner = inner
        self._config: BmsConnectionConfig | None = None
        self._blocked_message = ""
        self._runtime_enabled = False

    @property
    def adapter_id(self) -> str:
        return self._inner.adapter_id

    @property
    def capabilities(self) -> BmsAdapterCapabilities:
        return self._inner.capabilities

    async def connect(self, config: BmsConnectionConfig) -> BmsConnectionStatus:
        self._config = config
        commissioning = bool(config.metadata.get("commissioning"))
        self._runtime_enabled = await is_runtime_processing_enabled(config.site_id, commissioning=commissioning)

        if not self._runtime_enabled:
            self._blocked_message = f"SITE_PROCESSING_DISABLED: SIMBIOT runtime disconnected for {config.site_id}"
            return BmsConnectionStatus(
                connected=False,
                site_id=config.site_id,
                source_type=config.source_type,
                status="blocked",
                message=self._blocked_message,
                metadata={"policy_blocked": True},
            )

        self._blocked_message = ""
        return await self._inner.connect(config)

    async def disconnect(self) -> None:
        self._runtime_enabled = False
        self._blocked_message = ""
        await self._inner.disconnect()

    async def get_status(self) -> BmsConnectionStatus:
        if not self._runtime_enabled and self._config is not None and self._blocked_message:
            return BmsConnectionStatus(
                connected=False,
                site_id=self._config.site_id,
                source_type=self._config.source_type,
                status="blocked",
                message=self._blocked_message,
                metadata={"policy_blocked": True},
            )
        return await self._inner.get_status()

    async def discover_devices(self) -> list[BmsDeviceDescriptor]:
        self._ensure_runtime_enabled()
        return await self._inner.discover_devices()

    async def discover_points(self, device_id: str) -> list[BmsPointDescriptor]:
        self._ensure_runtime_enabled()
        points = await self._inner.discover_points(device_id)
        return [
            point
            for point in points
            if self._point_allowed(
                device_id=device_id,
                point_id=point.point_id,
                point_name=point.point_name,
                metadata=point.metadata,
            )
        ]

    async def read_point(self, device_id: str, point_id: str) -> BmsPointValue:
        self._ensure_runtime_enabled()
        if not self._point_allowed(device_id=device_id, point_id=point_id):
            raise PermissionError(f"Point {device_id}:{point_id} is blocked by module policy")
        return await self._inner.read_point(device_id, point_id)

    async def read_points(self, device_id: str, point_ids: Sequence[str]) -> list[BmsPointValue]:
        self._ensure_runtime_enabled()
        allowed_point_ids = [
            point_id for point_id in point_ids if self._point_allowed(device_id=device_id, point_id=point_id)
        ]
        if not allowed_point_ids:
            return []
        return await self._inner.read_points(device_id, allowed_point_ids)

    async def write_point(self, request: BmsWriteRequest) -> bool:
        self._ensure_runtime_enabled()
        if not self._point_allowed(
            device_id=request.device_id,
            point_id=request.point_id,
            metadata=request.metadata,
            equipment_type=str(request.metadata.get("equipment_type") or ""),
        ):
            raise PermissionError(f"Point {request.device_id}:{request.point_id} is blocked by module policy")
        return await self._inner.write_point(request)

    def _ensure_runtime_enabled(self) -> None:
        if not self._runtime_enabled:
            raise ConnectionError(self._blocked_message or "SIMBIOT runtime is disconnected for this site")

    def _point_allowed(
        self,
        *,
        device_id: str,
        point_id: str,
        point_name: str | None = None,
        metadata: dict | None = None,
        equipment_type: str | None = None,
    ) -> bool:
        if self._config is None:
            return True
        return is_point_allowed_for_site(
            self._config.site_id,
            device_id=device_id,
            point_id=point_id,
            point_name=point_name,
            equipment_type=equipment_type or str((metadata or {}).get("equipment_type") or ""),
            metadata=metadata,
        )
