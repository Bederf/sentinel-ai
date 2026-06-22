"""
Concept Evolution CAFM Integration API

Exposes Concept job card and asset data for health/condition assessment,
and provides the controlled document upload endpoint (F1-F8 enforced).
"""

from __future__ import annotations

import json
from datetime import date
from typing import Literal

from fastapi import APIRouter, Depends, File, Form, HTTPException, Query, UploadFile
from pydantic import BaseModel, Field, model_validator

from app.middleware.auth_middleware import require_auth
from app.models.auth import AuthContext, AuthLevel
from app.services.concept_loader import concept_loader
from app.services.simbiot_service import simbiot_service

router = APIRouter(prefix="/api/concept", tags=["concept-cafm"])

# ---------------------------------------------------------------------------
# F1-F8 Controlled field values
# Source: Concept MRI Controlled Fields Register v1.0 — March 2026
# ---------------------------------------------------------------------------

DISCIPLINE_VALUES = Literal[
    "Electrical",
    "Mechanical / HVAC",
    "Plumbing",
    "Fire Equipment",
    "Fire Detection",
    "Lifts & Escalators",
    "Structural",
    "Civil",
    "Environmental",
    "Health & Safety",
    "Contracts & Legal",
    "Project Management",
    "General / Administration",
]

DOCUMENT_TYPE_VALUES = Literal[
    "Checklist",
    "Service Report",
    "Test Result",
    "Certificate",
    "Warranty / Guarantee",
    "Compliance Report",
    "Register",
    "Drawing / Plan",
    "Contract / Agreement",
    "Permit / Licence",
    "Incident Report",
    "Meeting Minutes",
    "Photograph / Evidence",
    "Other",
]

FREQUENCY_VALUES = Literal[
    "Daily",
    "Weekly",
    "Monthly",
    "Biannual (6-monthly)",
    "Annual",
    "2-Yearly",
    "3-Yearly",
    "Once-off / Ad hoc",
    "Project-based",
]

TRIGGER_TYPE_VALUES = Literal[
    "Same as Document Creation Date",
    "Certificate / Permit Expiry Date",
    "Equipment Decommission Date",
    "Building Demolition / Disposal Date",
    "Lease Termination Date",
    "Installation Decommission Date",
    "Vessel Decommission Date",
    "Tank Decommission Date",
    "Date Survey Issued",
    "Date of Incident",
]

# Trigger types that require a trigger_date — Vital records only
VITAL_TRIGGER_TYPES: set[str] = {
    "Certificate / Permit Expiry Date",
    "Equipment Decommission Date",
    "Building Demolition / Disposal Date",
    "Lease Termination Date",
    "Installation Decommission Date",
    "Vessel Decommission Date",
    "Tank Decommission Date",
    "Date Survey Issued",
    "Date of Incident",
}


class ConceptDocumentUploadMetadata(BaseModel):
    """
    F1-F8 controlled upload fields — Concept MRI Controlled Fields Register v1.0.

    All mandatory fields must be provided. The chat UI collects these
    conversationally via dropdowns before submitting the upload.

    F7 (uploaded_by) is auto-populated from the authenticated user session.
    F8 (retention_period) is auto-calculated server-side — not submitted by the user.
    """

    # F1 — Site ID (SENTINEL canonical identifier, not the Concept building name)
    site_id: str = Field(..., description="SENTINEL site_id e.g. site-002")

    # F2 — Discipline
    discipline: DISCIPLINE_VALUES = Field(..., description="Technical discipline — F2 controlled dropdown")

    # F3 — Document Type
    document_type: DOCUMENT_TYPE_VALUES = Field(..., description="Document classification — F3 controlled dropdown")

    # F4 — Frequency
    frequency: FREQUENCY_VALUES = Field(..., description="Inspection / service frequency — F4 controlled dropdown")

    # F5 — Document Creation Date (actual activity date, NOT upload timestamp)
    document_creation_date: date = Field(
        ...,
        description=("Date the activity occurred — F5. This is the retention clock start. Must not default to today."),
    )

    # F6 — Trigger Type + Trigger Date (Vital records only)
    trigger_type: TRIGGER_TYPE_VALUES = Field(
        default="Same as Document Creation Date",
        description="Retention trigger type — F6",
    )
    trigger_date: date | None = Field(
        default=None,
        description=(
            "Required when trigger_type is a lifecycle-event (Vital records). "
            "Leave null when trigger_type is 'Same as Document Creation Date'."
        ),
    )

    @model_validator(mode="after")
    def validate_trigger_date(self) -> ConceptDocumentUploadMetadata:
        """Trigger date is required for Vital records."""
        if self.trigger_type in VITAL_TRIGGER_TYPES and self.trigger_date is None:
            raise ValueError(
                f"trigger_date is required when trigger_type is '{self.trigger_type}'. "
                "This is a Vital record — the retention clock starts on a future lifecycle event."
            )
        return self


# ---------------------------------------------------------------------------
# Dropdown fields endpoint — chat UI fetches this to build the form
# ---------------------------------------------------------------------------


@router.get("/documents/fields")
async def get_document_upload_fields():
    """
    Return approved dropdown values for the document upload form (F1-F8).

    The chat UI calls this to build the conversational upload flow.
    Values are sourced from the Concept MRI Controlled Fields Register v1.0.
    """
    return {
        "discipline": [
            "Electrical",
            "Mechanical / HVAC",
            "Plumbing",
            "Fire Equipment",
            "Fire Detection",
            "Lifts & Escalators",
            "Structural",
            "Civil",
            "Environmental",
            "Health & Safety",
            "Contracts & Legal",
            "Project Management",
            "General / Administration",
        ],
        "document_type": [
            "Checklist",
            "Service Report",
            "Test Result",
            "Certificate",
            "Warranty / Guarantee",
            "Compliance Report",
            "Register",
            "Drawing / Plan",
            "Contract / Agreement",
            "Permit / Licence",
            "Incident Report",
            "Meeting Minutes",
            "Photograph / Evidence",
            "Other",
        ],
        "frequency": [
            "Daily",
            "Weekly",
            "Monthly",
            "Biannual (6-monthly)",
            "Annual",
            "2-Yearly",
            "3-Yearly",
            "Once-off / Ad hoc",
            "Project-based",
        ],
        "trigger_type": [
            "Same as Document Creation Date",
            "Certificate / Permit Expiry Date",
            "Equipment Decommission Date",
            "Building Demolition / Disposal Date",
            "Lease Termination Date",
            "Installation Decommission Date",
            "Vessel Decommission Date",
            "Tank Decommission Date",
            "Date Survey Issued",
            "Date of Incident",
        ],
        "vital_trigger_types": sorted(VITAL_TRIGGER_TYPES),
        "notes": {
            "document_creation_date": (
                "The actual date the activity occurred — inspection date, "
                "service completion date, test date. NOT the upload date."
            ),
            "trigger_date": (
                "Only required for Vital records (lifecycle-event trigger types). "
                "Leave blank for standard operational records."
            ),
            "uploaded_by": "Auto-populated from your logged-in account. No manual entry.",
            "retention_period": "Auto-calculated from discipline + document_type + frequency.",
        },
    }


# ---------------------------------------------------------------------------
# Document upload — F1-F8 enforced
# ---------------------------------------------------------------------------


@router.post("/documents/upload")
async def upload_concept_document(
    file: UploadFile = File(...),
    metadata_json: str = Form(..., description="ConceptDocumentUploadMetadata as JSON string"),
    auth: AuthContext = Depends(require_auth(AuthLevel.AUTHENTICATED)),
):
    """
    Upload a document with mandatory F1-F8 controlled fields.

    The chat UI collects all fields conversationally before calling this endpoint.
    metadata_json must be a valid ConceptDocumentUploadMetadata JSON object.

    F7 (uploaded_by) is injected server-side from the authenticated session.
    F8 (retention_period) is calculated server-side — not accepted from the client.
    """
    # Parse and validate against controlled schema
    try:
        raw = json.loads(metadata_json)
        metadata = ConceptDocumentUploadMetadata.model_validate(raw)
    except Exception as exc:
        raise HTTPException(
            status_code=422,
            detail=f"Document metadata failed validation: {exc}",
        ) from exc

    # Build full payload — F7 injected here, F8 calculated here
    payload = {
        "site_id": metadata.site_id,
        "discipline": metadata.discipline,
        "document_type": metadata.document_type,
        "frequency": metadata.frequency,
        "document_creation_date": metadata.document_creation_date.isoformat(),
        "trigger_type": metadata.trigger_type,
        "trigger_date": metadata.trigger_date.isoformat() if metadata.trigger_date else None,
        # F7 — auto from session, no manual entry
        "uploaded_by_user_id": auth.user_id,
        # F8 — server-side calculation placeholder
        # TODO: wire to retention rule engine once confirmed feasible with Concept vendor
        "retention_period": _calculate_retention(
            discipline=metadata.discipline,
            document_type=metadata.document_type,
            frequency=metadata.frequency,
        ),
    }

    file_bytes = await file.read()
    try:
        result = await simbiot_service.upload_document(
            file_bytes=file_bytes,
            filename=file.filename or "upload.bin",
            site_id=metadata.site_id,
            metadata=payload,
        )
        return {"status": "ok", "site_id": metadata.site_id, "result": result}
    except Exception as exc:
        raise HTTPException(status_code=502, detail=f"Concept upload failed: {exc}") from exc


def _calculate_retention(discipline: str, document_type: str, frequency: str) -> str:
    """
    Derive retention period from discipline + document_type + frequency.
    Source: Concept MRI Controlled Fields Register — Retention Rules sheet.

    Returns a human-readable string. Full rule engine pending vendor confirmation
    of auto-calculation feasibility in Concept (action A4).
    """
    if document_type == "Compliance Report" and discipline == "Health & Safety":
        return "40 years from date survey issued"

    if document_type in {"Certificate", "Warranty / Guarantee", "Permit / Licence"}:
        return "Lifecycle event + 5 years (Vital record)"

    if document_type in {"Drawing / Plan", "Contract / Agreement"}:
        return "Building demolition / lease termination + 10 years (Vital record)"

    if frequency == "Weekly":
        return "3 years"

    if frequency == "2-Yearly":
        return "10 years"

    if document_type == "Incident Report":
        return "5 years from date of incident"

    # Default for most operational records
    return "5 years"


# ---------------------------------------------------------------------------
# Existing endpoints — unchanged
# ---------------------------------------------------------------------------


@router.get("/health")
async def get_integration_health():
    """Check Concept integration health and data availability."""
    return {
        "status": "connected",
        "job_cards_loaded": len(concept_loader.job_cards),
        "assets_loaded": len(concept_loader.assets),
        "data_source": "concept_evolution",
        "last_sync": "2026-01-29T00:00:00Z",
    }


@router.get("/assets")
async def get_assets(
    site_code: str | None = Query(None, description="Filter by building"),
    criticality: str | None = Query(None, description="Filter by criticality"),
    condition: str | None = Query(None, description="Filter by condition"),
):
    """Get all assets from Concept with optional filters."""
    assets = concept_loader.assets

    if site_code:
        assets = [a for a in assets if a.site_code == site_code]
    if criticality:
        assets = [a for a in assets if a.criticality.lower() == criticality.lower()]
    if condition:
        assets = [a for a in assets if a.condition.lower() == condition.lower()]

    return {
        "total": len(assets),
        "assets": [
            {
                "asset_code": a.asset_code,
                "asset_desc": a.asset_desc,
                "asset_category": a.asset_category,
                "asset_type": a.asset_type,
                "manufacturer": a.manufacturer,
                "model": a.model,
                "site_code": a.site_code,
                "site_name": a.site_name,
                "location": a.location_desc,
                "install_date": a.install_date.isoformat() if a.install_date else None,
                "age_years": a.age_years,
                "expected_life_years": a.expected_life_years,
                "remaining_life": a.remaining_life_years,
                "beyond_life": a.is_beyond_life,
                "criticality": a.criticality,
                "condition": a.condition,
                "condition_score": a.condition_score,
                "risk_rating": a.risk_rating,
                "replacement_cost": a.replacement_cost,
            }
            for a in assets
        ],
    }


@router.get("/assets/{asset_code}")
async def get_asset(asset_code: str):
    """Get single asset details."""
    asset = concept_loader.get_asset(asset_code)
    if not asset:
        raise HTTPException(status_code=404, detail="Asset not found")

    return {
        "asset_code": asset.asset_code,
        "asset_desc": asset.asset_desc,
        "asset_category": asset.asset_category,
        "asset_type": asset.asset_type,
        "manufacturer": asset.manufacturer,
        "model": asset.model,
        "serial_no": asset.serial_no,
        "site_code": asset.site_code,
        "site_name": asset.site_name,
        "location_code": asset.location_code,
        "location_desc": asset.location_desc,
        "install_date": asset.install_date.isoformat() if asset.install_date else None,
        "warranty_expiry": asset.warranty_expiry.isoformat() if asset.warranty_expiry else None,
        "age_years": asset.age_years,
        "expected_life_years": asset.expected_life_years,
        "remaining_life": asset.remaining_life_years,
        "beyond_life": asset.is_beyond_life,
        "criticality": asset.criticality,
        "condition": asset.condition,
        "condition_score": asset.condition_score,
        "last_service_date": asset.last_service_date.isoformat() if asset.last_service_date else None,
        "next_service_date": asset.next_service_date.isoformat() if asset.next_service_date else None,
        "ppm_frequency": asset.ppm_frequency,
        "replacement_cost": asset.replacement_cost,
        "annual_maint_cost": asset.annual_maint_cost,
        "risk_rating": asset.risk_rating,
        "compliance_req": asset.compliance_req,
        "notes": asset.notes,
    }


@router.get("/assets/{asset_code}/health")
async def get_asset_health(asset_code: str):
    """Get comprehensive health assessment for an asset."""
    health = concept_loader.calculate_health_score(asset_code)
    if "error" in health:
        raise HTTPException(status_code=404, detail=health["error"])
    return health


@router.get("/assets/{asset_code}/job-cards")
async def get_asset_job_cards(
    asset_code: str,
    limit: int = Query(20, description="Maximum results"),
):
    """Get job card history for an asset."""
    job_cards = concept_loader.get_job_cards_for_asset(asset_code)
    job_cards.sort(key=lambda x: x.logged_date or "", reverse=True)

    return {
        "asset_code": asset_code,
        "total_job_cards": len(job_cards),
        "job_cards": [
            {
                "job_card_no": jc.job_card_no,
                "priority": jc.priority,
                "priority_level": jc.priority_level,
                "status": jc.status,
                "logged_date": jc.logged_date.isoformat() if jc.logged_date else None,
                "completed_date": jc.completed_date.isoformat() if jc.completed_date else None,
                "sla_met": jc.sla_met,
                "fault_code": jc.fault_code,
                "fault_desc": jc.fault_desc,
                "problem_desc": jc.problem_desc,
                "cause_code": jc.cause_code,
                "cause_desc": jc.cause_desc,
                "action_taken": jc.action_taken,
                "technician_name": jc.technician_name,
                "total_cost": jc.total_cost,
                "repeat_call": jc.repeat_call,
                "related_job_card": jc.related_job_card,
                "tech_notes": jc.tech_notes,
                "has_warning": jc.has_warning_flags,
            }
            for jc in job_cards[:limit]
        ],
    }


@router.get("/job-cards")
async def get_job_cards(
    site_code: str | None = Query(None, description="Filter by building"),
    asset_code: str | None = Query(None, description="Filter by asset"),
    priority: str | None = Query(None, description="Filter by priority (P1-P4)"),
    status: str | None = Query(None, description="Filter by status"),
    repeat_only: bool = Query(False, description="Show only repeat calls"),
    warnings_only: bool = Query(False, description="Show only jobs with warnings"),
    limit: int = Query(50, description="Maximum results"),
):
    """Get job cards with optional filters."""
    job_cards = concept_loader.job_cards

    if site_code:
        job_cards = [jc for jc in job_cards if jc.site_code == site_code]
    if asset_code:
        job_cards = [jc for jc in job_cards if jc.asset_code == asset_code]
    if priority:
        job_cards = [jc for jc in job_cards if jc.priority == priority]
    if status:
        job_cards = [jc for jc in job_cards if jc.status.lower() == status.lower()]
    if repeat_only:
        job_cards = [jc for jc in job_cards if jc.repeat_call]
    if warnings_only:
        job_cards = [jc for jc in job_cards if jc.has_warning_flags]

    job_cards.sort(key=lambda x: x.logged_date or "", reverse=True)

    return {
        "total": len(job_cards),
        "job_cards": [
            {
                "job_card_no": jc.job_card_no,
                "priority": jc.priority,
                "status": jc.status,
                "logged_date": jc.logged_date.isoformat() if jc.logged_date else None,
                "site_name": jc.site_name,
                "asset_code": jc.asset_code,
                "asset_desc": jc.asset_desc,
                "fault_desc": jc.fault_desc,
                "technician_name": jc.technician_name,
                "total_cost": jc.total_cost,
                "repeat_call": jc.repeat_call,
                "has_warning": jc.has_warning_flags,
            }
            for jc in job_cards[:limit]
        ],
    }


@router.get("/at-risk")
async def get_assets_at_risk():
    """Get all assets with health score below 60."""
    at_risk = concept_loader.get_assets_at_risk()
    return {"total_at_risk": len(at_risk), "assets": at_risk}


@router.get("/buildings/{site_code}/summary")
async def get_site_summary(site_code: str):
    """Get health summary for all assets in a building."""
    summary = concept_loader.get_site_summary(site_code)
    if "error" in summary:
        raise HTTPException(status_code=404, detail=summary["error"])
    return summary


@router.get("/stats")
async def get_concept_stats():
    """Get overall statistics from Concept data."""
    job_cards = concept_loader.job_cards
    assets = concept_loader.assets

    total_cost = sum(jc.total_cost for jc in job_cards)
    repeat_calls = len([jc for jc in job_cards if jc.repeat_call])
    sla_failures = len([jc for jc in job_cards if not jc.sla_met])
    critical_assets = len([a for a in assets if a.criticality == "Critical"])
    poor_condition = len([a for a in assets if a.condition_score < 50])
    beyond_life = len([a for a in assets if a.is_beyond_life])

    cost_by_category: dict[str, float] = {}
    for jc in job_cards:
        cat = jc.asset_category
        cost_by_category[cat] = cost_by_category.get(cat, 0) + jc.total_cost

    priority_dist: dict[str, int] = {}
    for jc in job_cards:
        priority_dist[jc.priority] = priority_dist.get(jc.priority, 0) + 1

    return {
        "job_cards": {
            "total": len(job_cards),
            "total_cost": total_cost,
            "repeat_calls": repeat_calls,
            "repeat_rate": f"{(repeat_calls / len(job_cards) * 100):.1f}%" if job_cards else "0%",
            "sla_failures": sla_failures,
            "sla_compliance": f"{((len(job_cards) - sla_failures) / len(job_cards) * 100):.1f}%" if job_cards else "0%",
            "by_priority": priority_dist,
            "cost_by_category": cost_by_category,
        },
        "assets": {
            "total": len(assets),
            "critical": critical_assets,
            "poor_condition": poor_condition,
            "beyond_expected_life": beyond_life,
            "total_replacement_value": sum(a.replacement_cost for a in assets),
            "annual_maint_budget": sum(a.annual_maint_cost for a in assets),
        },
    }
