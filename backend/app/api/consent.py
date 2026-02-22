"""Consent Management API.

REST endpoints for POPIA-compliant consent capture and management.
Supports WhatsApp/Telegram/web consent recording, checking, withdrawal,
history, statistics, and audit export.

Phase 63-06: FSR privacy controls — consent API endpoints.

NOTE: This router is NOT registered in main.py yet.
To integrate, add to main.py:
    from app.api import consent
    app.include_router(consent.router, prefix="/api", tags=["consent"])
"""

import logging
from typing import Optional

from fastapi import APIRouter, HTTPException, Query
from pydantic import BaseModel, Field

from app.services.consent_service import (
    get_consent_service,
    hash_identifier,
    CONSENT_TEMPLATES,
)

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/consent", tags=["consent"])


# ---------------------------------------------------------------------------
# Request / Response models
# ---------------------------------------------------------------------------


class RecordConsentRequest(BaseModel):
    """Request to record a new consent decision."""

    data_subject_id: str = Field(..., description="Phone number or user identifier (will be hashed)")
    platform: str = Field(..., description="Platform: whatsapp, telegram, or web")
    consent_type: str = Field(..., description="Consent type: pi_processing, data_retention, or cross_border_transfer")
    consent_given: bool = Field(..., description="True if consent is given, False if declined")
    consent_text: Optional[str] = Field(None, description="Exact consent text shown to user (defaults to template)")
    ip_address: Optional[str] = Field(None, description="IP address of data subject")
    metadata: Optional[dict] = Field(None, description="Platform-specific metadata")


class WithdrawConsentRequest(BaseModel):
    """Request to withdraw consent."""

    data_subject_id: str = Field(..., description="Phone number or user identifier")
    consent_type: str = Field(..., description="Consent type to withdraw")
    metadata: Optional[dict] = Field(None, description="Withdrawal metadata (reason)")


class ConsentCheckResponse(BaseModel):
    """Response for consent check."""

    data_subject_id: str
    consent_type: str
    has_consent: bool


class ConsentStatsResponse(BaseModel):
    """Aggregate consent statistics."""

    total_records: int
    active_consents: int
    withdrawals: int
    by_platform: dict
    by_consent_type: dict
    last_updated: str


# ---------------------------------------------------------------------------
# Endpoints
# ---------------------------------------------------------------------------


@router.post("/record", response_model=dict)
async def record_consent(request: RecordConsentRequest):
    """Record a new consent decision.

    Creates an immutable consent record. The data subject ID is hashed
    with SHA-256 before storage for privacy protection.
    """
    service = get_consent_service()

    # Validate platform
    valid_platforms = {"whatsapp", "telegram", "web"}
    if request.platform not in valid_platforms:
        raise HTTPException(
            status_code=400,
            detail=f"Invalid platform. Must be one of: {', '.join(valid_platforms)}",
        )

    # Validate consent type
    valid_types = {"pi_processing", "data_retention", "cross_border_transfer"}
    if request.consent_type not in valid_types:
        raise HTTPException(
            status_code=400,
            detail=f"Invalid consent type. Must be one of: {', '.join(valid_types)}",
        )

    record = service.record_consent(
        data_subject_id=request.data_subject_id,
        platform=request.platform,
        consent_type=request.consent_type,
        consent_given=request.consent_given,
        consent_text=request.consent_text,
        ip_address=request.ip_address,
        metadata=request.metadata or {},
    )

    return {
        "status": "recorded",
        "record_id": record.record_id,
        "consent_given": record.consent_given,
        "given_at": record.given_at,
    }


@router.get("/check/{subject_id}/{consent_type}", response_model=ConsentCheckResponse)
async def check_consent(subject_id: str, consent_type: str):
    """Check if a data subject has active consent for a given type.

    The subject_id should be the raw (unhashed) identifier.
    """
    service = get_consent_service()

    valid_types = {"pi_processing", "data_retention", "cross_border_transfer"}
    if consent_type not in valid_types:
        raise HTTPException(
            status_code=400,
            detail=f"Invalid consent type. Must be one of: {', '.join(valid_types)}",
        )

    has_consent = service.check_consent(subject_id, consent_type)

    return ConsentCheckResponse(
        data_subject_id=hash_identifier(subject_id),
        consent_type=consent_type,
        has_consent=has_consent,
    )


@router.post("/withdraw", response_model=dict)
async def withdraw_consent(request: WithdrawConsentRequest):
    """Record a consent withdrawal.

    Creates a new withdrawal record (immutable — does not modify existing records).
    The original consent record is also marked with withdrawn_at timestamp.
    """
    service = get_consent_service()

    valid_types = {"pi_processing", "data_retention", "cross_border_transfer"}
    if request.consent_type not in valid_types:
        raise HTTPException(
            status_code=400,
            detail=f"Invalid consent type. Must be one of: {', '.join(valid_types)}",
        )

    record = service.withdraw_consent(
        data_subject_id=request.data_subject_id,
        consent_type=request.consent_type,
        metadata=request.metadata or {},
    )

    return {
        "status": "withdrawn",
        "record_id": record.record_id,
        "consent_type": request.consent_type,
        "withdrawn_at": record.given_at,
    }


@router.get("/history/{subject_id}", response_model=list)
async def get_consent_history(subject_id: str):
    """Get the full consent history for a data subject.

    Returns all consent records (grants and withdrawals) in chronological order.
    """
    service = get_consent_service()
    history = service.get_consent_history(subject_id)

    return [r.model_dump() for r in history]


@router.get("/stats", response_model=ConsentStatsResponse)
async def get_consent_stats():
    """Get aggregate consent statistics for admin/audit use.

    Returns totals, active consents, withdrawals, breakdowns by platform
    and consent type.
    """
    service = get_consent_service()
    stats = service.get_consent_stats()

    return ConsentStatsResponse(**stats)


@router.get("/export", response_model=list)
async def export_consent_records(
    start_date: Optional[str] = Query(None, description="ISO 8601 start date"),
    end_date: Optional[str] = Query(None, description="ISO 8601 end date"),
):
    """Export consent records for FSR audit.

    Optionally filter by date range. Returns all fields for audit compliance.
    """
    service = get_consent_service()
    records = service.export_consent_records(
        start_date=start_date,
        end_date=end_date,
    )

    return records


@router.get("/templates", response_model=dict)
async def get_consent_templates():
    """Get consent text templates for all platforms and types.

    Returns the standard consent messages used for first-contact flows
    on WhatsApp, Telegram, and web.
    """
    return CONSENT_TEMPLATES
