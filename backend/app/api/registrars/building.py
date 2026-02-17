"""
Building API router registrar.

Registers routers for buildings, equipment, devices, and building systems.
"""

from fastapi import FastAPI

from app.api import buildings, equipment, sensors, devices, devices_batch, device_init
from app.api import dali, dali_discovery, equipment_discovery, equipment_metadata
from app.api import generators, energy_centre, energy, modules
from app.api import hvac, fire, security
from app.api import niagara, niagara_bacnet, niagara_discovery
from app.api import buildings_3d, digital_twin
from app.api import zone_ingestion, desks, documents
from app.api import device_controls
from app.api import occupancy_analytics, occupancy_energy_correlation


def register_building_routers(app: FastAPI) -> None:
    """Register building API routers (buildings, equipment, devices, systems)."""
    # Building and equipment management
    app.include_router(buildings.router, tags=["buildings"])
    app.include_router(documents.router, prefix="/api", tags=["documents"])
    app.include_router(equipment.router, prefix="/api", tags=["equipment"])
    app.include_router(sensors.router, prefix="/api", tags=["sensors"])
    app.include_router(devices.router, prefix="/api", tags=["devices"])
    app.include_router(devices_batch.router, prefix="/api", tags=["devices-batch"])
    app.include_router(device_controls.router, prefix="/api", tags=["device-controls"])
    app.include_router(device_init.router, tags=["device-init"])
    app.include_router(equipment_metadata.router, prefix="/api", tags=["equipment-metadata"])
    
    # Building 3D configuration (structure + equipment placement)
    app.include_router(buildings_3d.router, prefix="/api", tags=["buildings-3d"])

    # Digital Twin Builder (floor plan extraction + AI-powered onboarding)
    app.include_router(digital_twin.router, prefix="/api", tags=["digital-twin"])

    # Zone ingestion system (per-building zone configuration)
    app.include_router(zone_ingestion.router, tags=["zone-ingestion"])

    # Desk positioning and data (workspace positions for Digital Twin accuracy)
    app.include_router(desks.router, tags=["desks"])

    # Equipment discovery
    app.include_router(dali_discovery.router, prefix="/api", tags=["dali-discovery"])
    app.include_router(equipment_discovery.router, prefix="/api", tags=["equipment-discovery"])

    # Building systems - HVAC
    app.include_router(hvac.router, prefix="/api", tags=["hvac"])

    # Building systems - Lighting
    app.include_router(dali.router, prefix="/api/dali", tags=["dali-lighting"])

    # Occupancy analytics (trends, zone utilization, peak hours)
    app.include_router(occupancy_analytics.router, prefix="/api", tags=["occupancy-analytics"])

    # Occupancy-energy correlation (wasted energy, "lights left on" cost impact)
    app.include_router(occupancy_energy_correlation.router, prefix="/api", tags=["occupancy-energy"])

    # Building systems - Fire & Security
    app.include_router(fire.router, tags=["fire"])
    app.include_router(security.router, tags=["security"])

    # Energy centre (generators, MV/LV, ATS, UPS, meters)
    app.include_router(generators.router, prefix="/api", tags=["generators"])
    app.include_router(energy_centre.router, prefix="/api", tags=["energy-centre"])
    
    # Energy analytics (energy comparison, predictions, actual vs SENTINEL)
    app.include_router(energy.router, prefix="/api", tags=["energy"])
    
    # Module management (module registry, status, access control)
    app.include_router(modules.router, prefix="/api", tags=["modules"])

    # Niagara integration
    app.include_router(niagara.router, tags=["niagara-obix"])
    app.include_router(niagara_bacnet.router, tags=["niagara-bacnet"])
    app.include_router(niagara_discovery.router, tags=["niagara-discovery"])
