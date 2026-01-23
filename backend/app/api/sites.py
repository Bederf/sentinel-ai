"""Sites API endpoints."""

import json
from pathlib import Path
from typing import Optional

from fastapi import APIRouter, HTTPException, Query
from pydantic import BaseModel

router = APIRouter()

# Load sites data
DATA_DIR = Path(__file__).parent.parent / "data"


def load_sites() -> list[dict]:
    """Load sites from JSON file."""
    sites_file = DATA_DIR / "sites.json"
    if sites_file.exists():
        with open(sites_file) as f:
            return json.load(f)
    return []


def load_equipment() -> list[dict]:
    """Load equipment from JSON file."""
    equipment_file = DATA_DIR / "equipment.json"
    if equipment_file.exists():
        with open(equipment_file) as f:
            return json.load(f)
    return []


def load_alerts() -> list[dict]:
    """Load alerts from JSON file."""
    alerts_file = DATA_DIR / "alerts.json"
    if alerts_file.exists():
        with open(alerts_file) as f:
            return json.load(f)
    return []


class OperatingHours(BaseModel):
    """Operating hours model."""

    start: str
    end: str


class SiteBase(BaseModel):
    """Base site model."""

    id: str
    name: str
    address: str
    region: str
    type: str
    sqm: int
    floors: int
    year_built: int
    operating_hours: OperatingHours
    occupancy_pattern: str
    latitude: float
    longitude: float
    contact_email: str
    contact_phone: str


class SiteResponse(SiteBase):
    """Site response with computed fields."""

    equipment_count: int = 0
    active_alerts: int = 0


class SiteListResponse(BaseModel):
    """Response for site list."""

    total: int
    sites: list[SiteResponse]


@router.get("/sites", response_model=SiteListResponse)
async def list_sites(
    region: Optional[str] = Query(None, description="Filter by region"),
    site_type: Optional[str] = Query(None, alias="type", description="Filter by type"),
) -> SiteListResponse:
    """
    List all sites with optional filtering.

    Args:
        region: Filter by region (Gauteng, Western Cape, KwaZulu-Natal)
        site_type: Filter by type (branch, regional_office, data_center)

    Returns:
        SiteListResponse with total count and list of sites.
    """
    sites = load_sites()
    equipment = load_equipment()
    alerts = load_alerts()

    # Apply filters
    if region:
        sites = [s for s in sites if s["region"].lower() == region.lower()]
    if site_type:
        sites = [s for s in sites if s["type"].lower() == site_type.lower()]

    # Enrich with counts
    result = []
    for site in sites:
        site_equipment = [e for e in equipment if e.get("site_id") == site["id"]]
        site_alerts = [
            a for a in alerts if a.get("site_id") == site["id"] and a.get("status") == "active"
        ]
        result.append(
            SiteResponse(
                **site,
                equipment_count=len(site_equipment),
                active_alerts=len(site_alerts),
            )
        )

    return SiteListResponse(total=len(result), sites=result)


@router.get("/sites/{site_id}", response_model=SiteResponse)
async def get_site(site_id: str) -> SiteResponse:
    """
    Get a single site by ID.

    Args:
        site_id: The site identifier.

    Returns:
        SiteResponse with site details.

    Raises:
        HTTPException: If site not found.
    """
    sites = load_sites()
    equipment = load_equipment()
    alerts = load_alerts()

    site = next((s for s in sites if s["id"] == site_id), None)
    if not site:
        raise HTTPException(status_code=404, detail=f"Site {site_id} not found")

    site_equipment = [e for e in equipment if e.get("site_id") == site_id]
    site_alerts = [
        a for a in alerts if a.get("site_id") == site_id and a.get("status") == "active"
    ]

    return SiteResponse(
        **site,
        equipment_count=len(site_equipment),
        active_alerts=len(site_alerts),
    )
