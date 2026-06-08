"""
Backfill equipment service history for site-002 large serviceable units.

Extracts equipment data, backfills missing commissioning_date intelligently,
and upserts into equipment_service_history. Links equipment back to service_history.
"""

import csv
import json
import os
import sys
from datetime import date, datetime

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from app.database.supabase_client import get_supabase_client

SITE_ID = "site-002"
SITE_UUID = "d7ad3a57-a67c-4aa3-968b-fb4566e07246"

LARGE_EQUIPMENT_TYPES = [
    "chiller",
    "ahu",
    "pump",
    "generator",
    "cooling_tower",
    "ups",
    "bess",
]

MANUFACTURER_INSTALL_YEAR_ESTIMATES = {
    "York": {"typical_year": 2010, "range": (2005, 2015)},
    "Carrier": {"typical_year": 2012, "range": (2008, 2018)},
    "Grundfos": {"typical_year": 2015, "range": (2012, 2020)},
    "Cummins": {"typical_year": 2012, "range": (2010, 2015)},
    "Baltimore Aircoil": {"typical_year": 2010, "range": (2005, 2015)},
    "Eaton": {"typical_year": 2012, "range": (2010, 2015)},
    "Huawei": {"typical_year": 2024, "range": (2023, 2025)},
}

EQUIPMENT_TYPE_INSTALL_YEAR_ESTIMATES = {
    "chiller": 2010,
    "ahu": 2012,
    "pump": 2014,
    "generator": 2012,
    "cooling_tower": 2010,
    "ups": 2012,
    "bess": 2024,
}


def extract_equipment(supabase) -> list[dict]:
    """Phase A: Extract all large serviceable equipment for site-002."""
    site_row = supabase.table("sites").select("id").eq("code", SITE_ID).limit(1).execute()
    site_uuid = site_row.data[0]["id"] if site_row.data else None
    if not site_uuid:
        print("ERROR: site-002 not found")
        sys.exit(1)

    rows = (
        supabase.table("equipment")
        .select("code,type,commissioning_date,manufacturer,model,notes,created_at,status")
        .eq("site_id", site_uuid)
        .in_("type", LARGE_EQUIPMENT_TYPES)
        .execute()
    )
    return rows.data


def estimate_commissioning_date(eq: dict) -> tuple[date, str]:
    """Phase B: Backfill missing commissioning_date intelligently."""
    existing = eq.get("commissioning_date")
    if existing:
        d = datetime.fromisoformat(str(existing))
        return d.date(), "original"

    manufacturer = (eq.get("manufacturer") or "").strip()
    eq_type = (eq.get("type") or "").lower()
    notes = eq.get("notes") or ""
    created_at_raw = eq.get("created_at")

    # 1. Manufacturer estimate
    if manufacturer in MANUFACTURER_INSTALL_YEAR_ESTIMATES:
        est = MANUFACTURER_INSTALL_YEAR_ESTIMATES[manufacturer]
        year = est["typical_year"]
        return date(year, 1, 1), f"manufacturer_estimated:{manufacturer}"

    # 2. Parse notes for a year
    import re

    year_match = re.search(r"(19|20)\d{2}", notes)
    if year_match:
        year = int(year_match.group(0))
        return date(year, 1, 1), "parsed_from_notes"

    # 3. Type estimate
    if eq_type in EQUIPMENT_TYPE_INSTALL_YEAR_ESTIMATES:
        year = EQUIPMENT_TYPE_INSTALL_YEAR_ESTIMATES[eq_type]
        return date(year, 1, 1), f"type_estimated:{eq_type}"

    # 4. Created_at proxy
    if created_at_raw:
        created_year = datetime.fromisoformat(str(created_at_raw).replace("Z", "+00:00")).year
        return date(created_year - 3, 1, 1), "created_at_proxy"

    # 5. Fallback
    return date(2015, 1, 1), "fallback_default"


def run_backfill():
    supabase = get_supabase_client()

    # Phase A: Extract
    equipment_list = extract_equipment(supabase)
    print(f"\n=== Phase A: Extracted {len(equipment_list)} large serviceable units ===\n")

    raw_path = "/tmp/site002_equipment_raw.json"
    with open(raw_path, "w") as f:
        json.dump(equipment_list, f, indent=2, default=str)
    print(f"Raw data saved to {raw_path}\n")

    # Phase B + C: Build service history records
    records = []
    csv_rows = []
    backfill_count = 0
    original_count = 0

    for eq in equipment_list:
        commissioning_date, source = estimate_commissioning_date(eq)
        if source == "original":
            original_count += 1
        else:
            backfill_count += 1

        confidence_notes = (
            f"Age-only baseline. Commissioning date sourced from: {source}. "
            f"No service history or runtime hours available."
        )

        records.append(
            {
                "site_id": SITE_ID,
                "equipment_code": eq["code"],
                "equipment_type": eq["type"],
                "commissioning_date": commissioning_date.isoformat(),
                "manufacturer": eq.get("manufacturer"),
                "model": eq.get("model"),
                "last_service_date": None,
                "service_interval_months": None,
                "runtime_hours": None,
                "baseline_calculation_method": "age_only",
                "confidence_notes": confidence_notes,
            }
        )

        csv_rows.append(
            {
                "equipment_code": eq["code"],
                "equipment_type": eq["type"],
                "commissioning_date": commissioning_date.isoformat(),
                "commissioning_date_source": source,
                "manufacturer": eq.get("manufacturer") or "",
                "baseline_calculation_method": "age_only",
            }
        )

    print(f"=== Phase C: {original_count} original dates, {backfill_count} backfilled ===\n")
    for r in records:
        src = (
            "original"
            if "original" in r["confidence_notes"]
            else r["confidence_notes"].split("from: ")[1].split(".")[0]
        )
        print(f"  {r['equipment_code']:30s} → {r['commissioning_date']}  [{src}]")

    # Phase D: Upsert into equipment_service_history
    print(f"\n=== Phase D: Upserting {len(records)} records ===\n")
    for rec in records:
        supabase.table("equipment_service_history").upsert(rec, on_conflict="site_id,equipment_code").execute()
        print(f"  {rec['equipment_code']:30s} → {rec['commissioning_date']} (upserted)")

    # Phase E: Link equipment to service_history
    print("\n=== Phase E: Linking equipment to service_history ===\n")
    site_row = supabase.table("sites").select("id").eq("code", SITE_ID).limit(1).execute()
    site_uuid = site_row.data[0]["id"]

    for rec in records:
        # Find the service_history record
        sh = (
            supabase.table("equipment_service_history")
            .select("id")
            .eq("site_id", SITE_ID)
            .eq("equipment_code", rec["equipment_code"])
            .limit(1)
            .execute()
        )
        if not sh.data:
            print(f"  WARN: No service_history for {rec['equipment_code']}")
            continue

        sh_id = sh.data[0]["id"]
        supabase.table("equipment").update(
            {
                "service_history_id": sh_id,
                "baseline_sourced_from": "age_only",
                "health_score_confidence": None,
            }
        ).eq("site_id", site_uuid).eq("code", rec["equipment_code"]).execute()
        print(f"  {rec['equipment_code']:30s} → linked to service_history {sh_id[:8]}")

    # CSV export
    csv_path = "/tmp/site002_equipment_service_history_backfill.csv"
    with open(csv_path, "w", newline="") as f:
        writer = csv.DictWriter(
            f,
            fieldnames=[
                "equipment_code",
                "equipment_type",
                "commissioning_date",
                "commissioning_date_source",
                "manufacturer",
                "baseline_calculation_method",
            ],
        )
        writer.writeheader()
        writer.writerows(csv_rows)
    print(f"\n=== CSV export: {csv_path} ({len(csv_rows)} rows) ===\n")

    # Summary
    print("=== Summary ===")
    print(f"  Total large units processed: {len(equipment_list)}")
    print(f"  Original commissioning dates: {original_count}")
    print(f"  Backfilled commissioning dates: {backfill_count}")
    print("  Baseline calculation method: age_only (all)")
    print("  Health score confidence: NULL (pending baseline calculation)")
    print()


if __name__ == "__main__":
    run_backfill()
