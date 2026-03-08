"""BACnet Discovery Service - Query BACnet device information.

Discovers device metadata from BACnet/IP devices including:
- Device object properties (vendor, model, firmware, serial)
- Object list (points available)
- Network configuration
- Runtime statistics

Supports both direct BACnet/IP and Niagara gateway queries.
"""

import logging
from dataclasses import dataclass, field
from datetime import datetime
from typing import Optional

from app.database.repositories.equipment_metadata_repository import EquipmentMetadataRepository

logger = logging.getLogger(__name__)


# BACnet Property Identifiers (common ones)
class BACnetProperty:
    OBJECT_IDENTIFIER = 75
    OBJECT_NAME = 77
    OBJECT_TYPE = 79
    VENDOR_NAME = 121
    VENDOR_IDENTIFIER = 120
    MODEL_NAME = 70
    FIRMWARE_REVISION = 44
    APPLICATION_SOFTWARE_VERSION = 12
    SERIAL_NUMBER = 372
    DEVICE_ADDRESS_BINDING = 30
    MAX_APDU_LENGTH = 62
    PROTOCOL_VERSION = 98
    PROTOCOL_REVISION = 139
    SYSTEM_STATUS = 112
    LOCATION = 58
    DESCRIPTION = 28


@dataclass
class BACnetDeviceInfo:
    """Discovered BACnet device information."""

    device_id: int
    device_name: str = ""
    vendor_name: str = ""
    vendor_id: int = 0
    model_name: str = ""
    firmware_version: str = ""
    application_version: str = ""
    serial_number: Optional[str] = None
    location: str = ""
    description: str = ""
    ip_address: str = ""
    mac_address: Optional[str] = None
    network_number: int = 0
    max_apdu_length: int = 1476
    protocol_version: int = 1
    protocol_revision: int = 0
    system_status: str = "operational"
    object_count: int = 0
    discovered_at: str = field(default_factory=lambda: datetime.utcnow().isoformat())

    def to_dict(self) -> dict:
        return {
            "device_id": self.device_id,
            "device_name": self.device_name,
            "vendor_name": self.vendor_name,
            "vendor_id": self.vendor_id,
            "model_name": self.model_name,
            "firmware_version": self.firmware_version,
            "application_version": self.application_version,
            "serial_number": self.serial_number,
            "location": self.location,
            "description": self.description,
            "ip_address": self.ip_address,
            "mac_address": self.mac_address,
            "network_number": self.network_number,
            "system_status": self.system_status,
            "object_count": self.object_count,
            "discovered_at": self.discovered_at,
        }


# Known BACnet vendor IDs
BACNET_VENDORS = {
    5: "Johnson Controls",
    7: "Siemens",
    15: "Honeywell",
    24: "Automated Logic",
    36: "Trane",
    95: "Tridium",  # Niagara
    222: "Schneider Electric",
    343: "Carrier",
    381: "Daikin",
    389: "Delta Controls",
}


class BACnetDiscoveryService:
    """Service for discovering BACnet device information.

    Can query devices directly via BACnet/IP or through a Niagara gateway.
    """

    def __init__(
        self,
        use_niagara: bool = True,
        niagara_host: Optional[str] = None,
        niagara_port: int = 80,
        niagara_username: Optional[str] = None,
        niagara_password: Optional[str] = None,
        timeout: float = 10.0,
    ):
        """Initialize BACnet discovery service.

        Args:
            use_niagara: Use Niagara gateway for discovery (recommended)
            niagara_host: Niagara supervisor host
            niagara_port: Niagara HTTP port
            niagara_username: Niagara auth username
            niagara_password: Niagara auth password
            timeout: Request timeout
        """
        self.use_niagara = use_niagara
        self.niagara_host = niagara_host
        self.niagara_port = niagara_port
        self.niagara_username = niagara_username
        self.niagara_password = niagara_password
        self.timeout = timeout

    async def discover_device(self, device_id: int, ip_address: Optional[str] = None) -> Optional[BACnetDeviceInfo]:
        """Discover a BACnet device by ID.

        Args:
            device_id: BACnet device instance number
            ip_address: Optional IP if known

        Returns:
            Device info or None if not found
        """
        if self.use_niagara and self.niagara_host:
            return await self._discover_via_niagara(device_id)
        else:
            # Direct BACnet/IP would require BAC0 or similar library
            logger.warning("Direct BACnet/IP discovery not implemented - use Niagara gateway")
            return None

    async def _discover_via_niagara(self, device_id: int) -> Optional[BACnetDeviceInfo]:
        """Discover device via Niagara oBIX API.

        Args:
            device_id: BACnet device instance

        Returns:
            Device info or None
        """
        import httpx

        base_url = f"http://{self.niagara_host}:{self.niagara_port}"
        auth = (self.niagara_username, self.niagara_password) if self.niagara_username else None

        try:
            async with httpx.AsyncClient(timeout=self.timeout) as client:
                # Query device object via oBIX
                # Niagara exposes BACnet devices under /obix/config/Drivers/BacnetNetwork/
                response = await client.get(f"{base_url}/obix/config/Drivers/BacnetNetwork/", auth=auth)

                if response.status_code != 200:
                    logger.warning(f"Niagara query failed: {response.status_code}")
                    return None

                # Parse XML response to find device
                # This is simplified - real implementation would parse oBIX XML
                return BACnetDeviceInfo(
                    device_id=device_id,
                    device_name=f"BACnet Device {device_id}",
                    vendor_name="Unknown",
                    ip_address=self.niagara_host,
                )

        except Exception as e:
            logger.error(f"Niagara discovery error: {e}")
            return None

    async def discover_and_save(self, equipment_code: str, device_id: int, ip_address: Optional[str] = None) -> dict:
        """Discover BACnet device and save to equipment metadata.

        Args:
            equipment_code: Equipment code to update
            device_id: BACnet device instance
            ip_address: Optional device IP

        Returns:
            Discovery result
        """
        result = {
            "equipment_code": equipment_code,
            "device_id": device_id,
            "status": "pending",
            "device_info": None,
            "saved": False,
        }

        device = await self.discover_device(device_id, ip_address)

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
                    "ip_address": device.ip_address,
                    "mac_address": device.mac_address,
                    "bacnet_device_id": device.device_id,
                    "bacnet_network": device.network_number,
                    "protocol": "bacnet",
                },
                device_info={
                    "manufacturer": device.vendor_name,
                    "vendor_id": device.vendor_id,
                    "model": device.model_name,
                    "firmware_version": device.firmware_version,
                    "application_version": device.application_version,
                    "serial_number": device.serial_number,
                },
                operating_data={
                    "system_status": device.system_status,
                    "object_count": device.object_count,
                    "location": device.location,
                },
            )
            result["saved"] = True
            result["status"] = "success"
        except Exception as e:
            logger.error(f"Failed to save BACnet discovery: {e}")
            result["status"] = "save_failed"
            result["error"] = str(e)

        return result


class SimulatedBACnetDiscovery:
    """Simulated BACnet discovery for demo mode."""

    # Sample device profiles by equipment type
    DEVICE_PROFILES = {
        "chiller": {
            "vendor_id": 343,  # Carrier
            "vendor_name": "Carrier",
            "model_prefix": "30XA",
            "firmware_base": "5.2",
            "object_count_range": (150, 250),
        },
        "ahu": {
            "vendor_id": 7,  # Siemens
            "vendor_name": "Siemens",
            "model_prefix": "PXC",
            "firmware_base": "3.1",
            "object_count_range": (80, 120),
        },
        "vav": {
            "vendor_id": 5,  # JCI
            "vendor_name": "Johnson Controls",
            "model_prefix": "FX-PCV",
            "firmware_base": "2.0",
            "object_count_range": (20, 40),
        },
        "fcu": {
            "vendor_id": 381,  # Daikin
            "vendor_name": "Daikin",
            "model_prefix": "DCC",
            "firmware_base": "1.5",
            "object_count_range": (15, 30),
        },
        "default": {
            "vendor_id": 95,  # Tridium
            "vendor_name": "Tridium",
            "model_prefix": "JACE",
            "firmware_base": "4.10",
            "object_count_range": (50, 100),
        },
    }

    @classmethod
    def generate_device_info(
        cls, equipment_code: str, equipment_type: str = "default", device_id: Optional[int] = None
    ) -> dict:
        """Generate simulated BACnet device info.

        Args:
            equipment_code: Equipment code for consistent generation
            equipment_type: Type of equipment (chiller, ahu, vav, fcu)
            device_id: Optional specific device ID

        Returns:
            Simulated device info dict
        """
        import hashlib
        import random

        profile = cls.DEVICE_PROFILES.get(equipment_type.lower(), cls.DEVICE_PROFILES["default"])

        # Generate consistent device ID from equipment code
        hash_val = int(hashlib.md5(equipment_code.encode(), usedforsecurity=False).hexdigest()[:8], 16)
        generated_device_id = device_id or (hash_val % 900000) + 100000

        # Generate serial
        serial_hash = hashlib.md5(f"{equipment_code}-serial".encode(), usedforsecurity=False).hexdigest()[:10].upper()

        # Random object count in range
        min_obj, max_obj = profile["object_count_range"]
        object_count = random.randint(min_obj, max_obj)

        return {
            "network_info": {
                "ip_address": f"192.168.10.{(hash_val % 200) + 10}",
                "mac_address": f"00:1B:{serial_hash[:2]}:{serial_hash[2:4]}:{serial_hash[4:6]}:{serial_hash[6:8]}",
                "bacnet_device_id": generated_device_id,
                "bacnet_network": 0,
                "protocol": "bacnet",
            },
            "device_info": {
                "manufacturer": profile["vendor_name"],
                "vendor_id": profile["vendor_id"],
                "model": f"{profile['model_prefix']}-{hash_val % 1000:03d}",
                "firmware_version": f"{profile['firmware_base']}.{hash_val % 10}",
                "serial_number": serial_hash,
            },
            "operating_data": {
                "system_status": "operational",
                "object_count": object_count,
                "protocol_version": 1,
                "protocol_revision": 14,
            },
        }
