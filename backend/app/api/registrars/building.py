"""
Building API router registrar.

Registers routers for buildings, equipment, devices, and building systems.
"""

from fastapi import FastAPI

from app.api import (
    building_schedule,
    building_state,
    buildings,
    cockpit,
    desks,
    device_controls,
    device_init,
    devices,
    devices_batch,
    digital_twin,
    documents,
    energy_centre,
    equipment,
    equipment_discovery,
    equipment_metadata,
    fire,
    generators,
    holiday_calendar,
    hvac,
    iaq,
    lighting,
    lighting_discovery,
    modules,
    niagara,
    niagara_bacnet,
    niagara_discovery,
    occupancy_analytics,
    occupancy_energy_correlation,
    sensors,
    simbiot_capabilities,
    site_profiles,
    sites_3d,
    zone_ingestion,
)
from app.api.equipment_knowledge import router as equipment_knowledge_router
from app.space.sensor_ingest import router as space_occupancy_router


def register_site_routers(app: FastAPI) -> None:
    """Register building API routers (buildings, equipment, devices, systems)."""
    # Building and equipment management
    app.include_router(buildings.router, tags=["sites"])
    app.include_router(building_state.router)
    app.include_router(documents.router, prefix="/api", tags=["documents"])
    app.include_router(equipment.router, prefix="/api", tags=["equipment"])
    app.include_router(sensors.router, prefix="/api", tags=["sensors"])
    app.include_router(devices.router, prefix="/api", tags=["devices"])
    app.include_router(devices_batch.router, prefix="/api", tags=["devices-batch"])
    app.include_router(device_controls.router, prefix="/api", tags=["device-controls"])
    app.include_router(device_init.router, tags=["device-init"])
    app.include_router(equipment_metadata.router, prefix="/api", tags=["equipment-metadata"])

    # Equipment knowledge (tech chat context — maintenance records, manuals)
    app.include_router(equipment_knowledge_router, tags=["equipment-knowledge"])

    # Building 3D configuration (structure + equipment placement)
    app.include_router(sites_3d.router, prefix="/api", tags=["sites-3d"])

    # Digital Twin Builder (floor plan extraction + AI-powered onboarding)
    app.include_router(digital_twin.router, prefix="/api", tags=["digital-twin"])

    # Cockpit decision system (tower risk, floor spread, deployment posture)
    app.include_router(cockpit.router, prefix="/api", tags=["cockpit"])

    # Zone ingestion system (per-building zone configuration)
    app.include_router(zone_ingestion.router, prefix="/api", tags=["zone-ingestion"])

    # Desk positioning and data (workspace positions for Digital Twin accuracy)
    app.include_router(desks.router, prefix="/api", tags=["desks"])

    # Equipment discovery
    app.include_router(lighting_discovery.router, prefix="/api", tags=["lighting-discovery"])
    app.include_router(equipment_discovery.router, prefix="/api", tags=["equipment-discovery"])

    # Building systems - Lighting
    app.include_router(lighting.router, prefix="/api/lighting", tags=["lighting"])

    # Building systems - HVAC (zones, equipment, overview, chillers, thermal runway)
    app.include_router(hvac.router, prefix="/api", tags=["hvac"])

    # Occupancy analytics (trends, zone utilization, peak hours)
    app.include_router(occupancy_analytics.router, prefix="/api", tags=["occupancy-analytics"])

    # Occupancy-driven control loop (Phase 130: trigger, status, history)
    app.include_router(occupancy_analytics.control_router, prefix="/api", tags=["occupancy-control"])

    # Occupancy-energy correlation (wasted energy, "lights left on" cost impact)
    app.include_router(occupancy_energy_correlation.router, prefix="/api", tags=["occupancy-energy"])

    # Indoor Air Quality intelligence (IAQ scores, alerts, WELL/ESG compliance)
    app.include_router(iaq.router, prefix="/api", tags=["iaq"])

    # Building systems - Fire & Security
    app.include_router(fire.router, tags=["fire"])

    # Energy centre (generators, MV/LV, ATS, UPS, meters)
    app.include_router(generators.router, prefix="/api", tags=["generators"])
    app.include_router(energy_centre.router, prefix="/api", tags=["energy-centre"])

    # Module management (module registry, status, access control)
    app.include_router(modules.router, prefix="/api", tags=["modules"])

    # Site profiles (building profile for onboarding gating — Phase 191)
    app.include_router(site_profiles.router, tags=["site-profiles"])

    # Space Occupancy POC (5-room sensor pipeline)
    app.include_router(space_occupancy_router, tags=["space-occupancy"])

    # Building schedule & holiday calendar
    app.include_router(building_schedule.router, tags=["building-schedule"])
    app.include_router(holiday_calendar.router, tags=["holiday-calendar"])

    # Niagara integration
    app.include_router(niagara.router, tags=["niagara-obix"])
    app.include_router(niagara_bacnet.router, tags=["niagara-bacnet"])
    app.include_router(niagara_discovery.router, tags=["niagara-discovery"])
    app.include_router(simbiot_capabilities.router, tags=["simbiot-capabilities"])
