import argparse
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
os.environ["ENVIRONMENT"] = "development"

import httpx
from app.database.supabase_client import get_supabase_client

parser = argparse.ArgumentParser(description="Create point_asset_mappings from a bridge object catalog")
parser.add_argument("--site-id", required=True, help="Site code, e.g. S002 or site-002")
args = parser.parse_args()

raw = args.site_id
site_code = f"site-{raw.removeprefix('site-').removeprefix('S')}"
site_num = site_code.split("-")[1]

sb = get_supabase_client()

print(f"Creating point_asset_mappings for {site_code}...")

site = sb.table("sites").select("id").eq("code", site_code).limit(1).execute()
if not site.data:
    print(f"ERROR: site {site_code} not found")
    sys.exit(1)
site_uuid = site.data[0]["id"]
print(f"Site UUID: {site_uuid}")

rows = (
    sb.table("site_adapter_config")
    .select("connection_config")
    .eq("site_id", site_code)
    .ilike("protocol", "%bridge%")
    .limit(1)
    .execute()
)
if not rows.data:
    print(f"ERROR: no bridge adapter config found for {site_code}")
    sys.exit(1)
cfg = rows.data[0]["connection_config"]

base_url = cfg["base_url"].rstrip("/")

url = f"{base_url}/api/sites/{site_code}/objects"
resp = httpx.get(url, params={"limit": 2000}, headers={"Authorization": f"Bearer {cfg['token']}"}, timeout=60)
if resp.status_code == 404:
    print("Bridge does not recognise site code, trying /objects directly...")
    url = f"{base_url}/objects"
    resp = httpx.get(url, params={"limit": 2000}, headers={"Authorization": f"Bearer {cfg['token']}"}, timeout=60)
resp.raise_for_status()
objects = resp.json().get("objects", [])
print(f"Fetched {len(objects)} objects from bridge catalog ({url})")

mappings = []
for obj in objects:
    equipment_id = (obj.get("equipment_id") or "").strip()
    eq_type = obj.get("equipment_type") or "unknown"
    bridge_writable = obj.get("writable") is True
    pt_type = (obj.get("point_type") or "").strip()
    if not pt_type and bridge_writable:
        pt_type = "writable"
    if not pt_type:
        pt_type = "sensor"
    object_type = (obj.get("object_type") or "").strip()
    instance = obj.get("instance")
    unit = obj.get("unit")
    parameter_type = pt_type
    if object_type and instance is not None:
        parameter_type = f"{parameter_type}:{object_type},{instance}"
    if unit:
        parameter_type = f"{parameter_type}:{unit}"
    match_conf = "exact" if equipment_id else "fuzzy"
    mappings.append(
        {
            "site_id": site_uuid,
            "bms_point_id": obj.get("object_id", ""),
            "extracted_asset_id": equipment_id,
            "parameter_name": obj.get("object_name", ""),
            "parameter_type": parameter_type,
            "match_confidence": match_conf,
            "is_verified": match_conf == "exact" and bridge_writable,
            "mapping_source": "catalog_resolver",
        }
    )

batch_size = 500
for i in range(0, len(mappings), batch_size):
    batch = mappings[i : i + batch_size]
    sb.table("point_asset_mappings").upsert(batch, on_conflict="site_id,bms_point_id").execute()
    print(f"  Upserted batch {i // batch_size + 1} ({len(batch)} rows)")

print(f"Done! {len(mappings)} point_asset_mappings created for {site_code}")
