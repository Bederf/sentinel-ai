#!/usr/bin/env python3
"""Check what's in the buildings table for site-012."""

import sys
from pathlib import Path
from dotenv import load_dotenv

load_dotenv(Path(__file__).parent.parent / ".env")

sys.path.insert(0, str(Path(__file__).parent.parent))

try:
    from app.database.supabase_client import get_supabase_client

    client = get_supabase_client()

    print("=" * 70)
    print("BUILDINGS TABLE - EQUIPMENT COUNT CHECK")
    print("=" * 70)

    # Get all buildings with their equipment_count
    result = client.table("buildings").select("code, name, equipment_count").execute()

    print("\nBuildings in Supabase:\n")
    for building in result.data:
        print(f"  {building['code']}: equipment_count = {building.get('equipment_count', 'N/A')}")

    print("\n" + "=" * 70)
    print("COMPARING WITH ACTUAL EQUIPMENT COUNTS")
    print("=" * 70 + "\n")

    for building in result.data:
        building_code = building["code"]
        building_id = building["id"]
        stored_count = building.get("equipment_count", 0)

        # Count actual equipment
        eq_result = client.table("equipment").select("id", count="exact").eq("building_id", building_id).execute()
        actual_count = eq_result.count or 0

        match = "✓" if stored_count == actual_count else "❌"
        print(f"{match} {building_code}:")
        print(f"   Stored in buildings.equipment_count: {stored_count}")
        print(f"   Actual equipment rows: {actual_count}")
        if stored_count != actual_count:
            print(f"   MISMATCH: {stored_count} vs {actual_count} ({actual_count - stored_count:+d})")
        print()

except Exception as e:
    print(f"❌ Error: {e}")
    import traceback

    traceback.print_exc()
    sys.exit(1)
