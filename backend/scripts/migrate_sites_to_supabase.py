#!/usr/bin/env python3
"""
Migrate legacy sites and equipment from JSON/CSV to Supabase.

This script:
1. Reads sites from sites.json
2. Reads equipment from assets.csv
3. Inserts buildings into Supabase (skipping existing)
4. Inserts equipment into Supabase (skipping existing)

Usage:
    python scripts/migrate_sites_to_supabase.py [--dry-run]
"""

import csv
import json
import sys
import uuid
from pathlib import Path

# Add backend to path
sys.path.insert(0, str(Path(__file__).parent.parent))

from app.database.supabase_client import get_supabase_client


def load_legacy_sites():
    """Load sites from sites.json"""
    sites_path = Path(__file__).parent.parent / "app/data/sites.json"
    with open(sites_path) as f:
        return json.load(f)


def load_legacy_equipment():
    """Load equipment from assets.csv"""
    assets_path = Path(__file__).parent.parent / "app/data/assets.csv"
    equipment = []
    with open(assets_path) as f:
        reader = csv.DictReader(f)
        for row in reader:
            equipment.append(row)
    return equipment


def site_to_building(site: dict) -> dict:
    """Convert legacy site format to Supabase building format"""
    # Generate deterministic UUID from site ID
    site_id = site.get("id", "")
    site_id = str(uuid.uuid5(uuid.NAMESPACE_DNS, f"sentinel-bms-{site_id}"))

    # Map all types to 'regional_office' (Supabase constraint limitation)
    # TODO: Update constraint to allow retail, hospital, etc.
    building_type = "regional_office"

    return {
        "id": site_id,
        "code": site_id,
        "name": site.get("name", ""),
        "address": site.get("address", ""),
        "region": site.get("region", ""),
        "type": building_type,
        "sqm": site.get("sqm", 0),
        "floors": site.get("floors", 1),
        "year_built": site.get("year_built"),
        "operating_hours": site.get("operating_hours"),
        "occupancy_pattern": site.get("occupancy_pattern", "office"),
        "latitude": site.get("latitude"),
        "longitude": site.get("longitude"),
        "contact_email": site.get("contact_email"),
        "contact_phone": site.get("contact_phone"),
        "optimization_enabled": site.get("optimization_enabled", False),
        "optimization_status": site.get("optimization_status"),
        "control_enabled": site.get("control_enabled", False),
        "control_note": site.get("control_note"),
        "equipment_count": 0,  # Will be updated after equipment migration
    }


def asset_to_equipment(asset: dict, site_id_map: dict) -> dict:
    """Convert legacy asset format to Supabase equipment format"""
    site_id = asset.get("site_id", "").lower()
    site_id = site_id_map.get(site_id)

    if not site_id:
        print(f"  Warning: No building found for site {site_id}")
        return None

    # Generate deterministic UUID from asset ID
    asset_id = asset.get("asset_id", "")
    equipment_id = str(uuid.uuid5(uuid.NAMESPACE_DNS, f"sentinel-equipment-{asset_id}"))

    # Map CSV column names to equipment fields
    # CSV: asset_id, site_id, site_name, asset_tag, asset_category, make, model,
    #      serial_number, install_date, warranty_expiry, expected_life_years,
    #      criticality, condition, last_service_date, next_service_date, notes

    # Determine health score based on condition
    condition = asset.get("condition", "good").lower()
    health_map = {"excellent": 95, "good": 80, "fair": 60, "poor": 40, "critical": 20}
    health_score = health_map.get(condition, 70)

    # Determine status based on condition
    status_map = {
        "excellent": "normal",
        "good": "normal",
        "fair": "warning",
        "poor": "critical",
        "critical": "critical",
    }
    status = status_map.get(condition, "normal")

    return {
        "id": equipment_id,
        "code": asset_id,
        "site_id": site_id,
        "name": asset.get("asset_tag", ""),
        "type": asset.get("asset_category", "unknown"),
        "manufacturer": asset.get("make", ""),
        "model": asset.get("model", ""),
        "capacity": "",  # Not in CSV
        "serial_number": asset.get("serial_number", ""),
        "install_date": asset.get("install_date") or None,
        "last_service": asset.get("last_service_date") or None,
        "status": status,
        "health_score": health_score,
        "location": asset.get("site_name", ""),
    }


def migrate(dry_run: bool = False):
    """Run the migration"""
    print("=" * 60)
    print("SENTINEL Site Migration to Supabase")
    print("=" * 60)

    if dry_run:
        print("\n*** DRY RUN - No changes will be made ***\n")

    client = get_supabase_client()

    # Load legacy data
    print("\n1. Loading legacy data...")
    sites = load_legacy_sites()
    equipment = load_legacy_equipment()
    print(f"   Found {len(sites)} sites and {len(equipment)} equipment items")

    # Get existing buildings
    print("\n2. Checking existing buildings...")
    existing = client.table("sites").select("code").execute()
    existing_codes = {b["code"] for b in existing.data}
    print(f"   Found {len(existing_codes)} existing buildings: {existing_codes}")

    # Convert and filter sites
    buildings_to_insert = []
    site_id_map = {}  # code -> uuid

    for site in sites:
        building = site_to_building(site)
        code = building["code"]
        site_id_map[code] = building["id"]

        if code in existing_codes:
            print(f"   Skipping {code} ({building['name']}) - already exists")
        else:
            buildings_to_insert.append(building)
            print(f"   Will insert {code} ({building['name']})")

    # Insert buildings
    if buildings_to_insert and not dry_run:
        print(f"\n3. Inserting {len(buildings_to_insert)} buildings...")
        try:
            result = client.table("sites").insert(buildings_to_insert).execute()
            print(f"   Inserted {len(result.data)} buildings")
        except Exception as e:
            print(f"   Error: {e}")
            return False
    else:
        print(f"\n3. Would insert {len(buildings_to_insert)} buildings")

    # Get existing equipment
    print("\n4. Checking existing equipment...")
    existing_eq = client.table("equipment").select("code").execute()
    existing_eq_codes = {e["code"] for e in existing_eq.data if e.get("code")}
    print(f"   Found {len(existing_eq_codes)} existing equipment items")

    # Convert and filter equipment
    equipment_to_insert = []

    for asset in equipment:
        eq = asset_to_equipment(asset, site_id_map)
        if not eq:
            continue

        code = eq["code"]
        if code in existing_eq_codes:
            print(f"   Skipping {code} - already exists")
        else:
            equipment_to_insert.append(eq)
            print(f"   Will insert {code} ({eq['name']})")

    # Insert equipment
    if equipment_to_insert and not dry_run:
        print(f"\n5. Inserting {len(equipment_to_insert)} equipment items...")
        try:
            result = client.table("equipment").insert(equipment_to_insert).execute()
            print(f"   Inserted {len(result.data)} equipment items")
        except Exception as e:
            print(f"   Error: {e}")
            return False
    else:
        print(f"\n5. Would insert {len(equipment_to_insert)} equipment items")

    # Update equipment counts
    if not dry_run:
        print("\n6. Updating equipment counts...")
        for code, site_id in site_id_map.items():
            count_result = client.table("equipment").select("id", count="exact").eq("site_id", site_id).execute()
            count = count_result.count or 0
            client.table("sites").update({"equipment_count": count}).eq("id", site_id).execute()
            print(f"   {code}: {count} items")

    print("\n" + "=" * 60)
    print("Migration complete!" if not dry_run else "Dry run complete!")
    print("=" * 60)

    return True


if __name__ == "__main__":
    dry_run = "--dry-run" in sys.argv
    success = migrate(dry_run=dry_run)
    sys.exit(0 if success else 1)
