"""
Populate bacnet_device_id on S002 equipment from JACE device instance numbers.

The Niagara BACnet adapter reads `device.metadata["bacnet_device_id"]` to address the
physical JACE on the BACnet/IP network. Without it, every supervised setpoint write
fails with "Device <id> has no bacnet_device_id in metadata".

This script writes the field into:
  1. Equipment JSON files at backend/app/data/sites/site-002/equipment/*.json
  2. DB `equipment.network_info` JSONB column (mirror — used by work_orders.py audit display)

Usage:
  # Edit BACNET_DEVICE_MAP below with the 3 JACE instance numbers, then:
  python3 scripts/populate_bacnet_device_ids.py --dry-run
  python3 scripts/populate_bacnet_device_ids.py --apply
  python3 scripts/populate_bacnet_device_ids.py --verify

Heuristic assignment of nc:X -> equipment prefix (validate with operator):
  nc:18 -> B1 plant (AHU/CHILLER/CT/PUMP/GEN/UPS/MTR-B01, etc.)
  nc:10 -> L1 floor (FCU/VAV/LUM/DALI-L1)
  nc:15 -> L2 floor (FCU/VAV/LUM-L2)
"""

from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path
from typing import Any

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from app.database.supabase_client import get_supabase_client  # noqa: E402

SITE_ID = "site-002"
SITE_UUID = "d7ad3a57-a67c-4aa3-968b-fb4566e07246"
EQUIPMENT_DIR = Path(__file__).resolve().parent.parent / "app" / "data" / "sites" / SITE_ID / "equipment"

# ---------------------------------------------------------------------------
# EDIT THIS MAP with the 3 JACE BACnet device instance numbers from the site operator.
# Key = the JACE / Niagara controller ID; Value = the BACnet device instance number.
# Example values below are placeholders — MUST be replaced with real operator input.
# ---------------------------------------------------------------------------
BACNET_DEVICE_MAP: dict[str, int] = {
    "nc:18": 3741,  # B1 plant field controller — confirmed by operator 2026-06-27
    "nc:10": 3745,  # L1 floor field controller — confirmed by operator 2026-06-27
    "nc:15": 3748,  # L2 floor field controller — confirmed by operator 2026-06-27
}

# Heuristic nc:X -> equipment filename prefix (case-insensitive substring match).
# Operator to validate or override; safe default keeps each JACE on a single value.
JACE_TO_PREFIX: dict[str, tuple[str, ...]] = {
    "nc:18": ("-B01", "-B1-001", "-R01", "-R001", "-001"),  # B1 plant / older chiller
    "nc:10": ("-L1-", "-101", "-202", "-102", "-201"),  # L1 floor / mixed
    "nc:15": ("-L2-", "-L2_A", "-L2_B"),  # L2 floor
}

# Equipment types that are not BACnet (DALI, etc.) — skip silently.
NON_BACNET_PROTOCOLS = {"dali", "modbus", "knx", "mqtt"}


def _jace_for_filename(name: str) -> str | None:
    """Return the nc:X key whose prefix matches the equipment filename, or None."""
    upper = name.upper()
    for jace, prefixes in JACE_TO_PREFIX.items():
        for prefix in prefixes:
            if prefix.upper() in upper:
                return jace
    return None


def _resolve_targets() -> list[tuple[Path, dict[str, Any], int, str]]:
    """Walk equipment JSONs; return [(path, parsed_json, bacnet_device_id, jace_key)] for BACnet files."""
    out: list[tuple[Path, dict[str, Any], int, str]] = []
    for path in sorted(EQUIPMENT_DIR.glob("*.json")):
        try:
            with path.open() as f:
                data = json.load(f)
        except (OSError, json.JSONDecodeError) as e:
            print(f"  ! skip {path.name}: {e}")
            continue

        protocol = (data.get("protocol") or "bacnet").lower()
        if protocol in NON_BACNET_PROTOCOLS:
            continue
        # Most equipment lacks explicit protocol; default BACnet here matches the
        # transform in backend/app/api/devices.py.
        if protocol not in {"bacnet", ""}:
            continue

        jace = _jace_for_filename(path.stem)
        if jace is None:
            print(f"  ? no JACE match for {path.name} — add to JACE_TO_PREFIX")
            continue
        if jace not in BACNET_DEVICE_MAP:
            print(f"  ! {path.name} maps to {jace} but {jace} not in BACNET_DEVICE_MAP")
            continue

        out.append((path, data, BACNET_DEVICE_MAP[jace], jace))
    return out


def cmd_dry_run() -> int:
    targets = _resolve_targets()
    if not targets:
        print("No targets resolved — check JACE_TO_PREFIX and BACNET_DEVICE_MAP.")
        return 1
    print(f"Would update {len(targets)} files:")
    by_jace: dict[str, list[str]] = {}
    for path, _data, dev_id, jace in targets:
        by_jace.setdefault(f"{jace} -> {dev_id}", []).append(path.name)
    for key, files in by_jace.items():
        print(f"  {key}  ({len(files)} files)")
    for f in files[:3]:
        print(f"    - {f}")
    if len(files) > 3:
        print(f"    ... and {len(files) - 3} more")
    return 0


def cmd_apply() -> int:
    targets = _resolve_targets()
    if not targets:
        print("No targets resolved — check JACE_TO_PREFIX and BACNET_DEVICE_MAP.")
        return 1

    # 1. Write JSON files
    for path, data, dev_id, jace in targets:
        metadata = data.setdefault("metadata", {})
        old = metadata.get("bacnet_device_id")
        metadata["bacnet_device_id"] = dev_id
        metadata["bacnet_jace"] = jace  # provenance — where the value came from
        with path.open("w") as f:
            json.dump(data, f, indent=2)
            f.write("\n")
        print(f"  {path.name}: {old} -> {dev_id} ({jace})")

    # 2. Mirror to DB equipment.network_info
    client = get_supabase_client()
    updated_db = 0
    failed_db: list[str] = []
    for path, _data, dev_id, jace in targets:
        equipment_id = path.stem  # S002-AHU-B01 etc.
        # network_info shape must match work_orders.py:411 — it reads .get("bacnet_device_id")
        network_info = {"bacnet_device_id": dev_id, "bacnet_jace": jace}
        try:
            result = (
                client.table("equipment")
                .update({"network_info": network_info})
                .eq("site_id", SITE_UUID)
                .eq("equipment_code", equipment_id)
                .execute()
            )
            if result.data:
                updated_db += 1
            else:
                # Row may exist by 'id' (UUID) or 'code' (S002-AHU-B01) — try both
                alt = (
                    client.table("equipment")
                    .update({"network_info": network_info})
                    .eq("site_id", SITE_UUID)
                    .eq("id", equipment_id)
                    .execute()
                )
                if alt.data:
                    updated_db += 1
                else:
                    failed_db.append(equipment_id)
        except Exception as e:  # noqa: BLE001
            failed_db.append(f"{equipment_id}: {e}")

    print(f"\nJSON files updated: {len(targets)}")
    print(f"DB rows updated:    {updated_db}")
    if failed_db:
        print(f"DB rows failed ({len(failed_db)}):")
        for failed in failed_db:
            print(f"  - {failed}")
    return 0 if not failed_db else 2


def cmd_verify() -> int:
    """Read back via the production transform; print bacnet_device_id per file."""
    from app.api.devices import _transform_equipment_to_device

    targets = _resolve_targets()
    failed = 0
    for path, _data, expected, jace in targets:
        with path.open() as f:
            data = json.load(f)
        device = _transform_equipment_to_device(data)
        if device is None:
            print(f"  X {path.name}: transform returned None")
            failed += 1
            continue
        actual = device["metadata"].get("bacnet_device_id")
        status = "OK" if actual == expected else "MISMATCH"
        if status != "OK":
            failed += 1
        print(f"  [{status}] {path.name}: expected={expected}  actual={actual}  jace={jace}")
    print(f"\n{len(targets) - failed}/{len(targets)} verified")
    return 0 if failed == 0 else 1


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.split("\n", 1)[0])
    group = parser.add_mutually_exclusive_group(required=True)
    group.add_argument("--dry-run", action="store_true", help="Print the planned updates, write nothing")
    group.add_argument("--apply", action="store_true", help="Write JSON files and update DB")
    group.add_argument("--verify", action="store_true", help="Read back via the production transform")
    args = parser.parse_args()

    if args.dry_run:
        return cmd_dry_run()
    if args.apply:
        return cmd_apply()
    if args.verify:
        return cmd_verify()
    return 0


if __name__ == "__main__":
    sys.exit(main())
