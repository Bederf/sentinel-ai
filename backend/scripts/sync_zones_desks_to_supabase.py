#!/usr/bin/env python3
"""
Sync zones and desks from JSON to Supabase.

Transforms desk data:
- Corrects floor names: L10→L0, L11→L1, L12→L2
- Generates x_coord, z_coord based on zone and context
- Syncs zones and desks to Supabase with upsert
"""

import json
import sys
import uuid
from pathlib import Path
from typing import Any

# Add backend to path
sys.path.insert(0, str(Path(__file__).parent.parent))

from app.database.supabase_client import get_supabase_client

# Floor mapping: legacy → correct
FLOOR_MAP = {
    "L10": "L0",
    "L11": "L1",
    "L12": "L2",
    "B1": "B1",
    "G": "G",
    "R": "R",
}

# Context positioning offsets (relative to zone centroid)
CONTEXT_OFFSETS = {
    "near_diffuser": (2.5, 0.5),
    "near_window": (-2.5, 1.5),
    "near_printer": (2.0, -2.0),
    "corner": (-2.0, -2.5),
    "open_plan": (0.0, 0.0),
}

# Zone center positions (approximate for 3D rendering)
ZONE_CENTERS = {
    "B1-001": (0.0, 0.0),
    "L1-A": (5.0, 5.0),
    "L2-B": (10.0, 10.0),
}


def load_zones_json(site_code: str) -> list[dict[str, Any]]:
    """Load zones from zones.json."""
    data_path = Path(__file__).parent.parent / "app" / "data" / "sites" / site_code / "zones.json"
    with open(data_path) as f:
        data = json.load(f)
    return data.get("zones", [])


def load_desks_json(site_code: str) -> list[dict[str, Any]]:
    """Load desks from desks.json.bak."""
    data_path = Path(__file__).parent.parent / "app" / "data" / "sites" / site_code / "desks.json.bak"
    with open(data_path) as f:
        # File starts with [ not { so wrap it
        content = f.read()
        if content.strip().startswith("["):
            desks = json.loads(content)
        else:
            # Wrap if it's raw array
            desks = json.loads(content)
    return desks


def get_site_uuid(client, site_code: str) -> str:
    """Get building UUID from building code."""
    response = client.table("sites").select("id").eq("code", site_code).execute()
    if response.data:
        return response.data[0]["id"]
    raise ValueError(f"Building {site_code} not found")


def transform_desks(desks: list[dict], site_id: str) -> list[dict]:
    """
    Transform desks:
    - Correct floor names
    - Generate x_coord, z_coord
    - Map to building UUID
    """
    transformed = []
    desk_by_zone = {}

    # Group desks by (corrected) zone to calculate context positioning
    for desk in desks:
        floor = FLOOR_MAP.get(desk["floor"], desk["floor"])
        zone_id = desk["zone_id"]
        # Update zone_id if it has legacy floor
        for old_floor, new_floor in FLOOR_MAP.items():
            if old_floor != new_floor:
                zone_id = zone_id.replace(f"Zone-{old_floor}-", f"Zone-{new_floor}-")

        if zone_id not in desk_by_zone:
            desk_by_zone[zone_id] = []
        desk_by_zone[zone_id].append((desk, floor, zone_id))

    # Generate coordinates
    for zone_id, desks_in_zone in desk_by_zone.items():
        # Get zone base center (default to origin if not found)
        _zone_letter = zone_id.split("-")[-1]  # e.g., "A", "B", "001"
        base_x, base_z = ZONE_CENTERS.get(zone_id.replace("Zone-", ""), (0.0, 0.0))

        for idx, (desk, floor, corrected_zone) in enumerate(desks_in_zone):
            context = desk.get("context", "open_plan")
            offset_x, offset_z = CONTEXT_OFFSETS.get(context, (0.0, 0.0))

            # Calculate unique position for desk within zone
            x_coord = base_x + offset_x + (idx % 5) * 0.5
            z_coord = base_z + offset_z + (idx // 5) * 0.5

            transformed.append(
                {
                    "id": str(uuid.uuid4()),
                    "site_id": site_id,
                    "desk_id": desk["desk_id"],
                    "desk_name": desk.get("desk_name", f"Desk {desk['desk_id']}"),
                    "floor": floor,
                    "zone_id": corrected_zone,
                    "context": context,
                    "x_coord": round(x_coord, 2),
                    "z_coord": round(z_coord, 2),
                    "y_coord": 0.0,
                }
            )

    return transformed


def transform_zones(zones: list[dict], site_id: str) -> list[dict]:
    """Transform zones for Supabase."""
    transformed = []
    for zone in zones:
        zone_id = zone["zone_id"]
        transformed.append(
            {
                "id": str(uuid.uuid4()),
                "site_id": site_id,
                "zone_id": zone_id,
                "zone_name": zone.get("zone_name", zone_id),
                "floor": zone["floor"],
                "zone_type": zone.get("zone_type", "open_office"),
                "typical_occupancy": zone.get("typical_occupancy"),
                "area_sqm": zone.get("area_sqm"),
                "zone_letter": zone.get("zone_letter"),
            }
        )
    return transformed


def sync_to_supabase(site_code: str):
    """Main sync function."""
    client = get_supabase_client()

    print(f"🔄 Syncing zones and desks for {site_code}...")

    # Get building UUID
    try:
        site_id = get_site_uuid(client, site_code)
        print(f"✓ Found building: {site_id}")
    except ValueError as e:
        print(f"✗ Error: {e}")
        return False

    # Load JSON data
    print("📂 Loading zones from zones.json...")
    zones = load_zones_json(site_code)
    print(f"  → Found {len(zones)} zones")

    print("📂 Loading desks from desks.json.bak...")
    desks_raw = load_desks_json(site_code)
    print(f"  → Found {len(desks_raw)} desks")

    # Transform data
    print("🔄 Transforming zones...")
    zones_transformed = transform_zones(zones, site_id)
    print(f"  → Prepared {len(zones_transformed)} zone records")

    print("🔄 Transforming desks (correcting floors, generating coordinates)...")
    desks_transformed = transform_desks(desks_raw, site_id)
    print(f"  → Prepared {len(desks_transformed)} desk records")

    # Upsert to Supabase
    try:
        print("📤 Upserting zones to Supabase...")
        response = client.table("zones").upsert(zones_transformed, on_conflict="site_id,zone_id").execute()
        print(f"  ✓ {len(response.data)} zones synced")

        print("📤 Upserting desks to Supabase...")
        # Upsert in batches to avoid payload limits
        batch_size = 500
        total_synced = 0
        for i in range(0, len(desks_transformed), batch_size):
            batch = desks_transformed[i : i + batch_size]
            response = client.table("desks").upsert(batch, on_conflict="desk_id").execute()
            total_synced += len(response.data)
            print(f"  ✓ Batch {i // batch_size + 1}: {len(response.data)} desks synced")

        print(f"  ✓ Total: {total_synced} desks synced")

        print("\n✅ Sync complete!")
        print(f"   - {len(zones_transformed)} zones")
        print(f"   - {total_synced} desks (with corrected floors L0, L1, L2)")
        print("   - All desks have x_coord and z_coord for centroid calculation")
        return True

    except Exception as e:
        print(f"✗ Sync failed: {e}")
        return False


if __name__ == "__main__":
    site_code = "site-002"
    success = sync_to_supabase(site_code)
    sys.exit(0 if success else 1)
