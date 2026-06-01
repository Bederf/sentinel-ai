#!/usr/bin/env python3
"""Re-classify equipment with type=unknown using BACnet object catalog.

Looks up the bridge object catalog for each unknown equipment code and applies
the same heuristic rules used in shadow_mode_polling._classify_from_catalog.

Usage:
    cd backend && python scripts/reclassify_unknown_equipment.py
"""

import asyncio
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

import httpx

from app.config.settings import settings
from app.database.repositories.equipment_repository import EquipmentRepository

SITE_ID = "site-002"


def classify_from_catalog(code: str, catalog: dict[str, dict]) -> str:
    """Mirror of ShadowModePolling._classify_from_catalog — must stay in sync."""
    candidates = [o for o in catalog.values() if o.get("equipment_id") == code]
    if not candidates:
        return "unknown"

    point_types: set[str] = set()
    object_types: set[str] = set()
    point_names: list[str] = []
    descriptions: list[str] = []
    parent_paths: set[str] = set()

    for obj in candidates:
        point_types.add(obj.get("point_type", "").lower())
        ot = obj.get("object_type", "").lower()
        object_types.add(ot)
        point_names.append(obj.get("point_name", "").lower())
        descriptions.append(obj.get("description", "").lower())
        if obj.get("parent_path"):
            parent_paths.add(obj["parent_path"].lower())

    search_text = " ".join(point_names + descriptions)

    # Power / electrical metering
    if "active_power" in search_text or "power" in search_text:
        if "kw" in search_text or "kwh" in search_text:
            return "meter"

    # Temperature sensors
    if "temp" in search_text or "temperature" in search_text:
        if "zone" in search_text or "space" in search_text:
            return "zone_sensor"
        if "return" in search_text or "supply" in search_text:
            return "ahu"
        return "zone_sensor"

    # Humidity sensors
    if "humidity" in search_text or "rh" in search_text.split():
        return "zone_sensor"

    # CO2 sensors
    if "co2" in search_text:
        return "zone_sensor"

    # Binary outputs / relays → lighting
    if "binary_output" in object_types or "binary_value" in object_types:
        return "lighting_zone"

    # Presence / occupancy
    if "occupancy" in search_text or "presence" in search_text:
        return "zone_sensor"

    # Parent-path hints
    for path in parent_paths:
        if "/lighting/" in path or "/dali/" in path:
            return "lighting_zone"
        if "/hvac/" in path or "/ahu/" in path:
            return "ahu"

    # All analog inputs → generic sensor
    if object_types == {"analog_input"}:
        return "zone_sensor"

    return "unknown"


async def main():
    repo = EquipmentRepository()

    # Resolve site UUID for site-002
    from supabase import create_client

    sb = create_client(settings.supabase_url, settings.supabase_service_role_key)
    site_rows = sb.table("sites").select("id").eq("code", SITE_ID).execute()
    site_uuid = site_rows.data[0]["id"] if site_rows.data else None
    print(f"Site UUID: {site_uuid}")

    # Load all equipment for this site, filter to unknown type
    all_eq = repo.get_all(site_uuid)
    unknown_eq = [e for e in all_eq if e.get("type") == "unknown"]
    print(f"Unknown equipment to reclassify: {len(unknown_eq)}")

    # Bridge credentials
    bridge_base = getattr(settings, "simbiot_api_url", None) or "http://10.99.0.1:8080"
    bridge_token = getattr(settings, "simbiot_api_token", None) or ""
    auth_headers = {"Authorization": f"Bearer {bridge_token}"} if bridge_token else {}

    # Load object catalog from bridge
    object_catalog = {}
    async with httpx.AsyncClient(timeout=30.0) as client:
        try:
            resp = await client.get(
                f"{bridge_base}/api/sites/{SITE_ID}/objects",
                headers=auth_headers,
                params={"limit": 500},
            )
            if resp.status_code == 200:
                raw_objs = resp.json()
                if isinstance(raw_objs, list):
                    object_catalog = {o["object_id"]: o for o in raw_objs}
                elif isinstance(raw_objs, dict) and "objects" in raw_objs:
                    object_catalog = {o["object_id"]: o for o in raw_objs["objects"]}
                print(f"Bridge object catalog: {len(object_catalog)} entries")
            else:
                print(f"Bridge returned {resp.status_code}: {resp.text[:100]}")
                print("Falling back to name-based heuristics...")
        except Exception as e:
            print(f"Bridge unavailable: {e}")
            print("Using name-based heuristics instead...")

    # ── Reclassify ──
    updated = 0
    skipped = 0
    for eq in unknown_eq:
        code = eq.get("code", "")
        if not code:
            continue

        new_type = classify_from_catalog(code, object_catalog)

        eq_id = eq.get("id")  # UUID for CacheInvalidation
        eq_code = eq.get("code")  # used by repo.update()

        if new_type != "unknown":
            try:
                repo.update(eq_code, {"type": new_type})
                updated += 1
                print(f"  ✓ {code}: unknown → {new_type}")
            except Exception as e:
                print(f"  ✗ {code}: failed to update: {e}")
        else:
            # Fallback: type from code pattern (e.g. S002-WEATHER → ahu, S002-LTG → lighting_zone)
            fallback = None
            code_upper = code.upper()
            if "WEATHER" in code_upper:
                fallback = "ahu"
            elif "LTG" in code_upper:
                fallback = "lighting_zone"
            elif "-L2-" in code_upper or "-L1-" in code_upper or "-L0-" in code_upper:
                # Floor-coded G-* sensors are zone sensors
                if "G-" in code_upper:
                    fallback = "zone_sensor"

            if fallback:
                try:
                    repo.update(eq_code, {"type": fallback})
                    updated += 1
                    print(f"  ✓ {code}: unknown → {fallback} (code pattern fallback)")
                except Exception as e:
                    print(f"  ✗ {code}: fallback failed: {e}")
            else:
                # Second-pass fallbacks for the remaining patterns
                fallback2 = None
                code_upper = code.upper()
                if code.startswith("S002-UNKNOWN-G-"):
                    # G-* sensors without BACnet catalog → zone sensors
                    fallback2 = "zone_sensor"
                elif "CO2" in code_upper:
                    fallback2 = "zone_sensor"
                elif "R-" in code and code.count("-") >= 2:
                    # S002-UNKNOWN-R-001 → outdoor air sensor
                    fallback2 = "outdoor_air_sensor"
                elif "-L1-" in code_upper or "-L2-" in code_upper:
                    # Floor zone sensors
                    fallback2 = "zone_sensor"
                elif "B1-" in code_upper:
                    # Basement area sensors
                    fallback2 = "zone_sensor"

                if fallback2:
                    try:
                        repo.update(eq_code, {"type": fallback2})
                        updated += 1
                        print(f"  ✓ {code}: unknown → {fallback2} (pattern v2)")
                    except Exception as e:
                        print(f"  ✗ {code}: v2 fallback failed: {e}")
                else:
                    skipped += 1
                    print(f"  - {code}: still unknown")

    print(f"\nDone: {updated} updated, {skipped} still unknown.")


if __name__ == "__main__":
    asyncio.run(main())
