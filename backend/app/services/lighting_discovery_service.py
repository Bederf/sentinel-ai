"""Lighting Discovery Service - Query lighting device information from gateways.

Supports discovering device metadata from lighting gateways including:
- Tridonic Scenecom
- Philips Dynalite
- Helvar Router
- Generic DALI-2 gateways via REST API

DALI-2 queries supported:
- Device type (0-8)
- GTIN (Global Trade Item Number)
- Firmware version
- Serial number
- Operating hours
- Lamp status/failures
"""

import logging
from dataclasses import dataclass, field
from datetime import datetime
from enum import IntEnum
from typing import Optional

import httpx

from app.database.repositories.equipment_metadata_repository import EquipmentMetadataRepository

logger = logging.getLogger(__name__)


class LightingDeviceType(IntEnum):
    """DALI-2 device types (IEC 62386-102)."""

    FLUORESCENT = 0
    EMERGENCY = 1
    DISCHARGE_HID = 2
    LOW_VOLTAGE_HALOGEN = 3
    INCANDESCENT = 4
    DC_DIMMER = 5
    LED_MODULE = 6
    SWITCHING = 7
    COLOR_CONTROL = 8


@dataclass
class LightingDeviceInfo:
    """Discovered DALI device information."""

    dali_address: int
    device_type: int
    device_type_name: str = ""
    gtin: Optional[str] = None
    firmware_version: Optional[str] = None
    hardware_version: Optional[str] = None
    serial_number: Optional[str] = None
    manufacturer: Optional[str] = None
    operating_hours: Optional[int] = None
    lamp_failure: bool = False
    lamp_power_on: bool = False
    min_level: int = 1
    max_level: int = 254
    power_on_level: int = 254
    system_failure_level: int = 254
    fade_time: int = 0
    fade_rate: int = 0
    actual_level: int = 0
    discovered_at: str = field(default_factory=lambda: datetime.utcnow().isoformat())

    def __post_init__(self):
        if not self.device_type_name and self.device_type is not None:
            try:
                self.device_type_name = LightingDeviceType(self.device_type).name.replace("_", " ").title()
            except ValueError:
                self.device_type_name = f"Unknown ({self.device_type})"

    def to_dict(self) -> dict:
        return {
            "dali_address": self.dali_address,
            "device_type": self.device_type,
            "device_type_name": self.device_type_name,
            "gtin": self.gtin,
            "firmware_version": self.firmware_version,
            "hardware_version": self.hardware_version,
            "serial_number": self.serial_number,
            "manufacturer": self.manufacturer,
            "operating_hours": self.operating_hours,
            "lamp_failure": self.lamp_failure,
            "lamp_power_on": self.lamp_power_on,
            "min_level": self.min_level,
            "max_level": self.max_level,
            "actual_level": self.actual_level,
            "discovered_at": self.discovered_at,
        }


@dataclass
class LightingGatewayInfo:
    """DALI gateway/controller information."""

    ip_address: str
    mac_address: Optional[str] = None
    firmware_version: Optional[str] = None
    model: Optional[str] = None
    manufacturer: Optional[str] = None
    dali_lines: int = 1
    devices_per_line: dict = field(default_factory=dict)
    total_devices: int = 0
    online: bool = False
    last_poll: Optional[str] = None

    def to_dict(self) -> dict:
        return {
            "ip_address": self.ip_address,
            "mac_address": self.mac_address,
            "firmware_version": self.firmware_version,
            "model": self.model,
            "manufacturer": self.manufacturer,
            "dali_lines": self.dali_lines,
            "devices_per_line": self.devices_per_line,
            "total_devices": self.total_devices,
            "online": self.online,
            "last_poll": self.last_poll,
        }


class LightingDiscoveryService:
    """Service for discovering DALI device information from gateways."""

    # Known DALI gateway manufacturers and their API patterns
    GATEWAY_TYPES = {
        "tridonic": {
            "port": 80,
            "info_endpoint": "/api/v1/system/info",
            "devices_endpoint": "/api/v1/dali/devices",
            "device_info_endpoint": "/api/v1/dali/device/{line}/{address}",
        },
        "philips": {
            "port": 8080,
            "info_endpoint": "/api/system",
            "devices_endpoint": "/api/dali/scan",
            "device_info_endpoint": "/api/dali/{line}/{address}/info",
        },
        "helvar": {
            "port": 50000,
            "info_endpoint": "/router/info",
            "devices_endpoint": "/dali/devices",
            "device_info_endpoint": "/dali/device/{line}/{address}",
        },
        "generic": {
            "port": 80,
            "info_endpoint": "/api/info",
            "devices_endpoint": "/api/dali/devices",
            "device_info_endpoint": "/api/dali/device/{line}/{address}",
        },
    }

    def __init__(
        self,
        gateway_ip: str,
        gateway_type: str = "generic",
        username: Optional[str] = None,
        password: Optional[str] = None,
        port: Optional[int] = None,
        timeout: float = 10.0,
    ):
        """Initialize DALI discovery service.

        Args:
            gateway_ip: IP address of the DALI gateway
            gateway_type: Type of gateway (tridonic, philips, helvar, generic)
            username: Optional username for authentication
            password: Optional password for authentication
            port: Optional port override
            timeout: HTTP request timeout
        """
        self.gateway_ip = gateway_ip
        self.gateway_type = gateway_type.lower()
        self.username = username
        self.password = password
        self.timeout = timeout

        config = self.GATEWAY_TYPES.get(self.gateway_type, self.GATEWAY_TYPES["generic"])
        self.port = port or config["port"]
        self.endpoints = config

        self.base_url = f"http://{gateway_ip}:{self.port}"

    async def _request(self, endpoint: str, method: str = "GET", **kwargs) -> Optional[dict]:
        """Make HTTP request to gateway.

        Args:
            endpoint: API endpoint path
            method: HTTP method
            **kwargs: Additional httpx request args

        Returns:
            JSON response or None on error
        """
        url = f"{self.base_url}{endpoint}"
        auth = (self.username, self.password) if self.username else None

        try:
            async with httpx.AsyncClient(timeout=self.timeout) as client:
                response = await client.request(method, url, auth=auth, **kwargs)
                response.raise_for_status()
                return response.json()
        except httpx.ConnectError:
            logger.warning(f"Cannot connect to DALI gateway at {self.gateway_ip}")
            return None
        except httpx.HTTPStatusError as e:
            logger.warning(f"HTTP error from DALI gateway: {e}")
            return None
        except Exception as e:
            logger.error(f"Error querying DALI gateway: {e}")
            return None

    async def get_gateway_info(self) -> Optional[LightingGatewayInfo]:
        """Get gateway/controller information.

        Returns:
            Gateway info or None if unavailable
        """
        data = await self._request(self.endpoints["info_endpoint"])

        if not data:
            # Try to at least verify gateway is reachable
            return LightingGatewayInfo(
                ip_address=self.gateway_ip, online=False, last_poll=datetime.utcnow().isoformat()
            )

        # Parse response based on gateway type
        if self.gateway_type == "tridonic":
            return LightingGatewayInfo(
                ip_address=self.gateway_ip,
                mac_address=data.get("mac"),
                firmware_version=data.get("firmware", data.get("version")),
                model=data.get("model", "Scenecom"),
                manufacturer="Tridonic",
                dali_lines=data.get("dali_lines", 1),
                total_devices=data.get("device_count", 0),
                online=True,
                last_poll=datetime.utcnow().isoformat(),
            )
        else:
            # Generic parsing
            return LightingGatewayInfo(
                ip_address=self.gateway_ip,
                mac_address=data.get("mac") or data.get("mac_address"),
                firmware_version=data.get("firmware") or data.get("version"),
                model=data.get("model"),
                manufacturer=data.get("manufacturer"),
                dali_lines=data.get("dali_lines", data.get("lines", 1)),
                total_devices=data.get("device_count", data.get("total_devices", 0)),
                online=True,
                last_poll=datetime.utcnow().isoformat(),
            )

    async def discover_devices(self, dali_line: int = 1) -> list[LightingDeviceInfo]:
        """Discover all devices on a DALI line.

        Args:
            dali_line: DALI line number (1-based)

        Returns:
            List of discovered device info
        """
        devices = []
        endpoint = self.endpoints["devices_endpoint"]

        if "{line}" in endpoint:
            endpoint = endpoint.format(line=dali_line)

        data = await self._request(endpoint)

        if not data:
            logger.info(f"No devices found or gateway unavailable for line {dali_line}")
            return devices

        # Parse device list
        device_list = data.get("devices", data) if isinstance(data, dict) else data

        for device_data in device_list:
            if isinstance(device_data, dict):
                device = self._parse_device_info(device_data, dali_line)
                if device:
                    devices.append(device)
            elif isinstance(device_data, int):
                # Just got address list, need to query each
                device = await self.get_device_info(dali_line, device_data)
                if device:
                    devices.append(device)

        return devices

    async def get_device_info(self, dali_line: int, dali_address: int) -> Optional[LightingDeviceInfo]:
        """Get detailed info for a specific DALI device.

        Args:
            dali_line: DALI line number (1-based)
            dali_address: DALI short address (0-63)

        Returns:
            Device info or None
        """
        endpoint = self.endpoints["device_info_endpoint"].format(line=dali_line, address=dali_address)

        data = await self._request(endpoint)

        if not data:
            return None

        return self._parse_device_info(data, dali_line, dali_address)

    def _parse_device_info(
        self, data: dict, dali_line: int, dali_address: Optional[int] = None
    ) -> Optional[LightingDeviceInfo]:
        """Parse device info from gateway response.

        Args:
            data: Raw response data
            dali_line: DALI line number
            dali_address: DALI address if known

        Returns:
            Parsed device info
        """
        address = dali_address or data.get("address", data.get("dali_address", 0))

        return LightingDeviceInfo(
            dali_address=address,
            device_type=data.get("device_type", data.get("type", 6)),  # Default to LED
            gtin=data.get("gtin") or data.get("product_code"),
            firmware_version=data.get("firmware") or data.get("fw_version"),
            hardware_version=data.get("hardware") or data.get("hw_version"),
            serial_number=data.get("serial") or data.get("serial_number"),
            manufacturer=data.get("manufacturer") or data.get("vendor"),
            operating_hours=data.get("operating_hours") or data.get("lamp_hours"),
            lamp_failure=data.get("lamp_failure", False) or data.get("fault", False),
            lamp_power_on=data.get("lamp_on", False) or data.get("power_on", False),
            min_level=data.get("min_level", 1),
            max_level=data.get("max_level", 254),
            actual_level=data.get("actual_level", data.get("level", 0)),
        )

    async def discover_and_save(
        self, equipment_code: str, dali_line: int = 1, dali_address: Optional[int] = None
    ) -> dict:
        """Discover device info and save to equipment metadata.

        Args:
            equipment_code: Equipment code to update (e.g., S002-DALI-L1-A)
            dali_line: DALI line number
            dali_address: Specific DALI address, or None to discover

        Returns:
            Discovery result with saved data
        """
        result = {
            "equipment_code": equipment_code,
            "gateway_ip": self.gateway_ip,
            "dali_line": dali_line,
            "status": "pending",
            "gateway_info": None,
            "device_info": None,
            "saved": False,
        }

        # Get gateway info
        gateway = await self.get_gateway_info()
        if gateway:
            result["gateway_info"] = gateway.to_dict()

        if not gateway or not gateway.online:
            result["status"] = "gateway_offline"
            return result

        # Discover device
        device = None
        if dali_address is not None:
            device = await self.get_device_info(dali_line, dali_address)
        else:
            # Try to find device on line
            devices = await self.discover_devices(dali_line)
            if devices:
                device = devices[0]  # Take first device

        if not device:
            result["status"] = "device_not_found"
            return result

        result["device_info"] = device.to_dict()

        # Save to database
        try:
            repo = EquipmentMetadataRepository()
            repo.update_from_discovery(
                equipment_id=equipment_code,
                network_info={
                    "gateway_ip": self.gateway_ip,
                    "gateway_type": self.gateway_type,
                    "dali_line": dali_line,
                    "dali_address": device.dali_address,
                    "mac_address": gateway.mac_address,
                },
                device_info={
                    "gtin": device.gtin,
                    "serial_number": device.serial_number,
                    "manufacturer": device.manufacturer or gateway.manufacturer,
                    "model": gateway.model,
                    "firmware_version": device.firmware_version or gateway.firmware_version,
                    "hardware_version": device.hardware_version,
                    "device_type": device.device_type_name,
                },
                operating_data={
                    "lamp_hours": device.operating_hours,
                    "lamp_failure": device.lamp_failure,
                    "actual_level": device.actual_level,
                    "min_level": device.min_level,
                    "max_level": device.max_level,
                },
            )
            result["saved"] = True
            result["status"] = "success"
        except Exception as e:
            logger.error(f"Failed to save discovery data: {e}")
            result["status"] = "save_failed"
            result["error"] = str(e)

        return result


# Simulated discovery for demo/testing when gateway not available
class SimulatedLightingDiscovery:
    """Simulated DALI discovery for demo mode."""

    # Sample device data for common DALI products
    SAMPLE_DEVICES = {
        "led_panel": {
            "gtin": "4008321951236",
            "manufacturer": "Tridonic",
            "model": "LC 40W 900mA",
            "firmware_version": "2.1.0",
            "hardware_version": "1.0",
            "device_type": 6,
            "lamp_hours_base": 8000,
        },
        "led_downlight": {
            "gtin": "4008321963147",
            "manufacturer": "Tridonic",
            "model": "LC 25W 700mA",
            "firmware_version": "2.0.3",
            "hardware_version": "1.1",
            "device_type": 6,
            "lamp_hours_base": 12000,
        },
        "emergency": {
            "gtin": "4008321854269",
            "manufacturer": "Tridonic",
            "model": "EM powerLED 3W",
            "firmware_version": "1.5.2",
            "hardware_version": "2.0",
            "device_type": 1,
            "lamp_hours_base": 5000,
        },
    }

    @classmethod
    def generate_device_info(cls, equipment_code: str, device_type: str = "led_panel", dali_address: int = 1) -> dict:
        """Generate simulated device info.

        Args:
            equipment_code: Equipment code for serial generation
            device_type: Type of device (led_panel, led_downlight, emergency)
            dali_address: DALI address

        Returns:
            Simulated device info dict
        """
        import hashlib
        import random

        base = cls.SAMPLE_DEVICES.get(device_type, cls.SAMPLE_DEVICES["led_panel"])

        # Generate consistent serial from equipment code
        hash_input = f"{equipment_code}-{dali_address}"
        serial_hash = hashlib.md5(hash_input.encode(), usedforsecurity=False).hexdigest()[:12].upper()
        serial = f"TRI{serial_hash}"

        # Randomize lamp hours within range
        lamp_hours = base["lamp_hours_base"] + random.randint(-2000, 5000)

        return {
            "network_info": {
                "gateway_ip": "192.168.10.50",
                "gateway_type": "tridonic",
                "dali_line": 1,
                "dali_address": dali_address,
                "mac_address": f"00:1A:2B:{serial_hash[:2]}:{serial_hash[2:4]}:{serial_hash[4:6]}",
            },
            "device_info": {
                "gtin": base["gtin"],
                "serial_number": serial,
                "manufacturer": base["manufacturer"],
                "model": base["model"],
                "firmware_version": base["firmware_version"],
                "hardware_version": base["hardware_version"],
                "device_type": f"DALI Type {base['device_type']} - LED Module",
            },
            "operating_data": {
                "lamp_hours": lamp_hours,
                "lamp_failure": False,
                "actual_level": random.randint(100, 254),
                "min_level": 10,
                "max_level": 254,
                "power_cycles": lamp_hours // 8,  # Approximate
            },
        }
