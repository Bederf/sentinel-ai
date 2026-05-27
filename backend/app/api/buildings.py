"""
Building Management API
=======================
REST API for managing buildings (onboarding, configuration, activation).

To add a new building:
1. POST /api/buildings - Create building with metadata
2. POST /api/buildings/{id}/desks - Upload desk data
3. POST /api/buildings/{id}/zones - Upload zone data
4. POST /api/buildings/{id}/activate - Activate building

To remove a building:
1. POST /api/buildings/{id}/deactivate - Deactivate (keeps data)
2. DELETE /api/buildings/{id} - Remove completely
"""

import json
import logging
import re
import shutil
from pathlib import Path
from typing import Literal

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel

from app.core.site_resolver import get_registered_sites
from app.middleware.auth_middleware import require_role, require_site_access
from app.models.auth import AuthContext, SentinelRole
from app.services.device_abstraction import device_manager
from app.services.site_loader import get_site_loader

logger = logging.getLogger(__name__)


def _building_to_site(site_id: str) -> str:
    """Map user-facing site identifiers to canonical site code.

    Supports:
    - exact code match (e.g. S002)
    - friendly name match
    - legacy "site-002" form -> "S002" when available
    """
    sites = get_registered_sites()
    normalized_input = (site_id or "").strip()
    lowered_input = normalized_input.lower()

    # 1) Exact code match first.
    for site in sites:
        code = str(site.get("code", "")).strip()
        if code and code.lower() == lowered_input:
            return code

    # 2) Friendly display/name match.
    for site in sites:
        if str(site.get("name", "")).strip().lower() == lowered_input:
            return str(site.get("code", normalized_input)).strip() or normalized_input

    # 3) Convert site-002 style aliases when registry uses S002 codes.
    import re

    m = re.fullmatch(r"site-(\d+)", lowered_input)
    if m:
        s_code = f"S{m.group(1).zfill(3)}"
        for site in sites:
            code = str(site.get("code", "")).strip()
            if code.lower() == s_code.lower():
                return code

    return normalized_input


def _normalize_device_id(device_id: str) -> str:
    """Normalize device ID to S### format for matching.

    Converts 'site-002-xxx' to 'S002-xxx' format.
    """
    import re

    # Match 'site-NNN-' prefix and convert to 'SNNN-'
    match = re.match(r"^site-(\d+)-(.+)$", device_id, re.IGNORECASE)
    if match:
        site_num = match.group(1).zfill(3)  # Zero-pad to 3 digits
        rest = match.group(2)
        return f"S{site_num}-{rest}"
    return device_id


def _normalize_equipment_type(equipment_code: str, equipment_type: str) -> str:
    """Extract equipment type from code if type is unknown.

    Equipment code format: {site}-{type}-{floor}-{zone}
    Example: S002-CHILLER-B1-001 -> chiller
    """
    if equipment_type and equipment_type.lower() != "unknown":
        return equipment_type.lower()

    # Extract type from code (second segment after first hyphen)
    try:
        parts = equipment_code.split("-")
        if len(parts) >= 2:
            # Second segment is the equipment type
            type_segment = parts[1].lower()
            # Map common type aliases
            type_aliases = {
                "chiller": "chiller",
                "ahu": "ahu",
                "fcu": "fcu",
                "vav": "vav",
                "dali": "dali",
                "lum": "luminaire",
                "gen": "generator",
                "tx": "transformer",
                "ups": "ups",
                "ats": "ats",
                "mtr": "meter",
            }
            return type_aliases.get(type_segment, type_segment)
    except Exception:
        pass

    return equipment_type.lower() if equipment_type else "unknown"


# ─── Equipment display name formatters ─────────────────────────────────────────


def _format_unknown_name(eq_code: str) -> str:
    """Format display name for UNKNOWN-type equipment (sensors)."""
    code = eq_code.strip().upper()
    if code.startswith("R"):
        return "Outdoor Air Sensor Roof"
    if code.startswith("B"):
        return "Sensor Basement"
    if code.startswith("L"):
        return f"Sensor {code.replace('-', ' ')}"
    if "-" in code:
        return f"Sensor {code.replace('-', ' ')}"
    return f"Unknown Equipment {code}"


def _format_display_name(eq_type: str, eq_code: str) -> str:
    """Convert equipment code location to human-readable name.

    Format: S002-{TYPE}-{LOCATION}  →  "{TYPE} {floor} Zone {N}"

    Location codes:
      Numeric: 105 → Level 1 Zone 5, 203 → Level 2 Zone 3, 001 → Ground Zone 1
      Letter:  B01 → Basement Zone 1,  R01 → Roof Zone 1
      Legacy:  B1-001 → Basement Zone 1

    Examples:
      _format_display_name("AHU", "105")   → "AHU Level 1 Zone 5"
      _format_display_name("FCU", "203")   → "FCU Level 2 Zone 3"
      _format_display_name("VAV", "003")   → "VAV Ground Zone 3"
      _format_display_name("RTU", "R01")   → "RTU Roof Zone 1"
      _format_display_name("DB", "B01")    → "DB Basement Zone 1"
    """
    if eq_type.upper() == "UNKNOWN":
        return _format_unknown_name(eq_code)

    code = eq_code.strip().upper()

    # Legacy: B1-001 → Basement Zone 1
    legacy_match = re.match(r"^([BL])(\d)[-]?\d+$", code)
    if legacy_match:
        prefix = legacy_match.group(1)
        num = legacy_match.group(2)
        floor_part = "Basement" if prefix == "B" else f"Level {num}"
        return f"{eq_type} {floor_part}"

    # Roof: R01, R1 (not R-SOLAR style suffix)
    if code.startswith("R") and code[1:].isdigit():
        zone = code[1:]
        return f"{eq_type} Roof Zone {int(zone):02d}"

    # Basement: B01 (not B1-MAIN style — handled by legacy match above)
    if code.startswith("B") and code[1:].isdigit():
        zone = code[1:]
        return f"{eq_type} Basement Zone {int(zone):02d}"

    # Numeric: 001, 105, 203
    if code.isdigit():
        level = int(code[0])
        zone = int(code[1:])
        floor_name = "Ground" if level == 0 else f"Level {level}"
        return f"{eq_type} {floor_name} Zone {zone}"

    return f"{eq_type} {code}"


def _normalize_equipment_name(eq: dict) -> str:
    """Return equipment code as the display name.

    Simply returns the equipment code (e.g., S002-INV-R01) without
    generating long descriptive names.
    """
    return eq.get("code", eq.get("id", "Unknown"))


def _extract_location_from_code(eq_code: str) -> str:
    """Extract location from equipment code.

    Format: S002-{TYPE}-{LOCATION}

    Location codes:
      - B01, B02 → Basement Zone 1, 2
      - R01, R02 → Roof Zone 1, 2
      - 001-099 → Ground Level Zone X
      - 101-199 → Level 1 Zone X
      - 201-299 → Level 2 Zone X
      - 301-399 → Level 3 Zone X
      - G-XXX → Ground Zone XXX
    """
    if not eq_code or "-" not in eq_code:
        return ""

    parts = eq_code.split("-")
    if len(parts) < 3:
        return ""

    # Location is everything after the type (parts[1])
    loc_parts = parts[2:]
    loc_code = "-".join(loc_parts)

    # Handle different location formats
    loc_upper = loc_code.upper()

    # Basement: B01, B02
    if loc_upper.startswith("B") and len(loc_upper) >= 2 and loc_upper[1:].isdigit():
        zone_num = loc_upper[1:].lstrip("0") or "0"
        return f"Basement Zone {zone_num}"

    # Roof: R01, R02
    if loc_upper.startswith("R") and len(loc_upper) >= 2 and loc_upper[1:].isdigit():
        zone_num = loc_upper[1:].lstrip("0") or "0"
        return f"Roof Zone {zone_num}"

    # Ground prefix: G-XXX
    if loc_upper.startswith("G-"):
        zone = loc_parts[0][2:] if len(loc_parts[0]) > 2 else loc_parts[1] if len(loc_parts) > 1 else ""
        return f"Ground Zone {zone}"

    # Numeric levels: XXX
    if loc_code.isdigit():
        num = int(loc_code)
        level = num // 100
        zone = num % 100
        if level == 0:
            return f"Ground Zone {zone}"
        else:
            return f"Level {level} Zone {zone}"

    # Return as-is for unrecognized formats
    return loc_code


def _is_device_controllable(device_id: str, equipment_points: dict) -> bool:
    """Check if device is controllable by checking equipment points or device_manager.

    First checks if the equipment JSON has writable points.
    If not, falls back to checking if the device exists in device_manager with writable points.
    Handles ID format differences (site-002-xxx vs S002-xxx).
    """
    # Check equipment JSON points first
    if any(p.get("writable", False) for p in equipment_points.values()):
        return True

    # Fall back to device_manager (which includes reference devices)
    # Access the internal _devices dict directly since this is a sync function
    try:
        # Try original ID first
        device = device_manager._devices.get(device_id)

        # If not found, try normalized ID (site-002-xxx -> S002-xxx)
        if not device:
            normalized_id = _normalize_device_id(device_id)
            device = device_manager._devices.get(normalized_id)

        if device and device.points:
            return any(p.writable for p in device.points.values())
    except Exception as e:
        logger.debug(f"Could not check device_manager for {device_id}: {e}")

    return False


router = APIRouter(prefix="/api/buildings", tags=["Building Management"])

# Data path
DATA_PATH = Path(__file__).parent.parent / "data" / "buildings"


def _next_site_id() -> str:
    """Find the next available site ID across disk and Supabase."""
    import re

    base = Path(__file__).parent.parent / "data"
    existing: set[int] = set()

    for data_dir in [base / "buildings", base / "sites"]:
        if not data_dir.exists():
            continue
        for d in data_dir.iterdir():
            if d.is_dir() and d.name.startswith("site-"):
                m = re.match(r"^site-(\d+)$", d.name)
                if m:
                    existing.add(int(m.group(1)))

    # Also check Supabase for existing site codes
    try:
        from app.database.supabase_client import get_supabase_client

        client = get_supabase_client()
        result = client.table("sites").select("code").execute()
        for row in result.data or []:
            m = re.match(r"^site-(\d+)$", row.get("code", ""))
            if m:
                existing.add(int(m.group(1)))
    except Exception:
        pass

    n = 1
    while n in existing:
        n += 1
    return f"site-{n:03d}"


class BuildingCreate(BaseModel):
    """Request model for creating a building."""

    id: str | None = None
    name: str
    display_name: str | None = None
    address: str | None = ""
    timezone: str = "Africa/Johannesburg"
    floors: list[str] = []
    features: dict = {}


class BuildingUpdate(BaseModel):
    """Request model for updating a building."""

    name: str | None = None
    display_name: str | None = None
    address: str | None = None
    timezone: str | None = None
    floors: list[str] | None = None
    features: dict | None = None


class BuildingConfigUpdate(BaseModel):
    """Request model for updating building configuration from Settings UI."""

    name: str | None = None
    display_name: str | None = None
    address: str | None = None
    building_type: str | None = None  # commercial_office, retail, industrial, mixed_use
    floors: list[str] | None = None
    sqm: int | None = None
    occupancy_capacity: int | None = None
    total_desks: int | None = None
    parking_bays: int | None = None
    optimization_profile: str | None = None  # cost_saving, comfort, balanced
    sentinel_operating_mode: Literal["comfort", "cost_saving", "asset_preservation"] | None = None
    control_tier: str | None = None  # human_in_loop, supervised, automatic
    features: dict | None = None
    contacts: dict | None = None


@router.get("")
async def list_sites(current_user: dict | None = None) -> dict:
    """
    List buildings accessible to the current user.

    Returns:
        - active: List of active buildings user has access to
        - inactive: List of inactive buildings (folders exist but not in registry)
        - default_building: The default building ID
    """
    from app.database.supabase_client import Supabase

    loader = get_site_loader()
    loader.load(force=True)  # Refresh

    registry = loader.get_registry()
    active_ids = set(registry.get("active_sites", []))

    # Get user's accessible sites from database
    # user_site_access stores site UUIDs; resolve to site codes for comparison
    accessible_codes: set[str] | None = set()
    if current_user and current_user.get("email"):
        try:
            supabase = Supabase.instance()

            # Step 1: get UUIDs the user has access to
            uuids_response = (
                supabase.table("user_site_access").select("site_id").eq("user_email", current_user["email"]).execute()
            )
            uuids = [str(row["site_id"]) for row in (uuids_response.data or [])]

            # Step 2: resolve UUIDs → site codes
            if uuids:
                codes_response = supabase.table("sites").select("code").in_("id", uuids).execute()
                accessible_codes = {row["code"] for row in (codes_response.data or [])}
            else:
                accessible_codes = set()
        except Exception as e:
            logger.warning(f"Could not fetch user site access: {e}")
            # Fall back to showing all buildings if DB query fails
            accessible_codes = None
    else:
        accessible_codes = None

    # Categorize
    active = []
    inactive = []

    for site_id in loader.get_active_site_ids():
        building = loader.get_site(site_id)
        if building:
            # Check if user has access to this building
            if accessible_codes is not None and site_id not in accessible_codes:
                continue  # Skip buildings user doesn't have access to

            info = building.to_dict()
            info["status"] = "active" if site_id in active_ids else "inactive"

            # Annotate with alarm flood indicator — does NOT override equipment-derived status
            # Equipment health (when available via equipment-summary) drives status; alerts annotate
            try:
                from app.database.supabase_client import get_supabase_client

                client = get_supabase_client()
                site_row = client.table("sites").select("id").eq("code", site_id).limit(1).execute()
                if site_row.data:
                    site_uuid = site_row.data[0]["id"]
                    alerts = (
                        client.table("alerts")
                        .select("severity")
                        .eq("site_id", site_uuid)
                        .eq("resolved", False)
                        .execute()
                    )
                    if alerts.data:
                        # Only annotate, never override — status is driven by equipment health
                        info["anomaly_flag"] = True
                        info["alarm_flood"] = len(alerts.data) > 5
                        info["alert_count"] = len(alerts.data)
            except Exception:
                pass

            if site_id in active_ids:
                active.append(info)
            else:
                inactive.append(info)

    return {
        "active": active,
        "inactive": inactive,
        "default_building": registry.get("default_building"),
        "total": len(active) + len(inactive),
    }


@router.get("/{site_id}")
async def get_site(site_id: str, auth: AuthContext = Depends(require_site_access("site_id"))) -> dict:
    """
    Get building details — Supabase is the source of truth.

    Returns full building config including extended metadata (floor labels, features,
    contacts, optimization settings).
    """
    site_code = _building_to_site(site_id)

    # --- Supabase (primary) ---
    try:
        from app.database.supabase_client import get_supabase_client

        client = get_supabase_client()
        result = client.table("buildings").select("*").eq("code", site_code).single().execute()
        if result.data:
            b = result.data
            # Map Supabase row → BuildingConfig shape the frontend expects
            opt = b.get("optimization_settings") or {}
            return {
                "id": b["code"],
                "code": b["code"],
                "name": b.get("name", ""),
                "display_name": b.get("display_name") or b.get("name", ""),
                "address": b.get("address", ""),
                "type": b.get("type", "commercial_office"),
                "region": b.get("region"),
                "floors": b.get("floor_labels") or [],
                "sqm": b.get("sqm"),
                "metadata": {
                    "sqm": b.get("sqm"),
                    "occupancy_capacity": b.get("occupancy_capacity"),
                    "total_desks": b.get("total_desks"),
                    "parking_bays": b.get("parking_bays"),
                    "bms_vendor": opt.get("bms_vendor"),
                    "operating_hours": b.get("operating_hours"),
                    "year_built": b.get("year_built"),
                },
                "features": b.get("features") or {},
                "contacts": {
                    "facility_manager": b.get("contact_facility_manager"),
                    "email": b.get("contact_email"),
                    "emergency": b.get("contact_emergency") or b.get("contact_phone"),
                },
                "optimization": {
                    "active_profile": opt.get("active_profile", "balanced"),
                    "sentinel_operating_mode": opt.get(
                        "sentinel_operating_mode", opt.get("active_profile", "balanced")
                    ),
                    "control_tier": opt.get("control_tier", "supervised"),
                    "zone_overrides": opt.get("zone_overrides", []),
                    "schedule_overrides": opt.get("schedule_overrides", []),
                },
                "is_active": b.get("sentinel_processing_enabled", False),
                "onboarding_phase": b.get("onboarding_phase") or "shadow",
                "desk_count": b.get("total_desks") or b.get("equipment_count", 0),
                "zone_count": 0,
                "equipment_count": b.get("equipment_count", 0),
                "latitude": b.get("latitude"),
                "longitude": b.get("longitude"),
            }
    except Exception as e:
        logger.warning(f"Supabase lookup failed for {site_code}: {e}")

    # --- Fallback: minimal data from registered sites ---
    from app.core.site_resolver import get_registered_sites

    sites = get_registered_sites()
    site_entry = next((s for s in sites if s.get("code") == site_code), None)
    if site_entry:
        return {
            "id": site_code,
            "code": site_code,
            "name": site_entry.get("name", f"Site {site_code}"),
            "display_name": site_entry.get("name", f"Site {site_code}"),
            "region": site_entry.get("region"),
            "type": site_entry.get("type", "commercial_office"),
            "address": site_entry.get("address"),
            "floors": [],
            "features": {},
            "contacts": {},
            "optimization": {
                "active_profile": "balanced",
                "sentinel_operating_mode": "balanced",
                "control_tier": "supervised",
            },
            "metadata": {},
            "desk_count": 0,
            "zone_count": 0,
            "is_active": False,
        }

    raise HTTPException(status_code=404, detail=f"Building '{site_id}' not found")


@router.put("/{site_id}/config")
async def update_building_config(
    site_id: str,
    config: BuildingConfigUpdate,
    auth: AuthContext = Depends(require_role(SentinelRole.ADMIN)),
) -> dict:
    """Update building configuration from Settings UI — writes to Supabase.

    Accepts building metadata, optimization profile, control tier, feature flags.
    Supabase `sites` table is the source of truth.
    """
    site_code = _building_to_site(site_id)

    try:
        from app.database.supabase_client import get_supabase_client

        client = get_supabase_client()
        existing = client.table("buildings").select("*").eq("code", site_code).single().execute()
        if not existing.data:
            raise HTTPException(status_code=404, detail=f"Building '{site_code}' not found in Supabase")
        current = existing.data
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=503, detail=f"Database unavailable: {e}") from e

    changes: dict = {}
    updates: dict = {}

    # Direct column fields
    if config.name is not None:
        changes["name"] = {"old": current.get("name"), "new": config.name}
        updates["name"] = config.name
    if config.display_name is not None:
        changes["display_name"] = {"old": current.get("display_name"), "new": config.display_name}
        updates["display_name"] = config.display_name
    if config.address is not None:
        changes["address"] = {"old": current.get("address"), "new": config.address}
        updates["address"] = config.address
    if config.building_type is not None:
        changes["type"] = {"old": current.get("type"), "new": config.building_type}
        updates["type"] = config.building_type
    if config.floors is not None:
        changes["floor_labels"] = {"old": current.get("floor_labels"), "new": config.floors}
        updates["floor_labels"] = config.floors
    if config.sqm is not None:
        changes["sqm"] = {"old": current.get("sqm"), "new": config.sqm}
        updates["sqm"] = config.sqm
    if config.occupancy_capacity is not None:
        changes["occupancy_capacity"] = {"old": current.get("occupancy_capacity"), "new": config.occupancy_capacity}
        updates["occupancy_capacity"] = config.occupancy_capacity
    if config.total_desks is not None:
        changes["total_desks"] = {"old": current.get("total_desks"), "new": config.total_desks}
        updates["total_desks"] = config.total_desks
    if config.parking_bays is not None:
        changes["parking_bays"] = {"old": current.get("parking_bays"), "new": config.parking_bays}
        updates["parking_bays"] = config.parking_bays
    if config.features is not None:
        changes["features"] = {"old": current.get("features"), "new": config.features}
        updates["features"] = config.features

    # Contacts
    if config.contacts is not None:
        if config.contacts.get("facility_manager") is not None:
            updates["contact_facility_manager"] = config.contacts["facility_manager"]
            changes["contact_facility_manager"] = {
                "old": current.get("contact_facility_manager"),
                "new": config.contacts["facility_manager"],
            }
        if config.contacts.get("email") is not None:
            updates["contact_email"] = config.contacts["email"]
            changes["contact_email"] = {"old": current.get("contact_email"), "new": config.contacts["email"]}
        if config.contacts.get("emergency") is not None:
            updates["contact_emergency"] = config.contacts["emergency"]
            changes["contact_emergency"] = {
                "old": current.get("contact_emergency"),
                "new": config.contacts["emergency"],
            }

    # Optimization settings stored in optimization_settings JSONB
    current_opt = current.get("optimization_settings") or {}
    new_opt = dict(current_opt)
    if config.optimization_profile is not None:
        changes["optimization.active_profile"] = {
            "old": current_opt.get("active_profile"),
            "new": config.optimization_profile,
        }
        new_opt["active_profile"] = config.optimization_profile
    if config.sentinel_operating_mode is not None:
        changes["optimization.sentinel_operating_mode"] = {
            "old": current_opt.get("sentinel_operating_mode"),
            "new": config.sentinel_operating_mode,
        }
        new_opt["sentinel_operating_mode"] = config.sentinel_operating_mode
    if config.control_tier is not None:
        changes["optimization.control_tier"] = {"old": current_opt.get("control_tier"), "new": config.control_tier}
        new_opt["control_tier"] = config.control_tier
    if new_opt != current_opt:
        updates["optimization_settings"] = new_opt

    if not changes:
        return {"status": "no_changes", "site_id": site_code}

    try:
        client.table("sites").update(updates).eq("code", site_code).execute()
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to update building config: {e}") from e

    # Emit audit event
    try:
        from app.services.audit_service import emit_audit_event

        await emit_audit_event(
            event_type="CONFIG_CHANGE",
            entity_type="building",
            entity_id=site_code,
            actor=auth.email if auth else "system",
            details={"changes": changes},
        )
    except Exception as e:
        logger.warning(f"Failed to emit audit event: {e}")

    logger.info(f"Building config updated for {site_code} in Supabase: {list(changes.keys())}")

    return {
        "status": "updated",
        "site_id": site_code,
        "changes": list(changes.keys()),
    }


@router.post("")
async def create_building(building: BuildingCreate) -> dict:
    """
    Create a new building.

    Creates the building folder structure and config files.
    Building is NOT activated by default - call /activate after setup.
    """
    # Auto-generate a site code from the name if not provided
    site_id = building.id or _next_site_id()
    site_path = DATA_PATH / site_id

    # If the ID is taken, keep trying the next one
    while site_path.exists():
        site_id = _next_site_id()
        site_path = DATA_PATH / site_id

    # Create folder structure
    site_path.mkdir(parents=True, exist_ok=True)

    # Create building.json
    site_data = {
        "id": site_id,
        "name": building.name,
        "display_name": building.display_name or building.name,
        "address": building.address,
        "timezone": building.timezone,
        "floors": building.floors,
        "features": building.features
        or {
            "hvac": True,
            "dali": False,
            "desk_diagnosis": True,
        },
        "metadata": {
            "created_at": "auto",
        },
    }

    with open(site_path / "building.json", "w") as f:
        json.dump(site_data, f, indent=2)

    # Create empty desks.json
    with open(site_path / "desks.json", "w") as f:
        json.dump([], f, indent=2)

    # Create empty zones.json
    with open(site_path / "zones.json", "w") as f:
        json.dump([], f, indent=2)

    logger.info(f"Created building: {site_id}")

    return {
        "id": site_id,
        "name": building.name,
        "status": "created",
        "message": "Building created. Upload desks/zones, then call /activate.",
        "next_steps": [
            f"POST /api/buildings/{site_id}/desks - Upload desk data",
            f"POST /api/buildings/{site_id}/zones - Upload zone data",
            f"POST /api/buildings/{site_id}/activate - Activate building",
        ],
    }


@router.post("/{site_id}/desks")
async def upload_desks(
    site_id: str, desks: list[dict], auth: AuthContext = Depends(require_site_access("site_id"))
) -> dict:
    """
    Upload/replace desk data for a building.

    Expects array of desk objects. Building field is added automatically.
    Maps friendly names to site codes for file operations.
    """
    site_code = _building_to_site(site_id)
    site_path = DATA_PATH / site_code

    if not site_path.exists():
        raise HTTPException(status_code=404, detail=f"Building '{site_id}' (site '{site_code}') not found")

    # Validate and save
    for desk in desks:
        if "desk_id" not in desk:
            raise HTTPException(status_code=400, detail="Each desk must have a desk_id")

    with open(site_path / "desks.json", "w") as f:
        json.dump(desks, f, indent=2)

    # Reload
    loader = get_site_loader()
    loader.load(force=True)

    return {
        "site_id": site_id,
        "desks_uploaded": len(desks),
        "status": "success",
    }


@router.post("/{site_id}/zones")
async def upload_zones(
    site_id: str, zones: list[dict], auth: AuthContext = Depends(require_site_access("site_id"))
) -> dict:
    """
    Upload/replace zone data for a building.

    Expects array of zone objects.
    Maps friendly names to site codes for file operations.
    """
    site_code = _building_to_site(site_id)
    site_path = DATA_PATH / site_code

    if not site_path.exists():
        raise HTTPException(status_code=404, detail=f"Building '{site_id}' (site '{site_code}') not found")

    # Validate and save
    for zone in zones:
        if "zone_id" not in zone:
            raise HTTPException(status_code=400, detail="Each zone must have a zone_id")

    with open(site_path / "zones.json", "w") as f:
        json.dump(zones, f, indent=2)

    # Reload
    loader = get_site_loader()
    loader.load(force=True)

    return {
        "site_id": site_id,
        "zones_uploaded": len(zones),
        "status": "success",
    }


@router.post("/{site_id}/activate")
async def activate_building(
    site_id: str, set_default: bool = False, auth: AuthContext = Depends(require_site_access("site_id"))
) -> dict:
    """
    Activate a building (add to registry).

    Args:
        set_default: If True, also set as the default building
    Maps friendly names to site codes for file operations.
    """
    site_code = _building_to_site(site_id)
    site_path = DATA_PATH / site_code

    if not site_path.exists():
        raise HTTPException(status_code=404, detail=f"Building '{site_id}' (site '{site_code}') not found")

    # Load and update registry
    registry_path = DATA_PATH / "_registry.json"
    if registry_path.exists():
        with open(registry_path) as f:
            registry = json.load(f)
    else:
        registry = {"active_sites": [], "default_building": None}

    # Add to active if not already (use site_code for registry)
    if site_code not in registry["active_sites"]:
        registry["active_sites"].append(site_code)

    # Set as default if requested or if first building (use site_code for registry)
    if set_default or not registry.get("default_building"):
        registry["default_building"] = site_code

    # Save registry
    with open(registry_path, "w") as f:
        json.dump(registry, f, indent=2)

    # Reload
    loader = get_site_loader()
    loader.load(force=True)

    logger.info(f"Activated building: {site_id} -> {site_code}")

    return {
        "site_id": site_id,
        "site_code": site_code,
        "status": "active",
        "is_default": registry["default_building"] == site_code,
        "message": f"Building '{site_id}' (site '{site_code}') is now active",
    }


@router.post("/{site_id}/deactivate")
async def deactivate_building(site_id: str, auth: AuthContext = Depends(require_site_access("site_id"))) -> dict:
    """
    Deactivate a building (remove from registry but keep data).
    Maps friendly names to site codes for registry operations.
    """
    site_code = _building_to_site(site_id)

    registry_path = DATA_PATH / "_registry.json"

    if not registry_path.exists():
        raise HTTPException(status_code=404, detail="No registry found")

    with open(registry_path) as f:
        registry = json.load(f)

    if site_code not in registry.get("active_sites", []):
        raise HTTPException(status_code=400, detail=f"Building '{site_id}' (site '{site_code}') is not active")

    # Remove from active
    registry["active_sites"].remove(site_code)

    # Clear default if this was the default
    if registry.get("default_building") == site_code:
        registry["default_building"] = registry["active_sites"][0] if registry["active_sites"] else None

    # Save registry
    with open(registry_path, "w") as f:
        json.dump(registry, f, indent=2)

    # Reload
    loader = get_site_loader()
    loader.load(force=True)

    logger.info(f"Deactivated building: {site_id}")

    return {
        "site_id": site_id,
        "status": "inactive",
        "message": f"Building '{site_id}' deactivated. Data preserved.",
    }


@router.delete("/{site_id}")
async def delete_building(
    site_id: str, confirm: bool = False, auth: AuthContext = Depends(require_site_access("site_id"))
) -> dict:
    """
    Delete a building and all its data.

    Requires confirm=true to actually delete.
    Maps friendly names to site codes for file operations.
    """
    site_code = _building_to_site(site_id)

    if not confirm:
        raise HTTPException(status_code=400, detail="Add ?confirm=true to confirm deletion")

    site_path = DATA_PATH / site_code

    if not site_path.exists():
        raise HTTPException(status_code=404, detail=f"Building '{site_id}' (site '{site_code}') not found")

    # First deactivate
    registry_path = DATA_PATH / "_registry.json"
    if registry_path.exists():
        with open(registry_path) as f:
            registry = json.load(f)
        if site_code in registry.get("active_sites", []):
            registry["active_sites"].remove(site_code)
        if registry.get("default_building") == site_code:
            registry["default_building"] = registry["active_sites"][0] if registry["active_sites"] else None
        with open(registry_path, "w") as f:
            json.dump(registry, f, indent=2)

    # Delete folder
    shutil.rmtree(site_path)

    # Reload
    loader = get_site_loader()
    loader.load(force=True)

    logger.info(f"Deleted building: {site_id} -> {site_code}")

    return {
        "site_id": site_id,
        "site_code": site_code,
        "status": "deleted",
        "message": f"Building '{site_id}' (site '{site_code}') and all data deleted",
    }


@router.get("/{site_id}/desks")
async def get_building_desks(site_id: str, auth: AuthContext = Depends(require_site_access("site_id"))) -> list[dict]:
    """Get all desks for a building. Maps friendly names to site codes."""
    site_code = _building_to_site(site_id)

    loader = get_site_loader()
    desks = loader.get_desks(site_code)
    if not desks and site_code not in loader.get_active_site_ids():
        raise HTTPException(status_code=404, detail=f"Building '{site_id}' (site '{site_code}') not found")
    return desks


@router.get("/{site_id}/zones")
async def get_site_zones(site_id: str, auth: AuthContext = Depends(require_site_access("site_id"))) -> list[dict]:
    """Get all zones for a building. Maps friendly names to site codes."""
    site_code = _building_to_site(site_id)

    loader = get_site_loader()
    zones = loader.get_zones(site_code)
    if not zones and site_code not in loader.get_active_site_ids():
        raise HTTPException(status_code=404, detail=f"Building '{site_id}' (site '{site_code}') not found")
    return zones


@router.get("/{site_id}/equipment-summary")
async def get_equipment_summary(site_id: str, auth: AuthContext = Depends(require_site_access("site_id"))) -> dict:
    """
    Get equipment count breakdown by category for a building.

    Returns categorized counts:
    - hvac_zones: HVAC thermal zones
    - generators, generator_groups, diesel_tanks: Generator plant
    - energy_centre components (transformers, meters, UPS, etc.)
    - dali_controllers: Lighting controllers
    - legacy_equipment: From equipment.json

    Note: Desks and luminaires are NOT counted as equipment.
    """
    # Try Supabase first
    try:
        from app.database.repositories.site_repository import SiteRepository

        repo = SiteRepository()
        summary = repo.get_asset_summary_by_code(site_id)

        if summary:
            return {
                "site_id": site_id,
                "site_name": summary.get("site_name"),
                "total_assets": summary.get("total_assets", 0),
                "categories": {
                    "equipment": summary.get("equipment_count", 0),
                    "hvac_zones": summary.get("hvac_zone_count", 0),
                    "generators": summary.get("generator_count", 0),
                    "generator_groups": summary.get("generator_group_count", 0),
                    "diesel_tanks": summary.get("diesel_tank_count", 0),
                    "energy_centres": summary.get("energy_centre_count", 0),
                    "mv_incomers": summary.get("mv_incomer_count", 0),
                    "transformers": summary.get("transformer_count", 0),
                    "lv_switchboards": summary.get("lv_switchboard_count", 0),
                    "ats_units": summary.get("ats_count", 0),
                    "power_meters": summary.get("power_meter_count", 0),
                    "pfc_banks": summary.get("pfc_bank_count", 0),
                    "ups_systems": summary.get("ups_count", 0),
                    "feeders": summary.get("feeder_count", 0),
                    "dali_controllers": summary.get("dali_controller_count", 0),
                },
                "supplementary": {
                    "desks": summary.get("desk_count", 0),
                    "luminaires": summary.get("luminaire_count", 0),
                    "dali_sensors": summary.get("dali_sensor_count", 0),
                },
                "source": "supabase",
            }
    except Exception as e:
        logger.debug(f"Supabase asset summary failed: {e}")

    # Fall back to JSON file counting
    # Map site_id to site code for JSON lookup
    site_code = _building_to_site(site_id)

    loader = get_site_loader()
    building = loader.get_site(site_code)

    if not building:
        raise HTTPException(status_code=404, detail=f"Building '{site_id}' (site '{site_code}') not found")

    site_path = DATA_PATH / site_code

    # Count from JSON files
    counts = {
        "equipment": 0,
        "hvac_zones": 0,
        "generators": 0,
        "generator_groups": 0,
        "diesel_tanks": 0,
        "energy_centres": 0,
        "mv_incomers": 0,
        "transformers": 0,
        "lv_switchboards": 0,
        "ats_units": 0,
        "power_meters": 0,
        "pfc_banks": 0,
        "ups_systems": 0,
        "feeders": 0,
        "dali_controllers": 0,
    }

    # HVAC zones
    zones_file = site_path / "zones.json"
    if zones_file.exists():
        with open(zones_file) as f:
            zones = json.load(f)
            counts["hvac_zones"] = len(zones)

    # Generators
    gen_file = site_path / "generators.json"
    if gen_file.exists():
        with open(gen_file) as f:
            gen_data = json.load(f)
            counts["generators"] = len(gen_data.get("generators", []))
            counts["generator_groups"] = len(gen_data.get("groups", []))
            counts["diesel_tanks"] = len(gen_data.get("diesel_tanks", []))

    # Energy centre
    ec_file = site_path / "energy_centre.json"
    if ec_file.exists():
        with open(ec_file) as f:
            ec_data = json.load(f)
            counts["energy_centres"] = 1 if ec_data.get("energy_centre") else 0
            counts["mv_incomers"] = len(ec_data.get("mv_incomers", []))
            counts["transformers"] = len(ec_data.get("transformers", []))
            counts["lv_switchboards"] = len(ec_data.get("lv_switchboards", []))
            counts["ats_units"] = len(ec_data.get("ats_units", []))
            counts["power_meters"] = len(ec_data.get("power_meters", []))
            counts["pfc_banks"] = len(ec_data.get("pfc_banks", []))
            counts["ups_systems"] = len(ec_data.get("ups_systems", []))
            counts["feeders"] = len(ec_data.get("feeders", []))

    # DALI controllers (from main data dir)
    dali_file = Path(__file__).parent.parent / "data" / "dali_mock_data.json"
    if dali_file.exists():
        with open(dali_file) as f:
            dali_data = json.load(f)
            # Count controllers for this site
            controllers = dali_data.get("controllers", [])
            counts["dali_controllers"] = len([c for c in controllers if c.get("site_id") == site_id])

    # Calculate total
    total = sum(counts.values())

    # Supplementary counts (not in total)
    desks_file = site_path / "desks.json"
    desk_count = 0
    if desks_file.exists():
        with open(desks_file) as f:
            desks = json.load(f)
            desk_count = len(desks)

    return {
        "site_id": site_id,
        "site_name": building.name,
        "total_assets": total,
        "categories": counts,
        "supplementary": {
            "desks": desk_count,
            "luminaires": 0,  # Not counted from JSON
            "dali_sensors": 0,  # Not counted from JSON
        },
        "source": "json",
    }


@router.get("/{site_id}/equipment")
async def get_site_equipment(site_id: str, auth: AuthContext = Depends(require_site_access("site_id"))) -> dict:
    """
    Get all equipment for a building with status.

    Returns all equipment items from:
    - Supabase equipment table (primary source)
    - JSON fallback: HVAC zones, generators, energy centre, DALI controllers

    Each item includes: id, name, type, category, status, health, details
    """
    # Handle both UUID and building code formats
    site_code = site_id
    site_uuid = None

    # Try mapping first (for legacy string IDs like "sandton")
    mapped = _building_to_site(site_id)
    if mapped != site_id:
        site_code = mapped
    else:
        # If site_id looks like a UUID, look it up in buildings table
        import uuid

        try:
            uuid.UUID(site_id)  # Validate UUID format
            # It's a UUID, so look it up to get the code
            from app.database.supabase_client import get_supabase_client

            client = get_supabase_client()
            site_result = client.table("sites").select("id, code").eq("id", site_id).execute()
            if site_result.data:
                site_code = site_result.data[0]["code"]
                site_uuid = site_result.data[0]["id"]
        except (ValueError, Exception):
            # Not a UUID, use as-is
            pass

    # Try Supabase first
    try:
        from app.database.repositories.equipment_repository import EquipmentRepository

        repo = EquipmentRepository()
        equipment_data = repo.get_by_site_code(site_code)

        if equipment_data:
            # Get building info from Supabase (needed in the loop)
            from app.database.supabase_client import get_supabase_client

            client = get_supabase_client()

            # Only query if we don't already have site_uuid
            if not site_uuid:
                site_result = client.table("sites").select("id, name").eq("code", site_code).execute()
                site_name = site_result.data[0]["name"] if site_result.data else site_id
                site_uuid = site_result.data[0]["id"] if site_result.data else None
            else:
                site_result = client.table("sites").select("id, name").eq("id", site_uuid).execute()
                site_name = site_result.data[0]["name"] if site_result.data else site_id

            # Cross-reference active alerts to derive equipment risk status
            alert_severity_map: dict[str, str] = {}  # equipment_uuid -> highest severity
            if site_uuid:
                try:
                    from app.database.repositories.alert_repository import AlertRepository

                    alert_repo = AlertRepository()
                    active_alerts = alert_repo.get_active_by_site(site_uuid)
                    for alert in active_alerts:
                        eq_uuid = alert.get("equipment_id")
                        if eq_uuid:
                            severity = alert.get("severity", "warning")
                            existing = alert_severity_map.get(eq_uuid)
                            if existing != "critical":
                                if severity == "critical" or existing is None:
                                    alert_severity_map[eq_uuid] = severity
                except Exception as e:
                    logger.warning(f"Failed to fetch alerts for equipment status: {e}")

            # Ensure device_manager is populated so _is_device_controllable can check it
            try:
                from app.services.ai_optimizer import ensure_device_manager_initialized

                await ensure_device_manager_initialized()
            except Exception as e:
                logger.debug(f"Device manager init skipped: {e}")

            equipment_list = []
            categories = {}

            for eq in equipment_data:
                # Determine category from type - normalize if type is unknown
                eq_code = eq.get("code", "")
                eq_type_raw = eq.get("type", "unknown")
                eq_type = _normalize_equipment_type(eq_code, eq_type_raw)
                type_to_category = {
                    "sensor": "Sensors",
                    "daylight_sensor": "Sensors",
                    "occupancy_sensor": "Sensors",
                    "zone_sensor": "Sensors",
                    "outdoor_air_sensor": "Sensors",
                    "vav": "HVAC",
                    "VAV": "HVAC",
                    "ahu": "HVAC",
                    "fcu": "HVAC",
                    "FCU": "HVAC",
                    "chiller": "HVAC",
                    "split_unit": "HVAC",
                    "cooling_tower": "HVAC",
                    "hvac_zone": "HVAC",
                    "pump": "HVAC",
                    "zone": "HVAC",
                    "generator": "Generator Plant",
                    "diesel_tank": "Generator Plant",
                    "generator_group": "Generator Plant",
                    "transformer": "Energy Centre",
                    "mv_incomer": "Energy Centre",
                    "lv_switchboard": "Energy Centre",
                    "ats": "Energy Centre",
                    "ups": "Energy Centre",
                    "power_meter": "Energy Centre",
                    "pfc_bank": "Energy Centre",
                    "feeder": "Energy Centre",
                    "bess": "Energy Centre",
                    "inverter": "Energy Centre",
                    "meter": "Energy Centre",
                    "dali_controller": "Lighting",
                    "dali": "Lighting",
                    "dali_zone": "Lighting",
                    "luminaire": "Lighting",
                    "lighting_zone": "Lighting",
                    "bms_controller": "Building Systems",
                    "bms_scada": "Building Systems",
                    "lift-passenger": "Lifts",
                }
                category = type_to_category.get(eq_type, "Other")
                status = eq.get("status", "normal")
                health = eq.get("health_score", 85)

                # Override status if equipment has active alerts
                eq_uuid = eq.get("id")
                if eq_uuid and eq_uuid in alert_severity_map:
                    alert_sev = alert_severity_map[eq_uuid]
                    if alert_sev == "critical" and status != "critical":
                        status = "critical"
                        health = min(health, 30)
                    elif alert_sev == "warning" and status not in ("critical", "warning"):
                        status = "warning"
                        health = min(health, 60)

                # Derive status from health score to align with SafetySummary thresholds
                # (sites_aggregation.py: <57 = alarm, 57-80 = warning, >=80 = safe)
                if status == "normal" and isinstance(health, (int, float)):
                    if health < 57:
                        status = "critical"
                    elif health < 80:
                        status = "warning"

                operating_data = eq.get("operating_data", {}) or {}
                capability_sync = operating_data.get("capability_sync", {}) if isinstance(operating_data, dict) else {}
                synced_controllable = capability_sync.get("controllable")
                inferred_controllable = _is_device_controllable(eq.get("code", eq.get("id", "")), eq.get("points", {}))
                is_simulated_sync = (
                    capability_sync.get("vendor") == "simulation"
                    and capability_sync.get("writable_point_count", 0) == 0
                )
                controllable_by_type = eq_type in (
                    "fcu",
                    "vav",
                    "ahu",
                    "chiller",
                    "pump",
                    "split",
                    "ct",
                    "dali",
                    "lum",
                    "gen",
                    "ups",
                    "bess",
                    "inv",
                )
                # Determine effective controllable status:
                # - Simulation sync (no real BMS): use type-based override when device_manager has no writable points
                # - Shadow mode (capability_sync empty): also use type-based override for known controllable types
                # - Real BMS sync: trust synced_controllable if available, else fall back to device_manager
                if is_simulated_sync or (not synced_controllable and controllable_by_type):
                    if not inferred_controllable and controllable_by_type:
                        # No real writable points found — fall back to type-based assumption.
                        # Real BMS sync should override this when connectivity is available.
                        inferred_controllable = True
                    effective_controllable = inferred_controllable
                else:
                    effective_controllable = (
                        bool(synced_controllable) if isinstance(synced_controllable, bool) else inferred_controllable
                    )

                # Extract location from equipment code
                eq_code = eq.get("code", "")
                extracted_location = _extract_location_from_code(eq_code)
                # Use extracted location if DB location is empty
                location = eq.get("location", "") or extracted_location

                equipment_list.append(
                    {
                        "id": eq.get("code", eq.get("id")),
                        "code": eq.get("code"),
                        "name": _normalize_equipment_name(eq),
                        "equipment_type": eq_type,  # Frontend expects equipment_type, not type
                        "type": eq_type,  # Keep for backward compatibility
                        "category": category,
                        "status": status,
                        "health_score": health,
                        "location": location,
                        "site_id": site_code,
                        "site_name": site_name,
                        "details": {
                            "manufacturer": eq.get("manufacturer"),
                            "model": eq.get("model"),
                            "metadata": eq.get("metadata", {}),
                        },
                        "controllable": effective_controllable,
                        "control_state": (
                            "synced_capability"
                            if isinstance(synced_controllable, bool)
                            else ("inferred_writable" if inferred_controllable else "read_only")
                        ),
                    }
                )

                # Update category stats
                if category not in categories:
                    categories[category] = {"total": 0, "normal": 0, "warning": 0, "critical": 0}
                categories[category]["total"] += 1
                if status == "normal":
                    categories[category]["normal"] += 1
                elif status == "warning":
                    categories[category]["warning"] += 1
                elif status == "critical":
                    categories[category]["critical"] += 1

            # Merge controllable status from building equipment directory (Niagara discovery)
            # The directory files have points with writable=true that Supabase doesn't have
            site_path = DATA_PATH / site_code
            equipment_dir = site_path / "equipment"
            if equipment_dir.exists():
                # Build lookup from directory files for controllable status
                dir_controllable = {}
                for eq_file in equipment_dir.glob("*.json"):
                    try:
                        with open(eq_file) as f:
                            eq = json.load(f)
                        eq_id = eq.get("id", eq.get("code", ""))
                        points = eq.get("points", {})
                        if any(p.get("writable", False) for p in points.values()):
                            dir_controllable[eq_id] = True
                    except Exception as e:
                        logger.warning(f"Failed to load equipment from {eq_file}: {e}")

                # Update controllable status for existing equipment
                for eq_item in equipment_list:
                    if eq_item["id"] in dir_controllable:
                        eq_item["controllable"] = True

            return {
                "site_id": site_id,
                "site_name": site_name,
                "total_equipment": len(equipment_list),
                "categories": categories,
                "equipment": equipment_list,
                "source": "supabase",
            }
    except Exception as e:
        logger.warning(f"Supabase equipment fetch failed for {site_id}: {e}")

    # Fall back to JSON files
    loader = get_site_loader()
    building = loader.get_site(site_code)

    if not building:
        # No data yet for this site — return empty equipment list instead of 404
        return {
            "site_id": site_id,
            "site_name": site_code,
            "total_equipment": 0,
            "categories": {},
            "equipment": [],
            "source": "none",
        }

    site_path = DATA_PATH / site_code
    equipment_list = []

    def get_status_health(status: str) -> tuple:
        """Convert status to normalized status and health score."""
        status_map = {
            "running": ("normal", 95),
            "online": ("normal", 95),
            "healthy": ("normal", 95),
            "idle": ("normal", 85),
            "standby": ("normal", 80),
            "closed": ("normal", 90),
            "fault": ("critical", 30),
            "alarm": ("critical", 25),
            "offline": ("critical", 20),
            "warning": ("warning", 60),
            "maintenance": ("warning", 50),
        }
        return status_map.get(status.lower() if status else "unknown", ("unknown", 50))

    # 1. HVAC Zones
    zones_file = site_path / "zones.json"
    if zones_file.exists():
        with open(zones_file) as f:
            zones = json.load(f)
            for zone in zones:
                status, health = get_status_health(zone.get("status", "idle"))
                equipment_list.append(
                    {
                        "id": zone.get("zone_id"),
                        "name": zone.get("zone_name"),
                        "type": "hvac_zone",
                        "category": "HVAC",
                        "status": status,
                        "health_score": health,
                        "location": f"Floor {zone.get('floor', 'N/A')}",
                        "site_id": site_code,
                        "site_name": building.name,
                        "details": {
                            "current_temp": zone.get("current_temp"),
                            "setpoint": zone.get("setpoint"),
                            "fcu_id": zone.get("fcu_id"),
                            "ahu_id": zone.get("ahu_id"),
                        },
                        "controllable": True,
                    }
                )

    # 2. Generators
    gen_file = site_path / "generators.json"
    if gen_file.exists():
        with open(gen_file) as f:
            gen_data = json.load(f)

            # Diesel tanks
            for tank in gen_data.get("diesel_tanks", []):
                level_pct = tank.get("current_level_pct", 0)
                status = "normal" if level_pct > 25 else ("warning" if level_pct > 10 else "critical")
                health = min(100, level_pct + 20)
                equipment_list.append(
                    {
                        "id": tank.get("tank_id"),
                        "name": tank.get("name"),
                        "type": "diesel_tank",
                        "category": "Generator Plant",
                        "status": status,
                        "health_score": health,
                        "location": tank.get("location", ""),
                        "site_id": site_code,
                        "site_name": building.name,
                        "details": {
                            "capacity_liters": tank.get("capacity_liters"),
                            "current_level_pct": level_pct,
                        },
                        "controllable": False,
                    }
                )

            # Generator groups
            for group in gen_data.get("groups", []):
                status, health = get_status_health("online" if group.get("generators_running", 0) > 0 else "standby")
                equipment_list.append(
                    {
                        "id": group.get("group_id"),
                        "name": group.get("name"),
                        "type": "generator_group",
                        "category": "Generator Plant",
                        "status": status,
                        "health_score": health,
                        "location": group.get("location", ""),
                        "site_id": site_code,
                        "site_name": building.name,
                        "details": {
                            "generators_running": group.get("generators_running"),
                            "total_load_kw": group.get("total_load_kw"),
                            "ats_position": group.get("ats_position"),
                        },
                        "controllable": False,
                    }
                )

            # Generators
            for gen in gen_data.get("generators", []):
                status, health = get_status_health(gen.get("status", "standby"))
                equipment_list.append(
                    {
                        "id": gen.get("generator_id"),
                        "name": gen.get("name"),
                        "type": "generator",
                        "category": "Generator Plant",
                        "status": status,
                        "health_score": health,
                        "location": gen.get("location", ""),
                        "site_id": site_code,
                        "site_name": building.name,
                        "details": {
                            "rated_power_kw": gen.get("rated_power_kw"),
                            "engine_running": gen.get("engine_running"),
                            "on_load": gen.get("on_load"),
                            "output_power_kw": gen.get("output_power_kw"),
                        },
                        "controllable": True,
                    }
                )

    # 3. Energy Centre
    ec_file = site_path / "energy_centre.json"
    if ec_file.exists():
        with open(ec_file) as f:
            ec_data = json.load(f)

            # MV Incomers
            for incomer in ec_data.get("mv_incomers", []):
                status, health = get_status_health("online" if incomer.get("healthy") else "fault")
                equipment_list.append(
                    {
                        "id": incomer.get("incomer_id"),
                        "name": incomer.get("name"),
                        "type": "mv_incomer",
                        "category": "Energy Centre",
                        "status": status,
                        "health_score": health,
                        "location": incomer.get("location", ""),
                        "site_id": site_code,
                        "site_name": building.name,
                        "details": {
                            "voltage_kv": incomer.get("voltage_kv"),
                            "power_kw": incomer.get("power_kw"),
                            "breaker_state": incomer.get("breaker_state"),
                        },
                        "controllable": False,
                    }
                )

            # Transformers
            for tx in ec_data.get("transformers", []):
                status, health = get_status_health("online" if tx.get("healthy") else "fault")
                equipment_list.append(
                    {
                        "id": tx.get("transformer_id"),
                        "name": tx.get("name"),
                        "type": "transformer",
                        "category": "Energy Centre",
                        "status": status,
                        "health_score": health,
                        "location": tx.get("location", ""),
                        "site_id": site_code,
                        "site_name": building.name,
                        "details": {
                            "rated_power_kva": tx.get("rated_power_kva"),
                            "load_percent": tx.get("load_percent"),
                            "oil_temp_c": tx.get("oil_temp_c"),
                        },
                        "controllable": False,
                    }
                )

            # LV Switchboards
            for sb in ec_data.get("lv_switchboards", []):
                status, health = get_status_health("online" if sb.get("healthy") else "fault")
                equipment_list.append(
                    {
                        "id": sb.get("switchboard_id"),
                        "name": sb.get("name"),
                        "type": "lv_switchboard",
                        "category": "Energy Centre",
                        "status": status,
                        "health_score": health,
                        "location": sb.get("location", ""),
                        "site_id": site_code,
                        "site_name": building.name,
                        "details": {
                            "total_load_kw": sb.get("total_load_kw"),
                            "bus_voltage_v": sb.get("bus_voltage_v"),
                        },
                        "controllable": False,
                    }
                )

            # ATS Units
            for ats in ec_data.get("ats_units", []):
                # ATS health: check if both interlocks are OK and at least one power source is available
                is_healthy = (
                    ats.get("mechanical_interlock_ok", False)
                    and ats.get("electrical_interlock_ok", False)
                    and (ats.get("mains_available", False) or ats.get("generator_available", False))
                )
                status, health = get_status_health("online" if is_healthy else "fault")
                equipment_list.append(
                    {
                        "id": ats.get("ats_id"),
                        "name": ats.get("name"),
                        "type": "ats",
                        "category": "Energy Centre",
                        "status": status,
                        "health_score": health,
                        "location": ats.get("location", ""),
                        "site_id": site_code,
                        "site_name": building.name,
                        "details": {
                            "position": ats.get("position"),
                            "mode": ats.get("mode"),
                        },
                        "controllable": True,
                    }
                )

            # Power Meters
            for meter in ec_data.get("power_meters", []):
                equipment_list.append(
                    {
                        "id": meter.get("meter_id"),
                        "name": meter.get("name"),
                        "type": "power_meter",
                        "category": "Energy Centre",
                        "status": "normal",
                        "health": 95,
                        "location": meter.get("location", ""),
                        "site_id": site_code,
                        "site_name": building.name,
                        "details": {
                            "power_kw": meter.get("power_kw"),
                            "energy_kwh": meter.get("energy_kwh_total"),
                        },
                        "controllable": False,
                    }
                )

            # PFC Banks
            for pfc in ec_data.get("pfc_banks", []):
                status, health = get_status_health("online" if pfc.get("healthy") else "fault")
                equipment_list.append(
                    {
                        "id": pfc.get("pfc_id"),
                        "name": pfc.get("name"),
                        "type": "pfc_bank",
                        "category": "Energy Centre",
                        "status": status,
                        "health_score": health,
                        "location": pfc.get("location", ""),
                        "site_id": site_code,
                        "site_name": building.name,
                        "details": {
                            "power_factor": pfc.get("power_factor"),
                            "stages_active": pfc.get("stages_active"),
                        },
                        "controllable": True,
                    }
                )

            # UPS Systems
            for ups in ec_data.get("ups_systems", []):
                status, health = get_status_health(ups.get("status", "online"))
                equipment_list.append(
                    {
                        "id": ups.get("ups_id"),
                        "name": ups.get("name"),
                        "type": "ups",
                        "category": "Energy Centre",
                        "status": status,
                        "health_score": health,
                        "location": ups.get("location", ""),
                        "site_id": site_code,
                        "site_name": building.name,
                        "details": {
                            "rated_power_kva": ups.get("rated_power_kva"),
                            "load_percent": ups.get("load_percent"),
                            "battery_pct": ups.get("battery_pct"),
                            "runtime_minutes": ups.get("runtime_minutes"),
                        },
                        "controllable": False,
                    }
                )

            # Feeders
            for feeder in ec_data.get("feeders", []):
                status, health = get_status_health("online" if feeder.get("breaker_state") == "closed" else "offline")
                equipment_list.append(
                    {
                        "id": feeder.get("feeder_id"),
                        "name": feeder.get("name"),
                        "type": "feeder",
                        "category": "Energy Centre",
                        "status": status,
                        "health_score": health,
                        "location": feeder.get("location", ""),
                        "site_id": site_code,
                        "site_name": building.name,
                        "details": {
                            "rated_current_a": feeder.get("rated_current_a"),
                            "current_a": feeder.get("current_a"),
                            "destination": feeder.get("destination"),
                        },
                        "controllable": True,
                    }
                )

    # 4. DALI Controllers
    # Map site_id to site_id for DALI data
    site_id = _building_to_site(site_id)

    dali_file = Path(__file__).parent.parent / "data" / "dali_mock_data.json"
    if dali_file.exists():
        with open(dali_file) as f:
            dali_data = json.load(f)
            # Check if site matches (using mapped site_id)
            if dali_data.get("site_id") == site_id:
                for controller in dali_data.get("controllers", []):
                    status, health = get_status_health(controller.get("status", "online"))
                    equipment_list.append(
                        {
                            "id": controller.get("controller_id"),
                            "name": controller.get("name"),
                            "type": "dali_controller",
                            "category": "Lighting",
                            "status": status,
                            "health_score": health,
                            "location": controller.get("location", ""),
                            "site_id": site_code,
                            "site_name": building.name,
                            "details": {
                                "ip_address": controller.get("ip_address"),
                                "channels": controller.get("channels"),
                                "firmware": controller.get("firmware_version"),
                            },
                            "controllable": True,
                        }
                    )

    # 5. Equipment from building equipment directory (Niagara discovery)
    equipment_dir = site_path / "equipment"
    if equipment_dir.exists():
        existing_ids = {eq["id"] for eq in equipment_list}  # Avoid duplicates
        for eq_file in equipment_dir.glob("*.json"):
            try:
                with open(eq_file) as f:
                    eq = json.load(f)

                eq_id = eq.get("id", eq.get("code", ""))
                eq_code = eq.get("code", eq_id)
                if eq_id in existing_ids:
                    continue  # Skip duplicates

                eq_type_raw = eq.get("equipment_type", eq.get("device_type", "unknown"))
                eq_type = _normalize_equipment_type(eq_code, eq_type_raw)
                type_to_category = {
                    "ahu": "HVAC",
                    "fcu": "HVAC",
                    "vav": "HVAC",
                    "chiller": "HVAC",
                    "cooling_tower": "HVAC",
                    "pump": "HVAC",
                    "boiler": "HVAC",
                    "hvac": "HVAC",
                    "split_unit": "HVAC",
                    "generator": "Generator Plant",
                    "ups": "Energy Centre",
                    "transformer": "Energy Centre",
                    "ats": "Energy Centre",
                    "power_meter": "Energy Centre",
                    "meter": "Energy Centre",
                    "dali_controller": "Lighting",
                    "dali_zone": "Lighting",
                    "luminaire": "Lighting",
                    "lighting": "Lighting",
                    "sensor": "Sensors",
                    "zone": "Building Systems",
                }
                category = type_to_category.get(eq_type.lower(), "Other")
                status, health = get_status_health(eq.get("status", "normal"))

                equipment_list.append(
                    {
                        "id": eq_id,
                        "code": eq_code,
                        "name": eq.get("name", eq_id),
                        "equipment_type": eq_type,  # Frontend expects equipment_type
                        "type": eq_type,  # Keep for backward compatibility
                        "category": category,
                        "status": status,
                        "health_score": health,
                        "location": eq.get("location", ""),
                        "site_id": site_code,
                        "site_name": building.name,
                        "details": {
                            "manufacturer": eq.get("manufacturer"),
                            "model": eq.get("model"),
                            "metadata": eq.get("metadata", {}),
                        },
                        "controllable": _is_device_controllable(eq_id, eq.get("points", {})),
                    }
                )
                existing_ids.add(eq_id)
            except Exception as e:
                logger.warning(f"Failed to load equipment from {eq_file}: {e}")

    # 6. Legacy Equipment from equipment.json
    equipment_file = Path(__file__).parent.parent / "data" / "equipment.json"
    if equipment_file.exists():
        with open(equipment_file) as f:
            legacy_equipment = json.load(f)
            for eq in legacy_equipment:
                # Match by site_id
                if eq.get("site_id") == site_id:
                    eq_code = eq.get("code", eq.get("id", ""))
                    eq_type_raw = eq.get("type", "unknown")
                    eq_type = _normalize_equipment_type(eq_code, eq_type_raw)
                    # Determine category based on type
                    type_to_category = {
                        "sensor": "Sensors",
                        "daylight_sensor": "Sensors",
                        "occupancy_sensor": "Sensors",
                        "ahu": "HVAC",
                        "split_unit": "HVAC",
                        "fcu": "HVAC",
                        "chiller": "HVAC",
                        "cooling_tower": "HVAC",
                        "vav": "HVAC",
                        "hvac_zone": "HVAC",
                        "ups": "Energy Centre",
                        "transformer": "Energy Centre",
                        "mv_incomer": "Energy Centre",
                        "lv_switchboard": "Energy Centre",
                        "ats": "Energy Centre",
                        "power_meter": "Energy Centre",
                        "pfc_bank": "Energy Centre",
                        "feeder": "Energy Centre",
                        "generator": "Generator Plant",
                        "diesel_tank": "Generator Plant",
                        "generator_group": "Generator Plant",
                        "dali_controller": "Lighting",
                        "luminaire": "Lighting",
                        "luminaire_group": "Lighting",
                        "fire_panel": "Fire & Safety",
                        "bms_controller": "Building Systems",
                        "bms_scada": "Building Systems",
                        "water_heater": "Building Systems",
                        "lift-passenger": "Lifts",
                    }
                    category = type_to_category.get(eq_type, "Other")
                    status, health = get_status_health(eq.get("status", "normal"))

                    equipment_list.append(
                        {
                            "id": eq.get("id"),
                            "code": eq_code,
                            "name": eq.get("name"),
                            "equipment_type": eq_type,  # Frontend expects equipment_type
                            "type": eq_type,  # Keep for backward compatibility
                            "category": category,
                            "status": status,
                            "health_score": health,
                            "location": eq.get("location", ""),
                            "site_id": site_code,
                            "site_name": building.name,
                            "details": {
                                "manufacturer": eq.get("manufacturer"),
                                "model": eq.get("model"),
                            },
                            "controllable": _is_device_controllable(eq.get("id", ""), eq.get("points", {})),
                        }
                    )

    # Summary by category
    categories = {}
    for eq in equipment_list:
        cat = eq["category"]
        if cat not in categories:
            categories[cat] = {"total": 0, "normal": 0, "warning": 0, "critical": 0}
        categories[cat]["total"] += 1
        if eq["status"] in ["normal"]:
            categories[cat]["normal"] += 1
        elif eq["status"] in ["warning"]:
            categories[cat]["warning"] += 1
        elif eq["status"] in ["critical"]:
            categories[cat]["critical"] += 1

    return {
        "site_id": site_id,
        "site_name": building.name,
        "total_equipment": len(equipment_list),
        "categories": categories,
        "equipment": equipment_list,
        "source": "json",
    }
