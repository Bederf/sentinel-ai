"""Sites API endpoints."""

import json
import logging
import re
from datetime import datetime
from pathlib import Path
from typing import Any, Literal

import httpx
from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, Field

from app.config.settings import settings
from app.database.repositories import SiteRepository
from app.middleware.auth_middleware import require_auth, require_site_access
from app.models.auth import AuthContext, AuthLevel, SentinelRole

router = APIRouter()
logger = logging.getLogger(__name__)

# Buildings directory for site metadata and new site creation
SITES_DIR = Path(__file__).parent.parent / "data" / "sites"

# Load sites data (fallback)
DATA_DIR = Path(__file__).parent.parent / "data"


def load_sites() -> list[dict]:
    """Load sites from JSON file (fallback)."""
    sites_file = DATA_DIR / "sites.json"
    if sites_file.exists():
        with open(sites_file) as f:
            sites = json.load(f)
            if sites:
                return sites
    return []


def load_equipment() -> list[dict]:
    """Load equipment from JSON file (fallback)."""
    equipment_file = DATA_DIR / "equipment.json"
    if equipment_file.exists():
        with open(equipment_file) as f:
            return json.load(f)
    return []


def load_alerts() -> list[dict]:
    """Load alerts from JSON file (fallback)."""
    alerts_file = DATA_DIR / "alerts.json"
    if alerts_file.exists():
        with open(alerts_file) as f:
            return json.load(f)
    return []


def _load_building_json(site_id: str) -> dict | None:
    """Load building.json for a site (canonical building metadata).

    Building metadata (contacts, BMS vendor, features) is external to SENTINEL
    and lives in JSON files under buildings/{site_id}/building.json.
    """
    site_file = SITES_DIR / site_id / "building.json"
    if site_file.exists():
        try:
            with open(site_file) as f:
                return json.load(f)
        except (json.JSONDecodeError, OSError) as e:
            logger.warning(f"Failed to read building.json for {site_id}: {e}")
    return None


def _enrich_from_building_json(site_dict: dict) -> dict:
    """Enrich a site dict with building.json metadata for missing fields.

    Building.json is the canonical source for building metadata (contacts,
    BMS info, etc.). Supabase may have these fields too, but building.json
    takes precedence when Supabase values are empty.
    """
    site_id = site_dict.get("id", "")
    building = _load_building_json(site_id)
    if not building:
        return site_dict

    # Map nested contacts to flat fields
    contacts = building.get("contacts", {})
    if not site_dict.get("contact_email"):
        site_dict["contact_email"] = contacts.get("email", "")
    if not site_dict.get("contact_phone"):
        site_dict["contact_phone"] = contacts.get("emergency", "")

    # Building.json is authoritative for building metadata — override Supabase defaults
    if building.get("type"):
        site_dict["type"] = building["type"]
    if building.get("year_built"):
        site_dict["year_built"] = building["year_built"]

    # Enrich other fields from building.json if missing from Supabase
    metadata = building.get("metadata", {})
    if not site_dict.get("sqm") and metadata.get("sqm"):
        site_dict["sqm"] = metadata["sqm"]

    if not site_dict.get("timezone"):
        site_dict["timezone"] = building.get("timezone", "")

    return site_dict


def get_json_asset_counts(site_id: str) -> dict:
    """Aggregate asset counts from all JSON sources for a site.

    Counts assets from:
    - equipment.json (legacy equipment)
    - buildings/{site_code}/zones.json (HVAC zones)
    - buildings/{site_code}/generators.json (generators, groups, tanks)
    - buildings/{site_code}/energy_centre.json (EC components)
    - dali_mock_data.json (DALI controllers by building)

    Returns:
        Dict with total_assets and breakdown by category
    """
    # Map site_id to site_code (for modular building structure)
    # TODO: Store this mapping in sites.json or buildings registry
    SITE_TO_BUILDING = {
        "site-002": "sandton",  # Sandton City Office Tower -> sandton folder
    }

    site_code = SITE_TO_BUILDING.get(site_id, site_id)

    counts = {
        "equipment": 0,
        "hvac_zones": 0,
        "generators": 0,
        "generator_groups": 0,
        "diesel_tanks": 0,
        "energy_centre": 0,
        "dali_controllers": 0,
    }

    # 1. Legacy equipment from equipment.json
    equipment_file = DATA_DIR / "equipment.json"
    if equipment_file.exists():
        with open(equipment_file) as f:
            equipment = json.load(f)
            counts["equipment"] = len([e for e in equipment if e.get("site_id") == site_id])

    # 2. Building-specific data
    site_path = DATA_DIR / "sites" / site_code

    # HVAC zones
    zones_file = site_path / "zones.json"
    if zones_file.exists():
        with open(zones_file) as f:
            zones = json.load(f)
            counts["hvac_zones"] = len(zones)

    # Generators (includes generators, groups, tanks)
    generators_file = site_path / "generators.json"
    if generators_file.exists():
        with open(generators_file) as f:
            gen_data = json.load(f)
            counts["generators"] = len(gen_data.get("generators", []))
            counts["generator_groups"] = len(gen_data.get("groups", []))
            counts["diesel_tanks"] = len(gen_data.get("diesel_tanks", []))

    # Energy centre components
    ec_file = site_path / "energy_centre.json"
    if ec_file.exists():
        with open(ec_file) as f:
            ec_data = json.load(f)
            ec_count = 1 if ec_data else 0  # The energy centre itself
            ec_count += len(ec_data.get("mv_incomers", []))
            ec_count += len(ec_data.get("transformers", []))
            ec_count += len(ec_data.get("lv_switchboards", []))
            ec_count += len(ec_data.get("ats_units", []))
            ec_count += len(ec_data.get("power_meters", []))
            ec_count += len(ec_data.get("pfc_banks", []))
            ec_count += len(ec_data.get("ups_systems", []))
            ec_count += len(ec_data.get("feeders", []))
            counts["energy_centre"] = ec_count

    # 3. DALI controllers from dali_mock_data.json
    dali_file = DATA_DIR / "dali_mock_data.json"
    if dali_file.exists():
        with open(dali_file) as f:
            dali_data = json.load(f)
            # Check if site_id matches (flat structure) or site_id matches (nested)
            if dali_data.get("site_id") == site_id:
                counts["dali_controllers"] = len(dali_data.get("controllers", []))
            else:
                # Try nested buildings structure
                for building in dali_data.get("sites", []):
                    if building.get("site_id", "").lower() == site_code.lower():
                        counts["dali_controllers"] = len(building.get("controllers", []))
                        break

    # Calculate total
    total = sum(counts.values())

    return {
        "total_assets": total,
        "breakdown": counts,
    }


def get_equipment_status_breakdown(site_uuid: str) -> dict:
    """Get equipment count by status for a building.

    Args:
        site_uuid: Building UUID

    Returns:
        Dict with total, ok, warning, critical counts
    """
    try:
        from app.database.supabase_client import get_supabase_client

        client = get_supabase_client()

        # Read once and derive health-aware safety buckets.
        # This keeps site status aligned with equipment warning state, not predictor events.
        result = client.table("equipment").select("status, health_score").eq("site_id", site_uuid).execute()

        equipment = result.data or []
        counts = {"total": len(equipment), "ok": 0, "warning": 0, "critical": 0}

        for eq in equipment:
            status = (eq.get("status") or "normal").lower()
            health = eq.get("health_score", 100)
            try:
                health_value = float(health)
            except (TypeError, ValueError):
                health_value = 100.0

            # Critical is explicit critical status or severe health degradation.
            if status == "critical" or health_value < 57:
                counts["critical"] += 1
            # Warning includes explicit warning plus non-operational or degraded-but-not-critical.
            elif status in ("warning", "offline", "maintenance") or health_value < 80:
                counts["warning"] += 1
            else:
                counts["ok"] += 1

        return counts
    except Exception as e:
        logger.warning(f"Failed to get equipment status breakdown: {e}")
        return {"total": 0, "ok": 0, "warning": 0, "critical": 0}


def get_prediction_risk_count(site_uuid: str) -> int:
    """Get count of active predictions with warning/critical severity for a building.

    This is the consolidated risk count (replacing alert_count).

    Args:
        site_uuid: Building UUID

    Returns:
        Count of active risk predictions
    """
    try:
        from app.database.supabase_client import get_supabase_client

        client = get_supabase_client()

        # Count predictions with warning or critical severity
        result = (
            client.table("predictions")
            .select("id", count="exact")
            .eq("site_id", site_uuid)
            .eq("status", "active")
            .in_("severity", ["warning", "critical"])
            .execute()
        )

        return result.count or 0
    except Exception as e:
        logger.warning(f"Failed to get prediction risk count: {e}")
        return 0


def calculate_site_status(site_alerts: list[dict]) -> Literal["normal", "warning", "critical"]:
    """Calculate site status based on active alerts."""
    if not site_alerts:
        return "normal"

    has_critical = any(a.get("severity", "").lower() == "critical" for a in site_alerts)
    if has_critical:
        return "critical"

    has_warning = any(a.get("severity", "").lower() in ["warning", "high"] for a in site_alerts)
    if has_warning:
        return "warning"

    return "normal"


def calculate_site_status_from_equipment(equipment_status: dict | None) -> Literal["normal", "warning", "critical"]:
    """Calculate site status from equipment warning/critical state."""
    if not equipment_status:
        return "normal"

    critical = int(equipment_status.get("critical", 0) or 0)
    warning = int(equipment_status.get("warning", 0) or 0)

    if critical > 0:
        return "critical"
    if warning > 0:
        return "warning"
    return "normal"


def db_to_site_dict(
    db_building: dict,
    equipment_count: int = 0,
    alert_count: int = 0,
    asset_summary: dict | None = None,
    equipment_status: dict | None = None,
) -> dict:
    """Convert database building record to API-compatible site dict.

    Args:
        db_building: Building record from database
        equipment_count: Legacy equipment count (fallback)
        alert_count: Active alert count
        asset_summary: Asset summary from v_site_asset_summary view (if available)
        equipment_status: Equipment status breakdown (ok/warning/critical counts)
    """
    operating_hours = db_building.get("operating_hours") or {"start": "08:00", "end": "18:00"}
    if isinstance(operating_hours, str):
        try:
            operating_hours = json.loads(operating_hours)
        except (json.JSONDecodeError, TypeError):
            operating_hours = {"start": "08:00", "end": "18:00"}
    # Normalize Supabase format {"weekday": "07:00-18:00"} to API format {"start": "07:00", "end": "18:00"}
    if "start" not in operating_hours and "weekday" in operating_hours:
        weekday = operating_hours.get("weekday", "08:00-18:00")
        if "-" in str(weekday):
            parts = str(weekday).split("-", 1)
            operating_hours = {"start": parts[0], "end": parts[1]}
        else:
            operating_hours = {"start": "08:00", "end": "18:00"}

    # ⚠️  IMPORTANT: Always use equipment_count from Supabase, never from asset_summary or JSON
    total_assets = equipment_count or 0

    result = {
        "id": db_building.get("code") or db_building.get("id", "unknown"),
        "name": db_building.get("name") or "Unknown Building",
        "address": db_building.get("address") or "",
        "region": db_building.get("region") or "Unknown",
        "type": db_building.get("type") or "regional_office",
        "sqm": db_building.get("sqm") or 0,
        "floors": db_building.get("floors") or 1,
        "year_built": db_building.get("year_built") or 2020,
        "operating_hours": operating_hours,
        "timezone": db_building.get("timezone") or "Africa/Johannesburg",
        "occupancy_pattern": db_building.get("occupancy_pattern") or "office",
        "latitude": float(db_building.get("latitude") or 0),
        "longitude": float(db_building.get("longitude") or 0),
        "contact_email": db_building.get("contact_email") or "",
        "contact_phone": db_building.get("contact_phone") or "",
        "optimization_enabled": db_building.get("optimization_enabled") or False,
        "optimization_status": db_building.get("optimization_status") or "unknown",
        "control_enabled": db_building.get("control_enabled") or False,
        "control_note": db_building.get("control_note"),
        "sentinel_processing_enabled": db_building.get("sentinel_processing_enabled", True) is not False,
        "onboarding_phase": db_building.get("onboarding_phase") or "shadow",
        "equipment_count": total_assets,  # Total assets from Supabase only
        "alert_count": alert_count,
        "active_alerts": alert_count,
    }

    # Include equipment status breakdown if available
    if equipment_status:
        result["equipment_status"] = equipment_status

    # Enrich from building.json (canonical source for building metadata)
    result = _enrich_from_building_json(result)

    return result


class OperatingHours(BaseModel):
    """Operating hours model."""

    start: str
    end: str


class SiteBase(BaseModel):
    """Base site model."""

    id: str
    name: str
    address: str = ""
    region: str = ""
    type: str = "unknown"
    sqm: int | None = 0
    floors: int | None = 0
    year_built: int | None = 0
    operating_hours: OperatingHours | None = None
    timezone: str = "Africa/Johannesburg"  # IANA timezone
    occupancy_pattern: str | None = ""
    latitude: float | None = 0.0
    longitude: float | None = 0.0
    contact_email: str | None = ""
    contact_phone: str | None = ""


class EquipmentStatusBreakdown(BaseModel):
    """Equipment status breakdown."""

    total: int = 0
    ok: int = 0
    warning: int = 0
    critical: int = 0


class SiteResponse(SiteBase):
    """Site response with computed fields."""

    model_config = {"extra": "ignore"}

    equipment_count: int = 0
    active_alerts: int = 0
    alert_count: int = 0
    location: str = ""
    status: Literal["normal", "warning", "critical"] = "normal"
    optimization_enabled: bool = False
    optimization_status: str = "unknown"
    optimization_settings: dict | None = None
    control_enabled: bool = False
    control_note: str | None = None
    equipment_status: EquipmentStatusBreakdown | None = None
    sentinel_processing_enabled: bool = True
    onboarding_phase: str = "shadow"
    last_phase_transition: dict | None = None  # most recent phase_transition_log row
    # SIMBIOT ingestion status
    bridge_connected: bool = False
    bridge_data_source: str = "none"  # "remote_bridge" | "local_adapter" | "none"
    bridge_last_sync: str | None = None  # ISO timestamp
    bridge_sync_error: str | None = None  # Error message if applicable


class SiteListResponse(BaseModel):
    """Response for site list."""

    total: int
    sites: list[SiteResponse]


def get_sites_from_supabase(
    region: str | None = None,
    site_type: str | None = None,
    user_email: str | None = None,
    user_role: SentinelRole | None = None,
) -> tuple[list[dict], bool]:
    """Try to get sites from Supabase. Returns (sites, success).

    If user_email and user_role are provided, filters buildings by user access.
    ADMIN role sees all buildings, others see only assigned buildings.
    """
    if settings.use_json_storage:
        return [], False

    try:
        repo = SiteRepository()

        # Filter by user access if auth context provided
        if user_email and user_role:
            buildings = repo.get_all_for_user(
                user_email=user_email, user_role=user_role, region=region, site_type=site_type
            )
        else:
            buildings = repo.get_all(region=region, site_type=site_type)

        if not buildings:
            return [], False

        # Filter to only onboarded sites (those with at least one active module)
        # Sites without modules haven't been ingested via SIMBIOT yet
        try:
            from app.database.supabase_client import get_supabase_client

            client = get_supabase_client()
            modules_result = client.table("site_modules").select("site_id").execute()
            onboarded_sites = {row["site_id"] for row in (modules_result.data or [])}
            if onboarded_sites:
                buildings = [b for b in buildings if b.get("code") in onboarded_sites]
        except Exception as e:
            logger.warning(f"Could not filter by onboarded sites: {e}")

        if not buildings:
            return [], False

        sites = []
        for b in buildings:
            # Get equipment and alert counts
            site_uuid = b.get("id")
            site_code = b.get("code")

            # ⚠️  IMPORTANT: Read ONLY from Supabase, NOT from JSON fallback
            # Get actual equipment count from equipment table (not from buildings.equipment_count column)
            try:
                from app.database.supabase_client import get_supabase_client

                client = get_supabase_client()
                eq_result = client.table("equipment").select("id", count="exact").eq("site_id", site_uuid).execute()
                eq_count = eq_result.count or 0
            except Exception as e:
                logger.warning(f"Failed to get equipment count from Supabase for {site_code}: {e}")
                eq_count = 0

            # Count active risks from predictions (consolidated risk system)
            alert_count = get_prediction_risk_count(site_uuid) if site_uuid else 0

            # Get equipment status breakdown
            equipment_status = get_equipment_status_breakdown(site_uuid) if site_uuid else None

            # Don't use asset_summary - only use actual Supabase equipment count
            sites.append(db_to_site_dict(b, eq_count, alert_count, None, equipment_status))

        return sites, True
    except Exception as e:
        logger.warning(f"Supabase query failed, falling back to JSON: {e}")
        return [], False


def get_site_from_supabase(site_id: str) -> tuple[dict | None, bool]:
    """Try to get a single site from Supabase. Returns (site, success)."""
    if settings.use_json_storage:
        return None, False

    try:
        repo = SiteRepository()
        building = repo.get_by_id(site_id)

        if not building:
            return None, True  # Success but not found

        site_uuid = building.get("id")

        # ⚠️  IMPORTANT: Read ONLY from Supabase, NOT from JSON fallback
        # Get actual equipment count from equipment table (not from buildings.equipment_count column)
        try:
            from app.database.supabase_client import get_supabase_client

            client = get_supabase_client()
            eq_result = client.table("equipment").select("id", count="exact").eq("site_id", site_uuid).execute()
            eq_count = eq_result.count or 0
        except Exception as e:
            logger.warning(f"Failed to get equipment count from Supabase for {site_id}: {e}")
            eq_count = 0

        # Count active risks from predictions (consolidated risk system)
        alert_count = get_prediction_risk_count(site_uuid) if site_uuid else 0

        # Get equipment status breakdown
        equipment_status = get_equipment_status_breakdown(site_uuid) if site_uuid else None

        # Don't use asset_summary - only use actual Supabase equipment count
        return db_to_site_dict(building, eq_count, alert_count, None, equipment_status), True
    except Exception as e:
        logger.warning(f"Supabase query failed, falling back to JSON: {e}")
        return None, False


@router.get("/sites", response_model=SiteListResponse)
async def list_sites(
    region: str | None = Query(None, description="Filter by region"),
    site_type: str | None = Query(None, alias="type", description="Filter by type"),
    auth: AuthContext = Depends(require_auth(AuthLevel.AUTHENTICATED)),
) -> SiteListResponse:
    """List all sites with optional filtering.

    ADMIN users see all buildings.
    Other users see only buildings they have been granted access to.
    """

    # Extract user info from auth context
    user_email = auth.email
    user_role = auth.role

    # Try Supabase first (with user filtering)
    sites, success = get_sites_from_supabase(
        region=region, site_type=site_type, user_email=user_email, user_role=user_role
    )

    if success and sites:
        # Merge persisted processing state (JSON is authoritative for toggle)
        processing_state = _load_processing_state()
        phase_state = _load_phase_state()
        result = []
        for site in sites:
            site_id = site.get("id", "")
            code = site.get("code", "")
            if site_id in processing_state:
                site["sentinel_processing_enabled"] = processing_state[site_id]
            if code in phase_state:
                site["onboarding_phase"] = phase_state[code]
            status = calculate_site_status_from_equipment(site.get("equipment_status"))

            # Merge live bridge status so SiteCard shows correct connectivity
            sentinel_enabled = site.get("sentinel_processing_enabled", True)
            bridge_status = _get_bridge_status(sentinel_enabled=sentinel_enabled)
            site_with_bridge = {**site, **bridge_status}

            result.append(
                SiteResponse(
                    **site_with_bridge,
                    location=site.get("address", ""),
                    status=status,
                )
            )
        return SiteListResponse(total=len(result), sites=result)

    # Fallback to JSON
    sites = load_sites()
    alerts = load_alerts()

    if region:
        sites = [s for s in sites if s["region"].lower() == region.lower()]
    if site_type:
        sites = [s for s in sites if s["type"].lower() == site_type.lower()]

    # Merge persisted processing state from JSON fallback
    processing_state = _load_processing_state()

    result = []
    for site in sites:
        site_id = site["id"]

        # Apply persisted processing toggle state
        if site_id in processing_state:
            site["sentinel_processing_enabled"] = processing_state[site_id]

        # Get aggregated asset counts from all JSON sources
        asset_counts = get_json_asset_counts(site_id)

        site_alerts = [a for a in alerts if a.get("site_id") == site_id and a.get("status") == "active"]
        status = calculate_site_status(site_alerts)
        alert_count = len(site_alerts)

        # Remove fields that will be set explicitly to avoid duplicate kwargs
        site_clean = {
            k: v
            for k, v in site.items()
            if k
            not in (
                "equipment_count",
                "active_alerts",
                "alert_count",
                "status",
            )
        }
        site_response = SiteResponse(
            **site_clean,
            equipment_count=asset_counts["total_assets"],
            active_alerts=alert_count,
            alert_count=alert_count,
            status=status,
        )

        # Add asset breakdown to the response dict (for SiteCard tooltip)
        site_dict = site_response.model_dump()
        site_dict["asset_breakdown"] = asset_counts["breakdown"]
        result.append(site_dict)

    # Convert back to SiteResponse objects (with extra fields preserved)
    return SiteListResponse(total=len(result), sites=[SiteResponse(**s) for s in result])


# ============= Template Buildings Endpoint =============
# NOTE: These specific routes MUST come before /sites/{site_id} to avoid being caught by the wildcard


class TemplateBuilding(BaseModel):
    """Template building available for onboarding/discovery seeding."""

    id: str
    name: str
    type: str
    equipment_count: int
    description: str


@router.get("/sites/template-buildings", response_model=list[TemplateBuilding])
async def list_template_buildings() -> list[TemplateBuilding]:
    """List template buildings available for onboarding/discovery seeding.

    Scans buildings directory for sites that have equipment files.
    These can be used as template data sources during onboarding.
    """
    registry_path = SITES_DIR / "_registry.json"

    if not registry_path.exists():
        return []

    with open(registry_path) as f:
        registry = json.load(f)

    template_buildings = []
    for site_id in registry.get("active_sites", []):
        site_file = SITES_DIR / site_id / "building.json"
        equipment_dir = SITES_DIR / site_id / "equipment"

        if not site_file.exists():
            continue

        if not equipment_dir.exists():
            continue

        with open(site_file) as f:
            building = json.load(f)

        # Count equipment files
        equipment_count = len(list(equipment_dir.glob("*.json")))
        if equipment_count == 0:
            continue  # Skip sites with no template equipment

        metadata = building.get("metadata", {})
        site_type = metadata.get("type", "office")

        template_buildings.append(
            TemplateBuilding(
                id=site_id,
                name=building.get("name", site_id),
                type=site_type,
                equipment_count=equipment_count,
                description=f"{equipment_count} equipment, {site_type.replace('_', ' ')}",
            )
        )

    return template_buildings


# ============= Site Creation Endpoints =============


class CreateSiteRequest(BaseModel):
    """Request to create a new site."""

    name: str = Field(..., description="Site name")
    address: str = Field("", description="Site address")
    region: str = Field("Gauteng", description="Region/province")
    type: str = Field("office", description="Building type (office, retail, hospital, industrial)")
    floors: list[str] = Field(default_factory=list, description="Floor list e.g. ['B1', 'G', 'L1', 'L2']")
    sqm: int = Field(0, description="Total floor area in square meters")


class CreateSiteResponse(BaseModel):
    """Response from site creation."""

    id: str
    name: str
    status: str


class NextSiteIdResponse(BaseModel):
    """Response with next available site ID."""

    next_id: str


def _get_next_site_number() -> int:
    """Scan registry to find the highest site number and return next available."""
    registry_path = SITES_DIR / "_registry.json"

    if not registry_path.exists():
        return 1

    with open(registry_path) as f:
        registry = json.load(f)

    max_num = 0
    for site_id in registry.get("active_sites", []):
        # Extract number from site-XXX format
        match = re.match(r"site-(\d+)", site_id)
        if match:
            num = int(match.group(1))
            if num > max_num:
                max_num = num

    return max_num + 1


@router.get("/sites/next-id", response_model=NextSiteIdResponse)
async def get_next_site_id() -> NextSiteIdResponse:
    """Get next available site ID (e.g., site-005)."""
    next_num = _get_next_site_number()
    return NextSiteIdResponse(next_id=f"site-{next_num:03d}")


@router.post("/sites", response_model=CreateSiteResponse)
async def create_site(request: CreateSiteRequest) -> CreateSiteResponse:
    """Create a new site with auto-generated ID.

    1. Determines next site ID from buildings directory
    2. Creates building.json in buildings/{site_id}/
    3. Creates empty equipment/ directory
    4. Adds to _registry.json
    5. Creates building record in Supabase (if configured)
    """
    if not request.name or not request.name.strip():
        raise HTTPException(status_code=400, detail="Site name is required")

    # Validate region/province
    if not request.region or not request.region.strip():
        raise HTTPException(status_code=400, detail="Region/province is required")

    # 1. Determine next site ID
    next_num = _get_next_site_number()
    site_id = f"site-{next_num:03d}"

    # 2. Create building directory structure
    site_dir = SITES_DIR / site_id
    equipment_dir = site_dir / "equipment"

    try:
        site_dir.mkdir(parents=True, exist_ok=True)
        equipment_dir.mkdir(parents=True, exist_ok=True)
    except Exception as e:
        logger.error(f"Failed to create site directory: {e}")
        raise HTTPException(status_code=500, detail=f"Failed to create site directory: {e}")

    # 3. Create building.json
    site_data = {
        "id": site_id,
        "name": request.name,
        "display_name": request.name,
        "address": request.address,
        "timezone": "Africa/Johannesburg",
        "floors": request.floors or ["G"],
        "features": {
            "hvac": True,
            "dali": False,
            "desk_diagnosis": False,
            "load_shedding_optimization": True,
        },
        "bms": {
            "vendor": "Unknown",
            "system": "Unknown",
            "protocol": "BACnet/IP",
        },
        "contacts": {},
        "metadata": {
            "type": request.type,
            "total_floors": len(request.floors) if request.floors else 1,
            "sqm": request.sqm,
            "total_devices": 0,
            "on_bms_count": 0,
            "bms_coverage_pct": 0,
        },
    }

    site_file = site_dir / "building.json"
    try:
        with open(site_file, "w") as f:
            json.dump(site_data, f, indent=2)
    except Exception as e:
        logger.error(f"Failed to write building.json: {e}")
        raise HTTPException(status_code=500, detail=f"Failed to write building configuration: {e}")

    # 4. Update registry
    registry_path = SITES_DIR / "_registry.json"
    try:
        if registry_path.exists():
            with open(registry_path) as f:
                registry = json.load(f)
        else:
            registry = {"active_sites": [], "default_building": site_id}

        if site_id not in registry.get("active_sites", []):
            registry.setdefault("active_sites", []).append(site_id)

        with open(registry_path, "w") as f:
            json.dump(registry, f, indent=2)

        processing_state = _load_processing_state()
        processing_state[site_id] = False
        _save_processing_state(processing_state)
    except Exception as e:
        logger.error(f"Failed to update registry: {e}")
        raise HTTPException(status_code=500, detail=f"Failed to update registry: {e}")

    # 5. Create in Supabase (best-effort)
    if not settings.use_json_storage:
        try:
            from app.database.supabase_client import get_supabase_client

            client = get_supabase_client()
            if client:
                client.table("sites").insert(
                    {
                        "code": site_id,
                        "name": request.name,
                        "address": request.address,
                        "type": request.type,
                        "region": request.region,
                        "sqm": request.sqm,
                        "floors": len(request.floors) if request.floors else 1,
                        "timezone": "Africa/Johannesburg",
                        "sentinel_processing_enabled": False,
                    }
                ).execute()
                logger.info(f"Created building in Supabase: {site_id}")

                # Auto-seed municipal tariff schedule + account based on region
                _seed_municipal_tariff_and_account(client, site_id, request.region)
        except Exception as e:
            # Log but don't fail - JSON is primary storage
            logger.warning(f"Failed to create building in Supabase: {e}")

    logger.info(f"Created new site: {site_id} ({request.name})")

    return CreateSiteResponse(
        id=site_id,
        name=request.name,
        status="created",
    )


def _seed_municipal_tariff_and_account(client, site_id: str, region: str) -> None:
    """Seed default municipal tariff schedule and account for a new site."""
    municipality_by_region = {
        "Gauteng": {"municipality": "City Power Johannesburg", "tariff": "TOU Commercial"},
        "Western Cape": {"municipality": "City of Cape Town", "tariff": "Commercial TOU"},
        "KwaZulu-Natal": {"municipality": "eThekwini", "tariff": "Commercial TOU"},
        "Eastern Cape": {"municipality": "Nelson Mandela Bay", "tariff": "Commercial TOU"},
        "Free State": {"municipality": "Mangaung", "tariff": "Commercial TOU"},
        "Limpopo": {"municipality": "Polokwane", "tariff": "Commercial TOU"},
        "Mpumalanga": {"municipality": "Mbombela", "tariff": "Commercial TOU"},
        "North West": {"municipality": "Rustenburg", "tariff": "Commercial TOU"},
        "Northern Cape": {"municipality": "Sol Plaatje", "tariff": "Commercial TOU"},
    }

    info = municipality_by_region.get(region, municipality_by_region["Gauteng"])
    municipality = info["municipality"]
    tariff_name = info["tariff"]

    # Load default tariff data if available (City Power JSON)
    tariff_data = {}
    try:
        import json
        from pathlib import Path

        tariff_path = Path(__file__).parent.parent / "data" / "solar" / "tariffs" / "city_power_2026.json"
        if tariff_path.exists() and "City Power" in municipality:
            with open(tariff_path) as f:
                tariff_data = json.load(f)
    except Exception as exc:
        logger.info("Tariff JSON load failed: %s", exc)

    # Upsert tariff schedule
    try:
        client.table("municipal_tariff_schedules").upsert(
            {
                "municipality": municipality,
                "tariff_name": tariff_name,
                "utility_type": "electricity",
                "effective_date": f"{datetime.now().year}-01-01",
                "tariff_data": tariff_data or {},
                "nersa_approved": False,
                "source_url": "auto-seeded",
                "notes": "Auto-seeded from site creation",
            }
        ).execute()
    except Exception as exc:
        logger.info("Tariff schedule auto-seed failed: %s", exc)

    # Ensure municipal account exists
    try:
        account_number = f"{municipality[:2].upper()}-{site_id.replace('site-', '')}-00001"
        account_result = (
            client.table("municipal_accounts")
            .select("id")
            .eq("site_id", site_id)
            .eq("municipality", municipality)
            .eq("utility_type", "electricity")
            .eq("account_number", account_number)
            .limit(1)
            .execute()
        )
        if not account_result.data:
            client.table("municipal_accounts").insert(
                {
                    "site_id": site_id,
                    "municipality": municipality,
                    "utility_type": "electricity",
                    "account_number": account_number,
                    "tariff_type": tariff_name,
                    "main_meter_id": f"{site_id.replace('site-', 'S').upper()}-MTR-E-MAIN",
                }
            ).execute()
    except Exception as exc:
        logger.info("Municipal account auto-seed failed: %s", exc)


# ============= SENTINEL Processing Toggle =============

# Demo-mode fallback for processing state
_PROCESSING_STATE_FILE = DATA_DIR / "site_processing_state.json"


def _load_processing_state() -> dict:
    """Load processing state from JSON fallback."""
    if _PROCESSING_STATE_FILE.exists():
        with open(_PROCESSING_STATE_FILE) as f:
            return json.load(f)
    return {}


def _save_processing_state(state: dict) -> None:
    """Save processing state to JSON fallback."""
    with open(_PROCESSING_STATE_FILE, "w") as f:
        json.dump(state, f, indent=2)


class ProcessingToggleRequest(BaseModel):
    """Request to toggle SENTINEL processing."""

    enabled: bool


class ProcessingToggleResponse(BaseModel):
    """Response from processing toggle."""

    site_id: str
    sentinel_processing_enabled: bool


async def is_site_processing_enabled(site_id: str) -> bool:
    """Check if SENTINEL processing is enabled for a site.

    Used by lifecycle orchestrator and ML feeder to gate processing.
    Returns True by default (fail-open: if we can't read state, process).
    """
    # Always try Supabase first — it's the source of truth for the dashboard
    try:
        from app.database.supabase_client import get_supabase_client

        client = get_supabase_client()
        result = client.table("sites").select("sentinel_processing_enabled").eq("code", site_id).limit(1).execute()
        if result.data:
            return result.data[0].get("sentinel_processing_enabled", True) is not False
    except Exception as e:
        logger.warning(f"Failed to check processing state for {site_id}: {e}")

    # JSON fallback if Supabase unavailable
    state = _load_processing_state()
    return state.get(site_id, True)


@router.get("/sites/{site_id}/processing", response_model=ProcessingToggleResponse)
async def get_site_processing(
    site_id: str,
    auth: AuthContext = Depends(require_site_access("site_id")),
) -> ProcessingToggleResponse:
    """Get SENTINEL processing state for a site."""
    enabled = await is_site_processing_enabled(site_id)
    return ProcessingToggleResponse(site_id=site_id, sentinel_processing_enabled=enabled)


@router.post("/sites/{site_id}/processing", response_model=ProcessingToggleResponse)
async def toggle_site_processing(
    site_id: str,
    request: ProcessingToggleRequest,
    auth: AuthContext = Depends(require_site_access("site_id", auth_level=AuthLevel.OPERATOR)),
) -> ProcessingToggleResponse:
    """Toggle SENTINEL processing for a site.

    When disabled, SENTINEL stops ML feeding, health monitoring, alerts, and
    recommendations for this building. Data persistence (Supabase writes for
    dashboard) continues regardless.
    """
    enabled = request.enabled
    supabase_ok = False

    # Always try Supabase first — dashboard reads building record directly
    try:
        from app.database.supabase_client import get_supabase_client

        client = get_supabase_client()
        client.table("sites").update({"sentinel_processing_enabled": enabled}).eq("code", site_id).execute()
        supabase_ok = True
        logger.info(f"SENTINEL processing {'enabled' if enabled else 'disabled'} for {site_id}")
    except Exception as e:
        logger.warning(f"Failed to update processing state in Supabase for {site_id}: {e}")

    # Also persist to JSON fallback for offline resilience
    state = _load_processing_state()
    state[site_id] = enabled
    _save_processing_state(state)
    if not supabase_ok:
        logger.info(f"SENTINEL processing {'enabled' if enabled else 'disabled'} for {site_id} (JSON fallback only)")

    return ProcessingToggleResponse(site_id=site_id, sentinel_processing_enabled=enabled)


@router.get("/sites/{site_id}/telemetry")
async def get_site_telemetry(
    site_id: str,
    auth: AuthContext = Depends(require_site_access("site_id")),
) -> dict[str, Any]:
    """Proxy live site telemetry from the remote bridge."""

    def _unavailable(reason: str) -> dict[str, Any]:
        return {
            "site_id": site_id,
            "source_mode": "unavailable",
            "bridge_connected": False,
            "timestamp": None,
            "error": reason,
        }

    if not settings.simbiot_api_url:
        logger.warning("Telemetry bridge unavailable for %s: remote bridge is not configured", site_id)
        return _unavailable("remote_bridge_not_configured")

    from app.services.simbiot_service import simbiot_service

    try:
        return await simbiot_service.get_site_telemetry(site_id)
    except httpx.HTTPStatusError as exc:
        status_code = exc.response.status_code if exc.response is not None else None
        detail = exc.response.text[:300] if exc.response is not None else str(exc)
        logger.warning(
            "Remote telemetry HTTP failure for %s: status=%s detail=%s",
            site_id,
            status_code,
            detail,
        )
        return _unavailable(f"remote_bridge_http_{status_code or 'error'}")
    except Exception as exc:
        logger.warning("Failed to fetch remote telemetry for %s: %s", site_id, exc)
        return _unavailable("remote_bridge_unavailable")


@router.get("/sites/{site_id}/status")
async def get_site_status(
    site_id: str,
    auth: AuthContext = Depends(require_site_access("site_id")),
) -> dict[str, Any]:
    """Proxy live site status from the remote bridge."""
    if not settings.simbiot_api_url:
        raise HTTPException(status_code=503, detail="Remote bridge is not configured")

    from app.services.simbiot_service import simbiot_service

    try:
        return await simbiot_service.get_site_status(site_id)
    except httpx.HTTPStatusError as exc:
        detail = exc.response.text[:300] if exc.response is not None else str(exc)
        raise HTTPException(status_code=exc.response.status_code, detail=detail) from exc
    except Exception as exc:
        logger.warning("Failed to fetch remote status for %s: %s", site_id, exc)
        raise HTTPException(status_code=503, detail="Remote bridge status unavailable") from exc


# ============= Onboarding Phase Endpoint =============


class PhaseUpdateRequest(BaseModel):
    phase: Literal[
        "commissioning", "shadow_live", "advisory", "supervised", "automatic",
        # Legacy aliases (normalised on write)
        "shadow", "auto",
    ]
    reason: str | None = None
    changed_by: str | None = None  # user email; defaults to "system" if omitted


class PhaseUpdateResponse(BaseModel):
    site_id: str
    onboarding_phase: str


_ONBOARDING_PHASE_FILE = DATA_DIR / "onboarding_phase_state.json"


def _load_phase_state() -> dict:
    if _ONBOARDING_PHASE_FILE.exists():
        try:
            return json.loads(_ONBOARDING_PHASE_FILE.read_text())
        except (json.JSONDecodeError, OSError) as e:
            logger.warning("Failed to load phase state from %s: %s", _ONBOARDING_PHASE_FILE, e)
    return {}


def _save_phase_state(state: dict) -> None:
    _ONBOARDING_PHASE_FILE.write_text(json.dumps(state, indent=2))


@router.patch("/sites/{site_id}/phase", response_model=PhaseUpdateResponse)
async def update_site_phase(site_id: str, request: PhaseUpdateRequest) -> PhaseUpdateResponse:
    """Set the onboarding phase for a site.

    Progresses SENTINEL's trust-building model:
      commissioning → shadow_live → advisory → supervised → automatic

    Transition rules:
    - Forward by one step: allowed
    - Same stage: no-op (succeeds)
    - Forward by more than one step: 400 error
    - Backward: 400 error
    """
    from app.models.onboarding_phase import LEGACY_MAP, normalise_stage, validate_transition

    requested = normalise_stage(request.phase)
    supabase_ok = False

    previous_phase: str | None = None
    try:
        from app.database.supabase_client import get_supabase_client

        client = get_supabase_client()

        # Capture current phase for audit log + transition validation
        current_row = client.table("sites").select("onboarding_phase").eq("code", site_id).limit(1).execute()
        if current_row.data:
            previous_phase = normalise_stage(
                current_row.data[0].get("onboarding_phase") or "commissioning"
            )

        # Validate transition before writing
        if previous_phase:
            valid, err = validate_transition(previous_phase, requested)
            if not valid:
                raise HTTPException(
                    status_code=400,
                    detail={
                        "error": "Invalid transition",
                        "current": previous_phase,
                        "requested": requested,
                        "message": err,
                    },
                )

        client.table("sites").update({"onboarding_phase": requested}).eq("code", site_id).execute()
        supabase_ok = True
        logger.info(f"Onboarding phase set to '{requested}' for {site_id} (Supabase)")

        # Write phase transition to dedicated immutable log table
        try:
            client.table("phase_transition_log").insert(
                {
                    "site_id": site_id,
                    "from_phase": previous_phase,
                    "to_phase": requested,
                    "changed_by": request.changed_by
                    if hasattr(request, "changed_by") and request.changed_by
                    else "system",
                    "reason": request.reason if hasattr(request, "reason") else None,
                }
            ).execute()
        except Exception as audit_err:
            logger.warning(f"Phase transition log insert failed for {site_id}: {audit_err}")
    except Exception as e:
        logger.warning(f"Supabase phase update failed for {site_id}: {e}")

    # JSON fallback — persist phase and last transition for offline visibility
    state = _load_phase_state()
    state[site_id] = requested
    state[f"{site_id}:last_transition"] = {
        "to_phase": requested,
        "from_phase": previous_phase,
        "changed_by": request.changed_by or "system",
        "created_at": __import__("datetime").datetime.now(__import__("datetime").timezone.utc).isoformat(),
        "reason": request.reason,
    }
    _save_phase_state(state)

    # Patch sites.json fallback
    if settings.use_json_storage:
        try:
            sites_file = SITES_DIR.parent / "sites.json"
            if sites_file.exists():
                sites = json.loads(sites_file.read_text())
                for s in sites:
                    if s.get("code") == site_id:
                        s["onboarding_phase"] = requested
                        break
                sites_file.write_text(json.dumps(sites, indent=2))
        except Exception as e:
            logger.warning(f"sites.json phase fallback failed: {e}")

    if not supabase_ok:
        logger.info(f"Onboarding phase set to '{requested}' for {site_id} (JSON fallback only)")

    return PhaseUpdateResponse(site_id=site_id, onboarding_phase=requested)


# ============= Get Single Site Endpoint =============
# NOTE: This MUST come after the specific routes above


def _get_bridge_status(sentinel_enabled: bool = True) -> dict:
    """Get SIMBIOT ingestion status (connection, transport source, sync time).

    Bridge status is tied to sentinel_processing_enabled (the data valve).
    When valve is CLOSED (sentinel_enabled=False), no data flows (bridge_data_source="none").
    When valve is OPEN (sentinel_enabled=True), data flows from configured source.
    """
    # Valve closed: no data flows (fast path, no service calls)
    if not sentinel_enabled:
        return {
            "bridge_connected": False,
            "bridge_data_source": "none",
            "bridge_last_sync": None,
            "bridge_sync_error": None,
        }

    # Valve open: check data source (only when needed)
    try:
        bridge_connected = False
        bridge_data_source = "none"
        bridge_last_sync = None
        bridge_sync_error = None

        # Check SIMBIOT remote bridge status when a bridge endpoint is configured
        if settings.simbiot_api_url:
            try:
                from app.services.simbiot_service import simbiot_service

                simbiot_status = simbiot_service.status
                if isinstance(simbiot_status, dict):
                    bridge_connected = simbiot_status.get("enabled", False)
                    if not bridge_connected:
                        bridge_sync_error = simbiot_status.get("reason", "not initialized")
            except Exception as e:
                logger.warning(f"Failed to get SIMBIOT status: {e}")
                bridge_sync_error = str(e)[:100]

            if bridge_connected or settings.simbiot_api_url:
                bridge_data_source = "remote_bridge"

        # Check ShadowModePollingService — it has the live bridge connection
        # when simbiot_service is not enabled but the bridge is configured.
        try:
            from app.services.shadow_mode_polling import get_shadow_mode_polling_service

            shadow = get_shadow_mode_polling_service()
            shadow_status = shadow.status
            if isinstance(shadow_status, dict) and shadow_status.get("connected"):
                bridge_connected = True
                bridge_last_sync = shadow_status.get("last_poll")
                bridge_sync_error = None
                bridge_data_source = "remote_bridge"
        except Exception as e:
            logger.debug("Shadow polling status unavailable: %s", e)

        if (
            settings.site002_source_enabled
            and settings.ingestion_mode == "simulation"
        ):
            bridge_data_source = "local_adapter"
            bridge_connected = True  # Local adapter is connected (data flows)

        return {
            "bridge_connected": bridge_connected,
            "bridge_data_source": bridge_data_source,
            "bridge_last_sync": bridge_last_sync,
            "bridge_sync_error": bridge_sync_error,
        }
    except Exception as e:
        logger.warning(f"Error getting bridge status: {e}")
        return {
            "bridge_connected": False,
            "bridge_data_source": "error",
            "bridge_last_sync": None,
            "bridge_sync_error": str(e)[:100],
        }


@router.get("/sites/{site_id}", response_model=SiteResponse)
async def get_site(
    site_id: str,
    auth: AuthContext = Depends(require_site_access("site_id")),
) -> SiteResponse:
    """Get a single site by ID."""

    # Load processing state first to determine sentinel_enabled for bridge status
    processing_state = _load_processing_state()
    sentinel_enabled = processing_state.get(site_id, True)  # Default to enabled

    # Get bridge status with sentinel state (valve open/closed)
    bridge_status = _get_bridge_status(sentinel_enabled=sentinel_enabled)

    # Try Supabase first
    site, success = get_site_from_supabase(site_id)

    if success:
        if site:
            # Merge persisted processing state (JSON is authoritative for toggle)
            if site_id in processing_state:
                site["sentinel_processing_enabled"] = processing_state[site_id]
            status = calculate_site_status_from_equipment(site.get("equipment_status"))

            # Fetch most recent phase transition for audit visibility
            last_phase_transition = None
            try:
                from app.database.supabase_client import get_supabase_client

                client = get_supabase_client()
                transition_result = (
                    client.table("phase_transition_log")
                    .select("to_phase,changed_by,created_at,reason")
                    .eq("site_id", site_id)
                    .order("created_at", desc=True)
                    .limit(1)
                    .execute()
                )
                last_phase_transition = transition_result.data[0] if transition_result.data else None
            except Exception as e:
                logger.debug(f"Could not fetch last phase transition for {site_id}: {e}")

            return SiteResponse(
                **site,
                location=site.get("address", ""),
                status=status,
                last_phase_transition=last_phase_transition,
                **bridge_status,
            )
        else:
            raise HTTPException(status_code=404, detail=f"Site {site_id} not found")

    # Fallback to JSON
    sites = load_sites()
    alerts = load_alerts()

    site = next((s for s in sites if s["id"] == site_id), None)
    if not site:
        raise HTTPException(status_code=404, detail=f"Site {site_id} not found")

    # Merge persisted processing state from JSON fallback
    if site_id in processing_state:
        site["sentinel_processing_enabled"] = processing_state[site_id]

    # Get aggregated asset counts from all JSON sources
    asset_counts = get_json_asset_counts(site_id)

    site_alerts = [a for a in alerts if a.get("site_id") == site_id and a.get("status") == "active"]
    alert_count = len(site_alerts)
    status = calculate_site_status(site_alerts)

    # Remove fields that will be set explicitly to avoid duplicate kwargs
    site_clean = {
        k: v
        for k, v in site.items()
        if k
        not in (
            "equipment_count",
            "active_alerts",
            "alert_count",
            "location",
            "status",
        )
    }
    # Populate last_phase_transition from JSON phase state (Supabase unavailable path)
    phase_state = _load_phase_state()
    json_last_transition = phase_state.get(f"{site_id}:last_transition")

    return SiteResponse(
        **site_clean,
        equipment_count=asset_counts["total_assets"],
        active_alerts=alert_count,
        alert_count=alert_count,
        location=site.get("address", ""),
        status=status,
        last_phase_transition=json_last_transition,
        **bridge_status,
    )


# ============= Batch Sites Endpoint =============


class BatchSiteRequest(BaseModel):
    """Request for batch site retrieval."""

    site_ids: list[str] = Field(
        ..., min_length=1, max_length=100, description="List of site IDs to retrieve (max 100 per request)"
    )


class BatchSiteResponse(BaseModel):
    """Response from batch site retrieval."""

    results: dict[str, Any] = Field(default_factory=dict, description="Dict of site_id -> SiteResponse data")
    errors: dict[str, str] = Field(
        default_factory=dict, description="Dict of site_id -> error message for missing/failed sites"
    )


@router.post(
    "/sites/batch",
    response_model=BatchSiteResponse,
    summary="Get multiple sites in a single batch request",
    description="Fetch data for up to 100 sites in one call. "
    "Prevents 429 rate limit errors when multiple dashboard cards load simultaneously.",
)
async def batch_get_sites(payload: BatchSiteRequest) -> BatchSiteResponse:
    """Get multiple sites efficiently in a single request.

    Deduplicates site IDs and fetches all sites using single Supabase query.
    Returns dict keyed by site_id for O(1) client-side lookup.

    Args:
        payload: BatchSiteRequest with site_ids list (max 100)

    Returns:
        BatchSiteResponse with results dict and errors dict

    Raises:
        HTTPException: 400 if > 100 sites requested
    """
    # Deduplicate site IDs
    unique_site_ids = list(set(payload.site_ids))

    if len(unique_site_ids) > 100:
        raise HTTPException(status_code=400, detail="Maximum 100 unique site IDs per request")

    results: dict[str, Any] = {}
    errors: dict[str, str] = {}

    # Load shared data once
    alerts = load_alerts()

    # Fetch each site (try Supabase first, fallback to JSON)
    for site_id in unique_site_ids:
        try:
            # Try Supabase first
            site, success = get_site_from_supabase(site_id)

            if success and site:
                status = calculate_site_status_from_equipment(site.get("equipment_status"))
                results[site_id] = {
                    **site,
                    "location": site.get("address", ""),
                    "status": status,
                }
                continue

            # Fallback to JSON
            sites = load_sites()
            site = next((s for s in sites if s["id"] == site_id), None)
            if not site:
                errors[site_id] = "Site not found"
                continue

            # Get aggregated asset counts
            asset_counts = get_json_asset_counts(site_id)

            # Get alerts for this site
            site_alerts = [a for a in alerts if a.get("site_id") == site_id and a.get("status") == "active"]
            site_status = calculate_site_status(site_alerts)
            alert_count = len(site_alerts)

            # Build response
            site_response = {
                **site,
                "equipment_count": asset_counts["total_assets"],
                "active_alerts": alert_count,
                "alert_count": alert_count,
                "location": site.get("address", ""),
                "status": site_status,
                "asset_breakdown": asset_counts["breakdown"],
            }
            results[site_id] = site_response

        except Exception as e:
            logger.error(f"Error getting site {site_id}: {e}")
            errors[site_id] = str(e)

    return BatchSiteResponse(results=results, errors=errors)
