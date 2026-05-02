"""Modbus TCP BMS Adapter for SIMBIOT.

For electrical equipment (generators, UPS, ATS, motor controllers)
that communicate via Modbus TCP. No auto-discovery — equipment point
definitions come from register maps uploaded during SIMBIOT onboarding.
"""

from __future__ import annotations

import asyncio
import csv
import json
import logging
from collections.abc import Sequence
from io import StringIO
from typing import Any

from pymodbus.client import AsyncModbusTcpClient
from pymodbus.exceptions import ModbusException

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


class ModbusBmsAdapter(BmsAdapter):
    """Modbus TCP adapter for electrical equipment."""

    def __init__(self) -> None:
        self._config: BmsConnectionConfig | None = None
        self._connected = False
        self._client: AsyncModbusTcpClient | None = None
        self._register_map: dict[str, dict[str, dict[str, Any]]] = {}

    @property
    def adapter_id(self) -> str:
        return "modbus"

    @property
    def capabilities(self) -> BmsAdapterCapabilities:
        return BmsAdapterCapabilities(
            supports_device_discovery=False,  # No auto-discovery in Modbus
            supports_point_discovery=False,
            supports_reads=True,
            supports_writes=True,
            supports_subscriptions=False,  # Poll-only protocol
            supports_history=False,
        )

    async def connect(self, config: BmsConnectionConfig) -> BmsConnectionStatus:
        self._config = config
        host = config.host or "localhost"
        port = config.port or 502
        timeout = config.timeout_seconds or 10.0

        # Parse register map from metadata
        self._register_map = self._parse_register_map(config.metadata.get("register_map", {}))

        self._client = AsyncModbusTcpClient(
            host=host,
            port=port,
            timeout=timeout,
        )

        try:
            connected = await asyncio.to_thread(self._client.connect)
            self._connected = connected
            if not connected:
                return BmsConnectionStatus(
                    connected=False,
                    site_id=config.site_id,
                    source_type=self.adapter_id,
                    status="disconnected",
                    message=f"Modbus TCP connection refused: {host}:{port}",
                )
        except Exception as e:
            self._connected = False
            return BmsConnectionStatus(
                connected=False,
                site_id=config.site_id,
                source_type=self.adapter_id,
                status="error",
                message=f"Modbus TCP connection failed: {e}",
            )

        return await self.get_status()

    async def disconnect(self) -> None:
        if self._client:
            await asyncio.to_thread(self._client.close)
        self._connected = False
        self._client = None

    async def get_status(self) -> BmsConnectionStatus:
        site_id = self._config.site_id if self._config else "unknown"
        source_type = self._config.source_type if self._config else self.adapter_id

        if self._client is not None:
            try:
                connected = await asyncio.to_thread(self._client.connected)
                status = "connected" if connected else "disconnected"
                message = "Modbus TCP client ready" if connected else "Modbus TCP client disconnected"
            except Exception:
                connected = False
                status = "error"
                message = "Error checking Modbus connection"
        else:
            connected = False
            status = "disconnected"
            message = "Modbus client not initialized"

        return BmsConnectionStatus(
            connected=connected,
            site_id=site_id,
            source_type=source_type,
            status=status,
            message=message,
        )

    async def discover_devices(self) -> list[BmsDeviceDescriptor]:
        # No auto-discovery — return logical devices from register map
        if not self._register_map:
            return []

        devices = []
        for equipment_id in self._register_map:
            equipment_type = self._infer_equipment_type(equipment_id)
            devices.append(
                BmsDeviceDescriptor(
                    device_id=equipment_id,
                    display_name=equipment_id,
                    protocol="modbus",
                    address=self._config.host if self._config else None,
                    metadata={"equipment_type": equipment_type},
                )
            )
        return devices

    async def discover_points(self, device_id: str) -> list[BmsPointDescriptor]:
        if device_id not in self._register_map:
            return []

        points = []
        for point_name, point_def in self._register_map[device_id].items():
            points.append(
                BmsPointDescriptor(
                    point_id=point_name,
                    point_name=point_name,
                    point_type=point_def.get("type", "holding"),
                    unit=point_def.get("unit"),
                    writable=point_def.get("writable", False),
                    metadata={
                        "address": point_def.get("address"),
                        "data_type": point_def.get("data_type", "uint16"),
                        "scale": point_def.get("scale", 1.0),
                    },
                )
            )
        return points

    async def read_point(self, device_id: str, point_id: str) -> BmsPointValue:
        self._ensure_connected()
        assert self._client is not None

        if device_id not in self._register_map or point_id not in self._register_map[device_id]:
            raise ValueError(f"Point not found: {device_id}.{point_id}")

        point_def = self._register_map[device_id][point_id]
        raw_value = await self._read_register(
            address=point_def["address"],
            register_type=point_def.get("type", "holding"),
            data_type=point_def.get("data_type", "uint16"),
        )

        scale = point_def.get("scale", 1.0)
        scaled_value = raw_value * scale

        return BmsPointValue(
            device_id=device_id,
            point_id=point_id,
            value=scaled_value,
            unit=point_def.get("unit"),
            metadata={"raw_value": raw_value, "scale": scale},
        )

    async def read_points(self, device_id: str, point_ids: Sequence[str]) -> list[BmsPointValue]:
        self._ensure_connected()
        results = []
        for point_id in point_ids:
            try:
                results.append(await self.read_point(device_id, point_id))
            except Exception as e:
                logger.error(f"Failed to read {device_id}.{point_id}: {e}")
                results.append(
                    BmsPointValue(
                        device_id=device_id,
                        point_id=point_id,
                        value=None,
                        quality="bad",
                        metadata={"error": str(e)},
                    )
                )
        return results

    async def write_point(self, request: BmsWriteRequest) -> bool:
        self._ensure_connected()
        assert self._client is not None

        device_id = request.device_id
        point_id = request.point_id

        if device_id not in self._register_map or point_id not in self._register_map[device_id]:
            logger.error(f"Write failed: point not found {device_id}.{point_id}")
            return False

        point_def = self._register_map[device_id][point_id]

        if not point_def.get("writable", False):
            logger.error(f"Write failed: {device_id}.{point_id} is read-only")
            return False

        try:
            # Read current value (audit trail)
            current_raw = await self._read_register(
                address=point_def["address"],
                register_type=point_def.get("type", "holding"),
                data_type=point_def.get("data_type", "uint16"),
            )
            logger.info(f"Modbus write: {device_id}.{point_id} current={current_raw}, new={request.value}")

            # Descale for raw register write
            scale = point_def.get("scale", 1.0)
            raw_value = int(request.value / scale)

            # Write register
            await self._write_register(
                address=point_def["address"],
                value=raw_value,
                register_type=point_def.get("type", "holding"),
            )

            # Read back to verify
            verified_raw = await self._read_register(
                address=point_def["address"],
                register_type=point_def.get("type", "holding"),
                data_type=point_def.get("data_type", "uint16"),
            )

            if verified_raw != raw_value:
                logger.warning(f"Modbus write verification failed: wrote {raw_value}, read {verified_raw}")

            return True

        except Exception as e:
            logger.error(f"Modbus write failed for {device_id}.{point_id}: {e}")
            return False

    async def subscribe_points(self, device_id: str, point_ids: Sequence[str]) -> Any:
        raise NotImplementedError("Modbus TCP does not support subscriptions")

    def _ensure_connected(self) -> None:
        if not self._connected or not self._client:
            raise ConnectionError("Modbus adapter is not connected")

    async def _read_register(
        self,
        address: int,
        register_type: str,
        data_type: str = "uint16",
    ) -> int | bool:
        assert self._client is not None

        # Normalize: Modbus UI uses 40001+ for holding, API uses 0-based
        addr = address - 1 if address >= 40001 else address
        slave_id = self._config.metadata.get("slave_id", 1) if self._config else 1

        if register_type == "holding":
            response = await self._client.read_holding_registers(
                address=addr,
                count=1,
                slave=slave_id,
            )
        elif register_type == "input":
            response = await self._client.read_input_registers(
                address=addr,
                count=1,
                slave=slave_id,
            )
        elif register_type == "coil":
            response = await self._client.read_coils(
                address=addr,
                count=1,
                slave=slave_id,
            )
        elif register_type == "discrete":
            response = await self._client.read_discrete_inputs(
                address=addr,
                count=1,
                slave=slave_id,
            )
        else:
            raise ValueError(f"Unknown register type: {register_type}")

        if response.isError():
            raise ModbusException(f"Modbus read error for address {address}")

        if register_type in ("coil", "discrete"):
            return response.bits[0]
        return response.registers[0]

    async def _write_register(
        self,
        address: int,
        value: int,
        register_type: str,
    ) -> None:
        assert self._client is not None

        addr = address - 1 if address >= 40001 else address
        slave_id = self._config.metadata.get("slave_id", 1) if self._config else 1

        if register_type == "holding":
            response = await self._client.write_register(
                address=addr,
                value=value,
                slave=slave_id,
            )
        elif register_type == "coil":
            response = await self._client.write_coil(
                address=addr,
                value=bool(value),
                slave=slave_id,
            )
        else:
            raise ValueError(f"Cannot write to {register_type} registers (read-only)")

        if response.isError():
            raise ModbusException(f"Modbus write error for address {address}")

    def _parse_register_map(self, register_map_input: Any) -> dict[str, dict[str, dict[str, Any]]]:
        """Parse register map from dict, JSON string, or CSV string."""
        if isinstance(register_map_input, dict):
            return register_map_input

        if isinstance(register_map_input, str):
            stripped = register_map_input.strip()
            if stripped.startswith("{"):
                return json.loads(stripped)
            return self._parse_csv_register_map(stripped)

        return {}

    def _parse_csv_register_map(self, csv_content: str) -> dict[str, dict[str, dict[str, Any]]]:
        """Parse CSV register map into nested dict structure."""
        register_map: dict[str, dict[str, dict[str, Any]]] = {}
        reader = csv.DictReader(StringIO(csv_content))

        for row in reader:
            equipment_id = row["equipment_id"]
            point_name = row["point_name"]

            if equipment_id not in register_map:
                register_map[equipment_id] = {}

            register_map[equipment_id][point_name] = {
                "address": int(row["address"]),
                "type": row["type"],
                "data_type": row.get("data_type", "uint16"),
                "scale": float(row.get("scale", 1.0)),
                "unit": row.get("unit") or None,
                "writable": row.get("writable", "false").lower() == "true",
            }

        return register_map

    def _infer_equipment_type(self, equipment_id: str) -> str:
        """Infer equipment type from ID prefix."""
        prefix = equipment_id.split("-")[0].upper()

        type_map = {
            "GEN": "generator",
            "UPS": "ups",
            "ATS": "transfer_switch",
            "MTR": "motor",
            "INV": "inverter",
            "PDU": "power_distribution",
        }

        return type_map.get(prefix, "electrical_equipment")
