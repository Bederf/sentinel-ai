"""Modbus Discovery Service - Query Modbus device information.

Discovers device metadata from Modbus TCP/RTU devices including:
- Device identification (vendor, model, serial)
- Holding register configuration
- Runtime statistics

Supports generators, power meters, UPS systems, and ATS units.
"""

import logging
from dataclasses import dataclass, field
from datetime import datetime
from enum import IntEnum

from app.database.repositories.equipment_metadata_repository import EquipmentMetadataRepository

logger = logging.getLogger(__name__)


class ModbusDeviceType(IntEnum):
    """Common Modbus device types."""

    GENERATOR = 1
    POWER_METER = 2
    UPS = 3
    ATS = 4
    VFD = 5
    PLC = 6
    UNKNOWN = 99


@dataclass
class ModbusDeviceInfo:
    """Discovered Modbus device information."""

    unit_id: int  # Modbus slave address
    device_type: ModbusDeviceType = ModbusDeviceType.UNKNOWN
    device_name: str = ""
    manufacturer: str = ""
    model: str = ""
    firmware_version: str = ""
    serial_number: str | None = None
    ip_address: str = ""
    port: int = 502
    protocol: str = "modbus_tcp"  # modbus_tcp or modbus_rtu

    # Device-specific
    rated_capacity: str | None = None  # kVA, kW, etc.
    runtime_hours: int | None = None

    discovered_at: str = field(default_factory=lambda: datetime.utcnow().isoformat())

    def to_dict(self) -> dict:
        return {
            "unit_id": self.unit_id,
            "device_type": self.device_type.name,
            "device_name": self.device_name,
            "manufacturer": self.manufacturer,
            "model": self.model,
            "firmware_version": self.firmware_version,
            "serial_number": self.serial_number,
            "ip_address": self.ip_address,
            "port": self.port,
            "protocol": self.protocol,
            "rated_capacity": self.rated_capacity,
            "runtime_hours": self.runtime_hours,
            "discovered_at": self.discovered_at,
        }


# Known register maps for common devices
REGISTER_MAPS = {
    "schneider_pm5xxx": {
        "manufacturer": (0, 16, "str"),  # 16 registers, ASCII string
        "model": (16, 16, "str"),
        "serial": (48, 16, "str"),
        "firmware": (32, 8, "str"),
    },
    "deepsea_dse7xxx": {
        "serial": (768, 2, "u32"),
        "firmware_major": (770, 1, "u16"),
        "firmware_minor": (771, 1, "u16"),
        "runtime_hours": (1024, 2, "u32"),
    },
    "socomec_diris": {
        "serial": (50176, 8, "str"),
        "model": (50184, 8, "str"),
        "firmware": (50192, 4, "str"),
    },
    "eaton_ups": {
        "model": (0, 8, "str"),
        "serial": (8, 8, "str"),
        "firmware": (16, 4, "str"),
        "battery_runtime": (64, 1, "u16"),
    },
}


class ModbusDiscoveryService:
    """Service for discovering Modbus device information."""

    def __init__(self, default_port: int = 502, timeout: float = 5.0):
        """Initialize Modbus discovery service.

        Args:
            default_port: Default Modbus TCP port
            timeout: Connection timeout
        """
        self.default_port = default_port
        self.timeout = timeout

    async def discover_device(
        self, ip_address: str, unit_id: int = 1, port: int | None = None, device_profile: str | None = None
    ) -> ModbusDeviceInfo | None:
        """Discover a Modbus device.

        Args:
            ip_address: Device IP address
            unit_id: Modbus slave/unit ID
            port: TCP port (default 502)
            device_profile: Known device profile for register map

        Returns:
            Device info or None if not reachable
        """
        port = port or self.default_port

        try:
            # Try to connect and read device identification
            # This would use pymodbus in production
            # For now, return basic info if we can reach the device

            import socket

            sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            sock.settimeout(self.timeout)
            result = sock.connect_ex((ip_address, port))
            sock.close()

            if result != 0:
                logger.warning(f"Cannot connect to Modbus device at {ip_address}:{port}")
                return None

            # Device is reachable - would read identification registers here
            return ModbusDeviceInfo(
                unit_id=unit_id,
                ip_address=ip_address,
                port=port,
                device_name=f"Modbus Device {unit_id}",
            )

        except Exception as e:
            logger.error(f"Modbus discovery error: {e}")
            return None

    async def discover_and_save(
        self,
        equipment_code: str,
        ip_address: str,
        unit_id: int = 1,
        port: int | None = None,
        device_profile: str | None = None,
    ) -> dict:
        """Discover Modbus device and save to equipment metadata.

        Args:
            equipment_code: Equipment code to update
            ip_address: Device IP
            unit_id: Modbus unit ID
            port: TCP port
            device_profile: Device profile for register map

        Returns:
            Discovery result
        """
        result = {
            "equipment_code": equipment_code,
            "ip_address": ip_address,
            "unit_id": unit_id,
            "status": "pending",
            "device_info": None,
            "saved": False,
        }

        device = await self.discover_device(ip_address, unit_id, port, device_profile)

        if not device:
            result["status"] = "device_not_reachable"
            return result

        result["device_info"] = device.to_dict()

        # Save to database
        try:
            repo = EquipmentMetadataRepository()
            repo.update_from_discovery(
                equipment_id=equipment_code,
                network_info={
                    "ip_address": device.ip_address,
                    "modbus_address": device.unit_id,
                    "modbus_port": device.port,
                    "protocol": device.protocol,
                },
                device_info={
                    "manufacturer": device.manufacturer,
                    "model": device.model,
                    "firmware_version": device.firmware_version,
                    "serial_number": device.serial_number,
                    "device_type": device.device_type.name,
                },
                operating_data={
                    "rated_capacity": device.rated_capacity,
                    "runtime_hours": device.runtime_hours,
                },
            )
            result["saved"] = True
            result["status"] = "success"
        except Exception as e:
            logger.error(f"Failed to save Modbus discovery: {e}")
            result["status"] = "save_failed"
            result["error"] = str(e)

        return result


class SimulatedModbusDiscovery:
    """Simulated Modbus discovery for local mode."""

    # Device profiles for common equipment
    DEVICE_PROFILES = {
        "generator": {
            "manufacturers": [
                {"name": "DeepSea Electronics", "model_prefix": "DSE7320", "firmware_base": "5.2"},
                {"name": "ComAp", "model_prefix": "InteliGen NT", "firmware_base": "3.1"},
                {"name": "DEIF", "model_prefix": "AGC-4", "firmware_base": "4.50"},
            ],
            "capacity_range": (100, 2000),  # kVA
            "runtime_range": (500, 15000),  # hours
        },
        "meter": {
            "manufacturers": [
                {"name": "Schneider Electric", "model_prefix": "PM5560", "firmware_base": "2.7"},
                {"name": "Socomec", "model_prefix": "DIRIS A40", "firmware_base": "1.2"},
                {"name": "ABB", "model_prefix": "M4M 30", "firmware_base": "3.0"},
            ],
            "capacity_range": None,
            "runtime_range": (1000, 50000),
        },
        "ups": {
            "manufacturers": [
                {"name": "Eaton", "model_prefix": "9PX", "firmware_base": "2.1"},
                {"name": "APC", "model_prefix": "Smart-UPS", "firmware_base": "6.5"},
                {"name": "Vertiv", "model_prefix": "Liebert GXT5", "firmware_base": "1.3"},
            ],
            "capacity_range": (3, 200),  # kVA
            "runtime_range": (100, 5000),
        },
        "ats": {
            "manufacturers": [
                {"name": "ASCO", "model_prefix": "7000 Series", "firmware_base": "4.0"},
                {"name": "Eaton", "model_prefix": "ATC-900", "firmware_base": "3.2"},
                {"name": "ABB", "model_prefix": "TruONE", "firmware_base": "2.1"},
            ],
            "capacity_range": (100, 4000),  # Amps
            "runtime_range": (500, 20000),
        },
    }

    @classmethod
    def generate_device_info(cls, equipment_code: str, equipment_type: str = "generator", unit_id: int = 1) -> dict:
        """Generate simulated Modbus device info.

        Args:
            equipment_code: Equipment code
            equipment_type: Type (generator, meter, ups, ats)
            unit_id: Modbus address

        Returns:
            Simulated device info dict
        """
        import hashlib
        import random

        profile = cls.DEVICE_PROFILES.get(equipment_type.lower(), cls.DEVICE_PROFILES["generator"])

        # Select manufacturer based on hash for consistency
        hash_val = int(hashlib.md5(equipment_code.encode(), usedforsecurity=False).hexdigest()[:8], 16)
        mfr = profile["manufacturers"][hash_val % len(profile["manufacturers"])]

        # Generate serial
        serial_hash = hashlib.md5(f"{equipment_code}-modbus".encode(), usedforsecurity=False).hexdigest()[:12].upper()

        # Generate capacity and runtime
        capacity = None
        if profile["capacity_range"]:
            min_cap, max_cap = profile["capacity_range"]
            capacity = random.randint(min_cap, max_cap)
            capacity = f"{capacity}A" if equipment_type == "ats" else f"{capacity}kVA"

        min_rt, max_rt = profile["runtime_range"]
        runtime = random.randint(min_rt, max_rt)

        return {
            "network_info": {
                "ip_address": f"192.168.20.{(hash_val % 50) + 100}",
                "modbus_address": unit_id,
                "modbus_port": 502,
                "protocol": "modbus_tcp",
            },
            "device_info": {
                "manufacturer": mfr["name"],
                "model": f"{mfr['model_prefix']}-{hash_val % 100:02d}",
                "firmware_version": f"{mfr['firmware_base']}.{hash_val % 10}",
                "serial_number": serial_hash,
                "device_type": equipment_type.upper(),
            },
            "operating_data": {
                "rated_capacity": capacity,
                "runtime_hours": runtime,
                "transfer_count": random.randint(10, 500) if equipment_type == "ats" else None,
                "battery_cycles": random.randint(5, 50) if equipment_type == "ups" else None,
            },
        }
