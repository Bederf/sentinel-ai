"""Solar configuration management API.

Provides endpoints for creating and managing solar site configurations,
including inverters, BESS, grid meters, and tariff information.
"""

import re

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, Field

from app.api.dependencies.module_access import require_active_module
from app.models.module_registry import ModuleType

router = APIRouter(
    prefix="/api/solar-config",
    tags=["solar-config"],
    dependencies=[
        Depends(
            require_active_module(
                ModuleType.SOLAR,
                site_keys=("site_id", "site"),
            )
        )
    ],
)


# ============================================================================
# Request/Response Models
# ============================================================================


class SolarPlant(BaseModel):
    """Solar plant configuration."""

    plant_id: str = Field(..., description="Unique plant ID (e.g., S002-rooftop)")
    name: str = Field(..., description="Human-readable plant name")
    capacity_kwp: float = Field(..., gt=0, description="Installed capacity in kWp")
    panel_model: str | None = Field(None, description="Solar panel model")
    panel_count: int = Field(..., gt=0, description="Number of panels")
    commissioning_date: str | None = Field(None, description="ISO 8601 date")


class SolarInverter(BaseModel):
    """Solar inverter configuration."""

    equipment_id: str = Field(
        ...,
        description="Equipment code (e.g., S002-INV-R-001)",
    )
    manufacturer: str = Field(..., description="Inverter manufacturer")
    model: str = Field(..., description="Inverter model")
    rated_kva: float = Field(..., gt=0, description="Rated power in kVA")
    modbus_ip: str = Field(..., description="Modbus TCP IP address")
    modbus_port: int = Field(default=502, description="Modbus TCP port")
    modbus_unit_id: int = Field(default=1, description="Modbus unit ID")


class BESSConfig(BaseModel):
    """Battery energy storage system configuration."""

    equipment_id: str = Field(..., description="Equipment code (e.g., S002-BESS-B1-001)")
    manufacturer: str = Field(..., description="BESS manufacturer")
    model: str = Field(..., description="BESS model")
    capacity_kwh: float = Field(..., gt=0, description="Storage capacity in kWh")
    rated_power_kw: float = Field(..., gt=0, description="Rated power in kW")
    modbus_ip: str = Field(..., description="Modbus TCP IP address")
    modbus_port: int = Field(default=502, description="Modbus TCP port")
    modbus_unit_id: int = Field(default=1, description="Modbus unit ID")


class GridMeterConfig(BaseModel):
    """Grid connection meter configuration."""

    equipment_id: str = Field(..., description="Equipment code (e.g., S002-MTR-R-GRID)")
    manufacturer: str = Field(..., description="Meter manufacturer")
    modbus_ip: str = Field(..., description="Modbus TCP IP address")
    modbus_port: int = Field(default=502, description="Modbus TCP port")
    modbus_unit_id: int = Field(default=1, description="Modbus unit ID")


class SolarConfig(BaseModel):
    """Complete solar site configuration."""

    plants: list[SolarPlant] = Field(..., description="Solar plants")
    inverters: dict[str, list[SolarInverter]] = Field(default_factory=dict, description="Inverters per plant")
    bess: BESSConfig | None = Field(None, description="Battery storage config")
    grid_meter: GridMeterConfig | None = Field(None, description="Grid meter config")
    utility: str = Field(default="City Power", description="Utility provider")
    tariff: str = Field(default="standard", description="Tariff code or custom rates")


class SolarSiteRequest(BaseModel):
    """Request to create/update solar site configuration."""

    site_id: str = Field(..., description="Site ID (e.g., S002)")
    site_name: str = Field(..., description="Site name")
    latitude: float = Field(..., ge=-90, le=90, description="GPS latitude")
    longitude: float = Field(..., ge=-180, le=180, description="GPS longitude")
    config: SolarConfig = Field(..., description="Solar configuration")


class SolarSiteResponse(BaseModel):
    """Response from solar site creation."""

    status: str = Field(default="success")
    site_id: str = Field(..., description="Created site ID")
    message: str | None = None


# ============================================================================
# Validation Functions
# ============================================================================


def validate_equipment_code(code: str, expected_type: str) -> None:
    """Validate equipment code format.

    Args:
        code: Equipment code (e.g., S002-INV-R-001)
        expected_type: Equipment type (INV, BESS, MTR)

    Raises:
        ValueError: If code format is invalid
    """
    # Pattern: S{3digits}-{type}-{location}-{sequence or identifier}
    # Location: Letters and/or digits (e.g., R, B1, L2, G)
    # Sequence/ID: Either 3 digits (e.g., 001) or text identifier (e.g., GRID)
    if not code:
        raise ValueError("Equipment code is required")

    pattern = r"^S\d{3}-[A-Z]+-[A-Z0-9]{1,2}-(?:\d{3}|[A-Z]+)$"
    if not re.match(pattern, code):
        raise ValueError(f"Invalid equipment code format: {code}")

    if expected_type and expected_type not in code:
        raise ValueError(f"Code {code} does not match expected type {expected_type}")


def validate_inverter_coverage(plant: SolarPlant, inverters: list[SolarInverter]) -> dict:
    """Validate inverter capacity covers plant capacity.

    Args:
        plant: Solar plant configuration
        inverters: List of inverters for this plant

    Returns:
        Dict with coverage percentage and warning if needed
    """
    total_kva = sum(inv.rated_kva for inv in inverters)
    coverage_pct = (total_kva / plant.capacity_kwp) * 100

    result = {"total_kva": total_kva, "coverage_pct": coverage_pct}

    if coverage_pct < 80:
        result["warning"] = (
            f"Inverter coverage {coverage_pct:.1f}% < 80% "
            f"(capacity {plant.capacity_kwp} kWp, inverters {total_kva} kVA)"
        )

    return result


def validate_solar_config(request: SolarSiteRequest) -> list[str]:
    """Validate complete solar configuration.

    Args:
        request: Solar site configuration request

    Returns:
        List of validation errors (empty if valid)
    """
    errors = []

    # Validate plants exist
    if not request.config.plants:
        errors.append("At least one solar plant is required")
        return errors

    # Validate each plant
    for plant in request.config.plants:
        try:
            if plant.capacity_kwp <= 0:
                raise ValueError(f"Plant {plant.plant_id}: Capacity must be > 0")
            if plant.panel_count <= 0:
                raise ValueError(f"Plant {plant.plant_id}: Panel count must be > 0")
        except ValueError as e:
            errors.append(str(e))

    # Validate inverters if specified (optional for MVP)
    for plant_id, inverters in request.config.inverters.items():
        if not inverters:
            errors.append(f"Plant {plant_id} has no inverters assigned")
            continue

        # Find matching plant
        plant = next((p for p in request.config.plants if p.plant_id == plant_id), None)
        if not plant:
            errors.append(f"Inverters reference non-existent plant {plant_id}")
            continue

        # Validate each inverter
        for inv in inverters:
            try:
                validate_equipment_code(inv.equipment_id, "INV")
            except ValueError as e:
                errors.append(str(e))

        # Check coverage
        coverage = validate_inverter_coverage(plant, inverters)
        if "warning" in coverage:
            errors.append(coverage["warning"])

    # Validate BESS if present
    if request.config.bess:
        try:
            validate_equipment_code(request.config.bess.equipment_id, "BESS")
        except ValueError as e:
            errors.append(str(e))

        if request.config.bess.capacity_kwh <= 0:
            errors.append("BESS capacity must be > 0")

    # Validate grid meter if present
    if request.config.grid_meter:
        try:
            validate_equipment_code(request.config.grid_meter.equipment_id, "MTR")
        except ValueError as e:
            errors.append(str(e))

    return errors


# ============================================================================
# API Endpoints
# ============================================================================


@router.post("/sites", response_model=SolarSiteResponse)
async def create_solar_site(request: SolarSiteRequest) -> dict:
    """Create solar site configuration and activate Solar module.

    Args:
        request: Solar site configuration with plants, inverters, BESS, meters

    Returns:
        Success response with site ID

    Raises:
        HTTPException: If validation fails or site creation fails
    """
    # Validate configuration
    errors = validate_solar_config(request)
    if errors:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail={"errors": errors, "message": "Solar configuration validation failed"},
        )

    try:
        # TODO: Save to Supabase solar_sites table or JSON fallback
        # config_json = request.config.model_dump_json()
        # site_record = await save_solar_config(request.site_id, config_json, ...)

        # TODO: Activate Solar module via module_registry
        # await module_registry.activate_module(
        #     site_id=request.site_id,
        #     site_name=request.site_name,
        #     module_type="solar",
        #     config=request.config.model_dump(),
        # )

        # TODO: Trigger SolarIngestionService reload
        # solar_service.reload_site_configs()

        return SolarSiteResponse(
            status="success",
            site_id=request.site_id,
            message=f"Solar site {request.site_name} configured successfully",
        )

    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to create solar site: {e!s}",
        )


@router.get("/sites/{site_id}")
async def get_solar_config(site_id: str) -> dict:
    """Retrieve existing solar configuration for editing.

    Args:
        site_id: Site ID to retrieve configuration for

    Returns:
        Solar configuration for the site

    Raises:
        HTTPException: If site not found
    """
    # TODO: Load from Supabase or JSON fallback
    # config = await load_solar_config(site_id)
    # if not config:
    #     raise HTTPException(404, f"Solar site {site_id} not found")
    # return config

    raise HTTPException(
        status_code=status.HTTP_404_NOT_FOUND,
        detail=f"Solar site {site_id} not found",
    )


@router.post("/validate", response_model=dict)
async def validate_config(request: SolarSiteRequest) -> dict:
    """Validate solar configuration without saving.

    Args:
        request: Solar site configuration to validate

    Returns:
        Validation result with errors (if any)
    """
    errors = validate_solar_config(request)
    return {
        "valid": len(errors) == 0,
        "errors": errors,
        "message": "Configuration is valid" if not errors else "Configuration has errors",
    }
