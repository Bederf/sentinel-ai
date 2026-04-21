#!/usr/bin/env python3
"""
Check equipment data availability in JSON fallback files.

This script verifies what equipment data exists in JSON files,
which the API should use if Supabase is empty or unavailable.
"""

import json
from pathlib import Path

DATA_PATH = Path("/opt/bms-intelligence/backend/app/data")
BUILDINGS_PATH = DATA_PATH / "sites"


def count_json_equipment(site_code: str) -> dict:
    """Count equipment available in JSON files for a site."""
    site_path = BUILDINGS_PATH / site_code
    equipment_dir = site_path / "equipment"

    counts = {
        "equipment_files": 0,
        "hvac_zones": 0,
        "generators": 0,
        "energy_centre": 0,
        "dali_controllers": 0,
    }

    # Count individual equipment files
    if equipment_dir.exists():
        counts["equipment_files"] = len(list(equipment_dir.glob("*.json")))

    # Count HVAC zones
    zones_file = site_path / "zones.json"
    if zones_file.exists():
        try:
            with open(zones_file) as f:
                zones = json.load(f)
                counts["hvac_zones"] = len(zones) if isinstance(zones, list) else 0
        except Exception:
            pass

    # Count generators
    gen_file = site_path / "generators.json"
    if gen_file.exists():
        try:
            with open(gen_file) as f:
                gen_data = json.load(f)
                counts["generators"] = (
                    len(gen_data.get("generators", []))
                    + len(gen_data.get("groups", []))
                    + len(gen_data.get("diesel_tanks", []))
                )
        except Exception:
            pass

    # Count energy centre
    ec_file = site_path / "energy_centre.json"
    if ec_file.exists():
        try:
            with open(ec_file) as f:
                ec_data = json.load(f)
                counts["energy_centre"] = (
                    (1 if ec_data.get("energy_centre") else 0)
                    + len(ec_data.get("mv_incomers", []))
                    + len(ec_data.get("transformers", []))
                    + len(ec_data.get("lv_switchboards", []))
                    + len(ec_data.get("ats_units", []))
                    + len(ec_data.get("power_meters", []))
                    + len(ec_data.get("pfc_banks", []))
                    + len(ec_data.get("ups_systems", []))
                    + len(ec_data.get("feeders", []))
                )
        except Exception:
            pass

    return counts


print("=" * 80)
print("JSON EQUIPMENT FALLBACK DATA AVAILABILITY")
print("=" * 80)

# List all sites
if BUILDINGS_PATH.exists():
    sites = sorted([d.name for d in BUILDINGS_PATH.iterdir() if d.is_dir() and not d.name.startswith("_")])

    print(f"\nFound {len(sites)} sites:")
    print()

    total_equipment = 0

    for site_code in sites:
        counts = count_json_equipment(site_code)
        total = sum(v for k, v in counts.items() if k != "equipment_files")
        total += counts["equipment_files"]

        print(f"  {site_code}:")
        print(f"    Equipment files:  {counts['equipment_files']:3d}")
        print(f"    HVAC zones:       {counts['hvac_zones']:3d}")
        print(f"    Generators:       {counts['generators']:3d}")
        print(f"    Energy centre:    {counts['energy_centre']:3d}")
        print("    ───────────────────────")
        print(f"    TOTAL:            {total:3d}")
        print()

        total_equipment += total

    print("=" * 80)
    print(f"TOTAL EQUIPMENT ACROSS ALL SITES: {total_equipment}")
    print("=" * 80)

    # Specific detail for site-002
    print("\nDETAIL: site-002 Equipment Files")
    print("-" * 80)
    site_002_equip = BUILDINGS_PATH / "site-002" / "equipment"
    if site_002_equip.exists():
        files = sorted(site_002_equip.glob("*.json"))
        print(f"Total files: {len(files)}")
        print("\nFirst 10 files:")
        for f in files[:10]:
            print(f"  - {f.name}")
        if len(files) > 10:
            print(f"  ... and {len(files) - 10} more")

    print("\n" + "=" * 80)
    print("NEXT STEPS:")
    print("=" * 80)
    print("""
If JSON shows equipment (good) but API shows only 1:
  → Supabase query is returning fewer results
  → Supabase building or equipment table is empty
  → Check: SELECT COUNT(*) FROM equipment WHERE site_id = '...'

If JSON shows 0 equipment (bad):
  → Check if data/buildings/{site-code}/equipment/ exists
  → Check if zones.json, generators.json, energy_centre.json exist
  → May need to seed/restore demo data

To verify API is using correct source:
  → curl http://localhost:9095/api/buildings/site-002/equipment | jq '.source'
  → Should show "supabase" or "json" depending on what's available
""")
else:
    print(f"ERROR: Buildings path not found: {BUILDINGS_PATH}")
