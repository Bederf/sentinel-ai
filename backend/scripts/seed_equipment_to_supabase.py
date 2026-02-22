#!/usr/bin/env python3
"""
Seed all equipment, zones, and buildings data from JSON files to Supabase.

This script:
1. Loads all buildings from data/buildings/{site-code}/building.json
2. Creates/updates buildings in Supabase
3. Loads all equipment from data/buildings/{site-code}/equipment/*.json
4. Creates/updates equipment in Supabase
5. Loads all zones from data/buildings/{site-code}/zones.json
6. Creates/updates zones in Supabase

Run: python backend/scripts/seed_equipment_to_supabase.py
"""

import sys
import json
from pathlib import Path
import uuid
from dotenv import load_dotenv

# Load environment variables from .env
load_dotenv(Path(__file__).parent.parent / ".env")

sys.path.insert(0, "/opt/bms-intelligence/backend")

from app.database.supabase_client import get_supabase_client

DATA_PATH = Path("/opt/bms-intelligence/backend/app/data")
BUILDINGS_PATH = DATA_PATH / "buildings"


def get_or_create_building(client, site_code: str, building_data: dict) -> str:
    """Get or create building in Supabase. Returns building UUID."""
    try:
        # Check if building already exists
        result = client.table("buildings").select("id").eq("code", site_code).execute()

        if result.data:
            building_uuid = result.data[0]["id"]
            print(f"  ✓ Building {site_code} already exists (UUID: {building_uuid[:8]}...)")
            return building_uuid

        # Create new building
        building_uuid = str(uuid.uuid4())

        insert_data = {
            "id": building_uuid,
            "code": site_code,
            "name": building_data.get("name", building_data.get("display_name", site_code)),
            "address": building_data.get("address", ""),
            "region": "Unknown",
            "type": "office",
            "sqm": 0,
            "floors": len(building_data.get("floors", [])),
            "year_built": 2020,
        }

        client.table("buildings").insert(insert_data).execute()
        print(f"  ✓ Created building {site_code} (UUID: {building_uuid[:8]}...)")

        return building_uuid

    except Exception as e:
        print(f"  ✗ ERROR creating building {site_code}: {e}")
        return None


def _map_equipment_status(status_value):
    """Map equipment status to valid database values.

    Equipment table only allows: 'normal', 'warning', 'critical', 'offline', 'maintenance'
    """
    if not status_value:
        return "normal"

    status_lower = str(status_value).lower().strip()

    # Direct mappings
    valid_statuses = {"normal", "warning", "critical", "offline", "maintenance"}
    if status_lower in valid_statuses:
        return status_lower

    # Smart mapping from common values
    mappings = {
        "online": "normal",
        "operational": "normal",
        "active": "normal",
        "running": "normal",
        "enabled": "normal",
        "ok": "normal",
        "healthy": "normal",
        "good": "normal",
        "offline": "offline",
        "down": "offline",
        "disconnected": "offline",
        "not responding": "offline",
        "degraded": "warning",
        "warning": "warning",
        "caution": "warning",
        "alert": "warning",
        "moderate": "warning",
        "critical": "critical",
        "error": "critical",
        "failed": "critical",
        "fault": "critical",
        "emergency": "critical",
        "maintenance": "maintenance",
        "servicing": "maintenance",
        "standby": "maintenance",
        "idle": "maintenance",
        "unknown": "normal",
    }

    return mappings.get(status_lower, "normal")


def seed_equipment_for_site(client, site_code: str, building_uuid: str) -> int:
    """
    Seed all equipment for a site from equipment/*.json files.
    Returns count of equipment created/updated.
    """
    site_path = BUILDINGS_PATH / site_code
    equipment_dir = site_path / "equipment"

    if not equipment_dir.exists():
        print(f"    ⓘ No equipment directory for {site_code}")
        return 0

    count = 0
    equipment_files = sorted(list(equipment_dir.glob("*.json")))

    for eq_file in equipment_files:
        try:
            with open(eq_file) as f:
                eq_data = json.load(f)

            equipment_code = eq_data.get("code") or eq_data.get("id")

            # Skip if no code
            if not equipment_code:
                print(f"    ⓘ Skipping {eq_file.name}: no code found")
                continue

            equipment_name = eq_data.get("name", equipment_code)
            equipment_type = eq_data.get("type", "unknown")

            # Map status to valid value
            mapped_status = _map_equipment_status(eq_data.get("status"))

            # Check if equipment already exists
            result = client.table("equipment").select("id").eq("code", equipment_code).execute()

            if result.data:
                # Update existing
                eq_uuid = result.data[0]["id"]
                client.table("equipment").update(
                    {
                        "name": equipment_name,
                        "type": equipment_type,
                        "status": mapped_status,
                        "health_score": eq_data.get("health_score", 85),
                        "location": eq_data.get("location", ""),
                        "manufacturer": eq_data.get("manufacturer", ""),
                        "model": eq_data.get("model", ""),
                    }
                ).eq("id", eq_uuid).execute()
            else:
                # Create new
                eq_uuid = str(uuid.uuid4())
                client.table("equipment").insert(
                    {
                        "id": eq_uuid,
                        "code": equipment_code,
                        "building_id": building_uuid,
                        "name": equipment_name,
                        "type": equipment_type,
                        "status": mapped_status,
                        "health_score": eq_data.get("health_score", 85),
                        "location": eq_data.get("location", ""),
                        "manufacturer": eq_data.get("manufacturer", ""),
                        "model": eq_data.get("model", ""),
                        "capacity": eq_data.get("capacity", ""),
                        "serial_number": eq_data.get("serial_number", ""),
                        "install_date": eq_data.get("install_date"),
                        "last_service": eq_data.get("last_service"),
                    }
                ).execute()

            count += 1

        except Exception as e:
            print(f"    ✗ ERROR processing {eq_file.name}: {e}")

    print(f"  ✓ Seeded {count} equipment items for {site_code}")
    return count


def _map_zone_status(status_value):
    """Map zone status to valid database values.

    HVAC zones table allows: 'running', 'idle', 'heating', 'cooling', 'fault', 'offline'
    """
    if not status_value:
        return "idle"

    status_lower = str(status_value).lower().strip()

    valid_statuses = {"running", "idle", "heating", "cooling", "fault", "offline"}
    if status_lower in valid_statuses:
        return status_lower

    # Smart mapping
    mappings = {
        "active": "running",
        "on": "running",
        "enabled": "running",
        "standby": "idle",
        "off": "idle",
        "disabled": "idle",
        "error": "fault",
        "down": "offline",
        "normal": "idle",
    }

    return mappings.get(status_lower, "idle")


def seed_zones_for_site(client, site_code: str, building_uuid: str) -> int:
    """
    Seed all HVAC zones for a site from zones.json.
    Returns count of zones created/updated.
    """
    site_path = BUILDINGS_PATH / site_code
    zones_file = site_path / "zones.json"

    if not zones_file.exists():
        print(f"    ⓘ No zones.json for {site_code}")
        return 0

    try:
        with open(zones_file) as f:
            zones_data = json.load(f)

        if not isinstance(zones_data, list):
            print(f"    ⓘ Invalid zones.json format for {site_code}")
            return 0

        count = 0

        for zone in zones_data:
            try:
                zone_id = zone.get("zone_id")
                zone_name = zone.get("zone_name", zone_id)

                if not zone_id:
                    print("    ⓘ Skipping zone with no zone_id")
                    continue

                # Map status to valid value
                mapped_status = _map_zone_status(zone.get("status"))

                # Check if zone already exists
                result = client.table("hvac_zones").select("id").eq("zone_id", zone_id).execute()

                if result.data:
                    # Update existing
                    zone_uuid = result.data[0]["id"]
                    client.table("hvac_zones").update(
                        {
                            "zone_name": zone_name,
                            "floor": zone.get("floor", ""),
                            "current_temp": zone.get("current_temp"),
                            "setpoint": zone.get("setpoint"),
                            "status": mapped_status,
                        }
                    ).eq("id", zone_uuid).execute()
                else:
                    # Create new
                    zone_uuid = str(uuid.uuid4())
                    client.table("hvac_zones").insert(
                        {
                            "id": zone_uuid,
                            "zone_id": zone_id,
                            "zone_name": zone_name,
                            "building_id": building_uuid,
                            "floor": zone.get("floor", ""),
                            "current_temp": zone.get("current_temp"),
                            "setpoint": zone.get("setpoint"),
                            "status": mapped_status,
                        }
                    ).execute()

                count += 1

            except Exception as e:
                print(f"    ✗ ERROR processing zone {zone.get('zone_id')}: {e}")

        if count > 0:
            print(f"  ✓ Seeded {count} HVAC zones for {site_code}")

        return count

    except Exception as e:
        print(f"  ✗ ERROR reading zones.json for {site_code}: {e}")
        return 0


def main():
    """Main seeding function."""
    print("=" * 80)
    print("SEEDING SUPABASE WITH EQUIPMENT & ZONES DATA FROM JSON FILES")
    print("=" * 80)

    try:
        client = get_supabase_client()
        print("✓ Connected to Supabase\n")
    except Exception as e:
        print(f"✗ FAILED to connect to Supabase: {e}")
        print("\nMake sure:")
        print("  1. Supabase is running: supabase start")
        print("  2. DATABASE_URL is set in .env")
        print("  3. Migrations have been run")
        return 1

    # Find all sites
    if not BUILDINGS_PATH.exists():
        print(f"✗ ERROR: Buildings path not found: {BUILDINGS_PATH}")
        return 1

    sites = sorted([d.name for d in BUILDINGS_PATH.iterdir() if d.is_dir() and not d.name.startswith("_")])

    if not sites:
        print(f"✗ ERROR: No sites found in {BUILDINGS_PATH}")
        return 1

    print(f"Found {len(sites)} sites to seed: {', '.join(sites)}\n")

    total_buildings = 0
    total_equipment = 0
    total_zones = 0

    # Process each site
    for site_code in sites:
        print(f"\nProcessing {site_code}...")
        site_path = BUILDINGS_PATH / site_code

        # Load building metadata
        building_file = site_path / "building.json"
        if not building_file.exists():
            print(f"  ⓘ No building.json for {site_code}")
            building_data = {"name": site_code}
        else:
            try:
                with open(building_file) as f:
                    building_data = json.load(f)
            except Exception as e:
                print(f"  ✗ ERROR reading building.json: {e}")
                building_data = {"name": site_code}

        # Get or create building
        building_uuid = get_or_create_building(client, site_code, building_data)
        if not building_uuid:
            print(f"  ✗ Skipping {site_code}: failed to create building")
            continue

        total_buildings += 1

        # Seed equipment
        eq_count = seed_equipment_for_site(client, site_code, building_uuid)
        total_equipment += eq_count

        # Seed zones
        zone_count = seed_zones_for_site(client, site_code, building_uuid)
        total_zones += zone_count

    print("\n" + "=" * 80)
    print("SEEDING COMPLETE")
    print("=" * 80)
    print(f"Buildings created/updated: {total_buildings}")
    print(f"Equipment created/updated: {total_equipment}")
    print(f"HVAC Zones created/updated: {total_zones}")
    print(f"Total items seeded: {total_buildings + total_equipment + total_zones}")
    print()

    # Verify
    print("VERIFICATION:")
    print("-" * 80)

    try:
        # Count buildings
        b_result = client.table("buildings").select("id", count="exact").execute()
        print(f"Buildings in Supabase: {b_result.count}")

        # Count equipment
        e_result = client.table("equipment").select("id", count="exact").execute()
        print(f"Equipment in Supabase: {e_result.count}")

        # Count zones
        z_result = client.table("hvac_zones").select("id", count="exact").execute()
        print(f"HVAC Zones in Supabase: {z_result.count}")

        # Count by building
        print("\nEquipment per building:")
        buildings_result = client.table("buildings").select("id, code, name").execute()
        for building in buildings_result.data[:5]:  # Show first 5
            eq_result = (
                client.table("equipment").select("id", count="exact").eq("building_id", building["id"]).execute()
            )
            print(f"  {building['code']}: {eq_result.count} equipment")

    except Exception as e:
        print(f"✗ ERROR during verification: {e}")

    print("\n✓ SUCCESS: Supabase is now the primary data source")
    print("  JSON files will only be used as fallback if Supabase is unavailable")

    return 0


if __name__ == "__main__":
    sys.exit(main())
