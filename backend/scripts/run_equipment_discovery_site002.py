#!/usr/bin/env python3
"""
Equipment Discovery Runner for Site-002

Bulk discovers all equipment for site-002, populating metadata including:
- Device info (manufacturer, model, serial)
- Network info (DALI address, BACnet device ID, IP)
- Operating data (lamp hours, power cycles, fault count)
- Commissioning dates

Uses simulated data to avoid network dependencies.
"""

import sys
import asyncio

# Add backend to path
sys.path.insert(0, "/opt/bms-intelligence/backend")

from app.database.repositories.site_repository import SiteRepository  # noqa: E402
from app.services.lighting_discovery_service import SimulatedLightingDiscovery  # noqa: E402
from app.services.bacnet_discovery_service import SimulatedBACnetDiscovery  # noqa: E402
from app.services.modbus_discovery_service import SimulatedModbusDiscovery  # noqa: E402
from app.database.repositories.equipment_metadata_repository import EquipmentMetadataRepository  # noqa: E402


def detect_protocol(equipment_code: str, equipment_type: str) -> str:
    """Detect protocol from equipment code or type."""
    code_upper = equipment_code.upper()
    _type_upper = (equipment_type or "").upper()

    # DALI - lighting equipment
    if any(x in code_upper for x in ["DALI", "LUM", "LIGHT"]):
        return "dali"

    # Modbus - electrical equipment
    if any(x in code_upper for x in ["GEN", "UPS", "ATS", "MTR", "METER", "MSB", "DB"]):
        return "modbus"

    # BACnet - HVAC and most other equipment
    if any(x in code_upper for x in ["CHILLER", "AHU", "FCU", "VAV", "CT", "PUMP", "BOILER"]):
        return "bacnet"

    # Default to BACnet
    return "bacnet"


def get_simulated_data(equipment_code: str, protocol: str, equipment_type: str) -> dict:
    """Get simulated discovery data for equipment."""
    if protocol == "dali":
        device_type = "led_panel"
        if "EMERG" in equipment_code.upper():
            device_type = "emergency"
        elif "DOWN" in equipment_code.upper():
            device_type = "led_downlight"

        return SimulatedLightingDiscovery.generate_device_info(
            equipment_code=equipment_code,
            device_type=device_type,
            dali_address=1,
        )
    elif protocol == "modbus":
        modbus_type = "generator"
        if equipment_type.lower() in ["ups", "ats", "meter"]:
            modbus_type = equipment_type.lower()

        return SimulatedModbusDiscovery.generate_device_info(
            equipment_code=equipment_code,
            equipment_type=modbus_type,
            unit_id=1,
        )
    else:  # bacnet
        return SimulatedBACnetDiscovery.generate_device_info(
            equipment_code=equipment_code,
            equipment_type=equipment_type,
        )


async def discover_equipment_for_site(site_code: str):
    """Discover all equipment for a site using simulated data."""

    print(f"\n📡 Starting equipment discovery for {site_code}...")

    # Get building
    building_repo = SiteRepository()
    building = building_repo.get_by_id(site_code)
    if not building:
        print(f"❌ Site {site_code} not found")
        return

    _site_uuid = building["id"]
    print(f"✅ Found site: {building['name']}")

    # Get all equipment
    equipment_list = building_repo.get_equipment(site_code)
    print(f"📦 Found {len(equipment_list)} equipment items")

    if not equipment_list:
        print("❌ No equipment found")
        return

    # Discover each equipment
    metadata_repo = EquipmentMetadataRepository()
    success_count = 0
    error_count = 0

    for idx, equipment in enumerate(equipment_list, 1):
        eq_code = equipment.get("code")
        eq_type = equipment.get("type")
        _eq_name = equipment.get("name")
        eq_id = equipment.get("id")

        try:
            # Determine protocol
            protocol = detect_protocol(eq_code, eq_type)

            # Get simulated data
            discovery_data = get_simulated_data(eq_code, protocol, eq_type)

            if not discovery_data:
                print(f"⚠️  [{idx:2d}/{len(equipment_list)}] {eq_code} - No discovery data")
                error_count += 1
                continue

            # Update equipment metadata
            network_info = discovery_data.get("network_info")
            device_info = discovery_data.get("device_info")
            operating_data = discovery_data.get("operating_data")

            metadata_repo.update_from_discovery(
                equipment_id=eq_id, network_info=network_info, device_info=device_info, operating_data=operating_data
            )

            # Extract useful info for display
            protocol_info = f"[{protocol.upper()}]"
            if device_info:
                if device_info.get("manufacturer"):
                    protocol_info += f" {device_info['manufacturer']}"
                if device_info.get("model"):
                    protocol_info += f" {device_info['model']}"

            print(f"✅ [{idx:2d}/{len(equipment_list)}] {eq_code:<25} {protocol_info}")
            success_count += 1

        except Exception as e:
            print(f"❌ [{idx:2d}/{len(equipment_list)}] {eq_code} - Error: {str(e)}")
            error_count += 1

    # Summary
    print(f"\n📊 Discovery Summary for {site_code}:")
    print(f"   ✅ Successful: {success_count}/{len(equipment_list)}")
    print(f"   ❌ Failed:     {error_count}/{len(equipment_list)}")
    print(f"   Success Rate: {success_count * 100 // len(equipment_list)}%")

    if success_count > 0:
        print("\n✨ Equipment metadata has been populated!")
        print("   - Device info (manufacturer, model, serial)")
        print("   - Network info (IP, DALI address, BACnet device ID)")
        print("   - Operating data (lamp hours, power cycles, fault count)")
        print("\n🔄 Equipment Age and Alarms should now display in the dashboard!")


if __name__ == "__main__":
    site_code = sys.argv[1] if len(sys.argv) > 1 else "site-002"
    asyncio.run(discover_equipment_for_site(site_code))
