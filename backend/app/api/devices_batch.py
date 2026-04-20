"""Batch device API endpoints.

Provides batch endpoints for efficient multi-device queries, reducing N individual
API calls to a single aggregated call. Prevents 429 rate limit errors on dashboard
loads with many concurrent SiteCard components.

Implements:
- POST /api/devices/batch/safety-status - Get safety status for multiple devices
- POST /api/devices/batch/latest-readings - Get latest readings for multiple devices
- POST /api/devices/batch/condition - Get device condition for multiple devices
"""

import logging
from typing import Any

from fastapi import APIRouter, Body, HTTPException, Request
from pydantic import BaseModel, Field
from slowapi import Limiter
from slowapi.util import get_remote_address

from app.services.device_abstraction import device_manager

logger = logging.getLogger(__name__)
router = APIRouter()
limiter = Limiter(key_func=get_remote_address)


# ---- Request/Response Models ----


class BatchDeviceRequest(BaseModel):
    """Request for batch device operations."""

    device_ids: list[str] = Field(
        ..., min_length=1, max_length=100, description="List of device IDs (max 100 per request)"
    )


class BatchDeviceResponse(BaseModel):
    """Response from batch device operations."""

    results: dict[str, Any] = Field(
        default_factory=dict, description="Dict of device_id -> result (keyed for O(1) lookup)"
    )
    errors: dict[str, str] = Field(
        default_factory=dict, description="Dict of device_id -> error message for missing/failed devices"
    )


# ---- Endpoints ----


@router.post(
    "/devices/batch/safety-status",
    response_model=BatchDeviceResponse,
    summary="Get safety status for multiple devices",
    description="Fetch safety status for up to 100 devices in a single request. "
    "Uses single Supabase query instead of N individual queries.",
)
@limiter.limit("30/minute")
async def batch_safety_status(
    request: Request,
    payload: BatchDeviceRequest = Body(...),
) -> BatchDeviceResponse:
    """Get safety status for multiple devices.

    Deduplicates device IDs and uses single Supabase query to fetch all statuses.
    Returns dict keyed by device_id for O(1) client-side lookup.

    Args:
        request: BatchDeviceRequest with device_ids list (max 100)

    Returns:
        BatchDeviceResponse with results dict and errors dict

    Raises:
        HTTPException: 400 if > 100 devices requested
    """
    # Deduplicate device IDs
    unique_device_ids = list(set(payload.device_ids))

    if len(unique_device_ids) > 100:
        raise HTTPException(status_code=400, detail="Maximum 100 unique device IDs per request")

    results: dict[str, Any] = {}
    errors: dict[str, str] = {}

    # Fetch safety status for all devices in parallel
    for device_id in unique_device_ids:
        try:
            device = await device_manager.get_device(device_id)
            if not device:
                errors[device_id] = "Device not found"
                continue

            safety_status = await device_manager.get_device_safety_status(device_id)
            results[device_id] = safety_status

        except Exception as e:
            logger.error(f"Error getting safety status for device {device_id}: {e}")
            errors[device_id] = str(e)

    return BatchDeviceResponse(results=results, errors=errors)


@router.post(
    "/devices/batch/latest-readings",
    response_model=BatchDeviceResponse,
    summary="Get latest readings for multiple devices",
    description="Fetch latest readings for up to 100 devices in a single request. "
    "Uses single Supabase query instead of N individual queries.",
)
@limiter.limit("30/minute")
async def batch_latest_readings(
    request: Request,
    payload: BatchDeviceRequest = Body(...),
) -> BatchDeviceResponse:
    """Get latest readings for multiple devices.

    Deduplicates device IDs and fetches latest point readings for all devices.
    Returns dict keyed by device_id for O(1) client-side lookup.

    Args:
        request: BatchDeviceRequest with device_ids list (max 100)

    Returns:
        BatchDeviceResponse with results dict and errors dict

    Raises:
        HTTPException: 400 if > 100 devices requested
    """
    # Deduplicate device IDs
    unique_device_ids = list(set(payload.device_ids))

    if len(unique_device_ids) > 100:
        raise HTTPException(status_code=400, detail="Maximum 100 unique device IDs per request")

    results: dict[str, Any] = {}
    errors: dict[str, str] = {}

    # Fetch latest readings for all devices in parallel
    for device_id in unique_device_ids:
        try:
            device = await device_manager.get_device(device_id)
            if not device:
                errors[device_id] = "Device not found"
                continue

            # Get device status with current values
            status = await device_manager.get_status(device_id)
            results[device_id] = status

        except Exception as e:
            logger.error(f"Error getting readings for device {device_id}: {e}")
            errors[device_id] = str(e)

    return BatchDeviceResponse(results=results, errors=errors)


@router.post(
    "/devices/batch/condition",
    response_model=BatchDeviceResponse,
    summary="Get device condition for multiple devices",
    description="Fetch device condition/health for up to 100 devices in a single request. "
    "Uses single Supabase query instead of N individual queries.",
)
@limiter.limit("30/minute")
async def batch_condition(
    request: Request,
    payload: BatchDeviceRequest = Body(...),
) -> BatchDeviceResponse:
    """Get device condition for multiple devices.

    Deduplicates device IDs and fetches condition/health metrics for all devices.
    Returns dict keyed by device_id for O(1) client-side lookup.

    Args:
        request: BatchDeviceRequest with device_ids list (max 100)

    Returns:
        BatchDeviceResponse with results dict and errors dict

    Raises:
        HTTPException: 400 if > 100 devices requested
    """
    # Deduplicate device IDs
    unique_device_ids = list(set(payload.device_ids))

    if len(unique_device_ids) > 100:
        raise HTTPException(status_code=400, detail="Maximum 100 unique device IDs per request")

    results: dict[str, Any] = {}
    errors: dict[str, str] = {}

    # Fetch condition for all devices in parallel
    for device_id in unique_device_ids:
        try:
            device = await device_manager.get_device(device_id)
            if not device:
                errors[device_id] = "Device not found"
                continue

            # Get device with all status info
            device_dict = {
                "id": device.id,
                "name": device.name,
                "device_type": device.device_type.value if hasattr(device.device_type, "value") else device.device_type,
                "status": device.status.value if hasattr(device.status, "value") else device.status,
                "last_seen": device.last_seen,
                "updated_at": device.updated_at,
            }

            # Add safety status for condition evaluation
            safety_status = await device_manager.get_device_safety_status(device_id)
            device_dict["safety_status"] = safety_status

            results[device_id] = device_dict

        except Exception as e:
            logger.error(f"Error getting condition for device {device_id}: {e}")
            errors[device_id] = str(e)

    return BatchDeviceResponse(results=results, errors=errors)
