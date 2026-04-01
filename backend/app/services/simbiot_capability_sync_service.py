"""Durable SIMBIOT capability sync into Supabase equipment records."""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Optional

from app.database.supabase_client import get_supabase_client
from app.services.simbiot import BmsConnectionConfig, create_bms_adapter


def _normalize_id(value: Any) -> str:
    return str(value or "").strip().lower()


def _extract_equipment_device_candidates(equipment: dict[str, Any]) -> list[str]:
    metadata = equipment.get("metadata") or {}
    device_info = equipment.get("device_info") or {}
    operating_data = equipment.get("operating_data") or {}
    candidates = [
        equipment.get("code"),
        equipment.get("id"),
        metadata.get("device_id"),
        metadata.get("bacnet_device_id"),
        metadata.get("controller_id"),
        device_info.get("device_id"),
        device_info.get("bacnet_device_id"),
        device_info.get("controller_id"),
        operating_data.get("device_id"),
        operating_data.get("bacnet_device_id"),
    ]
    normalized = [_normalize_id(c) for c in candidates if c is not None and str(c).strip()]
    # preserve order, remove dupes
    out: list[str] = []
    seen: set[str] = set()
    for c in normalized:
        if c not in seen:
            out.append(c)
            seen.add(c)
    return out


async def sync_site_capabilities_to_supabase(
    *,
    site_code: str,
    bms_vendor: str = "bacnet",
    host: Optional[str] = None,
    port: Optional[int] = None,
    commissioning: bool = True,
) -> dict[str, Any]:
    """Sync site capabilities into equipment.operating_data for existing assets."""
    client = get_supabase_client()
    site_result = client.table("sites").select("id,code").eq("code", site_code).limit(1).execute()
    if not site_result.data:
        raise ValueError(f"Site '{site_code}' not found in Supabase")

    site_uuid = site_result.data[0]["id"]
    # Backward-compatible column selection across deployments.
    try:
        eq_result = (
            client.table("equipment")
            .select("id, code, metadata, device_info, operating_data")
            .eq("site_id", site_uuid)
            .execute()
        )
    except Exception:
        eq_result = (
            client.table("equipment")
            .select("id, code, device_info, operating_data")
            .eq("site_id", site_uuid)
            .execute()
        )
    equipment_rows = eq_result.data or []

    adapter = create_bms_adapter(adapter_type=bms_vendor, bms_vendor=bms_vendor, device_ip=host)
    cfg = BmsConnectionConfig(
        site_id=site_code,
        source_type=bms_vendor,
        host=host,
        port=port,
        metadata={"commissioning": commissioning},
    )

    try:
        status = await adapter.connect(cfg)
        if not status.connected:
            raise RuntimeError(status.message or "SIMBIOT adapter unavailable")

        devices = await adapter.discover_devices()
        device_caps: dict[str, dict[str, Any]] = {}
        for dev in devices:
            points = await adapter.discover_points(dev.device_id)
            writable_count = sum(1 for p in points if p.writable)
            key = _normalize_id(dev.device_id)
            device_caps[key] = {
                "device_id": str(dev.device_id),
                "display_name": dev.display_name,
                "point_count": len(points),
                "writable_point_count": writable_count,
                "controllable": writable_count > 0,
                "synced_at": datetime.now(timezone.utc).isoformat(),
            }

        updated = 0
        matched = 0
        unmatched = 0
        now = datetime.now(timezone.utc).isoformat()
        for eq in equipment_rows:
            candidates = _extract_equipment_device_candidates(eq)
            matched_cap = None
            for candidate in candidates:
                if candidate in device_caps:
                    matched_cap = device_caps[candidate]
                    break

            operating_data = dict(eq.get("operating_data") or {})
            cap_state = dict(operating_data.get("capability_sync") or {})
            cap_state.update(
                {
                    "last_sync_at": now,
                    "vendor": bms_vendor,
                    "site_code": site_code,
                }
            )
            if matched_cap:
                matched += 1
                cap_state.update(
                    {
                        "linked_device_id": matched_cap["device_id"],
                        "controllable": matched_cap["controllable"],
                        "writable_point_count": matched_cap["writable_point_count"],
                        "point_count": matched_cap["point_count"],
                    }
                )
            else:
                unmatched += 1
                cap_state.update(
                    {
                        "linked_device_id": None,
                        "controllable": False,
                        "writable_point_count": 0,
                        "point_count": 0,
                    }
                )
            operating_data["capability_sync"] = cap_state

            client.table("equipment").update({"operating_data": operating_data, "updated_at": now}).eq("id", eq["id"]).execute()
            updated += 1

        return {
            "site_code": site_code,
            "equipment_total": len(equipment_rows),
            "devices_discovered": len(devices),
            "matched": matched,
            "unmatched": unmatched,
            "updated": updated,
        }
    finally:
        try:
            await adapter.disconnect()
        except Exception:
            pass
