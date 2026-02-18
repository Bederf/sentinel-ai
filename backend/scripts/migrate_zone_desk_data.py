#!/usr/bin/env python3
"""
Migration script for site-002 zone and desk data from backup JSON files to Supabase.

This script migrates:
- zones.json.bak → zones table (with floor code migration L10→L0, L11→L1, L12→L2)
- desks.json.bak → desks table (with coordinate calculation and zone_id assignment)

Run as:
    python backend/scripts/migrate_zone_desk_data.py --site site-002 --dry-run
    python backend/scripts/migrate_zone_desk_data.py --site site-002
"""

import json
import sys
import argparse
from pathlib import Path
from typing import List, Dict, Any, Optional, Tuple

# Add parent directory to path
sys.path.insert(0, str(Path(__file__).parent.parent.parent))

from app.database.supabase_client import get_supabase_client


def migrate_floor_code(old_code: str) -> str:
    """Convert old floor codes to standard format.

    L10 → L0 (Ground)
    L11 → L1 (First)
    L12 → L2 (Second)
    B1 → B1 (Basement)
    G → G (Ground alternate)
    R → R (Roof)
    """
    mapping = {
        "L10": "L0",
        "L11": "L1",
        "L12": "L2",
        "B1": "B1",
        "G": "G",
        "R": "R",
    }
    return mapping.get(old_code, old_code)


def migrate_zone_id(old_zone_id: str) -> str:
    """Convert zone ID with old floor codes to new format."""
    parts = old_zone_id.split("-")
    if len(parts) == 3:
        parts[1] = migrate_floor_code(parts[1])
    return "-".join(parts)


def calculate_desk_coordinates(
    desk_index_in_zone: int,
    zone_letter: str,
    floor: str,
) -> Dict[str, float]:
    """
    Calculate 3D position for a desk based on its location in the zone grid.

    Layout:
    - Zone width: 6m (zones A-E span 30m total)
    - Zone depth: 20m
    - Grid: 4 rows × 5 columns = 20 desks per zone
    - Row spacing: 5m
    - Column spacing: 1.2m

    Floor heights (Y-coordinate):
    - B1: 0.5m (basement)
    - L0/G: 3.5m (ground)
    - L1: 6.5m (first)
    - L2: 9.5m (second)
    - R: 12.5m (roof)
    """
    # Zone X offset (5 zones × 6m each = 30m floor width)
    zone_offset_x = (ord(zone_letter) - ord('A')) * 6.0

    # Desk grid position within zone (4 rows × 5 cols = 20 desks)
    row = desk_index_in_zone // 5
    col = desk_index_in_zone % 5

    # Base grid position
    x = zone_offset_x + (col * 1.2) + 0.6  # 1.2m spacing between desks
    z = (row * 5.0) + 2.5  # 5m row spacing

    # Floor Y-coordinate (height)
    floor_heights = {
        "B1": 0.5,
        "G": 3.5,
        "L0": 3.5,
        "L1": 6.5,
        "L2": 9.5,
        "R": 12.5,
    }
    y = float(floor_heights.get(floor, 3.5))

    return {
        "x": round(x, 2),
        "y": y,
        "z": round(z, 2),
    }


def load_zones_backup(backup_path: Path) -> List[Dict[str, Any]]:
    """Load and migrate zones from zones.json.bak."""
    print(f"Loading zones from {backup_path}...")

    with open(backup_path, "r") as f:
        data = json.load(f)

    # Handle both array and object formats
    zone_list = data if isinstance(data, list) else data.get("zones", [])

    zones = []
    for zone in zone_list:
        # Migrate zone_name to reflect correct floor levels
        old_name = zone.get("zone_name", "")
        zone_name_mapping = {
            "Level 10": "Level 0",
            "Level 11": "Level 1",
            "Level 12": "Level 2",
            "L10": "L0",
            "L11": "L1",
            "L12": "L2",
        }
        zone_name = old_name
        for old_level, new_level in zone_name_mapping.items():
            zone_name = zone_name.replace(old_level, new_level)

        migrated_zone = {
            "zone_id": migrate_zone_id(zone["zone_id"]),
            "zone_name": zone_name,
            "floor": migrate_floor_code(zone["floor"]),
            "zone_letter": zone.get("zone_letter", zone["zone_id"].split("-")[-1] if "-" in zone["zone_id"] else ""),
            "zone_type": zone.get("zone_type", "open_office"),
            "typical_occupancy": zone.get("typical_occupancy"),
            "area_sqm": zone.get("area_sqm"),
        }
        zones.append(migrated_zone)

    print(f"  Loaded {len(zones)} zones")
    print(f"  Sample: {zones[0] if zones else 'None'}")
    return zones


def load_desks_backup(backup_path: Path) -> List[Dict[str, Any]]:
    """Load and migrate desks from desks.json.bak."""
    print(f"Loading desks from {backup_path}...")

    with open(backup_path, "r") as f:
        data = json.load(f)

    # Handle both array and object formats
    desk_list = data if isinstance(data, list) else data.get("desks", [])

    desks = []
    desk_counter = 1000  # Start desk IDs at 1000
    desks_by_zone = {}

    for desk_idx, desk in enumerate(desk_list):
        zone_id_old = desk.get("zone_id", "Zone-L10-A")
        zone_id = migrate_zone_id(zone_id_old)

        # Track desk count per zone
        if zone_id not in desks_by_zone:
            desks_by_zone[zone_id] = 0
        desk_index_in_zone = desks_by_zone[zone_id]
        desks_by_zone[zone_id] += 1

        # Get zone letter from zone_id (e.g., "Zone-L0-A" -> "A")
        zone_letter = zone_id.split("-")[-1] if "-" in zone_id else "A"

        # Calculate 3D coordinates
        coords = calculate_desk_coordinates(
            desk_index_in_zone,
            zone_letter,
            migrate_floor_code(desk.get("floor", "L10")),
        )

        # Generate unique desk_id if not present
        desk_id = desk.get("id")
        if desk_id is None or desk_id == "":
            desk_id = str(desk_counter)
            desk_counter += 1

        migrated_desk = {
            "desk_id": str(desk_id),
            "floor": migrate_floor_code(desk.get("floor", "L10")),
            "zone_id": zone_id,
            "context": desk.get("context", "open_plan"),
            "x_coord": float(coords["x"]),
            "y_coord": float(coords["y"]),
            "z_coord": float(coords["z"]),
        }
        desks.append(migrated_desk)

    print(f"  Loaded {len(desks)} desks")
    print(f"  Sample: {desks[0] if desks else 'None'}")
    return desks


def get_building_uuid(supabase_client: Any, building_code: str) -> Optional[str]:
    """Get building UUID from building code."""
    response = supabase_client.table("buildings").select("id").eq("code", building_code).execute()

    if response.data:
        return response.data[0]["id"]
    return None


def validate_zones_and_desks(zones: List[Dict], desks: List[Dict]) -> Tuple[bool, List[str]]:
    """Validate zone and desk data integrity."""
    errors = []

    # Check unique zone IDs
    zone_ids = [z["zone_id"] for z in zones]
    if len(zone_ids) != len(set(zone_ids)):
        errors.append("❌ Duplicate zone_ids detected")
    else:
        print(f"✓ Zone IDs unique: {len(set(zone_ids))} unique zones")

    # Check each zone has desks
    zone_id_set = set(zone_ids)
    desks_per_zone = {}
    for desk in desks:
        zone = desk["zone_id"]
        desks_per_zone[zone] = desks_per_zone.get(zone, 0) + 1

    # Verify 20 desks per zone (expected distribution)
    for zone_id in zone_id_set:
        desk_count = desks_per_zone.get(zone_id, 0)
        if desk_count != 20:
            errors.append(f"⚠ Zone {zone_id} has {desk_count} desks (expected 20)")

    if not errors:
        print(f"✓ Desk distribution: {len(desks_per_zone)} zones with ~20 desks each")

    # Check desk coordinates are within bounds
    # Floor width: 30m (X), depth: 20m (Z)
    for desk in desks:
        x = float(desk["x_coord"])
        z = float(desk["z_coord"])

        if not (0 <= x <= 30):
            errors.append(f"❌ Desk {desk['desk_id']}: X coordinate {x} out of bounds (0-30)")
        if not (0 <= z <= 20):
            errors.append(f"❌ Desk {desk['desk_id']}: Z coordinate {z} out of bounds (0-20)")

    if not errors:
        print("✓ Desk coordinates within bounds (X: 0-30m, Z: 0-20m)")

    # Check floor codes
    valid_floors = {"B1", "G", "L0", "L1", "L2", "R"}
    for zone in zones:
        if zone["floor"] not in valid_floors:
            errors.append(f"❌ Invalid floor code: {zone['floor']}")

    for desk in desks:
        if desk["floor"] not in valid_floors:
            errors.append(f"❌ Invalid floor code in desk: {desk['floor']}")

    if not errors:
        print(f"✓ Floor codes valid: {sorted(set(z['floor'] for z in zones))}")

    return len(errors) == 0, errors


def insert_zones(supabase_client: Any, building_id: str, zones: List[Dict[str, Any]]) -> bool:
    """Upsert zones into Supabase (insert or update if exists)."""
    print(f"\nUpserting {len(zones)} zones...")

    for zone in zones:
        zone["building_id"] = building_id

    try:
        # Use upsert to handle existing zones with updated names
        response = supabase_client.table("zones").upsert(zones, on_conflict="building_id,zone_id").execute()
        print(f"✓ Upserted {len(response.data)} zones")
        return True
    except Exception as e:
        print(f"❌ Failed to upsert zones: {e}")
        return False


def insert_desks(supabase_client: Any, building_id: str, desks: List[Dict[str, Any]]) -> bool:
    """Insert/update desks into Supabase."""
    print(f"\nInserting/updating {len(desks)} desks...")

    for desk in desks:
        desk["building_id"] = building_id

    try:
        # Upsert instead of insert (in case some desks already exist)
        response = supabase_client.table("desks").upsert(desks, on_conflict="desk_id").execute()
        print(f"✓ Upserted {len(response.data)} desks")
        return True
    except Exception as e:
        print(f"❌ Failed to insert desks: {e}")
        return False


def verify_insertion(supabase_client: Any, building_id: str) -> bool:
    """Verify data was inserted correctly."""
    print("\nVerifying insertion...")

    # Check zones
    zones_response = supabase_client.table("zones").select("*").eq("building_id", building_id).execute()
    zone_count = len(zones_response.data)

    # Check desks
    desks_response = supabase_client.table("desks").select("*").eq("building_id", building_id).execute()
    desk_count = len(desks_response.data)

    print(f"✓ Zones in Supabase: {zone_count}")
    print(f"✓ Desks in Supabase: {desk_count}")

    # Check zone centroids via the view
    try:
        centroids_response = supabase_client.table("zone_centroids").select("*").eq("building_id", building_id).execute()
        centroid_count = len(centroids_response.data)
        print(f"✓ Zone centroids available: {centroid_count} zones with centroids")
    except Exception as e:
        print(f"⚠ Zone centroids view not accessible: {e}")

    return zone_count > 0 and desk_count > 0


def main():
    parser = argparse.ArgumentParser(
        description="Migrate site zone and desk data from backup JSON to Supabase"
    )
    parser.add_argument("--site", required=True, help="Site ID (e.g., site-002)")
    parser.add_argument("--dry-run", action="store_true", help="Preview migration without modifying database")

    args = parser.parse_args()

    # Paths
    data_dir = Path(__file__).parent.parent / "app" / "data" / "buildings" / args.site
    zones_backup = data_dir / "zones.json.bak"
    desks_backup = data_dir / "desks.json.bak"

    print(f"\n{'='*60}")
    print(f"Zone & Desk Migration for {args.site}")
    print(f"{'='*60}\n")

    # Check files exist
    if not zones_backup.exists():
        print(f"❌ Backup file not found: {zones_backup}")
        sys.exit(1)

    if not desks_backup.exists():
        print(f"❌ Backup file not found: {desks_backup}")
        sys.exit(1)

    # Load data
    zones = load_zones_backup(zones_backup)
    desks = load_desks_backup(desks_backup)

    # Validate
    print("\nValidating data integrity...")
    is_valid, errors = validate_zones_and_desks(zones, desks)

    if errors:
        print("\n❌ Validation errors found:")
        for error in errors:
            print(f"  {error}")
        sys.exit(1)

    print("✓ All validations passed!")

    # Dry run
    if args.dry_run:
        print("\n[DRY RUN] Migration complete (no database changes)")
        print("\nWould migrate:")
        print(f"  {len(zones)} zones from zones.json.bak")
        print(f"  {len(desks)} desks from desks.json.bak")
        print("\nTo confirm and execute, run without --dry-run flag")
        sys.exit(0)

    # Connect to Supabase
    print("\nConnecting to Supabase...")
    try:
        supabase_client = get_supabase_client()
    except Exception as e:
        print(f"❌ Failed to connect to Supabase: {e}")
        sys.exit(1)

    # Get building UUID
    building_uuid = get_building_uuid(supabase_client, args.site)
    if not building_uuid:
        print(f"❌ Building not found: {args.site}")
        sys.exit(1)

    print(f"✓ Found building {args.site}: {building_uuid}")

    # Insert data
    zones_ok = insert_zones(supabase_client, building_uuid, zones)
    desks_ok = insert_desks(supabase_client, building_uuid, desks)

    if not (zones_ok and desks_ok):
        print("\n❌ Migration failed during insertion")
        sys.exit(1)

    # Verify
    verify_insertion(supabase_client, building_uuid)

    print(f"\n{'='*60}")
    print("✓ Migration complete!")
    print(f"  {len(zones)} zones → Supabase")
    print(f"  {len(desks)} desks → Supabase")
    print(f"{'='*60}\n")


if __name__ == "__main__":
    main()
