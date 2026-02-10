"""Digital Twin Builder API Endpoints.

Handles floor plan extraction and building configuration for SIMBIOT wizard.
Supports sanitized image input (Tier 1) and DXF parsing (Tier 2).
"""

import logging
from typing import Dict, Optional

from fastapi import APIRouter, HTTPException, status, File, UploadFile
from pydantic import BaseModel, Field

from app.services.digital_twin_service import get_digital_twin_service

logger = logging.getLogger(__name__)

# ============= Request/Response Models =============


class ImageExtractionRequest(BaseModel):
    """Request to extract building config from floor plan image."""

    image_base64: str = Field(..., description="Base64-encoded floor plan image")
    building_code: str = Field(..., description="Building code (e.g., site-002)")
    building_name: str = Field(..., description="Building name (e.g., Sandton City)")
    floors_count: int = Field(
        ..., ge=1, le=50, description="Expected number of floors"
    )
    skip_sanitization: bool = Field(
        default=False,
        description="If False (default), sanitize image before API transmission for security",
    )


class EquipmentLocation(BaseModel):
    """Equipment position in building."""

    name: str = Field(..., description="Equipment name")
    equipment_type: str = Field(..., description="Equipment type (chiller, ahu, fcu, etc.)")
    floor: str = Field(..., description="Floor level (B1, G, L1, etc.)")
    x: float = Field(..., description="X coordinate (meters)")
    y: float = Field(..., description="Y coordinate (meters)")
    zone: Optional[str] = Field(None, description="Zone assignment (A, B, etc.)")
    confidence: Optional[float] = Field(None, description="Extraction confidence (0-1)")


class FloorDefinition(BaseModel):
    """Floor structure definition."""

    level: str = Field(..., description="Floor level (B1, G, L1, etc.)")
    height: float = Field(..., description="Floor height (meters)")
    width: float = Field(..., description="Floor width (meters)")
    depth: float = Field(..., description="Floor depth (meters)")


class ZoneDefinition(BaseModel):
    """HVAC zone definition."""

    zone_id: str = Field(..., description="Zone identifier")
    floor: str = Field(..., description="Floor level")
    zone_type: str = Field(..., description="Zone type (open_office, mechanical, etc.)")
    equipment: Optional[list[str]] = Field(
        None, description="Equipment IDs in this zone"
    )


class BuildingConfigResponse(BaseModel):
    """Extracted building configuration for SIMBIOT wizard."""

    building_code: str = Field(..., description="Building code")
    building_name: str = Field(..., description="Building name")
    floors: list[FloorDefinition] = Field(..., description="Floor definitions")
    equipment: list[EquipmentLocation] = Field(..., description="Equipment locations")
    zones: list[ZoneDefinition] = Field(..., description="Zone definitions")
    extraction_metadata: Dict = Field(
        ..., description="Extraction method, accuracy, counts"
    )


# ============= Router =============

router = APIRouter(prefix="/digital-twin", tags=["digital-twin"])


@router.post(
    "/extract-from-image",
    response_model=BuildingConfigResponse,
    status_code=status.HTTP_200_OK,
    summary="Extract building config from floor plan image",
    responses={
        400: {"description": "Invalid image or parameters"},
        422: {"description": "Validation error"},
        500: {"description": "Extraction failed"},
    },
)
async def extract_from_image(
    request: ImageExtractionRequest,
) -> BuildingConfigResponse:
    """
    Extract building configuration from floor plan image using Claude vision.

    **Security:** By default (skip_sanitization=False), the floor plan image
    is sanitized locally to remove identifying information (room names, labels,
    sensitive metadata) before sending to Claude API. This keeps security-sensitive
    data on-device while allowing AI-powered equipment extraction.

    **Sanitization Process:**
    1. Threshold image to extract walls and equipment symbols
    2. Remove all text labels locally using OCR
    3. Build lookup table mapping positions to original text (stays local)
    4. Send sanitized geometric skeleton to Claude
    5. Re-identify equipment with original zone names after API response

    **Use Cases:**
    - Set skip_sanitization=False (default) for production/sensitive buildings
    - Set skip_sanitization=True only for demo/non-sensitive test buildings

    Args:
        request: Image extraction request with floor plan and building info

    Returns:
        Building configuration with floors, equipment, zones ready for
        SIMBIOT wizard Step 5 (Building Structure)

    Raises:
        400: Invalid image encoding or parameters
        500: Extraction failed
    """
    try:
        # Validate image size
        import base64

        try:
            image_bytes = base64.b64decode(request.image_base64)
        except Exception as e:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"Invalid base64 image encoding: {str(e)}",
            )

        if len(image_bytes) > 20 * 1024 * 1024:  # 20MB limit
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Image too large (max 20MB)",
            )

        # Get service
        service = get_digital_twin_service()

        # Extract config
        logger.info(
            f"Extracting building config: {request.building_code} "
            f"(sanitize={not request.skip_sanitization})"
        )

        config = await service.extract_from_image(
            image_base64=request.image_base64,
            building_code=request.building_code,
            building_name=request.building_name,
            floors_count=request.floors_count,
            skip_sanitization=request.skip_sanitization,
        )

        # Validate response
        if not config or "equipment" not in config:
            logger.warning(f"Empty extraction for {request.building_code}")
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail="No equipment extracted from image",
            )

        # Convert to response model
        return BuildingConfigResponse(
            building_code=config.get("building_code", request.building_code),
            building_name=config.get("building_name", request.building_name),
            floors=[FloorDefinition(**f) for f in config.get("floors", [])],
            equipment=[EquipmentLocation(**e) for e in config.get("equipment", [])],
            zones=[ZoneDefinition(**z) for z in config.get("zones", [])],
            extraction_metadata=config.get(
                "extraction_metadata",
                {
                    "method": "unknown",
                    "equipment_count": len(config.get("equipment", [])),
                },
            ),
        )

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Extract from image failed: {e}", exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Extraction failed: {str(e)}",
        )


@router.get(
    "/demo-config",
    response_model=BuildingConfigResponse,
    summary="Get demo building configuration",
)
async def get_demo_config(
    building_code: str = "site-002",
    building_name: str = "Demo Building",
    floors_count: int = 5,
) -> BuildingConfigResponse:
    """
    Get realistic demo building configuration for testing SIMBIOT wizard.

    Generates a realistic South African commercial office building with:
    - Basement + ground floor (plant rooms with chillers, AHUs, generators)
    - Multiple office floors with FCUs and VAVs
    - Realistic HVAC zones and equipment placement
    - Metrics suitable for testing the full onboarding workflow

    Args:
        building_code: Building identifier (default: site-002)
        building_name: Building display name (default: Demo Building)
        floors_count: Number of floors (1-5, default: 5)

    Returns:
        Demo building configuration
    """
    try:
        service = get_digital_twin_service()
        config = service._generate_demo_config(building_code, building_name, floors_count)

        return BuildingConfigResponse(
            building_code=config["building_code"],
            building_name=config["building_name"],
            floors=[FloorDefinition(**f) for f in config["floors"]],
            equipment=[EquipmentLocation(**e) for e in config["equipment"]],
            zones=[ZoneDefinition(**z) for z in config["zones"]],
            extraction_metadata=config["extraction_metadata"],
        )
    except Exception as e:
        logger.error(f"Demo config generation failed: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Demo config failed: {str(e)}",
        )


@router.post(
    "/extract-from-dxf",
    response_model=BuildingConfigResponse,
    status_code=status.HTTP_200_OK,
    summary="Extract building config from DXF file",
    responses={
        400: {"description": "Invalid DXF or parameters"},
        501: {"description": "DXF parsing not yet implemented (Phase B)"},
    },
)
async def extract_from_dxf(
    file: UploadFile = File(...),
    building_code: str = ...,
) -> BuildingConfigResponse:
    """
    Extract building configuration from DXF (AutoCAD) file.

    **Status:** Phase B implementation (not yet available)

    DXF parser will extract equipment from architectural drawings based on:
    - Layer names (AR-WALL, AE-HVAC, EL-POWER, FP-LIFE, etc.)
    - Block names and symbols
    - Text annotations for equipment IDs
    - Coordinate positions

    This endpoint will be available after Phase B: DXF Parser implementation.

    Args:
        file: DXF file upload
        building_code: Building identifier (query parameter)

    Returns:
        Building configuration extracted from DXF
    """
    raise HTTPException(
        status_code=status.HTTP_501_NOT_IMPLEMENTED,
        detail="DXF parsing coming in Phase B. Use /extract-from-image for now.",
    )
