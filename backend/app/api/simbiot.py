"""
SIMBIOT Site & Adapter Configuration API.

Manages site lifecycle and per-site BMS adapter configs.
Called by the SIMBIOT onboarding wizard to persist connection credentials.

Brand-agnostic — works with BACnet, Modbus, oBIX, Bridge, or any future protocol.
"""

from __future__ import annotations

import logging
from typing import Any

from fastapi import APIRouter, HTTPException, Query
from pydantic import BaseModel

from app.services.site_adapter_manager import SiteAdapterManager
from app.services.site_creation_service import SiteCreationService

logger = logging.getLogger("sentinel.simbiot_api")


# ---------------------------------------------------------------------------
# Request/Response Models
# ---------------------------------------------------------------------------


class CreateSiteRequest(BaseModel):
    site_name: str
    building_type: str
    location: str
    gross_floor_area: float | None = None
    site_code: str | None = None  # None = auto-generate next sequential ID


class SaveAdapterConfigRequest(BaseModel):
    enabled: bool = True
    poll_interval_seconds: int = 300


router = APIRouter(prefix="/api/simbiot", tags=["simbiot"])


@router.post("/sites")
async def create_site(request: CreateSiteRequest):
    """
    Create a new site with auto-generated or manual site code.

    POST /api/simbiot/sites
    {
        "site_name": "Example Hospital",
        "building_type": "hospital",
        "location": "Umhlanga, Durban",
        "gross_floor_area": 12000
    }

    Response:
    {
        "site_code": "S006",
        "site_id": "uuid...",
        "site_name": "Example Hospital",
        "message": "Site S006 created successfully"
    }
    """
    service = SiteCreationService()

    try:
        site = service.create_site(
            site_name=request.site_name,
            building_type=request.building_type,
            location=request.location,
            gross_floor_area=request.gross_floor_area,
            site_code=request.site_code,
        )

        # Seed only base modules. Add-ons remain inactive until explicitly activated.
        try:
            from app.services.module_registry_service import module_registry

            site_code = site["code"]
            seeded = module_registry.ensure_base_modules(site_code, request.site_name)
            if seeded:
                logger.info(
                    "Seeded base modules for %s via SIMBIOT wizard: %s",
                    site_code, seeded,
                )
        except Exception as mod_err:
            logger.warning("Failed to seed base modules for %s: %s", site.get("code"), mod_err)

        return {
            "site_code": site["code"],
            "site_id": site["id"],
            "site_name": site["name"],
            "message": f"Site {site['code']} created successfully",
        }
    except Exception as exc:
        logger.error("[SIMBIOT] Failed to create site: %s", exc)
        raise HTTPException(500, detail=str(exc)) from exc


# PHASE 191 GATE: Shadow mode requires confirmed building profile.
# Before transitioning any new site to shadow, call:
#   POST /api/site-profiles/{site_id}
# Gate enforced at PATCH /api/sites/{site_id}/phase.
# See SiteProfileService.has_confirmed_profile() for gate implementation.


@router.get("/sites/next-id")
async def get_next_site_id():
    """
    Preview the next auto-generated site code.
    Shows the user what ID will be assigned before they commit.

    GET /api/simbiot/sites/next-id

    Response:
    { "next_site_code": "S006" }
    """
    service = SiteCreationService()
    next_code = service.generate_next_site_code()
    return {"next_site_code": next_code}


@router.put("/sites/{site_id}/adapters/{protocol}/config")
async def save_adapter_config(
    site_id: str,
    protocol: str,
    config: dict[str, Any],
    enabled: bool = True,
    poll_interval_seconds: int = Query(default=300, ge=60, le=3600),
):
    """
    Save or update BMS adapter connection config for a site.
    Called by SIMBIOT wizard on approval step — persists credentials.

    PUT /api/simbiot/sites/{site_id}/adapters/{protocol}/config

    Path params:
        site_id:   Site code (e.g., "site-002", "site-003")
        protocol: Protocol name (bacnet, obix, modbus, bridge)

    Body (example for bridge):
        {
            "base_url": "http://10.99.0.1:8080",
            "token": "ScUAjUet7...",
            "poll_interval_seconds": 300
        }

    Body (example for BACnet):
        {
            "host": "192.168.10.50",
            "port": 47808,
            "device_instance": 1234
        }

    Response:
        { "status": "success", "message": "Saved bridge config for site-003" }
    """
    manager = SiteAdapterManager()

    success = manager.save_adapter_config(
        site_id=site_id,
        protocol=protocol,
        connection_config=config,
        enabled=enabled,
        poll_interval_seconds=poll_interval_seconds,
    )

    if not success:
        raise HTTPException(500, detail=f"Failed to save {protocol} config for {site_id}")

    return {"status": "success", "message": f"Saved {protocol} config for {site_id}"}


@router.get("/sites/{site_id}/adapters")
async def get_adapter_configs(site_id: str):
    """
    List all adapter configs for a site.
    GET /api/simbiot/sites/{site_id}/adapters
    """
    manager = SiteAdapterManager()
    configs = manager._fetch_adapter_configs(site_id)
    return {"site_id": site_id, "adapters": configs}
