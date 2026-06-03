"""KNXnet/IP client — xknx wrapper with DPT encoding/decoding.

SENTINEL integration path: KNXnet/IP tunnelling (UDP 3671).
Hardware requirement: KNXnet/IP gateway at client site.
"""

from __future__ import annotations

import asyncio
import logging
from dataclasses import dataclass, field
from typing import Any

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# DPT (Data Point Type) encoding/decoding
# ---------------------------------------------------------------------------

DPT_1_TYPES = {"1.001"}
DPT_5_TYPES = {"5.001", "5.010"}
DPT_9_TYPES = {"9.001", "9.002", "9.007", "9.020", "9.021"}
DPT_14_TYPES = {"14.019", "14.056", "14.068"}


def encode_dpt(value: Any, dpt: str) -> bytes:
    """Encode a Python value to a KNX payload (big-endian bytes)."""
    if dpt in DPT_1_TYPES:
        # DPT 1.001: binary (0 = off, 1 = on)
        return bytes([1 if bool(value) else 0])

    if dpt in DPT_5_TYPES:
        if dpt == "5.001":
            # 0–100% -> 1 byte, 0–255 raw
            return bytes([int(float(value) * 2.55) & 0xFF])
        if dpt == "5.010":
            # 0–255 counter
            return bytes([int(value) & 0xFF])

    if dpt in DPT_9_TYPES:
        if isinstance(value, float):
            value = round(value, 2)
        return _encode_knx_float(float(value))

    if dpt in DPT_14_TYPES:
        import struct

        return struct.pack(">f", float(value))

    raise ValueError(f"Unsupported DPT: {dpt}")


def decode_dpt(payload: bytes, dpt: str) -> Any:
    """Decode a KNX payload to a Python value."""
    if not payload:
        return None

    if dpt in DPT_1_TYPES:
        return bool(payload[0] & 1)

    if dpt in DPT_5_TYPES:
        if dpt == "5.001":
            return round((payload[0] & 0xFF) / 255.0 * 100.0, 1)
        if dpt == "5.010":
            return payload[0] & 0xFF

    if dpt in DPT_9_TYPES:
        return _decode_knx_float(payload)

    if dpt in DPT_14_TYPES:
        import struct

        return round(struct.unpack(">f", payload[:4])[0], 3)

    raise ValueError(f"Unsupported DPT: {dpt}")


def _encode_knx_float(value: float) -> bytes:
    """Encode a float to KNX 2-byte format (DPT 9.xxx).

    Algorithm from xknx DPTTemperature.to_knx():
    1. Multiply value by 100 (DPT 9.001 stores 0.01 units)
    2. Divide by 2 until abs(knx_value) <= 2047 -> exponent 0-15
    3. mantissa = round(knx_value) & 0x7FF
    4. msb = (exponent << 3) | (mantissa >> 8); if value < 0: msb |= 0x80
    """
    if value == 0.0:
        return bytes([0, 0])

    knx_value = value * 100.0

    # xknx special-cases values near zero
    if round(knx_value) == 0:
        return bytes([0, 0])

    # Find exponent so knx_value fits in 12-bit signed
    exponent = 0
    while not -2048 <= knx_value <= 2047 and exponent < 15:
        knx_value /= 2.0
        exponent += 1

    mantissa = round(knx_value) & 0x7FF
    msb = (exponent << 3) | (mantissa >> 8)
    if value < 0:
        msb |= 0x80

    return bytes([msb, mantissa & 0xFF])


def _decode_knx_float(payload: bytes) -> float:
    """Decode KNX 2-byte float to Python float (DPT 9.xxx)."""
    if len(payload) < 2:
        return 0.0

    raw = (payload[0] << 8) | payload[1]
    exponent = (raw >> 11) & 0x0F
    significand = raw & 0x7FF  # 11-bit unsigned

    # Sign bit is bit 15 of the 16-bit raw value
    if raw & 0x8000:
        significand -= 2048  # two's complement for negative

    # value = significand * 2^exponent / 100
    return round((significand << exponent) / 100.0, 2)


# ---------------------------------------------------------------------------
# KNX Client singleton per gateway
# ---------------------------------------------------------------------------

_knx_clients: dict[tuple[str, int], KNXClient] = {}


def get_knx_client(gateway_host: str, gateway_port: int = 3671) -> KNXClient:
    """Return (or create) a singleton KNXClient per gateway host:port."""
    key = (gateway_host, gateway_port)
    if key not in _knx_clients:
        _knx_clients[key] = KNXClient(gateway_host, gateway_port)
    return _knx_clients[key]


@dataclass
class KNXConnectionConfig:
    gateway_host: str
    gateway_port: int = 3671
    local_ip: str | None = None
    rate_limit_ms: int = 20
    timeout_s: float = 5.0


@dataclass
class KNXClient:
    """Async KNXnet/IP client wrapping xknx.

    Manages KNXnet/IP tunnel connection and exposes
    group-address read/write and event listening.
    """

    gateway_host: str
    gateway_port: int = 3671
    local_ip: str | None = None
    rate_limit_ms: int = 20
    timeout_s: float = 5.0

    _xknx_instance: Any = field(default=None, init=False, repr=False)
    _connected: bool = field(default=False, init=False, repr=False)
    _last_write: dict[str, float] = field(default_factory=dict, init=False, repr=False)
    _write_lock: asyncio.Lock = field(default_factory=asyncio.Lock, init=False, repr=False)

    def _import_xknx(self) -> None:
        """Verify xknx is available and import key classes."""
        try:
            import xknx  # noqa: F401
            from xknx.core.group_address_dpt import GroupAddress as GA
            from xknx.core.value_reader import ValueReader
            from xknx.dpt import DPTArray
            from xknx.tools.group_communication import group_value_read, group_value_write
            from xknx.telegram import Telegram
            from xknx.telegram.address import parse_device_group_address
            from xknx.telegram.apci import GroupValueWrite as GVW

            self._GA = GA
            self._ValueReader = ValueReader
            self._DPTArray = DPTArray
            self._gvr = group_value_read
            self._gvw = group_value_write
            self._Telegram = Telegram
            self._parse_ga = parse_device_group_address
            self._GVW = GVW
        except ImportError as e:
            raise ImportError(
                "xknx is required for KNX integration. Install with: pip install xknx --break-system-packages"
            ) from e

    def __post_init__(self):
        self._import_xknx()

    async def connect(self) -> bool:
        """Establish KNXnet/IP tunnel connection to the gateway."""
        if self._connected:
            return True

        try:
            from xknx import XKNX

            self._xknx_instance = XKNX()
            gateway_addr = f"{self.gateway_host}:{self.gateway_port}"
            logger.info("Connecting to KNX gateway at %s", gateway_addr)

            # Start the xknx stack (opens UDP socket, starts telegram processor)
            await asyncio.wait_for(
                self._xknx_instance.start(),
                timeout=self.timeout_s,
            )
            self._connected = True
            logger.info("KNX gateway connected: %s", gateway_addr)
            return True

        except TimeoutError:
            logger.error("KNX gateway connection timed out: %s", self.gateway_host)
            return False
        except Exception as e:
            logger.error("KNX gateway connection failed (%s): %s", self.gateway_host, e)
            return False

    async def disconnect(self) -> None:
        """Close the KNXnet/IP tunnel."""
        if not self._connected:
            return

        try:
            await self._xknx_instance.stop()
        except Exception as e:
            logger.warning("Error disconnecting KNX gateway: %s", e)
        finally:
            self._connected = False

    @property
    def is_connected(self) -> bool:
        return self._connected

    async def read_group_address(self, group_address: str, dpt: str = "9.001") -> Any:
        """Send GroupValueRead and return decoded value.

        Uses xknx ValueReader which:
        1. Sends GroupValueRead telegram via xknx.telegrams queue
        2. Registers callback on telegram_queue for matching response
        3. Waits for response (or timeout)
        """
        if not self._connected:
            raise ConnectionError(f"Not connected to KNX gateway {self.gateway_host}")

        try:
            ga = self._GA(group_address)

            reader = self._ValueReader(
                self._xknx_instance,
                ga,
                timeout_in_seconds=self.timeout_s,
            )

            result = await reader.read()

            if result is None:
                raise TimeoutError(f"No response from group address {group_address}")

            # Extract payload from response telegram
            payload_obj = result.payload
            # GroupValueResponse or GroupValueWrite has .value that is DPTArray
            raw_bytes = payload_obj.value.value if hasattr(payload_obj.value, "value") else payload_obj.value

            return decode_dpt(bytes(raw_bytes), dpt)

        except TimeoutError:
            logger.warning("KNX read timeout: %s", group_address)
            raise TimeoutError(f"KNX read timeout for {group_address}") from None
        except Exception as e:
            logger.error("KNX read error (%s, %s): %s", group_address, dpt, e)
            raise

    async def write_group_address(
        self,
        group_address: str,
        value: Any,
        dpt: str = "9.001",
        priority: int = 8,
    ) -> bool:
        """Send GroupValueWrite to a group address.

        Applies rate limiting: minimum interval between writes
        to the same group address is rate_limit_ms.
        """
        if not self._connected:
            raise ConnectionError(f"Not connected to KNX gateway {self.gateway_host}")

        async with self._write_lock:
            import time

            now = time.monotonic()
            last = self._last_write.get(group_address, 0)
            elapsed_ms = (now - last) * 1000

            if elapsed_ms < self.rate_limit_ms:
                await asyncio.sleep((self.rate_limit_ms - elapsed_ms) / 1000)

            try:
                payload_bytes = encode_dpt(value, dpt)
                payload = self._DPTArray(payload_bytes)

                self._gvw(
                    self._xknx_instance,
                    group_address,
                    payload,
                )

                self._last_write[group_address] = time.monotonic()
                logger.debug("KNX write: %s = %s (DPT %s)", group_address, value, dpt)
                return True

            except Exception as e:
                logger.error("KNX write error (%s = %s): %s", group_address, value, e)
                return False

    async def listen_to_group_address(
        self,
        group_address: str,
        callback: Any,
        dpt: str = "9.001",
    ) -> None:
        """Start listening for GroupValueWrite/Response on a group address.

        Callback receives the decoded value.
        """
        if not self._connected:
            raise ConnectionError(f"Not connected to KNX gateway {self.gateway_host}")

        ga = self._GA(group_address)

        def on_telegram(telegram: Any) -> None:
            """Called by telegram queue when matching telegram arrives."""
            if hasattr(telegram, "payload") and hasattr(telegram.payload, "value"):
                raw = (
                    telegram.payload.value.value if hasattr(telegram.payload.value, "value") else telegram.payload.value
                )
                value = decode_dpt(bytes(raw), dpt)
                try:
                    callback(value)
                except Exception as e:
                    logger.warning("KNX listener callback error for %s: %s", group_address, e)

        self._xknx_instance.telegram_queue.register_telegram_received_cb(
            on_telegram,
            group_addresses=[ga],
            match_for_outgoing=False,
        )

    async def gateway_health_check(self) -> dict[str, Any]:
        """Verify gateway connectivity by attempting a queue put."""
        if not self._connected:
            return {"status": "disconnected", "gateway": self.gateway_host}

        try:
            if self._xknx_instance.started:
                return {
                    "status": "healthy",
                    "gateway": self.gateway_host,
                    "port": self.gateway_port,
                }
            return {"status": "unreachable", "gateway": self.gateway_host}

        except Exception as e:
            return {"status": "error", "gateway": self.gateway_host, "error": str(e)}


# ---------------------------------------------------------------------------
# Supported DPT types registry
# ---------------------------------------------------------------------------

SUPPORTED_DPT_TYPES = [
    {"dpt": "1.001", "name": "Binary", "description": "On/Off, Open/Close", "encoding": "1 bit", "example": "0 or 1"},
    {"dpt": "5.001", "name": "Percentage", "description": "0-100%", "encoding": "1 byte (0-255)", "example": "0-100"},
    {
        "dpt": "5.010",
        "name": "Counter",
        "description": "0-255 counter",
        "encoding": "1 byte (0-255)",
        "example": "0-255",
    },
    {"dpt": "9.001", "name": "Temperature", "description": "C", "encoding": "2-byte float", "example": "21.5"},
    {"dpt": "9.007", "name": "Humidity", "description": "%RH", "encoding": "2-byte float", "example": "65.0"},
    {"dpt": "9.020", "name": "Voltage", "description": "V", "encoding": "2-byte float", "example": "230.0"},
    {
        "dpt": "14.019",
        "name": "Electric Current",
        "description": "A",
        "encoding": "4-byte float (IEEE 754)",
        "example": "5.2",
    },
    {"dpt": "14.056", "name": "Power", "description": "W", "encoding": "4-byte float (IEEE 754)", "example": "1500.0"},
    {"dpt": "14.068", "name": "Energy", "description": "Wh", "encoding": "4-byte float (IEEE 754)", "example": "2500"},
]
