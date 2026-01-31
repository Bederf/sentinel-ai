"""Energy Centre API endpoints.

SCADA-style monitoring for complete electrical infrastructure:
MV/LV switchgear, ATS, transformers, power metering, PFC, UPS.
"""

from typing import Optional
from fastapi import APIRouter, HTTPException, Query

from app.services.energy_centre_service import get_energy_centre_service

router = APIRouter(prefix="/energy-centre", tags=["energy-centre"])


# === SCADA Overview ===

@router.get("/scada/{site_id}")
async def get_scada_overview(site_id: str):
    """Get complete SCADA overview for energy centre."""
    service = get_energy_centre_service()
    overview = service.get_scada_overview(site_id)
    return overview


@router.get("/sld/{site_id}")
async def get_sld_data(site_id: str):
    """Get single-line diagram data for visualization."""
    service = get_energy_centre_service()
    return service.get_sld_data(site_id)


# === Energy Centres ===

@router.get("")
async def list_centres(
    site_id: Optional[str] = Query(None, description="Filter by site"),
):
    """List all energy centres."""
    service = get_energy_centre_service()
    centres = service.get_centres(site_id=site_id)
    return {
        "centres": [c.to_dict() for c in centres],
        "total": len(centres),
    }


# === ATS (Automatic Transfer Switch) ===

@router.get("/ats")
async def list_ats_units(
    site_id: Optional[str] = Query(None, description="Filter by site"),
):
    """List all ATS units."""
    service = get_energy_centre_service()
    units = service.get_ats_units(site_id=site_id)
    return {
        "ats_units": [u.to_dict() for u in units],
        "total": len(units),
    }


@router.get("/ats/{ats_id}")
async def get_ats(ats_id: str):
    """Get single ATS unit."""
    service = get_energy_centre_service()
    ats = service.get_ats(ats_id)
    if not ats:
        raise HTTPException(status_code=404, detail=f"ATS {ats_id} not found")
    return ats.to_dict()


@router.get("/ats/{ats_id}/status")
async def get_ats_status(ats_id: str):
    """Get detailed ATS status with transfer history."""
    service = get_energy_centre_service()
    status = service.get_ats_status(ats_id)
    if not status:
        raise HTTPException(status_code=404, detail=f"ATS {ats_id} not found")
    return status


# === MV Switchgear ===

@router.get("/mv-incomers")
async def list_mv_incomers(
    site_id: Optional[str] = Query(None, description="Filter by site"),
):
    """List all MV incomers."""
    service = get_energy_centre_service()
    incomers = service.get_mv_incomers(site_id=site_id)
    return {
        "mv_incomers": [i.to_dict() for i in incomers],
        "total": len(incomers),
    }


@router.get("/mv-incomers/{incomer_id}")
async def get_mv_incomer(incomer_id: str):
    """Get single MV incomer."""
    service = get_energy_centre_service()
    incomer = service.get_mv_incomer(incomer_id)
    if not incomer:
        raise HTTPException(status_code=404, detail=f"MV incomer {incomer_id} not found")
    return incomer.to_dict()


# === Transformers ===

@router.get("/transformers")
async def list_transformers(
    site_id: Optional[str] = Query(None, description="Filter by site"),
):
    """List all transformers."""
    service = get_energy_centre_service()
    transformers = service.get_transformers(site_id=site_id)
    return {
        "transformers": [t.to_dict() for t in transformers],
        "total": len(transformers),
    }


@router.get("/transformers/{transformer_id}")
async def get_transformer(transformer_id: str):
    """Get single transformer."""
    service = get_energy_centre_service()
    transformer = service.get_transformer(transformer_id)
    if not transformer:
        raise HTTPException(status_code=404, detail=f"Transformer {transformer_id} not found")
    return transformer.to_dict()


# === LV Switchboards ===

@router.get("/switchboards")
async def list_switchboards(
    site_id: Optional[str] = Query(None, description="Filter by site"),
):
    """List all LV switchboards."""
    service = get_energy_centre_service()
    switchboards = service.get_switchboards(site_id=site_id)
    return {
        "switchboards": [s.to_dict() for s in switchboards],
        "total": len(switchboards),
    }


@router.get("/switchboards/{switchboard_id}")
async def get_switchboard(switchboard_id: str):
    """Get single switchboard."""
    service = get_energy_centre_service()
    switchboard = service.get_switchboard(switchboard_id)
    if not switchboard:
        raise HTTPException(status_code=404, detail=f"Switchboard {switchboard_id} not found")
    return switchboard.to_dict()


# === Power Metering ===

@router.get("/meters")
async def list_meters(
    site_id: Optional[str] = Query(None, description="Filter by site"),
    meter_type: Optional[str] = Query(None, description="Filter by type (main, sub, check, generator)"),
):
    """List all power meters."""
    service = get_energy_centre_service()
    meters = service.get_meters(site_id=site_id, meter_type=meter_type)
    return {
        "meters": [m.to_dict() for m in meters],
        "total": len(meters),
    }


@router.get("/meters/{meter_id}")
async def get_meter(meter_id: str):
    """Get single power meter."""
    service = get_energy_centre_service()
    meter = service.get_meter(meter_id)
    if not meter:
        raise HTTPException(status_code=404, detail=f"Meter {meter_id} not found")
    return meter.to_dict()


@router.get("/power-summary/{site_id}")
async def get_power_summary(site_id: str):
    """Get power summary from all meters at a site."""
    service = get_energy_centre_service()
    return service.get_power_summary(site_id)


# === Power Factor Correction ===

@router.get("/pfc")
async def list_pfc_banks(
    site_id: Optional[str] = Query(None, description="Filter by site"),
):
    """List all PFC banks."""
    service = get_energy_centre_service()
    banks = service.get_pfc_banks(site_id=site_id)
    return {
        "pfc_banks": [b.to_dict() for b in banks],
        "total": len(banks),
    }


@router.get("/pfc/{pfc_id}")
async def get_pfc(pfc_id: str):
    """Get single PFC bank."""
    service = get_energy_centre_service()
    pfc = service.get_pfc(pfc_id)
    if not pfc:
        raise HTTPException(status_code=404, detail=f"PFC bank {pfc_id} not found")
    return pfc.to_dict()


# === UPS Systems ===

@router.get("/ups")
async def list_ups_systems(
    site_id: Optional[str] = Query(None, description="Filter by site"),
):
    """List all UPS systems."""
    service = get_energy_centre_service()
    systems = service.get_ups_systems(site_id=site_id)
    return {
        "ups_systems": [s.to_dict() for s in systems],
        "total": len(systems),
    }


@router.get("/ups/{ups_id}")
async def get_ups(ups_id: str):
    """Get single UPS system."""
    service = get_energy_centre_service()
    ups = service.get_ups(ups_id)
    if not ups:
        raise HTTPException(status_code=404, detail=f"UPS {ups_id} not found")
    return ups.to_dict()


@router.get("/ups-summary/{site_id}")
async def get_ups_summary(site_id: str):
    """Get UPS summary for a site."""
    service = get_energy_centre_service()
    return service.get_ups_summary(site_id)


# === Distribution Feeders ===

@router.get("/feeders")
async def list_feeders(
    site_id: Optional[str] = Query(None, description="Filter by site"),
):
    """List all distribution feeders."""
    service = get_energy_centre_service()
    feeders = service.get_feeders(site_id=site_id)
    return {
        "feeders": feeders,
        "total": len(feeders),
    }
