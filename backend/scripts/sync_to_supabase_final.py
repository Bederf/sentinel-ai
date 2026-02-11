#!/usr/bin/env python3
"""
Final sync script: Push corrected zones and desks to Supabase.

Usage:
  python sync_to_supabase_final.py [--dry-run]
  
Requires Supabase credentials in .env:
  SUPABASE_URL
  SUPABASE_SERVICE_ROLE_KEY
"""

import json
import sys
import uuid
from pathlib import Path
from typing import List, Dict, Any, Optional
import argparse
import os
from dotenv import load_dotenv

# Load environment
load_dotenv()

# Add backend to path
sys.path.insert(0, str(Path(__file__).parent.parent))


def get_building_uuid(client, building_code: str) -> Optional[str]:
    """Get building UUID from building code."""
    try:
        response = client.table("buildings").select("id").eq("code", building_code).execute()
        if response.data:
            return response.data[0]["id"]
    except Exception as e:
        print(f"  ✗ Error fetching building: {e}")
    return None


def load_zones_json(building_code: str) -> List[Dict]:
    """Load zones from corrected zones.json."""
    path = Path(__file__).parent.parent / "app/data/buildings" / building_code / "zones.json"
    with open(path) as f:
        data = json.load(f)
    return data.get("zones", [])


def load_desks_json(building_code: str) -> List[Dict]:
    """Load desks from corrected desks.json."""
    path = Path(__file__).parent.parent / "app/data/buildings" / building_code / "desks.json"
    with open(path) as f:
        return json.load(f)


def prepare_zones(zones: List[Dict], building_id: str) -> List[Dict]:
    """Prepare zones for Supabase insert."""
    result = []
    for zone in zones:
        result.append({
            "id": str(uuid.uuid4()),
            "building_id": building_id,
            "zone_id": zone["zone_id"],
            "zone_name": zone.get("zone_name", zone["zone_id"]),
            "floor": zone["floor"],
            "zone_type": zone.get("zone_type", "open_office"),
            "typical_occupancy": zone.get("typical_occupancy"),
            "area_sqm": zone.get("area_sqm"),
            "zone_letter": zone.get("zone_letter"),
        })
    return result


def prepare_desks(desks: List[Dict], building_id: str) -> List[Dict]:
    """Prepare desks for Supabase insert."""
    result = []
    for desk in desks:
        result.append({
            "desk_id": desk["desk_id"],
            "building_id": building_id,
            "floor": desk["floor"],
            "zone_id": desk["zone_id"],
            "context": desk.get("context", "open_plan"),
            "x_coord": float(desk.get("x_coord", 0.0)),
            "z_coord": float(desk.get("z_coord", 0.0)),
            "y_coord": 0.0,
        })
    return result


def sync_to_supabase(building_code: str, dry_run: bool = False):
    """Main sync function."""
    print(f"🚀 Syncing zones and desks for {building_code}")
    
    # Check for Supabase credentials
    supabase_url = os.getenv("SUPABASE_URL")
    supabase_key = os.getenv("SUPABASE_SERVICE_ROLE_KEY")
    
    if not supabase_url or not supabase_key:
        print("  ⚠️  Supabase credentials not found in .env")
        print("  Required: SUPABASE_URL and SUPABASE_SERVICE_ROLE_KEY")
        print("\n  📝 To use local Supabase:")
        print("     1. Run: supabase start")
        print("     2. Add to .env:")
        print("        SUPABASE_URL=http://localhost:54321")
        print("        SUPABASE_SERVICE_ROLE_KEY=<service role key from supabase status>")
        return False
    
    try:
        from app.database.supabase_client import get_supabase_client
    except ImportError as e:
        print(f"  ✗ Failed to import Supabase client: {e}")
        return False
    
    client = get_supabase_client()
    
    # Get building UUID
    print(f"\n📍 Looking up building {building_code}...")
    building_id = get_building_uuid(client, building_code)
    if not building_id:
        print(f"  ✗ Building {building_code} not found in Supabase")
        return False
    print(f"  ✓ Found building ID: {building_id}")
    
    # Load JSON data
    print(f"\n📂 Loading data files...")
    zones = load_zones_json(building_code)
    desks = load_desks_json(building_code)
    print(f"  ✓ Loaded {len(zones)} zones")
    print(f"  ✓ Loaded {len(desks)} desks (with corrected floors L0, L1, L2)")
    
    # Prepare data
    print(f"\n📋 Preparing records...")
    zones_prepared = prepare_zones(zones, building_id)
    desks_prepared = prepare_desks(desks, building_id)
    print(f"  ✓ {len(zones_prepared)} zone records ready")
    print(f"  ✓ {len(desks_prepared)} desk records ready")
    
    if dry_run:
        print(f"\n🔍 DRY RUN MODE - Would sync:")
        print(f"   - {len(zones_prepared)} zones")
        print(f"   - {len(desks_prepared)} desks")
        return True
    
    # Sync to Supabase
    try:
        print(f"\n📤 Syncing to Supabase...")
        
        print(f"   Upserting {len(zones_prepared)} zones...")
        response = client.table("zones").upsert(
            zones_prepared,
            on_conflict="building_id,zone_id"
        ).execute()
        zones_synced = len(response.data) if response.data else 0
        print(f"   ✓ {zones_synced} zones synced")
        
        # Upsert desks in batches
        batch_size = 500
        total_synced = 0
        num_batches = (len(desks_prepared) + batch_size - 1) // batch_size
        
        for batch_idx in range(num_batches):
            start = batch_idx * batch_size
            end = min(start + batch_size, len(desks_prepared))
            batch = desks_prepared[start:end]
            
            print(f"   Batch {batch_idx + 1}/{num_batches}: {len(batch)} desks...")
            response = client.table("desks").upsert(
                batch,
                on_conflict="desk_id"
            ).execute()
            synced = len(response.data) if response.data else 0
            total_synced += synced
            print(f"   ✓ {synced} desks synced")
        
        print(f"\n✅ Sync complete!")
        print(f"   📊 {zones_synced} zones")
        print(f"   📊 {total_synced} desks")
        print(f"\n🎯 Next steps:")
        print(f"   1. Zone centroids will auto-calculate from desk coordinates")
        print(f"   2. Equipment will appear in zones on the digital twin")
        print(f"   3. Refresh the browser to see updated 3D visualization")
        return True
        
    except Exception as e:
        print(f"  ✗ Sync failed: {e}")
        import traceback
        traceback.print_exc()
        return False


def main():
    parser = argparse.ArgumentParser(
        description="Sync corrected zones and desks to Supabase"
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Preview sync without actually writing to Supabase"
    )
    args = parser.parse_args()
    
    success = sync_to_supabase("site-002", dry_run=args.dry_run)
    sys.exit(0 if success else 1)


if __name__ == "__main__":
    main()
