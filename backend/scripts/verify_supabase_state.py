#!/usr/bin/env python3
"""
Quick verification of Supabase state to check if equipment has been seeded.
"""

import sys
from pathlib import Path
from dotenv import load_dotenv

# Load .env file
load_dotenv(Path(__file__).parent.parent / ".env")

sys.path.insert(0, str(Path(__file__).parent.parent))

try:
    from app.database.supabase_client import get_supabase_client

    client = get_supabase_client()
    print("✓ Connected to Supabase\n")

    # Check buildings
    buildings_result = client.table("buildings").select("id, code, name", count="exact").execute()
    print(f"Buildings: {buildings_result.count}")
    if buildings_result.data:
        for b in buildings_result.data[:5]:
            print(f"  - {b['code']}: {b['name']}")
    print()

    # Check equipment total
    equipment_result = client.table("equipment").select("id", count="exact").execute()
    print(f"Total Equipment: {equipment_result.count}")

    # Equipment by building
    if buildings_result.data:
        print("\nEquipment per building:")
        for building in buildings_result.data[:5]:
            eq_result = (
                client.table("equipment").select("id", count="exact").eq("building_id", building["id"]).execute()
            )
            print(f"  {building['code']}: {eq_result.count} items")

    # Check zones
    zones_result = client.table("hvac_zones").select("id", count="exact").execute()
    print(f"\nHVAC Zones: {zones_result.count}")

    # Sample equipment from site-002
    if buildings_result.data:
        site002 = next((b for b in buildings_result.data if b["code"] == "site-002"), None)
        if site002:
            sample = (
                client.table("equipment").select("code, name, type").eq("building_id", site002["id"]).limit(5).execute()
            )
            if sample.data:
                print("\nSample equipment from site-002:")
                for item in sample.data:
                    print(f"  {item['code']}: {item['name']} ({item['type']})")

    print("\n" + "=" * 60)
    if equipment_result.count == 0:
        print("⚠️  Supabase equipment table is EMPTY - needs seeding!")
        print("\nRun: python backend/scripts/seed_equipment_to_supabase.py")
    elif equipment_result.count < 50:
        print("⚠️  Supabase has only partial data - may need full seeding")
    else:
        print("✓ Supabase appears to be properly seeded with equipment data")

except Exception as e:
    print(f"✗ Error: {e}")
    import traceback

    traceback.print_exc()
    sys.exit(1)
