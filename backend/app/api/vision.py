"""
Vision API Endpoints

Provides REST API for AI-powered image analysis:
- POST /api/vision/analyze - General image analysis
- POST /api/vision/component - Component identification
- POST /api/vision/model-plate - Model plate OCR
- POST /api/vision/diagnose - Visual damage assessment
- POST /api/vision/error-display - Extract fault codes from screens
"""

import logging
from typing import Optional
from pydantic import BaseModel, Field

from fastapi import APIRouter, HTTPException, UploadFile, File, Form

from app.services.vision_service import get_vision_service

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/vision", tags=["vision"])

# Max image size: 5MB
MAX_IMAGE_SIZE = 5 * 1024 * 1024

ALLOWED_MEDIA_TYPES = {"image/jpeg", "image/jpg", "image/png", "image/gif", "image/webp"}


class AnalyzeRequest(BaseModel):
    """Request for image analysis with base64 image."""

    image: str = Field(..., description="Base64-encoded image data")
    media_type: str = Field(default="image/jpeg", description="Image MIME type")
    prompt: Optional[str] = Field(None, description="Custom analysis prompt")


class ComponentRequest(BaseModel):
    """Request for component identification."""

    image: str = Field(..., description="Base64-encoded image data")
    media_type: str = Field(default="image/jpeg", description="Image MIME type")
    context: Optional[str] = Field(None, description="Equipment context")


class DiagnoseRequest(BaseModel):
    """Request for damage diagnosis."""

    image: str = Field(..., description="Base64-encoded image data")
    media_type: str = Field(default="image/jpeg", description="Image MIME type")
    equipment_context: Optional[str] = Field(None, description="Equipment context")


class ErrorDisplayRequest(BaseModel):
    """Request for error display reading."""

    image: str = Field(..., description="Base64-encoded image data")
    media_type: str = Field(default="image/jpeg", description="Image MIME type")
    manufacturer: Optional[str] = Field(None, description="Equipment manufacturer")


def _validate_media_type(media_type: str) -> str:
    """Validate and normalize media type."""
    normalized = media_type.lower()
    if normalized == "image/jpg":
        normalized = "image/jpeg"
    if normalized not in ALLOWED_MEDIA_TYPES:
        raise HTTPException(
            status_code=400, detail=f"Unsupported media type: {media_type}. Allowed: {ALLOWED_MEDIA_TYPES}"
        )
    return normalized


def _decode_base64_image(image_b64: str) -> bytes:
    """Decode base64 image data."""
    import base64

    try:
        # Handle data URL format
        if "," in image_b64:
            image_b64 = image_b64.split(",")[1]
        return base64.b64decode(image_b64)
    except Exception as e:
        raise HTTPException(status_code=400, detail=f"Invalid base64 image: {e}")


@router.post("/analyze", response_model=dict)
async def analyze_image(request: AnalyzeRequest):
    """
    General image analysis.

    Takes an image and optional prompt, returns AI analysis.
    Useful for open-ended questions about equipment images.

    Example:
        POST /api/vision/analyze
        {
            "image": "base64-encoded-image",
            "prompt": "What type of compressor is this?"
        }
    """
    vision = get_vision_service()

    media_type = _validate_media_type(request.media_type)
    image_data = _decode_base64_image(request.image)

    if len(image_data) > MAX_IMAGE_SIZE:
        raise HTTPException(status_code=400, detail="Image exceeds 5MB limit")

    try:
        result = vision.analyze_image(image_data, media_type, request.prompt)
        return result
    except Exception as e:
        logger.error(f"Vision analysis error: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/component", response_model=dict)
async def identify_component(request: ComponentRequest):
    """
    Identify equipment component from image.

    Returns structured identification with component name,
    manufacturer, model, and condition assessment.

    Example:
        POST /api/vision/component
        {
            "image": "base64-encoded-image",
            "context": "chiller plant room"
        }
    """
    vision = get_vision_service()

    media_type = _validate_media_type(request.media_type)
    image_data = _decode_base64_image(request.image)

    if len(image_data) > MAX_IMAGE_SIZE:
        raise HTTPException(status_code=400, detail="Image exceeds 5MB limit")

    try:
        result = vision.identify_component(image_data, media_type, request.context)
        return result
    except Exception as e:
        logger.error(f"Component identification error: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/model-plate", response_model=dict)
async def read_model_plate(request: AnalyzeRequest):
    """
    Extract information from equipment model plate.

    Uses OCR to extract manufacturer, model, serial number,
    and other specifications from equipment nameplates.

    Example:
        POST /api/vision/model-plate
        {"image": "base64-encoded-image"}
    """
    vision = get_vision_service()

    media_type = _validate_media_type(request.media_type)
    image_data = _decode_base64_image(request.image)

    if len(image_data) > MAX_IMAGE_SIZE:
        raise HTTPException(status_code=400, detail="Image exceeds 5MB limit")

    try:
        result = vision.read_model_plate(image_data, media_type)
        return result
    except Exception as e:
        logger.error(f"Model plate OCR error: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/diagnose", response_model=dict)
async def diagnose_damage(request: DiagnoseRequest):
    """
    Assess visible damage or wear in equipment image.

    Returns detected issues with severity ratings and
    maintenance recommendations.

    Example:
        POST /api/vision/diagnose
        {
            "image": "base64-encoded-image",
            "equipment_context": "scroll compressor, 5 years old"
        }
    """
    vision = get_vision_service()

    media_type = _validate_media_type(request.media_type)
    image_data = _decode_base64_image(request.image)

    if len(image_data) > MAX_IMAGE_SIZE:
        raise HTTPException(status_code=400, detail="Image exceeds 5MB limit")

    try:
        result = vision.diagnose_damage(image_data, media_type, request.equipment_context)
        return result
    except Exception as e:
        logger.error(f"Damage diagnosis error: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/error-display", response_model=dict)
async def read_error_display(request: ErrorDisplayRequest):
    """
    Extract fault codes from equipment error display.

    Reads control panel displays to extract fault codes,
    error messages, and status indicators.

    Example:
        POST /api/vision/error-display
        {
            "image": "base64-encoded-image",
            "manufacturer": "Carrier"
        }
    """
    vision = get_vision_service()

    media_type = _validate_media_type(request.media_type)
    image_data = _decode_base64_image(request.image)

    if len(image_data) > MAX_IMAGE_SIZE:
        raise HTTPException(status_code=400, detail="Image exceeds 5MB limit")

    try:
        result = vision.read_error_display(image_data, media_type, request.manufacturer)
        return result
    except Exception as e:
        logger.error(f"Error display reading error: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/upload", response_model=dict)
async def upload_and_analyze(
    file: UploadFile = File(...),
    analysis_type: str = Form(default="analyze"),
    context: Optional[str] = Form(default=None),
):
    """
    Upload image file and analyze.

    Convenience endpoint for direct file upload (multipart/form-data).
    Useful for mobile camera capture.

    Args:
        file: Image file upload
        analysis_type: Type of analysis (analyze, component, model-plate, diagnose)
        context: Optional context string

    Example:
        POST /api/vision/upload
        Content-Type: multipart/form-data
        file: <image file>
        analysis_type: component
        context: AHU motor
    """
    vision = get_vision_service()

    # Validate content type
    if file.content_type not in ALLOWED_MEDIA_TYPES:
        raise HTTPException(status_code=400, detail=f"Unsupported file type: {file.content_type}")

    # Read file
    image_data = await file.read()
    if len(image_data) > MAX_IMAGE_SIZE:
        raise HTTPException(status_code=400, detail="Image exceeds 5MB limit")

    media_type = file.content_type
    if media_type == "image/jpg":
        media_type = "image/jpeg"

    try:
        if analysis_type == "component":
            result = vision.identify_component(image_data, media_type, context)
        elif analysis_type == "model-plate":
            result = vision.read_model_plate(image_data, media_type)
        elif analysis_type == "diagnose":
            result = vision.diagnose_damage(image_data, media_type, context)
        else:
            result = vision.analyze_image(image_data, media_type, context)

        return result
    except Exception as e:
        logger.error(f"Vision upload error: {e}")
        raise HTTPException(status_code=500, detail=str(e))
