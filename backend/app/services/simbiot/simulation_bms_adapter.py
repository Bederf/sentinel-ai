"""Simulation-backed BMS adapter for SIMBIOT.

This adapter exposes the lifecycle simulation's persisted building state
through the canonical BmsAdapter contract. It does not talk to the
LifecycleOrchestrator directly. Instead it reads and writes against the
building's JSON-backed simulation store, preserving the architectural
boundary:

    building -> lifecycle simulation -> simulation store -> SIMBIOT adapter -> SENTINEL
"""

from __future__ import annotations

from collections.abc import Sequence
from datetime import datetime
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
from app.services.simulation_store import SimulationStore, get_simulation_store


class SimulationBmsAdapter(BmsAdapter):
    """Concrete BmsAdapter that wraps the lifecycle simulation store."""

    def __init__(self):
        self._config: BmsConnectionConfig | None = None
        self._store: SimulationStore | None = None
        self._connected = False
        self._latest_sensor_cache: dict[str, dict[str, dict[str, Any]]] | None = None

    @property
    def adapter_id(self) -> str:
        return "simulation"

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
        self._store = get_simulation_store(config.site_id)
        self._connected = True
        self._latest_sensor_cache = None
        return await self.get_status()

    async def disconnect(self) -> None:
        self._connected = False
        self._latest_sensor_cache = None

    async def get_status(self) -> BmsConnectionStatus:
        site_id = self._config.site_id if self._config else "unknown"
        source_type = self._config.source_type if self._config else self.adapter_id
        status = "connected" if self._connected else "disconnected"
        message = "Connected to simulation store" if self._connected else "Not connected"
        return BmsConnectionStatus(
            connected=self._connected,
            site_id=site_id,
            source_type=source_type,
            status=status,
            message=message,
        )

    async def discover_devices(self) -> list[BmsDeviceDescriptor]:
        store = self._require_store()
        devices = []
        equipment_codes = set(store.get_all_equipment_state().keys())
        equipment_codes.update(self._latest_sensor_readings().keys())
        for equipment_code in sorted(equipment_codes):
            devices.append(
                BmsDeviceDescriptor(
                    device_id=equipment_code,
                    display_name=equipment_code,
                    protocol="simulation",
                    metadata={"site_id": store.site_id},
                )
            )
        return devices

    async def discover_points(self, device_id: str) -> list[BmsPointDescriptor]:
        latest_points, equipment_state, state_values, command_overrides = self._device_snapshot(device_id)
        point_ids = set(latest_points.keys())
        point_ids.update(state_values.keys())
        point_ids.update(command_overrides.keys())

        descriptors = []
        for point_id in sorted(point_ids):
            point_value = latest_points.get(point_id, {}).get("value")
            if point_id in state_values:
                point_value = state_values[point_id]
            writable = point_id in command_overrides
            descriptors.append(
                BmsPointDescriptor(
                    point_id=point_id,
                    point_name=point_id,
                    point_type=self._infer_point_type(point_value),
                    unit=self._infer_unit(point_id),
                    writable=writable,
                    metadata={"device_id": device_id, "source": "simulation_store"},
                )
            )
        return descriptors

    async def read_point(self, device_id: str, point_id: str) -> BmsPointValue:
        point_values = await self.read_points(device_id, [point_id])
        if not point_values:
            raise ValueError(f"Point {point_id} not found for device {device_id}")
        return point_values[0]

    async def read_points(self, device_id: str, point_ids: Sequence[str]) -> list[BmsPointValue]:
        latest_points, equipment_state, state_values, command_overrides = self._device_snapshot(device_id)
        values = []
        for point_id in point_ids:
            if point_id in latest_points:
                reading = latest_points[point_id]
                values.append(
                    BmsPointValue(
                        device_id=device_id,
                        point_id=point_id,
                        value=reading.get("value"),
                        timestamp=reading.get("timestamp"),
                        unit=self._infer_unit(point_id),
                        metadata={"source": "sensor_readings"},
                    )
                )
                continue

            if point_id in state_values:
                values.append(
                    BmsPointValue(
                        device_id=device_id,
                        point_id=point_id,
                        value=state_values[point_id],
                        timestamp=equipment_state.get("updated_at"),
                        metadata={"source": "equipment_state"},
                    )
                )
                continue

            if point_id in command_overrides:
                values.append(
                    BmsPointValue(
                        device_id=device_id,
                        point_id=point_id,
                        value=command_overrides[point_id],
                        timestamp=equipment_state.get("last_command", {}).get("timestamp"),
                        metadata={"source": "command_override"},
                    )
                )

        return values

    async def write_point(self, request: BmsWriteRequest) -> bool:
        store = self._require_store()
        if request.device_id not in set(store.get_equipment_codes()):
            raise ValueError(f"Device {request.device_id} not found in simulation store")

        record = {
            "site_id": store.site_id,
            "device_id": request.device_id,
            "point_id": request.point_id,
            "value": request.value,
            "priority": request.priority,
            "user": request.user,
            "timestamp": datetime.utcnow().isoformat() + "Z",
            "metadata": dict(request.metadata),
        }
        store.write_command(record)
        return True

    def _require_store(self) -> SimulationStore:
        if not self._connected or self._store is None:
            raise ConnectionError("Simulation BMS adapter is not connected")
        return self._store

    def _device_snapshot(self, device_id: str) -> tuple[dict[str, Any], dict[str, Any], dict[str, Any], dict[str, Any]]:
        store = self._require_store()
        latest_points = self._latest_sensor_readings().get(device_id, {})
        equipment_state = store.get_equipment_state(device_id)
        state_values = self._scalar_state_points(equipment_state)
        command_overrides = dict(equipment_state.get("command_overrides", {}))
        return latest_points, equipment_state, state_values, command_overrides

    def _latest_sensor_readings(self) -> dict[str, dict[str, dict[str, Any]]]:
        if self._latest_sensor_cache is None:
            self._latest_sensor_cache = self._require_store().get_latest_sensor_readings()
        return self._latest_sensor_cache

    def _scalar_state_points(self, equipment_state: dict[str, Any]) -> dict[str, Any]:
        state_points = {}
        for key, value in equipment_state.items():
            if key in {"command_overrides", "last_command"}:
                continue
            if isinstance(value, (str, int, float, bool)) or value is None:
                state_points[key] = value
        return state_points

    def _infer_point_type(self, value: Any) -> str:
        if isinstance(value, bool):
            return "binary"
        if isinstance(value, int):
            return "integer"
        if isinstance(value, float):
            return "analog"
        return "string"

    def _infer_unit(self, point_id: str) -> str | None:
        point_name = point_id.lower()
        if "temp" in point_name:
            return "C"
        if "humidity" in point_name:
            return "%"
        if "co2" in point_name:
            return "ppm"
        if point_name.endswith("_kw"):
            return "kW"
        if point_name.endswith("_kwh"):
            return "kWh"
        return None
